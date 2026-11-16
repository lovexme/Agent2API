import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import db
from .api import adapter_for
from .platforms import ADAPTERS

router=APIRouter(prefix="/v1")

class Completion(BaseModel):
    model:str
    messages:list[dict[str,Any]]
    stream:bool=False
    temperature:float|None=None

class GatewayError(Exception): pass

def authorize(header):
    """校验 Bearer：主密钥（settings.gateway_key）或 tokens 表内有效令牌。返回 token_id（主密钥为 None）。"""
    if not header or not header.startswith("Bearer "):
        raise HTTPException(401,{"error":{"message":"invalid API key","type":"authentication_error"}})
    value = header[7:].strip()
    expected = db.get_setting("gateway_key","aam-local-key")
    if value == expected:
        return None
    with db.connect() as conn:
        row = conn.execute("SELECT id,enabled FROM tokens WHERE token=?",(value,)).fetchone()
    if not row or not row["enabled"]:
        raise HTTPException(401,{"error":{"message":"invalid API key","type":"authentication_error"}})
    return row["id"]

def bump_token(token_id):
    if not token_id:
        return
    with db.connect() as conn:
        conn.execute("UPDATE tokens SET last_used_at=datetime('now','localtime'),request_count=request_count+1 WHERE id=?",(token_id,))

def resolve_model(model):
    if "/" in model:
        key,name=model.split("/",1)
        with db.connect() as conn:
            platform=conn.execute("SELECT * FROM platforms WHERE key=? AND enabled=1",(key,)).fetchone()
        return (dict(platform),name) if platform else None
    with db.connect() as conn:
        platforms=conn.execute("SELECT DISTINCT p.* FROM platforms p JOIN accounts a ON a.platform_id=p.id WHERE p.enabled=1 AND a.enabled=1 AND a.status='active' ORDER BY p.id").fetchall()
    for platform in platforms:
        if platform["adapter"] != "tabbit": continue
        accounts=accounts_for(platform["id"])
        for account in accounts:
            try:
                if model in await_models(adapter_for(dict(platform)),account):
                    return dict(platform),model
            except Exception: continue
    return None

def accounts_for(platform_id):
    with db.connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM accounts WHERE platform_id=? AND enabled=1 AND status='active' ORDER BY COALESCE(last_used_at,'') ASC,id",(platform_id,))]

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
        if p["adapter"] != "tabbit": continue
        for account in accounts_for(p["id"]):
            try:
                if model in await adapter_for(p).models(account): return p,model
            except Exception: pass
    return None

@router.get("/models")
async def models(authorization:str|None=Header(None)):
    authorize(authorization)
    data=[]
    with db.connect() as conn:
        platforms=[dict(r) for r in conn.execute("SELECT DISTINCT p.* FROM platforms p JOIN accounts a ON a.platform_id=p.id WHERE p.enabled=1 AND a.enabled=1 AND a.status='active' ORDER BY p.id")]
    for p in platforms:
        if p["adapter"] not in ADAPTERS: continue
        for account in accounts_for(p["id"]):
            try: names=await adapter_for(p).models(account)
            except Exception: continue
            data.extend({"id":f"{p['key']}/{name}","object":"model","owned_by":p["key"]} for name in names)
    unique={item["id"]:item for item in data}
    return {"object":"list","data":list(unique.values())}

def openai_chunk(cid,created,model,delta,finish=None):
    choice={"index":0,"delta":delta,"finish_reason":finish}
    return {"id":cid,"object":"chat.completion.chunk","created":created,"model":model,"choices":[choice]}

@router.post("/chat/completions")
async def completions(body:Completion,request:Request,authorization:str|None=Header(None)):
    token_id=authorize(authorization)
    resolved=await resolve(body.model)
    if not resolved: raise HTTPException(404,{"error":{"message":"model not found","type":"invalid_request_error"}})
    p,display_model=resolved
    if p["adapter"] not in ADAPTERS: raise HTTPException(404,{"error":{"message":"model not found","type":"invalid_request_error"}})
    account=db.pick_account(p["id"])
    if not account: raise HTTPException(503,{"error":{"message":"no active account","type":"server_error"}})
    adapter=adapter_for(p)
    cid="chatcmpl-"+uuid.uuid4().hex; created=int(time.time()); started=time.monotonic()
    try:
        if body.stream:
            async def generate():
                ok=True; err=""; done=False
                try:
                    yield "data: "+json.dumps(openai_chunk(cid,created,body.model,{"role":"assistant","content":""}),ensure_ascii=False)+"\n\n"
                    async for raw in await adapter.complete(account,display_model,body.messages,True,body.temperature):
                        if raw=="[DONE]": continue
                        try: event=json.loads(raw)
                        except json.JSONDecodeError: continue
                        typ=event.get("type"); value=event.get("data") or {}
                        if typ=="message_chunk":
                            text=value.get("content","")
                            if text: yield "data: "+json.dumps(openai_chunk(cid,created,body.model,{"content":text}),ensure_ascii=False)+"\n\n"
                        elif typ=="error":
                            ok=False; err=str(value.get("message") or "Tabbit error")
                            yield "data: "+json.dumps({"error":{"message":err,"code":value.get("code")}},ensure_ascii=False)+"\n\n"
                    yield "data: "+json.dumps(openai_chunk(cid,created,body.model,{},"stop"),ensure_ascii=False)+"\n\n"
                    done=True
                    yield "data: [DONE]\n\n"
                except Exception as exc:
                    ok=False; err=str(exc)
                    yield "data: "+json.dumps({"error":{"message":err,"type":"upstream_error"}},ensure_ascii=False)+"\n\n"
                finally:
                    db.log_request(account["id"],p["key"],body.model,ok and done,int((time.monotonic()-started)*1000),err)
                    db.bump_account_usage(account["id"])
                    bump_token(token_id)
            return StreamingResponse(generate(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
        text=await adapter.complete(account,display_model,body.messages,False,body.temperature)
        result={"id":cid,"object":"chat.completion","created":created,"model":body.model,"choices":[{"index":0,"message":{"role":"assistant","content":text},"finish_reason":"stop"}],"usage":{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}}
        db.log_request(account["id"],p["key"],body.model,True,int((time.monotonic()-started)*1000))
        db.bump_account_usage(account["id"])
        bump_token(token_id)
        return result
    except Exception as exc:
        db.log_request(account["id"],p["key"],body.model,False,int((time.monotonic()-started)*1000),str(exc))
        raise HTTPException(502,{"error":{"message":str(exc),"type":"upstream_error"}})
