"""Trae 交互式登录：noVNC 代理 + 沙箱浏览器控制 + 登录状态同步。

用户通过 AAM 面板（IPv6 双栈）访问 /novnc/vnc.html，直接在面板里操作
两台一体沙箱浏览器（Xvfb+Chromium 已打开 trae2api /web/login），
滑滑块/授权后 trae2api 自动写入 data/accounts.json，这里负责展示状态。
"""
import json
import os
import time
import os
import secrets
from contextlib import contextmanager
from pathlib import Path

import httpx
import websockets
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from fastapi.responses import Response

from . import db
from .auth import require_admin, require_admin_ws

router = APIRouter(prefix="/api/trae-login", dependencies=[Depends(require_admin)])
novnc_router = APIRouter()  # 挂 /novnc/*

TRAE2API_DATA = Path(os.environ.get("TRAE2API_DATA", "/opt/trae2api/data/accounts.json"))
BOX_CDP = "http://127.0.0.1:9223/json"
NOVNC_UP = "http://127.0.0.1:6080"
TRAE2API_PAGE = "http://127.0.0.1:8770/web/login"


async def cdp_navigate(url: str):
    """通过沙箱 CDP(9223) 导航到指定 URL"""
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            pages = (await c.get(BOX_CDP)).json()
        pg = next((p for p in pages if p.get("type") == "page" and "chrome://" not in p.get("url", "")), pages[0])
        ws_url = pg["webSocketDebuggerUrl"]
        ws = await websockets.connect(ws_url, subprotocols=["chrome"])
        await ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}}))
        await asyncio_wait_close(ws)
        return True
    except Exception:
        return False


async def asyncio_wait_close(ws):
    import asyncio
    try:
        await asyncio.wait_for(ws.recv(), timeout=6)
    except Exception:
        pass
    try:
        await ws.close()
    except Exception:
        pass


SLIDER_FILE = Path(os.environ.get("AAM_SLIDER_FILE", str(Path(__file__).resolve().parent.parent / "data" / "sliders.json")))
_PUBLIC_BASE_CACHE = {"at": 0.0, "value": ""}


@contextmanager
def _file_lock(path: Path, timeout: float = 5.0):
    """跨进程文件锁：trae sliders / workbuddy states 等 JSON 读改写互斥。

    非阻塞尝试 + 超时：避免持锁请求异常时其它请求无限阻塞（会表现为面板"打不开"）。
    """
    import fcntl
    lock_path = Path(str(path) + ".lock")
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


def _load_sliders() -> dict:
    try:
        return json.loads(SLIDER_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_sliders(d: dict) -> None:
    try:
        SLIDER_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SLIDER_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        tmp.replace(SLIDER_FILE)
    except Exception:
        pass


@router.post("/request-slider")
async def request_slider(request: Request, phone: str = ""):
    """返回一个 rmc 滑块短链接（5 分钟有效）。必须显式传手机号，且限频。

    注意：全程异步（httpx），绝不 subprocess 同步跑 curl —— 否则会卡死整个
    uvicorn 事件循环，面板"打不开"（历史教训：曾有同步 curl 阻塞 20-30s）。
    """
    import json as _json, urllib.parse
    ph = phone.strip()
    if len(ph) != 11 or not ph.isdigit() or ph[0] != "1":
        raise HTTPException(400, "手机号格式不对（11 位大陆号）")
    client = request.client
    ip = client.host if client else "?"
    if not db.rate_limit("trae_slider", f"phone:{ph}", 60):
        raise HTTPException(429, "该手机号 60 秒内只能获取一次，请稍后再试")
    if not db.rate_limit("trae_slider", f"ip:{ip}", 10):
        raise HTTPException(429, "请求过于频繁，请稍后再试")
    enc = lambda s: "".join(f"{ord(c)^5:02x}" for c in s)
    q = urllib.parse.urlencode({"passport_jssdk_version":"3.0.11","passport_jssdk_type":"normal",
        "aid":711126,"language":"zh","account_sdk_source":"web","account_sdk_source_info":"7e276d647"})
    body = f"mix_mode=1&mobile={enc(ph)}&type={enc('24')}&is6Digits=true&fixed_mix_mode=1"
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post("https://www.trae.cn/passport/web/send_code/?"+q,
                content=body,
                headers={"User-Agent": "Mozilla/5.0 Chrome/124",
                         "Content-Type": "application/x-www-form-urlencoded",
                         "Referer": "https://www.trae.cn/login",
                         "Origin": "https://www.trae.cn"})
    except httpx.HTTPError as exc:
        return {"ok": False, "message": str(exc)[:80]}
    try:
        d = _json.loads(r.text)
        if d.get("data",{}).get("error_code") != 1105:
            return {"ok": False, "message": d.get("data",{}).get("description","")[:80]}
        conf = _json.loads(d["data"]["verify_center_decision_conf"])
    except Exception as e:
        return {"ok": False, "message": str(e)[:80]}
    vd = json.dumps(conf)
    qs = urllib.parse.urlencode({"from":"iframe","fp":conf["fp"],"verify_data":vd,
        "aid":711126,"appName":"trae","lang":"zh-CN","pageId":"trae-login","os_type":"-1","repoId":"trae"})
    url = "https://rmc.bytedance.com/verifycenter/captcha/v2?" + qs
    sid = secrets.token_hex(4)

    def _append():
        sliders = _load_sliders()
        sliders = {k: v for k, v in sliders.items() if v.get("exp", 0) > time.time()}
        sliders[sid] = {"url": url, "exp": time.time() + 1800, "phone": ph, "ticket": conf.get("verify_ticket", "")}
        _save_sliders(sliders)

    try:
        with _file_lock(SLIDER_FILE):
            _append()
    except TimeoutError:
        return {"ok": False, "message": "滑块短链写入繁忙，请稍后再试"}
    return {"ok": True, "phone": ph, "url": url, "short": f"/api/trae-login/s/{sid}", "ticket": conf.get("verify_ticket","")}

@router.get("/s/{sid}")
async def slider_redirect(sid: str):
    item = _load_sliders().get(sid)
    if not item:
        return {"ok": False, "message": "链接已失效，请重新获取"}
    if time.time() > item.get("exp", 0):
        return {"ok": False, "message": "链接已过期，请重新获取"}
    from fastapi.responses import RedirectResponse
    return RedirectResponse(item["url"])


def _public_base() -> str:
    """动态公网 base（IPv6 前缀会变，实时查询，但缓存 60s 避免频繁起子进程）"""
    _c = _PUBLIC_BASE_CACHE
    if _c["value"] and time.monotonic() - _c["at"] < 60:
        return _c["value"]
    import re
    import subprocess as _sp
    value = "http://127.0.0.1:8770"
    try:
        out = _sp.run(["ip", "-6", "addr", "show", "enp2s0"], capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"inet6 (2409:[0-9a-f:]+)/64", out)
        if m:
            value = f"http://[{m.group(1)}]:8770"
    except Exception:
        pass
    _c["value"] = value
    _c["at"] = time.monotonic()
    return value


@router.get("/status")
async def status():
    box = {"up": False, "pages": []}
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            pages = (await c.get(BOX_CDP)).json()
            box = {"up": True, "pages": [p.get("url", "")[:80] for p in pages if p.get("type") == "page"]}
    except Exception:
        pass
    accts = {"count": 0, "names": []}
    try:
        data = json.loads(TRAE2API_DATA.read_text())
        acc = data.get("accounts", {})
        accts["count"] = len(acc)
        accts["names"] = [str(a.get("label") or a.get("user_id") or k)[:40] for k, a in list(acc.items())[:8]]
    except Exception:
        pass
    return {"box": box, "accounts": accts, "page": TRAE2API_PAGE, "relay_base": _public_base()}


@router.post("/open")
async def open_login():
    ok = await cdp_navigate(TRAE2API_PAGE)
    return {"ok": ok}


@router.post("/reset")
async def reset_login():
    """把沙箱回 trae2api 登录页（重新登录新号）"""
    ok = await cdp_navigate(TRAE2API_PAGE)
    return {"ok": ok}


# ── noVNC 代理（继承 AAM 面板的 IPv6 双栈） ──────────────────────────

@novnc_router.get("/novnc/{p:path}")
async def novnc_file(p: str, request: Request, _auth: None = Depends(require_admin)):
    if not p:
        return Response(status_code=302, headers={"Location": "/novnc/vnc.html"})
    url = f"{NOVNC_UP}/{p}"
    if request.url.query:
        url += "?" + request.url.query
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url)
        content_type = r.headers.get("content-type", "application/octet-stream")
        return Response(content=r.content, media_type=content_type)
    except Exception:
        return Response(status_code=502, content=b"noVNC upstream unavailable")


@novnc_router.websocket("/novnc/websockify")
async def novnc_ws(ws: WebSocket):
    if not require_admin_ws(ws):
        await ws.close(code=4401)
        return
    proto = ws.headers.get("sec-websocket-protocol")
    await ws.accept(subprotocol=proto if proto else None)
    import asyncio
    try:
        async with websockets.connect(
            "ws://127.0.0.1:6080/websockify",
            subprotocols=[proto] if proto else None,
        ) as up:
            async def c2u():
                try:
                    while True:
                        msg = await ws.receive()
                        if msg["type"] == "websocket.receive":
                            if msg.get("bytes") is not None:
                                await up.send(msg["bytes"])
                            else:
                                await up.send(msg.get("text", ""))
                        elif msg["type"] == "websocket.disconnect":
                            break
                except Exception:
                    pass

            async def u2c():
                try:
                    async for msg in up:
                        if isinstance(msg, bytes):
                            await ws.send_bytes(msg)
                        else:
                            await ws.send_text(msg)
                except Exception:
                    pass

            await asyncio.gather(c2u(), u2c())
    except Exception:
        pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass