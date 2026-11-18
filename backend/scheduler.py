"""每日自动检测调度(进程内 asyncio 任务,每天 08:00)。

设计要点:
- 每天 08:00(本机时区)检测全部 enabled 账号的状态与积分,结果写回账号表;
- systemd 双实例(v4/v6)都会启动调度器,用 settings 里的日期戳做跨进程抢占,保证一天只真正跑一次;
- daily_auto_check='off' 时跳过当天(仍持续写入 next 时间,便于面板显示);
- 结果落 settings:auto_check_last_at / auto_check_next_at / auto_check_summary;
- 配置了 notify_webhook 时把汇总 POST 过去,留空则只在面板记录(不假装推送)。
"""
import asyncio
import json
import logging
from datetime import date, datetime, timedelta

import httpx

from . import db

logger = logging.getLogger("aam.scheduler")
# uvicorn 只给自己的 logger 配 handler,root 无 handler、本 logger 无 handler,
# 于是 INFO 级日志会被静默丢弃(systemd 捕获的 data/aam-*.log 里看不到自动检测痕迹)。
# 这里挂一个自带 handler 让这个无人值守任务的运行情况可见;propagate=False 防重复输出。
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s aam.scheduler: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

CHECK_HOUR = 8
CHECK_MINUTE = 0
CLAIM_KEY = "auto_check_last_date"
CONCURRENCY = 4

_task = None


def next_run_at(now: datetime | None = None) -> datetime:
    """下一次 08:00(严格大于 now)。"""
    now = now or datetime.now()
    target = now.replace(hour=CHECK_HOUR, minute=CHECK_MINUTE, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return target


def claim_day(today: str | None = None) -> bool:
    """原子抢占今天(双实例并发时只有一个返回 True)。"""
    today = today or date.today().isoformat()
    with db.connect() as conn:
        cur = conn.execute("UPDATE settings SET value=? WHERE key=? AND value<>?", (today, CLAIM_KEY, today))
        claimed = bool(cur.rowcount)
        if not claimed:
            cur = conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (CLAIM_KEY, today))
            claimed = bool(cur.rowcount)
    return claimed


def _summary_text(payload: dict) -> str:
    return (f"AAM 自动检测 {payload['at']}:共 {payload['total']} 个账号,"
            f"有效 {payload['active']} / 过期 {payload['expired']} / "
            f"错误 {payload['error']} / 未知 {payload['unknown']}")


async def _push_summary(webhook: str, payload: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook, json={"type": "aam_auto_check", "text": _summary_text(payload), "summary": payload})
        if resp.status_code >= 400:
            logger.warning("auto check webhook http %s", resp.status_code)
            return False
        return True
    except Exception:
        logger.warning("auto check webhook failed", exc_info=True)
        return False


async def run_auto_check(force: bool = False) -> dict:
    """跑一轮全量账号检测并写汇总返回。force=True 时跳过当日去重(手动触发)。"""
    from .api import check_account  # 延迟导入:api 依赖 db/platforms,避免启动期循环导入

    if not force and not claim_day():
        logger.info("auto check skipped: already ran today")
        return {"skipped": True, "reason": "already-ran-today"}
    with db.connect() as conn:
        account_ids = [row["id"] for row in conn.execute("SELECT id FROM accounts WHERE enabled=1 ORDER BY id")]
    stats = {"total": len(account_ids), "active": 0, "expired": 0, "error": 0, "unknown": 0}
    sem = asyncio.Semaphore(CONCURRENCY)

    async def _one(account_id: int) -> str:
        async with sem:
            try:
                result = await check_account(account_id)
                return (result or {}).get("status") or "unknown"
            except Exception:
                logger.warning("auto check failed account=%s", account_id, exc_info=True)
                return "error"

    for status in await asyncio.gather(*(_one(i) for i in account_ids)):
        stats[status if status in ("active", "expired", "error") else "unknown"] += 1

    payload = {"at": datetime.now().isoformat(timespec="seconds"), **stats}
    webhook = (db.get_setting("notify_webhook", "") or "").strip()
    pushed = await _push_summary(webhook, payload) if webhook else False
    payload["pushed"] = pushed
    db.set_setting("auto_check_last_at", payload["at"])
    db.set_setting("auto_check_summary", json.dumps(stats | {"pushed": pushed}, ensure_ascii=False))
    db.set_setting("auto_check_next_at", next_run_at().isoformat(timespec="seconds"))
    logger.info("auto check done: %s pushed=%s", stats, pushed)
    return payload


async def loop():
    """常驻循环:睡到下一个 08:00 → 按开关决定是否检测。"""
    logger.info("auto check scheduler started (daily %02d:%02d)", CHECK_HOUR, CHECK_MINUTE)
    while True:
        try:
            target = next_run_at()
            db.set_setting("auto_check_next_at", target.isoformat(timespec="seconds"))
            delay = max(1.0, (target - datetime.now()).total_seconds())
            await asyncio.sleep(delay)
            enabled = (db.get_setting("daily_auto_check", "on") or "on").strip() != "off"
            if not enabled:
                logger.info("auto check disabled by setting, skip today")
                continue
            await run_auto_check()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("auto check loop error", exc_info=True)
            await asyncio.sleep(60)


def start():
    """在事件循环内启动调度器任务(重复调用安全)。"""
    global _task
    if _task and not _task.done():
        return _task
    _task = asyncio.create_task(loop())
    return _task


async def stop():
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
    logger.info("auto check scheduler stopped")
