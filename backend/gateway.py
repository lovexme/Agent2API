import hmac
import json
import logging
import time
import uuid
from collections import deque
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import db
from .api import adapter_for
from .platforms import ADAPTERS

router=APIRouter(prefix="/v1")
logger = logging.getLogger(__name__)
MODEL_CACHE_TTL = 60
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 120
_model_cache = {}
_request_windows = {}

class Completion(BaseModel):
    model:str
    messages:list[dict[str,Any]]
    stream:bool=False
    temperature:float|None=None
    tools:list[dict[str,Any]]|None=None
    tool_choice:str|dict[str,Any]|None=None

class GatewayError(Exception): pass

def authorize(header):
    """校验 Bearer：主密钥（settings.gateway_key）或 tokens 表内有效令牌。返回 token_id（主密钥为 None）。"""
    if not header or not header.startswith("Bearer "):
        raise HTTPException(401,{"error":{"message":"invalid API key","type":"authentication_error"}})
    value = header[7:].strip()
    if not value:
        raise HTTPException(401,{"error":{"message":"invalid API key","type":"authentication_error"}})
    expected = (db.get_setting("gateway_key", "") or "").strip()
    # 拒绝公开默认值/空配置：网关主密钥必须是管理员显式设置的随机值，防止匿名消耗账号额度
    if expected and expected != "aam-local-key" and hmac.compare_digest(value, expected):
        return None
    with db.connect() as conn:
        row = conn.execute("SELECT id,enabled FROM tokens WHERE token=? AND token != 'aam-local-key'",(value,)).fetchone()
    if not row or not row["enabled"]:
        raise HTTPException(401,{"error":{"message":"invalid API key","type":"authentication_error"}})
    return row["id"]

def bump_token(token_id):
    if not token_id:
        return
    with db.connect() as conn:
        conn.execute("UPDATE tokens SET last_used_at=datetime('now','localtime'),request_count=request_count+1 WHERE id=?",(token_id,))

def token_platform_scope(token_id):
    """令牌绑定的平台 key;未绑定(或主密钥 token_id=None)返回 None = 不限制。"""
    if token_id is None:
        return None
    with db.connect() as conn:
        row = conn.execute("SELECT platform_key FROM tokens WHERE id=?",(token_id,)).fetchone()
    return ((row["platform_key"] if row else "") or "").strip() or None

def accounts_for(platform_id):
    with db.connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM accounts WHERE platform_id=? AND enabled=1 AND status='active' ORDER BY COALESCE(last_used_at,'') ASC,id",(platform_id,))]

def _model_cache_key(platform, account):
    return (platform.get("id") or platform.get("key"), account["id"])

async def cached_models(adapter, platform, account):
    now = time.monotonic()
    key = _model_cache_key(platform, account)
    cached = _model_cache.get(key)
    if cached and now < cached[0]:
        return cached[1]
    names = await adapter.models(account)
    _model_cache[key] = (now + MODEL_CACHE_TTL, names)
    for stale_key, (expires, _) in list(_model_cache.items()):
        if expires <= now:
            _model_cache.pop(stale_key, None)
    return names

def _rate_limit(token_id):
    """跨进程限流：SQLite 固定窗口 120 次/60 秒（主密钥用 master 桶）。进程内双实例共享。"""
    bucket = token_id if token_id is not None else "master"
    allowed, _count = db.rate_window_incr("gw", str(bucket), RATE_LIMIT_WINDOW, RATE_LIMIT_MAX)
    return allowed

async def await_models(adapter,account):
    return await adapter.models(account)

async def resolve(model):
    if "/" in model:
        key,name=model.split("/",1)
        with db.connect() as conn: p=conn.execute("SELECT * FROM platforms WHERE key=? AND enabled=1",(key,)).fetchone()
        if not p: return None
        return dict(p),name
    with db.connect() as conn:
        platforms=[dict(r) for r in conn.execute("SELECT DISTINCT p.* FROM platforms p JOIN accounts a ON a.platform_id=p.id WHERE p.enabled=1 AND a.enabled=1 AND a.status='active' ORDER BY p.id")]
    for p in platforms:
        if p["adapter"] not in ADAPTERS: continue
        for account in accounts_for(p["id"]):
            try:
                if model in await cached_models(adapter_for(p),p,account): return p,model
            except Exception: pass
    return None

async def collect_models(scope=None):
    """聚合全部已注册适配器对外声称的模型(与 /v1/models 同口径);scope=平台 key 时只返回该平台。"""
    data=[]
    sql="SELECT DISTINCT p.* FROM platforms p JOIN accounts a ON a.platform_id=p.id WHERE p.enabled=1 AND a.enabled=1 AND a.status='active'"
    args=[]
    if scope:
        sql+=" AND p.key=?"
        args.append(scope)
    with db.connect() as conn:
        platforms=[dict(r) for r in conn.execute(sql+" ORDER BY p.id",args)]
    for p in platforms:
        if p["adapter"] not in ADAPTERS: continue
        for account in accounts_for(p["id"]):
            try: names=await cached_models(adapter_for(p),p,account)
            except Exception: continue
            data.extend({"id":f"{p['key']}/{name}","object":"model","owned_by":p["key"]} for name in names)
    return list({item["id"]:item for item in data}.values())

@router.get("/models")
async def models(authorization:str|None=Header(None)):
    token_id=authorize(authorization)
    return {"object":"list","data":await collect_models(token_platform_scope(token_id))}

def openai_chunk(cid,created,model,delta,finish=None):
    choice={"index":0,"delta":delta,"finish_reason":finish}
    return {"id":cid,"object":"chat.completion.chunk","created":created,"model":model,"choices":[choice]}

@router.post("/chat/completions")
async def completions(body:Completion,request:Request,authorization:str|None=Header(None)):
    token_id=authorize(authorization)
    if not _rate_limit(token_id):
        return JSONResponse(status_code=429, content={"error":{"message":"rate limit exceeded","type":"rate_limit_error"}})
    resolved=await resolve(body.model)
    if not resolved: raise HTTPException(404,{"error":{"message":"model not found","type":"invalid_request_error"}})
    p,display_model=resolved
    if p["adapter"] not in ADAPTERS: raise HTTPException(404,{"error":{"message":"model not found","type":"invalid_request_error"}})
    scope=token_platform_scope(token_id)
    if scope and p["key"]!=scope:
        raise HTTPException(403,{"error":{"message":f"token bound to platform '{scope}',拒绝访问 '{p['key']}'","type":"permission_error"}})
    # 每账号并发上限：默认 1（单账号同一时刻只跑一个请求，防止上游会话冲突）
    try:
        max_inflight = max(1, int(db.get_setting("account_max_inflight", "1") or 1))
    except (TypeError, ValueError):
        max_inflight = 1
    account=db.pick_account(p["id"], max_inflight)
    if not account:
        raise HTTPException(503,{"error":{"message":"no active account or all accounts busy","type":"server_error"}})
    adapter=adapter_for(p)
    # 平台不支持工具调用时留痕，避免「请求成功但永不调工具」的静默误导
    if body.tools and not getattr(adapter, "supports_tools", False):
        logger.info("platform %s does not support tools; ignoring %d tool definitions", p["key"], len(body.tools))
    cid="chatcmpl-"+uuid.uuid4().hex; created=int(time.time()); started=time.monotonic()
    try:
        if body.stream:
            async def generate():
                ok=True; err=""; done=False; has_tool_calls=False
                try:
                    yield "data: "+json.dumps(openai_chunk(cid,created,body.model,{"role":"assistant","content":""}),ensure_ascii=False)+"\n\n"
                    async for raw in await adapter.complete(account,display_model,body.messages,True,body.temperature,tools=body.tools):
                        if raw=="[DONE]": continue
                        try: event=json.loads(raw)
                        except json.JSONDecodeError: continue
                        typ=event.get("type"); value=event.get("data") or {}
                        if typ=="message_chunk":
                            text=value.get("content","")
                            if text: yield "data: "+json.dumps(openai_chunk(cid,created,body.model,{"content":text}),ensure_ascii=False)+"\n\n"
                        elif typ=="tool_call_chunk":
                            # 工具调用增量: value={index,id,type,function:{name,arguments}}
                            fn=value.get("function") if isinstance(value.get("function"),dict) else {}
                            delta_tc={"index":value.get("index",0),"type":value.get("type") or "function",
                                      "function":{"name":fn.get("name") or "","arguments":fn.get("arguments") or ""}}
                            if value.get("id"): delta_tc["id"]=value["id"]
                            yield "data: "+json.dumps(openai_chunk(cid,created,body.model,{"tool_calls":[delta_tc]}),ensure_ascii=False)+"\n\n"
                            has_tool_calls=True
                        elif typ=="error":
                            # 上游错误不透传：客户端只见固定文案，日志只记错误类型
                            ok=False; err="UpstreamEventError"
                            logger.warning("Streaming upstream event error: code=%s", value.get("code"))
                            yield "data: "+json.dumps({"error":{"message":"upstream_error","type":"upstream_error"}},ensure_ascii=False)+"\n\n"
                            break
                    if ok:
                        yield "data: "+json.dumps(openai_chunk(cid,created,body.model,{},"tool_calls" if has_tool_calls else "stop"),ensure_ascii=False)+"\n\n"
                        done=True
                        yield "data: [DONE]\n\n"
                except Exception as exc:
                    logger.warning("Streaming upstream error: %s", type(exc).__name__, exc_info=True)
                    ok=False; err=type(exc).__name__
                    yield "data: "+json.dumps({"error":{"message":"upstream_error","type":"upstream_error"}},ensure_ascii=False)+"\n\n"
                finally:
                    # 助手内部代调（X-AAM-Source: assistant）不写 request_log，避免自污染报表
                    if request.headers.get("x-aam-source", "") != "assistant":
                        db.log_request(account["id"],p["key"],body.model,ok and done,int((time.monotonic()-started)*1000),err)
                    db.bump_account_usage(account["id"])
                    db.release_account(account["id"])
                    bump_token(token_id)
            return StreamingResponse(generate(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
        text=await adapter.complete(account,display_model,body.messages,False,body.temperature,tools=body.tools)
        if isinstance(text, dict):
            # 带 tools 的适配器返回 {role, content, tool_calls}
            msg = {"role": text.get("role") or "assistant", "content": text.get("content") or ""}
            tcs = text.get("tool_calls")
            if tcs:
                msg["tool_calls"] = tcs
            finish = "tool_calls" if tcs else "stop"
        else:
            msg = {"role": "assistant", "content": text}
            finish = "stop"
        result={"id":cid,"object":"chat.completion","created":created,"model":body.model,"choices":[{"index":0,"message":msg,"finish_reason":finish}],"usage":{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}}
        if request.headers.get("x-aam-source", "") != "assistant":
            db.log_request(account["id"],p["key"],body.model,True,int((time.monotonic()-started)*1000))
        db.bump_account_usage(account["id"])
        bump_token(token_id)
        return result
    except Exception as exc:
        logger.warning("Upstream completion error: %s", type(exc).__name__, exc_info=True)
        db.log_request(account["id"],p["key"],body.model,False,int((time.monotonic()-started)*1000),type(exc).__name__)
        raise HTTPException(502,{"error":{"message":"upstream_error","type":"upstream_error"}})
    finally:
        # 非流式路径归还账号在飞名额（流式路径在 generate() finally 归还）
        if not body.stream:
            db.release_account(account["id"])
