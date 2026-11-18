"""WorkBuddy OAuth 授权并自动导入 AAM 账号。

授权流程转发给 wb2api 网关（/panel/api/login/start + poll）：
- wb2api 负责与腾讯 CodeBuddy 完成 OAuth、凭证落盘 auths/、热加载进账号池
- AAM 侧拿到 done 后建账号，credential 存「wb2api 网关 api_key」（openai_compat 探活 7863 用它）
- 后端直连腾讯的旧实现会拿到 accessToken 却无法通过 7863 探活（7863 只认自己 api_key）→ 账号恒 expired
"""
import json
import re
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from . import db
from .auth import require_admin
from .config import DATA_DIR

router = APIRouter(prefix="/api/login/workbuddy", dependencies=[Depends(require_admin)])
_UUID_RE = re.compile(r"^[A-Za-z0-9-]{8,128}$")
STATE_FILE = DATA_DIR / "workbuddy_oauth_states.json"

_REDACT_KEYS = {
    "credential", "refreshToken", "accessToken", "access_token", "refresh_token",
    "api_key", "apiKey", "id_token", "client_secret", "password", "authorization",
    "session", "cookie", "secret", "token",
}


def _redact(item):
    """递归移除凭据字段并脱敏用户令牌。"""
    if isinstance(item, dict):
        redacted = {}
        for key, value in item.items():
            if key == "credential":
                continue
            if key in _REDACT_KEYS:
                redacted[key] = "***"
            else:
                redacted[key] = _redact(value)
        return redacted
    if isinstance(item, list):
        return [_redact(value) for value in item]
    return item


def _gw_url() -> str:
    """wb2api 网关地址：优先 settings.workbuddy_gw_url；回退 workbuddy 平台 base_url 去掉 /v1。"""
    url = (db.get_setting("workbuddy_gw_url", "") or "").strip()
    if url:
        return url.rstrip("/")
    with db.connect() as conn:
        row = conn.execute("SELECT base_url FROM platforms WHERE key='workbuddy'").fetchone()
    base = (row["base_url"] if row else "") or ""
    base = base.strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base.rstrip("/") if base else "http://127.0.0.1:7863"


def _gw_key() -> str:
    """wb2api 网关 api_key：优先 settings.workbuddy_gw_key；回退任一 workbuddy 账号的 credential。
    credential 为空/无账号时抛错，提示到「设置」页配置。"""
    key = (db.get_setting("workbuddy_gw_key", "") or "").strip()
    if key:
        return key
    with db.connect() as conn:
        row = conn.execute(
            "SELECT a.credential FROM accounts a JOIN platforms p ON p.id=a.platform_id "
            "WHERE p.key='workbuddy' AND a.credential IS NOT NULL AND TRIM(a.credential)<>'' "
            "ORDER BY a.id LIMIT 1").fetchone()
    if row and row["credential"]:
        return row["credential"]
    raise HTTPException(400, "未配置 WorkBuddy 网关 API Key：请到「设置」页填写 workbuddy 网关地址与 API Key")


def _states():
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_states(states):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(states, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


@contextmanager
def _states_lock(timeout: float = 5.0):
    import contextlib
    with contextlib.suppress(ImportError):
        from filelock import FileLock
        lock = FileLock(str(STATE_FILE) + ".lock", timeout=timeout)
        with lock:
            yield
        return
    yield


async def _upstream(method, url, key="", body=None):
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.request(method, url, headers=headers, json=body)
    if response.status_code >= 300:
        raise HTTPException(502, f"WorkBuddy 网关返回 HTTP {response.status_code}: {response.text[:200]}")
    try:
        payload = response.json()
    except ValueError:
        raise HTTPException(502, "WorkBuddy 网关返回无法解析的数据")
    return payload


@router.post("/start")
async def start(realm: str = Query("cn")):
    url = _gw_url()
    key = _gw_key()
    payload = await _upstream("POST", f"{url}/panel/api/login/start", key=key, body={"realm": realm})
    state = str(payload.get("state") or "")
    auth_url = str(payload.get("url") or "")
    if not state or not _UUID_RE.match(state) or not auth_url:
        raise HTTPException(502, "WorkBuddy 网关未返回有效授权状态")
    now = int(time.time())
    with _states_lock():
        states = {k: v for k, v in _states().items() if int(v.get("expires_at", 0)) > now}
        states[state] = {"created_at": now, "expires_at": now + 900, "account_id": None}
        _save_states(states)
    return {"ok": True, "state": state, "url": auth_url, "expires_at": now + 900}


@router.get("/status")
async def status(state: str = Query(..., min_length=8, max_length=128)):
    states = _states()
    session = states.get(state)
    if not session:
        return {"ok": False, "status": "expired", "message": "授权状态不存在或已过期"}
    if int(session.get("expires_at", 0)) <= int(time.time()):
        return {"ok": False, "status": "expired", "message": "授权已过期，请重新开始"}
    if session.get("account_id"):
        account = db.get_account(session["account_id"])
        if account:
            account["quota_json"] = db.parse_json(account.get("quota_json"))
            account["user_info"] = db.parse_json(account.get("user_info"))
        return _redact({"ok": True, "status": "done", "account": account})

    url = _gw_url()
    key = _gw_key()
    payload = await _upstream("GET", f"{url}/panel/api/login/poll?state={state}", key=key)
    done = bool(payload.get("done"))
    if not done:
        return {"ok": True, "status": "pending"}
    # wb2api 已完成 OAuth 并热加载入池；AAM 侧建账号，credential=网关 api_key（探活用）
    uid = str(payload.get("uid") or "")
    nickname = str(payload.get("nickname") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", uid):
        raise HTTPException(502, "WorkBuddy 网关已授权，但未返回有效账号 ID")
    credits = payload.get("credits")
    credits_total = payload.get("credits_total")
    realm2 = payload.get("realm", "")
    user_info = {"uid": uid, "nickname": nickname, "credits": credits,
                 "credits_total": credits_total, "realm": realm2,
                 "source": "wb2api-oauth"}
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM platforms WHERE key='workbuddy'").fetchone()
        if not row:
            raise HTTPException(500, "缺少 key=workbuddy 的平台记录,请先在「平台」页创建(adapter=openai_compat)")
        platform_id = row["id"]
        existing = conn.execute(
            "SELECT id FROM accounts WHERE platform_id=? AND json_extract(user_info, '$.uid')=?",
            (platform_id, uid)).fetchone()
        if existing:
            account_id = existing["id"]
            conn.execute("UPDATE accounts SET name=?,credential=?,credential_type='token',user_info=? WHERE id=?",
                         (f"WorkBuddy-{uid[-4:]}", key, json.dumps(user_info, ensure_ascii=False), account_id))
        else:
            cur = conn.execute(
                "INSERT INTO accounts(platform_id,name,credential,credential_type,user_info) VALUES(?,?,?,?,?)",
                (platform_id, f"WorkBuddy-{uid[-4:]}", key, "token",
                 json.dumps(user_info, ensure_ascii=False)))
            account_id = cur.lastrowid
    with _states_lock():
        if state in _states():
            st = _states()
            st[state]["account_id"] = account_id
            _save_states(st)
    from .api import check_account
    account = await check_account(account_id)
    return _redact({"ok": True, "status": "done", "account": account})

# ---------------- WorkBuddy 每日任务（转发 wb2api 面板任务 API） ----------------

def _task_done(item) -> bool:
    """判断单个成长任务是否已完成。"""
    status = str(item.get("accept_status") or "").lower()
    if status in ("completed", "accepted", "done", "received", "claimed"):
        return True
    try:
        cur, tgt = item.get("current"), item.get("target")
        if tgt not in (None, 0) and cur is not None and int(cur) >= int(tgt):
            return True
    except (TypeError, ValueError):
        pass
    return bool(item.get("completed") or item.get("finished"))


@router.get("/tasks")
async def workbuddy_tasks():
    """WorkBuddy 每日任务与账号池状态（wb2api 侧自动签到/成长/旅行/保活）。"""
    url, key = _gw_url(), _gw_key()
    # 1) 扫描各账号成长任务（读操作）
    scan = await _upstream("POST", f"{url}/panel/api/tasks/scan_all", key=key, body={})
    # 2) 执行队列状态
    queue = {}
    try:
        queue = await _upstream("GET", f"{url}/panel/api/tasks/queue", key=key)
    except HTTPException:
        queue = {}
    # 3) 账号池概览（积分/最近成功）
    overview = {}
    try:
        overview = await _upstream("GET", f"{url}/panel/api/overview", key=key)
    except HTTPException:
        overview = {}
    ov_map = {}
    for a in (overview.get("accounts") or []):
        if isinstance(a, dict) and a.get("uid"):
            ov_map[str(a["uid"])] = a
    accounts = []
    for acc in (scan.get("accounts") or []):
        if not isinstance(acc, dict):
            continue
        uid = str(acc.get("uid") or "")
        growth = acc.get("growth") if isinstance(acc.get("growth"), list) else []
        done = sum(1 for x in growth if isinstance(x, dict) and _task_done(x))
        reward = sum(1 for x in growth if isinstance(x, dict) and x.get("has_reward") and not _task_done(x))
        ovd = ov_map.get(uid, {})
        accounts.append({
            "uid": uid,
            "nickname": acc.get("nickname") or ovd.get("nickname") or uid[-4:],
            "tasks_total": len(growth),
            "tasks_done": done,
            "rewards_pending": reward,
            "credits": ovd.get("credits"),
            "credits_total": ovd.get("credits_total"),
            "cooling": bool(ovd.get("cooling")),
            "last_success": str(ovd.get("last_success") or "")[:19],
        })
    return {
        "ok": True,
        "gateway": url,
        "pool_total": len(accounts),
        "accounts": accounts,
        "queue": {
            "running": bool(queue.get("running")),
            "total": queue.get("total") or 0,
            "conc": queue.get("conc") or 0,
        },
        "schedule": {
            "checkin": "09:00 / 21:00",
            "growth": "01:00",
            "activity": "10:00",
            "travel": "09:00 / 21:00",
            "keepalive": "22:00",
            "blackcat": "23:00",
        },
    }


@router.post("/tasks/scan")
async def workbuddy_tasks_scan():
    """重新扫描成长任务（读操作，仅刷新任务列表）。"""
    url, key = _gw_url(), _gw_key()
    data = await _upstream("POST", f"{url}/panel/api/tasks/scan_all", key=key, body={})
    return {"ok": True, "accounts": len(data.get("accounts") or [])}


@router.post("/tasks/run")
async def workbuddy_tasks_run():
    """触发 wb2api 一键任务队列（有副作用：会真实执行任务）。"""
    url, key = _gw_url(), _gw_key()
    data = await _upstream("POST", f"{url}/panel/api/tasks/run_queue", key=key, body={})
    return {"ok": bool(data.get("ok")), "started": data.get("started"),
            "total": data.get("total"), "seq": data.get("seq")}


@router.post("/tasks/checkin")
async def workbuddy_tasks_checkin():
    """触发 wb2api 全账号签到（有副作用：真实签到）。"""
    url, key = _gw_url(), _gw_key()
    data = await _upstream("POST", f"{url}/panel/api/checkin_all", key=key, body={})
    return {"ok": bool(data.get("ok")), "started": data.get("started")}
