from datetime import date, timedelta
import asyncio
import json
import os
import secrets
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from . import db
from .auth import require_admin
from .platforms import ADAPTERS

router = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])

class PlatformInput(BaseModel):
    key: str
    name: str
    adapter: str
    base_url: str = ""
    proxy: str = ""
    enabled: bool = True
    meta: dict = {}

class AccountInput(BaseModel):
    platform_id: int
    name: str
    credential: str
    credential_type: str = "cookie"

class AccountUpdate(BaseModel):
    name: str | None = None
    credential: str | None = None
    enabled: bool | None = None

class SettingsInput(BaseModel):
    panel_key: str | None = None
    gateway_key: str | None = None
    daily_auto_check: str | None = None

class RefreshInput(BaseModel):
    pass

_ADAPTER_CACHE: dict = {}
_ADAPTER_TTL = 300


def invalidate_adapter(platform_id: int | None = None):
    """平台配置变更后清掉 adapter 实例缓存（sign-key/models/session 缓存失效）。"""
    if platform_id is None:
        _ADAPTER_CACHE.clear()
    else:
        _ADAPTER_CACHE.pop(platform_id, None)


def adapter_for(platform):
    cls = ADAPTERS.get(platform["adapter"])
    if not cls:
        raise HTTPException(400, f"unsupported adapter: {platform['adapter']}")
    pid = platform.get("id")
    if pid is None:
        return cls(platform)
    now = time.monotonic()
    entry = _ADAPTER_CACHE.get(pid)
    if entry and entry[0] > now:
        return entry[1]
    adapter = cls(platform)
    _ADAPTER_CACHE[pid] = (now + _ADAPTER_TTL, adapter)
    if len(_ADAPTER_CACHE) > 64:
        for stale in [k for k, (exp, _) in _ADAPTER_CACHE.items() if exp <= now]:
            _ADAPTER_CACHE.pop(stale, None)
    return adapter


SENSITIVE_KEYS = {"refreshToken", "refresh_token", "accessToken", "access_token",
                  "token", "session", "cookie", "credential", "password", "secret"}


def _redact_user_info(value):
    """序列化账号时剥掉 user_info 里可续用的凭据字段（refreshToken 等）。"""
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if k not in SENSITIVE_KEYS}
    return value


async def check_account(account_id):
    account = db.get_account(account_id)
    if not account:
        raise HTTPException(404, "account not found")
    platform = db.get_platform(account["platform_id"])
    try:
        result = await adapter_for(platform).check(account)
    except Exception as exc:
        result = {"status":"error", "status_msg":str(exc), "member_level":account.get("member_level", ""),
                  "quota_pct":account.get("quota_pct"), "quota_json":db.parse_json(account.get("quota_json")),
                  "user_info":db.parse_json(account.get("user_info"))}
    # 合并而非覆盖：adapter 返回的 user_info/quota_json 只更新它提供的字段，
    # 保留 DB 里的扩展字段（loomy 的 session_expire_at、tabbit 的 secret_mobile 等），
    # 否则每次「检测」都会把到期时间等额外信息冲掉（表现为面板不显示到期）。
    ui_old = db.parse_json(account.get("user_info"))
    ui_new = result.get("user_info")
    ui_merged = {**ui_old, **ui_new} if isinstance(ui_new, dict) else ui_old
    qj_old = db.parse_json(account.get("quota_json"))
    qj_new = result.get("quota_json")
    qj_merged = {**qj_old, **qj_new} if isinstance(qj_new, dict) else qj_old
    fields = {"status":result["status"], "status_msg":result.get("status_msg", ""),
              "member_level":result.get("member_level", account.get("member_level", "")),
              "quota_pct":result.get("quota_pct", account.get("quota_pct")),
              "quota_json":json.dumps(qj_merged, ensure_ascii=False),
              "user_info":json.dumps(ui_merged, ensure_ascii=False),
              "check_at":time.strftime("%Y-%m-%d %H:%M:%S")}
    saved = db.update_account(account_id, fields)
    saved.pop("credential", None)
    return {**saved, "quota_json": db.parse_json(saved["quota_json"]),
            "user_info": _redact_user_info(db.parse_json(saved["user_info"]))}

async def daily_tasks_data():
    key = _trae_relay_api_key()
    accounts = []
    try:
        from pathlib import Path as _Path
        data = {}
        _env = os.environ.get("TRAE2API_DATA", "")
        if _env:
            data = json.loads(_Path(_env).read_text(encoding="utf-8"))
        for k, v in (data.get("accounts") or {}).items():
            accounts.append({"account_id": k, "label": str(v.get("label") or v.get("user_id") or k)})
    except Exception:
        accounts = []
    sem = asyncio.Semaphore(8)

    async def _query(account):
        account_id = account["account_id"]
        async with sem:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.get(
                        f"http://127.0.0.1:8770/api/checkin/account/{account_id}",
                        headers={"Authorization": f"Bearer {key}"},
                    )
                payload = response.json()
                data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
                checked_in = bool(data.get("checked_in") or data.get("already_checked_in"))
                account["checked_in"] = checked_in
                account["status"] = "已签到" if checked_in else "未签到"
            except (httpx.HTTPError, ValueError):
                account["checked_in"] = None
                account["status"] = "状态未知"

    await asyncio.gather(*(_query(account) for account in accounts))
    return accounts


async def _daily_task_status(account_id: str, key: str):
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"http://127.0.0.1:8770/api/checkin/account/{account_id}",
                headers={"Authorization": f"Bearer {key}"},
            )
        payload = response.json()
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        checked_in = bool(data.get("checked_in") or data.get("already_checked_in"))
        message = data.get("message") or ("已签到" if checked_in else "未签到")
        return {"account_id": account_id, "checked_in": checked_in, "message": message}
    except (httpx.HTTPError, ValueError) as exc:
        return {"account_id": account_id, "checked_in": None, "message": f"状态查询失败：{exc}"}


def _trae_relay_api_key():
    env_path = os.environ.get("TRAE2API_ENV", "")
    try:
        with open(env_path, encoding="utf-8") as source:
            for line in source:
                if line.strip().startswith("RELAY_API_KEYS="):
                    value = line.split("=", 1)[1].strip().strip("\\\"'")
                    key = value.split(",", 1)[0].strip()
                    if key:
                        return key
    except OSError as exc:
        raise HTTPException(500, f"读取 Trae API 配置失败: {exc}")
    raise HTTPException(500, "Trae API 未配置 RELAY_API_KEYS")


@router.get("/daily-tasks")
async def daily_tasks_get():
    """Trae 账号每日任务状态（签到情况）"""
    return await daily_tasks_data()


@router.post("/daily-tasks/checkin")
async def daily_tasks_checkin(account_id: str | None = None):
    key = _trae_relay_api_key()
    accounts = await daily_tasks_data()
    if account_id:
        accounts = [account for account in accounts if account["account_id"] == account_id]
        if not accounts:
            raise HTTPException(404, "Trae 账号不存在")
    results = []
    sem = asyncio.Semaphore(5)

    async def _checkin(account):
        account_id = account["account_id"]
        async with sem:
            try:
                async with httpx.AsyncClient(timeout=90) as client:
                    response = await client.post(
                        f"http://127.0.0.1:8770/api/checkin/account/{account_id}",
                        headers={"Authorization": f"Bearer {key}"},
                        json={},
                    )
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                success = response.is_success and payload.get("success") is True
                message = payload.get("message") or payload.get("error")
                if not message and isinstance(payload.get("data"), dict):
                    message = payload["data"].get("message")
                if not message:
                    message = "签到成功" if success else f"上游返回 HTTP {response.status_code}"
                results.append({"account_id": account_id, "ok": success, "message": message})
            except httpx.HTTPError as exc:
                results.append({"account_id": account_id, "ok": False, "message": str(exc)})

    await asyncio.gather(*(_checkin(account) for account in accounts))
    return results


@router.get("/overview")
def overview():
    with db.connect() as conn:
        platforms = [dict(row) for row in conn.execute("SELECT p.*,COUNT(a.id) account_count,COALESCE(SUM(a.status='active'),0) active_count,AVG(a.quota_pct) avg_quota_pct FROM platforms p LEFT JOIN accounts a ON a.platform_id=p.id GROUP BY p.id ORDER BY p.id")]
        stats = conn.execute("SELECT COUNT(*) total_accounts,COALESCE(SUM(status='active'),0) active_accounts FROM accounts").fetchone()
        today = date.today().isoformat()
        req = conn.execute("SELECT COALESCE(SUM(created_at>=?),0) requests_today,COALESCE(SUM(created_at>=? AND ok=0),0) errors_today FROM request_log", (today,today)).fetchone()
        count = conn.execute("SELECT COUNT(*) FROM (SELECT DISTINCT p.key,m.value FROM platforms p JOIN accounts a ON a.platform_id=p.id AND a.enabled=1 AND a.status='active' JOIN json_each(a.quota_json,'$.models') m WHERE p.adapter='tabbit')").fetchone()[0]
    return {"ok":True,"platforms":platforms,"stats":{**dict(stats),**dict(req)},"gateway":{"base_url":"/v1","models_count":count}}

@router.get("/platforms")
def list_platforms():
    with db.connect() as conn:
        rows=conn.execute("SELECT p.*,COUNT(a.id) account_count FROM platforms p LEFT JOIN accounts a ON a.platform_id=p.id GROUP BY p.id ORDER BY p.id").fetchall()
    return {"ok":True,"items":[dict(row) for row in rows]}

@router.post("/platforms")
def create_platform(body:PlatformInput):
    try:
        with db.connect() as conn:
            cur=conn.execute("INSERT INTO platforms(key,name,adapter,base_url,proxy,enabled,meta) VALUES(?,?,?,?,?,?,?)",(body.key,body.name,body.adapter,body.base_url,body.proxy,int(body.enabled),json.dumps(body.meta)))
        invalidate_adapter()
        return {"ok":True,"item":db.get_platform(cur.lastrowid)}
    except Exception as exc:
        raise HTTPException(400,str(exc))

@router.put("/platforms/{platform_id}")
def update_platform(platform_id:int,body:dict):
    allowed={k:v for k,v in body.items() if k in {"key","name","adapter","base_url","proxy","enabled","meta"}}
    if "meta" in allowed: allowed["meta"]=json.dumps(allowed["meta"])
    if "enabled" in allowed: allowed["enabled"]=int(allowed["enabled"])
    with db.connect() as conn:
        cur=conn.execute("UPDATE platforms SET " +",".join(f"{k}=?" for k in allowed)+" WHERE id=?",(*allowed.values(),platform_id)) if allowed else None
    invalidate_adapter(platform_id)
    item=db.get_platform(platform_id)
    if not item: raise HTTPException(404,"platform not found")
    return {"ok":True,"item":item}

@router.delete("/platforms/{platform_id}")
def delete_platform(platform_id:int):
    with db.connect() as conn:
        row=conn.execute("SELECT builtin FROM platforms WHERE id=?",(platform_id,)).fetchone()
        if not row: raise HTTPException(404,"platform not found")
        if row[0]: raise HTTPException(400,"built-in platform cannot be deleted")
        conn.execute("DELETE FROM platforms WHERE id=?",(platform_id,))
    invalidate_adapter(platform_id)
    return {"ok":True}

@router.get("/accounts")
def list_accounts(platform_id:int|None=None,status:str|None=None):
    sql="SELECT a.*,p.key platform_key,p.name platform_name FROM accounts a JOIN platforms p ON p.id=a.platform_id WHERE 1=1"; args=[]
    if platform_id is not None: sql+=" AND a.platform_id=?"; args.append(platform_id)
    if status: sql+=" AND a.status=?"; args.append(status)
    with db.connect() as conn: rows=conn.execute(sql+" ORDER BY a.id DESC",args).fetchall()
    return {"ok":True,"items":[dict(r,credential="[redacted]",quota_json=db.parse_json(r["quota_json"]),
            user_info=_redact_user_info(db.parse_json(r["user_info"]))) for r in rows]}

@router.post("/accounts")
async def create_account(body:AccountInput):
    platform=db.get_platform(body.platform_id)
    if not platform: raise HTTPException(404,"platform not found")
    with db.connect() as conn:
        cur=conn.execute("INSERT INTO accounts(platform_id,name,credential,credential_type) VALUES(?,?,?,?)",(body.platform_id,body.name,body.credential,body.credential_type))
    return {"ok":True,"item":await check_account(cur.lastrowid)}

@router.put("/accounts/{account_id}")
def edit_account(account_id:int,body:AccountUpdate):
    fields={k:v for k,v in body.model_dump(exclude_none=True).items()}
    if "enabled" in fields: fields["enabled"]=int(fields["enabled"])
    item=db.update_account(account_id,fields)
    if not item: raise HTTPException(404,"account not found")
    item.update(credential="[redacted]",quota_json=db.parse_json(item["quota_json"]),
                user_info=_redact_user_info(db.parse_json(item["user_info"])))
    return {"ok":True,"item":item}

@router.delete("/accounts/{account_id}")
def delete_account(account_id:int):
    with db.connect() as conn: cur=conn.execute("DELETE FROM accounts WHERE id=?",(account_id,))
    if not cur.rowcount: raise HTTPException(404,"account not found")
    return {"ok":True}

@router.post("/accounts/{account_id}/check")
async def check_route(account_id:int):
    result=await check_account(account_id)
    return {"ok":True,**{k:result.get(k) for k in ("status","status_msg","member_level","quota_pct","quota_json","user_info")}}

@router.post("/accounts/{account_id}/refresh-quota")
async def refresh_quota(account_id:int):
    result=await check_account(account_id)
    return {"ok":True,**{k:result.get(k) for k in ("status","member_level","quota_pct","quota_json")}}

@router.get("/accounts/{account_id}/models")
async def account_models(account_id:int):
    account=db.get_account(account_id)
    if not account: raise HTTPException(404,"account not found")
    platform=db.get_platform(account["platform_id"])
    try: models=await adapter_for(platform).models(account)
    except Exception as exc: raise HTTPException(502,str(exc))
    with db.connect() as conn:
        quota=db.parse_json(account.get("quota_json")); quota["models"]=models
        conn.execute("UPDATE accounts SET quota_json=? WHERE id=?",(json.dumps(quota,ensure_ascii=False),account_id))
    return {"ok":True,"items":models}

@router.get("/stats")
def stats(days:int=Query(7,ge=1,le=365)):
    start=(date.today()-timedelta(days=days-1)).isoformat()
    with db.connect() as conn: rows=conn.execute("SELECT date(created_at) date,SUM(ok) ok,SUM(ok=0) err FROM request_log WHERE date(created_at)>=? GROUP BY date(created_at) ORDER BY date(created_at)",(start,)).fetchall()
    return {"ok":True,"items":[dict(r) for r in rows]}

@router.get("/logs")
def logs(limit:int=Query(100,ge=1,le=1000)):
    with db.connect() as conn: rows=conn.execute("SELECT * FROM request_log ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
    return {"ok":True,"items":[dict(r) for r in rows]}

@router.get("/settings")
def settings():
    return {"ok":True,"panel_key":db.get_setting("panel_key",""),"gateway_key":db.get_setting("gateway_key","aam-local-key"),
            "daily_auto_check":db.get_setting("daily_auto_check","on")}

@router.post("/settings")
def save_settings(body:SettingsInput):
    if body.panel_key is not None: db.set_setting("panel_key",body.panel_key)
    if body.gateway_key is not None: db.set_setting("gateway_key",body.gateway_key)
    if body.daily_auto_check is not None: db.set_setting("daily_auto_check",body.daily_auto_check)
    return settings()

# ---------------- API 密钥（令牌）管理 ----------------

class TokenInput(BaseModel):
    name: str
    platform_key: str = ""
    note: str = ""
    enabled: bool = True

def new_token_value():
    while True:
        value = "aam-" + secrets.token_hex(20)
        with db.connect() as conn:
            row = conn.execute("SELECT id FROM tokens WHERE token=?", (value,)).fetchone()
        if not row:
            return value

@router.get("/tokens")
def list_tokens():
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM tokens ORDER BY id DESC").fetchall()
    return {"ok": True, "items": [dict(r) for r in rows], "master_key": db.get_setting("gateway_key", "aam-local-key")}

@router.post("/tokens")
def create_token(body: TokenInput):
    if not body.name.strip():
        raise HTTPException(400, "请填写密钥名称")
    value = new_token_value()
    with db.connect() as conn:
        cur = conn.execute("INSERT INTO tokens(name,token,platform_key,note,enabled) VALUES(?,?,?,?,?)",
                           (body.name.strip(), value, body.platform_key.strip(), body.note.strip(), int(body.enabled)))
        row = conn.execute("SELECT * FROM tokens WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"ok": True, "item": dict(row)}

@router.put("/tokens/{token_id}")
def update_token(token_id: int, body: dict):
    allowed = {k: v for k, v in body.items() if k in {"name", "platform_key", "note", "enabled"}}
    if "enabled" in allowed:
        allowed["enabled"] = int(allowed["enabled"])
    if allowed:
        with db.connect() as conn:
            conn.execute("UPDATE tokens SET " + ",".join(f"{k}=?" for k in allowed) + " WHERE id=?", (*allowed.values(), token_id))
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM tokens WHERE id=?", (token_id,)).fetchone()
    if not row:
        raise HTTPException(404, "token not found")
    return {"ok": True, "item": dict(row)}

@router.delete("/tokens/{token_id}")
def delete_token(token_id: int):
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM tokens WHERE id=?", (token_id,))
    if not cur.rowcount:
        raise HTTPException(404, "token not found")
    return {"ok": True}

@router.post("/tokens/{token_id}/reset")
def reset_token(token_id: int):
    value = new_token_value()
    with db.connect() as conn:
        conn.execute("UPDATE tokens SET token=? WHERE id=?", (value, token_id))
        row = conn.execute("SELECT * FROM tokens WHERE id=?", (token_id,)).fetchone()
    if not row:
        raise HTTPException(404, "token not found")
    return {"ok": True, "item": dict(row)}
