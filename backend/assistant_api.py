"""AI 助手（轻量版）。

设计要点：
- 会话/消息落 sqlite（sessions + messages 表）
- 对话走后端薄代理：前端只带 admin cookie，服务端持 gateway_key 调自家 /v1/chat/completions
- 独立限流桶 bucket="assistant"（不与主密钥 master 桶共享）
- 带 X-AAM-Source: assistant 头，网关侧跳过 request_log，避免自污染报表
"""
import asyncio
import json
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from . import db
from .auth import require_admin

router = APIRouter(prefix="/api/assistant", dependencies=[Depends(require_admin)])

# 独立限流：助手 60 次/60s、模型测试 20 次/60s
ASSISTANT_LIMIT = (60, 60)
TEST_LIMIT = (20, 60)


def _gateway_key():
    key = (db.get_setting("gateway_key", "") or "").strip()
    if not key or key == "aam-local-key":
        raise HTTPException(400, "网关主密钥未配置，请先在设置页设置 gateway_key")
    return key


def _gateway_base():
    return "http://127.0.0.1:8710/v1"


# ---------------- 会话 CRUD ----------------


class SessionInput(BaseModel):
    title: str = "未命名对话"
    model: str = ""


@router.get("/sessions")
def list_sessions():
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM assistant_messages m WHERE m.session_id=s.id) msg_count "
            "FROM assistant_sessions s ORDER BY s.updated_at DESC").fetchall()
    return {"ok": True, "items": [dict(r) for r in rows]}


@router.post("/sessions")
def create_session(body: SessionInput):
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO assistant_sessions(title,model) VALUES(?,?)",
            (body.title.strip() or "未命名对话", body.model.strip()))
        row = conn.execute("SELECT * FROM assistant_sessions WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"ok": True, "item": dict(row)}


@router.put("/sessions/{session_id}")
def rename_session(session_id: int, body: dict):
    allowed = {k: v for k, v in body.items() if k in {"title", "model"} and v is not None}
    allowed["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with db.connect() as conn:
        conn.execute("UPDATE assistant_sessions SET " + ",".join(f"{k}=?" for k in allowed) + " WHERE id=?",
                     (*allowed.values(), session_id))
        row = conn.execute("SELECT * FROM assistant_sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        raise HTTPException(404, "session not found")
    return {"ok": True, "item": dict(row)}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int):
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM assistant_sessions WHERE id=?", (session_id,))
    if not cur.rowcount:
        raise HTTPException(404, "session not found")
    return {"ok": True}


@router.post("/sessions/{session_id}/fork")
def fork_session(session_id: int):
    """从指定会话复制一份新会话（保留已落库消息）。"""
    with db.connect() as conn:
        src = conn.execute("SELECT * FROM assistant_sessions WHERE id=?", (session_id,)).fetchone()
        if not src:
            raise HTTPException(404, "session not found")
        cur = conn.execute(
            "INSERT INTO assistant_sessions(title,model) VALUES(?,?)",
            (src["title"] + "（分叉）", src["model"] or ""))
        new_id = cur.lastrowid
        # 深拷贝消息（不含 tool_json 里的敏感内容，只拷贝 role/content）
        msg_rows = conn.execute(
            "SELECT role,content FROM assistant_messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
        conn.executemany(
            "INSERT INTO assistant_messages(session_id,role,content) VALUES(?,?,?)",
            [(new_id, r["role"], r["content"]) for r in msg_rows])
        row = conn.execute("SELECT * FROM assistant_sessions WHERE id=?", (new_id,)).fetchone()
    return {"ok": True, "item": dict(row)}


# ---------------- 消息 ----------------


@router.get("/sessions/{session_id}/messages")
def list_messages(session_id: int):
    with db.connect() as conn:
        sess = conn.execute("SELECT id FROM assistant_sessions WHERE id=?", (session_id,)).fetchone()
        if not sess:
            raise HTTPException(404, "session not found")
        rows = conn.execute(
            "SELECT * FROM assistant_messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
    return {"ok": True, "items": [dict(r, tool_json=db.parse_json(r["tool_json"])) for r in rows]}


@router.delete("/sessions/{session_id}/messages/{message_id}")
def delete_message(session_id: int, message_id: int):
    with db.connect() as conn:
        cur = conn.execute(
            "DELETE FROM assistant_messages WHERE id=? AND session_id=?", (message_id, session_id))
    if not cur.rowcount:
        raise HTTPException(404, "message not found")
    return {"ok": True}


# ---------------- 对话薄代理 ----------------


class ChatInput(BaseModel):
    session_id: int | None = None
    model: str
    messages: list[dict]
    stream: bool = False


def _rate(bucket: str, limit, window):
    allowed, _count = db.rate_window_incr("assistant", bucket, window, limit)
    if not allowed:
        raise HTTPException(429, "助手调用过于频繁，请稍后再试")
    return allowed


@router.post("/chat")
async def assistant_chat(body: ChatInput):
    """后端薄代理：服务端持 gateway_key 调自家 /v1/chat/completions。
    前端只带 admin cookie，主密钥不落地浏览器；独立限流桶；skip request_log。"""
    _rate("chat", ASSISTANT_LIMIT[0], ASSISTANT_LIMIT[1])
    key = _gateway_key()
    if not body.model.strip():
        raise HTTPException(400, "请先选择模型")
    if not body.messages:
        raise HTTPException(400, "消息不能为空")

    # 1) 落库 user 消息（有会话则记录）
    if body.session_id:
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO assistant_messages(session_id,role,content) VALUES(?,?,?)",
                (body.session_id, "user", body.messages[-1].get("content", "") or "[图片]"))
            conn.execute("UPDATE assistant_sessions SET updated_at=? WHERE id=?",
                         (time.strftime("%Y-%m-%d %H:%M:%S"), body.session_id))

    # 2) 调自家网关（带内部标记，跳过 request_log）
    payload = {"model": body.model, "messages": body.messages, "stream": body.stream}
    headers = {"Authorization": f"Bearer {key}", "X-AAM-Source": "assistant", "Content-Type": "application/json"}
    url = _gateway_base() + "/chat/completions"
    started = time.monotonic()

    async def _non_stream():
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                r = await client.post(url, headers=headers, json=payload)
            if r.status_code >= 400:
                try:
                    err = r.json()
                except ValueError:
                    err = {"error": {"message": r.text[:200]}}
                msg = ((err.get("error") or {}).get("message")) or err.get("message") or f"HTTP {r.status_code}"
                raise HTTPException(r.status_code, msg)
            result = r.json()
            content = ((result.get("choices") or [{}])[0].get("message") or {}).get("content", "")
            ms = int((time.monotonic() - started) * 1000)
            result["_ms"] = ms
            # 3) 落库 assistant 回复
            if body.session_id:
                with db.connect() as conn:
                    conn.execute(
                        "INSERT INTO assistant_messages(session_id,role,content) VALUES(?,?,?)",
                        (body.session_id, "assistant", content))
                    conn.execute("UPDATE assistant_sessions SET updated_at=? WHERE id=?",
                                 (time.strftime("%Y-%m-%d %H:%M:%S"), body.session_id))
            return result
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"网关调用失败：{exc}")

    if not body.stream:
        return await _non_stream()

    # 流式透传（SSE），结束时落库全文
    async def _stream_body():
        collected = []
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as r:
                    if r.status_code >= 400:
                        text = (await r.aread()).decode("utf-8", "ignore")[:200]
                        yield f"data: {json.dumps({'error': {'message': f'HTTP {r.status_code}: {text}', 'type': 'upstream_error'}}, ensure_ascii=False)}\n\n"
                        return
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        yield line + "\n"
                        data = line[5:].strip()
                        if data and data != "[DONE]":
                            try:
                                chunk = json.loads(data)
                                delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                                content = delta.get("content") or ""
                                if content:
                                    collected.append(content)
                            except json.JSONDecodeError:
                                pass
        finally:
            if body.session_id and collected:
                with db.connect() as conn:
                    conn.execute(
                        "INSERT INTO assistant_messages(session_id,role,content) VALUES(?,?,?)",
                        (body.session_id, "assistant", "".join(collected)))
                    conn.execute("UPDATE assistant_sessions SET updated_at=? WHERE id=?",
                                 (time.strftime("%Y-%m-%d %H:%M:%S"), body.session_id))

    from fastapi.responses import StreamingResponse
    return StreamingResponse(_stream_body(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------- 模型下拉 / 测试 ----------------


@router.get("/models")
async def assistant_models():
    """代取可用模型列表（/v1/models），供模型下拉与空态判定。"""
    key = _gateway_key()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(_gateway_base() + "/models", headers={"Authorization": f"Bearer {key}"})
        if r.status_code >= 400:
            return {"ok": True, "items": [], "error": f"HTTP {r.status_code}"}
        data = (r.json() or {}).get("data") or []
        return {"ok": True, "items": [m["id"] for m in data]}
    except httpx.HTTPError as exc:
        return {"ok": True, "items": [], "error": str(exc)}


class ModelTestInput(BaseModel):
    model: str


@router.post("/models/test")
async def assistant_models_test(body: ModelTestInput):
    """模型连通性测试：经网关发 max_tokens=1 真实请求，回报状态与耗时（独立限流桶，skip 日志）。"""
    _rate("test", TEST_LIMIT[0], TEST_LIMIT[1])
    key = _gateway_key()
    if not body.model.strip():
        raise HTTPException(400, "请选择模型")
    payload = {"model": body.model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
    headers = {"Authorization": f"Bearer {key}", "X-AAM-Source": "assistant", "Content-Type": "application/json"}
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(_gateway_base() + "/chat/completions", headers=headers, json=payload)
        ms = int((time.monotonic() - started) * 1000)
        if r.status_code >= 400:
            try:
                err = r.json()
            except ValueError:
                err = {}
            msg = ((err.get("error") or {}).get("message")) or f"HTTP {r.status_code}"
            return {"ok": True, "reachable": False, "status": msg[:120], "ms": ms}
        ok = bool(r.json().get("choices"))
        return {"ok": True, "reachable": ok, "status": "连通" if ok else "无 choices", "ms": ms}
    except httpx.HTTPError as exc:
        ms = int((time.monotonic() - started) * 1000)
        return {"ok": True, "reachable": False, "status": str(exc)[:120], "ms": ms}