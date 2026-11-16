"""AAM 面板管理鉴权：面板密钥（panel_key）+ 签名 Cookie + X-Admin-Key 头。

- GET/POST /api/admin/login、/api/admin/me、/api/admin/logout 不要求鉴权（登录入口本身）。
- 其余所有 /api/* 与 /api/login/*、/api/trae-login/*、/novnc/* 都要求管理员身份：
    方式一：请求头 X-Admin-Key: <panel_key>
    方式二：登录后种下的 HttpOnly Cookie aam_admin（HMAC 签名 + 30 天有效期）
- **多会话共存**：cookie 值是 `expire_ts.hmac(panel_key, expire_ts)`，无服务端状态，
  改 panel_key 才全部失效。登录/多设备/多入口互不顶掉，每入口登录一次管 30 天。
- 缺省 panel_key 不再用固定默认值：首次访问时自动生成随机密钥并存到 data/admin_key.txt。
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import db
from .config import DATA_DIR

COOKIE_NAME = "aam_admin"
PANEL_KEY_SETTING = "panel_key"
KEY_FILE = DATA_DIR / "admin_key.txt"
COOKIE_TTL = 30 * 86400  # 30 天


def _load_or_create_panel_key() -> str:
    """返回当前面板密钥；若从未设置则生成随机密钥并落盘提示。"""
    key = db.get_setting(PANEL_KEY_SETTING, "")
    if key:
        return key
    key = secrets.token_urlsafe(24)
    db.set_setting(PANEL_KEY_SETTING, key)
    _write_key_file(key)
    return key


def _write_key_file(key: str) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        KEY_FILE.write_text(
            "AAM Panel Admin Key (面板登录密钥):\n" + key + "\n\n"
            "在面板登录框输入此密钥即可；可在「设置」页修改后此文件自动更新。\n",
            encoding="utf-8",
        )
        KEY_FILE.chmod(0o600)
    except OSError:
        pass


def _rotated_panel_key(key: str) -> None:
    db.set_setting(PANEL_KEY_SETTING, key)
    _write_key_file(key)


def _safe_eq(a: str, b: str) -> bool:
    return bool(a and b) and hmac.compare_digest(a.encode(), b.encode())


def _sign(panel_key: str, expire_ts: int) -> str:
    raw = f"{expire_ts}.{panel_key}"
    return hmac.new(panel_key.encode(), raw.encode(), hashlib.sha256).hexdigest()[:32]


def _make_cookie_value(panel_key: str) -> str:
    expire_ts = int(time.time()) + COOKIE_TTL
    return f"{expire_ts}.{_sign(panel_key, expire_ts)}"


def _cookie_ok(panel_key: str, cookie: str) -> bool:
    """校验签名 cookie：格式 expire_ts.sig，签名匹配且未过期。"""
    try:
        expire_ts_s, sig = cookie.rsplit(".", 1)
        expire_ts = int(expire_ts_s)
    except (ValueError, AttributeError):
        return False
    if time.time() > expire_ts:
        return False
    return _safe_eq(sig, _sign(panel_key, expire_ts))


def _request_authed(request: Request, x_admin_key: str | None) -> bool:
    header = (x_admin_key or "").strip()
    panel_key = _load_or_create_panel_key()
    if _safe_eq(header, panel_key):
        return True
    cookie = request.cookies.get(COOKIE_NAME, "")
    return bool(cookie) and _cookie_ok(panel_key, cookie)


def require_admin(request: Request, x_admin_key: str | None = Header(None)):
    """FastAPI 依赖：管理接口鉴权。未通过返回 401。"""
    if not _request_authed(request, x_admin_key):
        raise HTTPException(401, "需要面板密钥（X-Admin-Key 或登录 Cookie）")


def require_admin_ws(ws) -> bool:
    """WebSocket 手写鉴权：不通过时关闭连接并返回 False。"""
    if not _request_authed(ws, ws.headers.get("x-admin-key")):
        return False
    return True


router = APIRouter(prefix="/api/admin")


class LoginInput(BaseModel):
    key: str = ""


@router.post("/login")
async def admin_login(body: LoginInput, request: Request):
    """校验面板密钥 → 种 30 天签名 Cookie（多设备/多入口互不顶掉）。附简易 IP 限频。"""
    if not db.rate_limit("admin_login", request.client.host if request.client else "?", 1):
        raise HTTPException(429, "登录过于频繁，请稍后再试")
    key = body.key.strip()
    expected = _load_or_create_panel_key()
    if not _safe_eq(key, expected):
        raise HTTPException(401, "面板密钥错误")
    resp = JSONResponse({"ok": True, "message": "登录成功"})
    resp.set_cookie(
        COOKIE_NAME, _make_cookie_value(expected),
        max_age=COOKIE_TTL, httponly=True, samesite="strict",
    )
    return resp


@router.post("/logout")
async def admin_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME)
    return resp


@router.get("/me")
async def admin_me(request: Request, x_admin_key: str | None = Header(None)):
    return {"ok": True, "authed": _request_authed(request, x_admin_key)}