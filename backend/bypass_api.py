"""auto_bypass 面板集成 — LLM 拒答自动绕过工具路由。

复用 auto_bypass 工具的 safe_chat（直调→分步模板→多轮诱导→换模型）。
auto_bypass 模块目录由环境变量 AAM_AUTO_BYPASS_DIR 指定（默认 ./tools/auto_bypass.py），
缺失时返回可读错误，不硬编码部署机器路径。
"""
import os
import sys
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import db
from .auth import require_admin

_BYPASS_DIR = os.environ.get("AAM_AUTO_BYPASS_DIR", "tools")
sys.path.insert(0, os.path.abspath(_BYPASS_DIR))
try:
    from auto_bypass import safe_chat  # noqa: E402
except ImportError as exc:  # auto_bypass.py 缺失时给出可读错误
    def safe_chat(*_a, **_k):
        raise HTTPException(500, f"auto_bypass 模块不可用: {exc}")

router = APIRouter(prefix="/api/tools", tags=["tools"], dependencies=[Depends(require_admin)])


def _gateway_key():
    key = (db.get_setting("gateway_key", "") or "").strip()
    if not key or key == "aam-local-key":
        raise HTTPException(400, "网关主密钥未配置，请先在设置页设置 gateway_key")
    return key


def _gateway_base():
    return os.environ.get("AAM_INTERNAL_BASE", "http://127.0.0.1:8710/v1")


class BypassInput(BaseModel):
    model: str
    prompt: str
    fallback: str = ""          # 逗号分隔的兜底模型，可空
    max_tokens: int = 3000
    timeout: int = 180


@router.post("/refusal-bypass")
def refusal_bypass(body: BypassInput):
    """调 auto_bypass.safe_chat，经自家网关，返回 content/strategy/attempts。"""
    if not body.model.strip():
        raise HTTPException(400, "请先选择模型")
    if not body.prompt.strip():
        raise HTTPException(400, "任务内容不能为空")
    allowed, _ = db.rate_window_incr("assistant", "bypass", 60, 20)
    if not allowed:
        raise HTTPException(429, "调用过于频繁，请稍后再试")

    fallback = [m.strip() for m in body.fallback.split(",") if m.strip()] or None
    started = time.monotonic()
    try:
        r = safe_chat(
            body.model.strip(),
            body.prompt.strip(),
            token=_gateway_key(),
            base=_gateway_base() + "/chat/completions",
            fallback=fallback,
            max_tokens=max(1000, min(body.max_tokens, 8000)),
            timeout=max(30, min(body.timeout, 300)),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"auto_bypass 调用失败：{exc}")

    r["_ms"] = int((time.monotonic() - started) * 1000)
    r["ok"] = True
    return r