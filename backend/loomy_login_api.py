"""Loomy 手机验证码登录 → 自动建号（面板内「发短信添加」）"""
import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from . import db
from .auth import require_admin
from .config import LOOMY_AK_ID, LOOMY_AK_SECRET, LOOMY_APPID

from pydantic import BaseModel


class LoomyVerifyInput(BaseModel):
    phone: str = ""
    mcode: str = ""
    msgid: str = ""


router = APIRouter(prefix="/api/login", dependencies=[Depends(require_admin)])

ACCOUNT_BASE = "https://account.xfinfr.com"
AK_ID = LOOMY_AK_ID
AK_SECRET = LOOMY_AK_SECRET
APPID = LOOMY_APPID


def _base():
    return {"appid": APPID, "modelid": "Web", "version": "1.0.0",
            "devid": "web", "ua": "Loomy|Desktop|Electron|macOS",
            "traceid": secrets.token_hex(16)}


def _escaped_path(path: str) -> str:
    return "/".join(urllib.parse.quote(seg, safe="!()*") for seg in path.split("/"))


def _escaped_query(query) -> str:
    if not query:
        return ""
    return "&".join(f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
                    for k, v in sorted(query.items()))


def _content_md5(body: str) -> str:
    return base64.b64encode(hashlib.md5(body.encode()).digest()).decode() if body else ""


def _sign_headers(method: str, path: str, body: str, query=None):
    date = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
    nonce = str(uuid.uuid4())
    s2s = "\n".join([method.upper(), _escaped_path(path), _escaped_query(query),
                     _content_md5(body), "application/json", date, nonce, "", ""])
    sig = base64.b64encode(hmac.new(AK_SECRET.encode(), s2s.encode(), hashlib.sha1).digest()).decode()
    h = {"Authorization": f"account {AK_ID}:{sig}", "Date": date, "Nonce": nonce,
         "Content-Type": "application/json"}
    md = _content_md5(body)
    if md:
        h["Content-MD5"] = md
    return h


async def _api_post(path: str, param: dict):
    body = json.dumps({"base": _base(), "param": param}, ensure_ascii=False, separators=(",", ":"))
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post(ACCOUNT_BASE + path, content=body, headers=_sign_headers("POST", path, body))
    try:
        data = r.json()
    except Exception:
        data = {}
    # 结构化校验：只接受 dict；非预期响应统一按失败处理，避免 AttributeError 500
    return data if isinstance(data, dict) else {}


@router.post("/loomy/send")
async def loomy_send(request: Request, phone: str = ""):
    """给手机号发 Loomy 短信验证码，返回 msgid（后面 verify 用）。限频防轰炸。"""
    phone = phone.strip()
    if len(phone) != 11 or not phone.isdigit() or phone[0] != "1":
        raise HTTPException(400, "手机号格式不对（11 位大陆号）")
    client = request.client
    ip = client.host if client else "?"
    if not db.rate_limit("sms_send:loomy", f"phone:{phone}", 60):
        raise HTTPException(429, "该手机号 60 秒内只能发送一次，请稍后再试")
    if not db.rate_limit("sms_send_ip", f"ip:{ip}", 5):
        raise HTTPException(429, "发送过于频繁，请稍后再试")
    payload = await _api_post("/login/phone/sendMsgCode", {"ccode": "86", "phone": phone, "expire": 300})
    data = payload.get("data") or {}
    msgid = (data.get("msgid") or data.get("msgId") or data.get("msg_id")
             or data.get("smsId") or data.get("sms_id") or data.get("serialNo")
             or payload.get("msgid") or payload.get("msgId") or "")
    code = str(payload.get("code", ""))
    ok = code in ("0", "000000") or bool(data.get("success")) or bool(data.get("result")) is True
    return {"ok": ok, "msgid": msgid or ""}


@router.post("/loomy/verify")
async def loomy_verify(request: Request, body: LoomyVerifyInput):
    """校验验证码 → 换 session → 自动建号入 AAM。验证码尝试限频。"""
    phone = body.phone.strip()
    mcode = body.mcode.strip()
    msgid = body.msgid.strip()
    if not (phone and mcode and msgid):
        raise HTTPException(400, "缺少手机号/验证码/msgid")
    client = request.client
    ip = client.host if client else "?"
    if not db.rate_limit("sms_verify:loomy", f"phone:{phone}", 10):
        raise HTTPException(429, "验证次数过于频繁，请稍后再试")
    payload = await _api_post("/login/phone/checkCode", {
        "ccode": "86", "phone": phone, "mcode": mcode, "msgid": msgid, "expire": 1209600})
    data = payload.get("data") or {}
    session = data.get("session") or payload.get("session") or data.get("sessionId") or payload.get("sessionId")
    if not session:
        return {"ok": False, "status": "failed", "msg": "验证失败"}
    # 建号（Loomy 平台），同时记录 session 到期时间（14 天）
    import time as _t
    expire_at = _t.strftime("%Y-%m-%d %H:%M:%S", _t.localtime(_t.time() + 1209600))
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM platforms WHERE key='loomy'").fetchone()
        if not row:
            raise HTTPException(500, "AAM 无 loomy 平台")
        pid = row["id"]
        cur = conn.execute(
            "INSERT INTO accounts(platform_id,name,credential,credential_type,user_info) VALUES(?,?,?,?,?)",
            (pid, f"Loomy-{phone[-4:]}", session, "session",
             json.dumps({"phone": phone, "session_expire_at": expire_at}, ensure_ascii=False)))
        acct_id = cur.lastrowid
    from .api import check_account
    item = await check_account(acct_id)
    return {"ok": True, "status": "success", "msg": "验证成功"}