"""Tabbit 国内版手机验证码登录 → 自动建号（面板内「发短信添加」）

协议要点（2026-11-15 逆向确认）：
- 发码: POST https://web.tabbit.com/proxy/v0/oauth/send-verification-code
  body = {uuid(64位字母数字), platform:"1", version:"", app:"1000", mobile}
  返回 code=0 即接受；无需额外签名。
- 登录: POST https://web.tabbit.com/proxy/v0/oauth/login
  body = {uuid(64位, 可新生成), platform:"1", version:"", app:"1000", mobile, smsCode}
  返回 success + Set-Cookie: next-auth.session-token / token / expires_in / user_id
- uuid 不参与验证码校验（验证码只绑手机号），登录可换新 uuid。
- 验证码一次性：登录成功后即作废。
"""
import json
import secrets
import string

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from . import db
from .auth import require_admin

router = APIRouter(prefix="/api/login", dependencies=[Depends(require_admin)])

BASE = "https://web.tabbit.com"
UA = "Mozilla/5.0"


class SMSInput(BaseModel):
    phone: str = ""


class VerifyInput(BaseModel):
    phone: str = ""
    mcode: str = ""


def _uuid64() -> str:
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))


def _headers() -> dict:
    return {"Content-Type": "application/json", "Origin": BASE,
            "Referer": BASE + "/login", "User-Agent": UA}


@router.post("/tabbit/send")
async def tabbit_send(request: Request, body: SMSInput):
    """给手机号发 Tabbit 短信验证码。限频防轰炸。"""
    phone = body.phone.strip()
    if len(phone) != 11 or not phone.isdigit() or phone[0] != "1":
        raise HTTPException(400, "手机号格式不对（11 位大陆号）")
    client = request.client
    ip = client.host if client else "?"
    if not db.rate_limit("sms_send", f"phone:{phone}", 60):
        raise HTTPException(429, "该手机号 60 秒内只能发送一次，请稍后再试")
    if not db.rate_limit("sms_send", f"ip:{ip}", 5):
        raise HTTPException(429, "发送过于频繁，请稍后再试")
    payload = {"uuid": _uuid64(), "platform": "1", "version": "", "app": "1000", "mobile": phone}
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post(BASE + "/proxy/v0/oauth/send-verification-code",
                         json=payload, headers=_headers())
    try:
        d = r.json()
    except Exception:
        raise HTTPException(502, f"上游响应异常: {r.text[:120]}")
    if d.get("code") == 0:
        data = d.get("data") or {}
        if isinstance(data, dict) and (data.get("verifyUrl") or data.get("requestCode")):
            raise HTTPException(400, "触发 YodaSeed 滑块验证，需在 Tabbit 客户端过验证后重试")
        return {"ok": True, "msg": f"验证码已发送到 {phone}"}
    err = d.get("error") or {}
    raise HTTPException(400, f"发码失败: {err.get('msg') or d.get('message') or json.dumps(d, ensure_ascii=False)[:120]}")


@router.post("/tabbit/verify")
async def tabbit_verify(request: Request, body: VerifyInput):
    """校验验证码 → 登录拿到 cookie → 自动建号入 AAM。验证码尝试限频。"""
    phone = body.phone.strip()
    mcode = body.mcode.strip()
    if len(phone) != 11 or not phone.isdigit():
        raise HTTPException(400, "手机号格式不对")
    if not mcode:
        raise HTTPException(400, "请输入验证码")
    client = request.client
    ip = client.host if client else "?"
    if not db.rate_limit("sms_verify", f"phone:{phone}", 10):
        raise HTTPException(429, "验证次数过于频繁，请稍后再试")
    payload = {"uuid": _uuid64(), "platform": "1", "version": "",
               "app": "1000", "mobile": phone, "smsCode": mcode}
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post(BASE + "/proxy/v0/oauth/login", json=payload, headers=_headers())
    try:
        d = r.json()
    except Exception:
        raise HTTPException(502, f"上游响应异常: {r.text[:120]}")
    if not d.get("success"):
        raise HTTPException(400, f"登录失败: {d.get('message') or d.get('error') or json.dumps(d, ensure_ascii=False)[:120]}")
    uid = d.get("user_id") or ""
    # 把 Set-Cookie 拼成 adapter 需要的 Cookie 串
    items = [(k, v) for k, v in r.cookies.items() if k in ("next-auth.session-token", "token", "expires_in", "user_id")]
    cred = "; ".join(f"{k}={v}" for k, v in items)
    if not cred:
        raise HTTPException(502, "登录成功但未返回 Cookie")
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM platforms WHERE key='tabbit-domestic'").fetchone()
        pid = row["id"] if row else 1
        cur = conn.execute(
            "INSERT INTO accounts(platform_id,name,credential,credential_type,user_info) VALUES(?,?,?,?,?)",
            (pid, f"Tabbit-{phone[-4:]}", cred, "cookie",
             json.dumps({"phone": phone, "id": uid, "display_name": "",
                         "secret_mobile": f"*******{phone[-4:]}"}, ensure_ascii=False)))
        acct_id = cur.lastrowid
    from .api import check_account
    item = await check_account(acct_id)
    if isinstance(item, dict):
        item.pop("credential", None)
    return {"ok": True, "account": item}