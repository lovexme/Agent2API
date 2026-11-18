"""WorkBuddy OAuth 授权并自动导入 AAM 账号。"""
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
UPSTREAM = "https://copilot.tencent.com"
ORIGIN = "https://www.codebuddy.cn"
UA = "CLI/2.63.2 CodeBuddy/2.63.2"
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


TTL = 900


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
    """跨进程文件锁：读改写 workbuddy_oauth_states.json 时互斥。

    非阻塞尝试 + 超时：避免持锁请求异常时其它请求无限阻塞（会表现为面板"打不开"）。
    """
    import fcntl
    lock_path = Path(str(STATE_FILE) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    with open(lock_path, "a+") as lf:
        while True:
            try:
                fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"file lock timeout: {lock_path}")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def _headers(token=""):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/plain, */*",
               "X-Requested-With": "XMLHttpRequest", "Origin": ORIGIN,
               "Referer": ORIGIN + "/", "User-Agent": UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _upstream(method, url, token="", body=None):
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.request(method, url, headers=_headers(token), json=body)
    if response.status_code >= 300:
        raise HTTPException(502, f"WorkBuddy 上游返回 HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError:
        raise HTTPException(502, "WorkBuddy 上游返回无法解析的数据")
    if not isinstance(payload, dict) or payload.get("code") != 0:
        return None
    return payload.get("data") or {}


@router.post("/start")
async def start():
    data = await _upstream("POST", f"{UPSTREAM}/v2/plugin/auth/state?platform=CLI", body={})
    state = str((data or {}).get("state") or "")
    url = str((data or {}).get("authUrl") or "")
    if not state or not url or not re.fullmatch(r"[A-Za-z0-9-]{8,128}", state):
        raise HTTPException(502, "WorkBuddy 未返回有效授权状态")
    now = int(time.time())
    with _states_lock():
        states = {k: v for k, v in _states().items() if int(v.get("expires_at", 0)) > now}
        states[state] = {"created_at": now, "expires_at": now + TTL, "account_id": None}
        _save_states(states)
    return {"ok": True, "state": state, "url": url, "expires_at": now + TTL}


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

    token_data = await _upstream("GET", f"{UPSTREAM}/v2/plugin/auth/token?state={state}")
    access_token = str((token_data or {}).get("accessToken") or "")
    if not access_token:
        return {"ok": True, "status": "pending"}
    account_data = await _upstream("GET", f"{UPSTREAM}/v2/plugin/login/account?state={state}", token=access_token)
    account_data = account_data or {}
    uid = str(account_data.get("uid") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", uid):
        raise HTTPException(502, "WorkBuddy 已授权，但未返回有效账号 ID")
    nickname = str(account_data.get("nickname") or "")
    user_info = {"uid": uid, "nickname": nickname,
                 "enterpriseId": account_data.get("enterpriseId", ""),
                 "refreshToken": token_data.get("refreshToken", ""),
                 "expiresIn": token_data.get("expiresIn", 0),
                 "domain": token_data.get("domain", "")}
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM platforms WHERE key='workbuddy'").fetchone()
        if not row:
            raise HTTPException(500, "缺少 key=workbuddy 的平台记录,请先在「平台」页创建(adapter=openai_compat)")
        platform_id = row["id"]
        existing = conn.execute("SELECT id FROM accounts WHERE platform_id=? AND json_extract(user_info, '$.uid')=?", (platform_id, uid)).fetchone()
        if existing:
            account_id = existing["id"]
            conn.execute("UPDATE accounts SET name=?,credential=?,credential_type='token',user_info=? WHERE id=?",
                         (f"WorkBuddy-{uid[-4:]}", access_token, json.dumps(user_info, ensure_ascii=False), account_id))
        else:
            cur = conn.execute("INSERT INTO accounts(platform_id,name,credential,credential_type,user_info) VALUES(?,?,?,?,?)",
                               (platform_id, f"WorkBuddy-{uid[-4:]}", access_token, "token", json.dumps(user_info, ensure_ascii=False)))
            account_id = cur.lastrowid
    with _states_lock():
        states = _states()
        if state in states:
            states[state]["account_id"] = account_id
            _save_states(states)
    from .api import check_account
    account = await check_account(account_id)
    return _redact({"ok": True, "status": "done", "account": account})
