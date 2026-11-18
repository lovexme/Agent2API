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

UA = "Mozilla/5.0"
DEFAULT_BASES = {
    "tabbit-domestic": "https://web.tabbit.com",
    "tabbit-intl": "https://web.tabbit.ai",
}

def _tab_endpoint(platform: str):
    """按平台 key 返回 (base, proxy, platform_key)。

    base/proxy 优先取「平台接入」页该平台配置(别人部署可自行改),
    未配置时回退默认域名;国际版通常需要出口代理。
    """
    key = platform if platform in DEFAULT_BASES else "tabbit-domestic"
    base, proxy = DEFAULT_BASES[key], None
    try:
        with db.connect() as conn:
            row = conn.execute("SELECT base_url, proxy FROM platforms WHERE key=?", (key,)).fetchone()
        if row:
            base = (row["base_url"] or base).rstrip("/")
            proxy = row["proxy"] or None
    except Exception:
        pass
    return base, proxy, key


class SMSInput(BaseModel):
    phone: str = ""


class VerifyInput(BaseModel):
    phone: str = ""
    mcode: str = ""


def _uuid64() -> str:
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))


def _headers(base: str) -> dict:
    return {"Content-Type": "application/json", "Origin": base,
            "Referer": base + "/login", "User-Agent": UA}


@router.post("/tabbit/send")
async def tabbit_send(request: Request, body: SMSInput, platform: str = "tabbit-domestic"):
    """给手机号发 Tabbit 短信验证码（国内 web.tabbit.com / 国际 web.tabbit.ai）。限频防轰炸。"""
    phone = body.phone.strip()
    if platform in ("tabbit-intl",):
        if not (phone.startswith("+") and phone[1:].isdigit() and 8 <= len(phone) - 1 <= 15)            and not (phone.isdigit() and 8 <= len(phone) <= 15):
            raise HTTPException(400, "国际版手机号格式: 如 +8618900000000 或纯数字 8-15 位")
    else:
        if len(phone) != 11 or not phone.isdigit() or phone[0] != "1":
            raise HTTPException(400, "手机号格式不对（11 位大陆号）")
    client = request.client
    ip = client.host if client else "?"
    scope = "sms_send:tabbit-intl" if platform == "tabbit-intl" else "sms_send:tabbit"
    if not db.rate_limit(scope, f"phone:{phone}", 60):
        raise HTTPException(429, "该手机号 60 秒内只能发送一次，请稍后再试")
    if not db.rate_limit("sms_send_ip", f"ip:{ip}", 5):
        raise HTTPException(429, "发送过于频繁，请稍后再试")
    base, proxy, _ = _tab_endpoint(platform)
    payload = {"uuid": _uuid64(), "platform": "1", "version": "", "app": "1000", "mobile": phone}
    async with httpx.AsyncClient(timeout=25, proxy=proxy) as c:
        r = await c.post(base + "/proxy/v0/oauth/send-verification-code",
                         json=payload, headers=_headers(base))
    try:
        d = r.json()
    except Exception:
        raise HTTPException(502, f"上游响应异常: {r.text[:120]}")
    if d.get("code") == 0:
        data = d.get("data") or {}
        if isinstance(data, dict) and (data.get("verifyUrl") or data.get("requestCode")):
            raise HTTPException(400, "触发 YodaSeed 滑块验证，需在 Tabbit 客户端过验证后重试")
        # Tabbit 验证流程不需要 msgid（verify 只用 phone+smsCode），返回空串保持响应结构一致
        return {"ok": True, "msgid": "", "msg": f"验证码已发送到 {phone}"}
    err = d.get("error") or {}
    raw = str(err.get("msg") or d.get("message") or d.get("detail") or "")
    if "noBetaPermission" in raw or "beta" in raw.lower():
        raise HTTPException(400, "Tabbit 国际版暂未开放手机号登录（auth.noBetaPermission）。"
                                 "请改用 Cookie 添加：浏览器(需挂出口代理)打开 https://web.tabbit.ai → Google 登录 → F12 复制 Cookie → 面板新增账号选 Tabbit 国际版粘贴")
    raise HTTPException(400, f"发码失败: {raw or json.dumps(d, ensure_ascii=False)[:120]}")


@router.post("/tabbit/verify")
async def tabbit_verify(request: Request, body: VerifyInput, platform: str = "tabbit-domestic"):
    """校验验证码 → 登录拿到 cookie → 自动建号入 AAM。验证码尝试限频。

    platform: tabbit-domestic(默认) / tabbit-intl
    """
    phone = body.phone.strip()
    mcode = body.mcode.strip()
    if platform in ("tabbit-intl",):
        if not (phone.startswith("+") and phone[1:].isdigit() and 8 <= len(phone) - 1 <= 15)            and not (phone.isdigit() and 8 <= len(phone) <= 15):
            raise HTTPException(400, "国际版手机号格式: 如 +8618900000000 或纯数字 8-15 位")
    else:
        if len(phone) != 11 or not phone.isdigit():
            raise HTTPException(400, "手机号格式不对")
    if not mcode:
        raise HTTPException(400, "请输入验证码")
    client = request.client
    ip = client.host if client else "?"
    scope = "sms_verify:tabbit-intl" if platform == "tabbit-intl" else "sms_verify:tabbit"
    if not db.rate_limit(scope, f"phone:{phone}", 10):
        raise HTTPException(429, "验证次数过于频繁，请稍后再试")
    base, proxy, _ = _tab_endpoint(platform)
    payload = {"uuid": _uuid64(), "platform": "1", "version": "",
               "app": "1000", "mobile": phone, "smsCode": mcode}
    async with httpx.AsyncClient(timeout=25, proxy=proxy) as c:
        r = await c.post(base + "/proxy/v0/oauth/login", json=payload, headers=_headers(base))
    try:
        d = r.json()
    except Exception:
        raise HTTPException(502, f"上游响应异常: {r.text[:120]}")
    if not d.get("success"):
        raw = str(d.get("message") or d.get("error") or d.get("detail") or "")
        if "noBetaPermission" in raw or "beta" in raw.lower():
            raise HTTPException(400, "Tabbit 国际版暂未开放手机号登录（auth.noBetaPermission）。"
                                     "请改用 Cookie 添加：浏览器(需挂出口代理)打开 https://web.tabbit.ai → Google 登录 → F12 复制 Cookie → 面板新增账号选 Tabbit 国际版粘贴")
        raise HTTPException(400, f"登录失败: {raw or json.dumps(d, ensure_ascii=False)[:120]}")
    uid = d.get("user_id") or ""
    # 把 Set-Cookie 拼成 adapter 需要的 Cookie 串
    items = [(k, v) for k, v in r.cookies.items() if k in ("next-auth.session-token", "token", "expires_in", "user_id")]
    cred = "; ".join(f"{k}={v}" for k, v in items)
    if not cred:
        raise HTTPException(502, "登录成功但未返回 Cookie")
    plat_key = "tabbit-intl" if platform == "tabbit-intl" else "tabbit-domestic"
    user_id_suffix = phone[-4:] if phone and len(phone) >= 4 else (uid[-4:] or "x")
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM platforms WHERE key=?", (plat_key,)).fetchone()
        pid = row["id"] if row else 1
        cur = conn.execute(
            "INSERT INTO accounts(platform_id,name,credential,credential_type,user_info) VALUES(?,?,?,?,?)",
            (pid, f"Tabbit-{user_id_suffix}", cred, "cookie",
             json.dumps({"phone": phone, "id": uid, "display_name": "", "realm": "intl" if platform == "tabbit-intl" else "cn",
                         "secret_mobile": f"*******{user_id_suffix}"}, ensure_ascii=False)))
        acct_id = cur.lastrowid
    from .api import check_account
    item = await check_account(acct_id)
    if isinstance(item, dict):
        item.pop("credential", None)
    return {"ok": True, "account": item}