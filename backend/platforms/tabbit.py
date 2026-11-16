import base64
import hashlib
import hmac
import json
import random
import re
import time
import uuid
from html import escape

import httpx

from ..config import VERSION
from .base import PlatformAdapter

SESSION_ACTION="607f3555ebab54eceed6d8c97b0ef64a9badccbb3b"
ROUTER_STATE='%5B%22%22%2C%7B%22children%22%3A%5B%22newtab%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D'

class TabbitAdapter(PlatformAdapter):
    def __init__(self,platform):
        self.platform=platform; self.base=platform["base_url"].rstrip("/"); self.proxy=platform.get("proxy") or None
        self._sign_keys={}; self._sessions={}; self._models={}
    def _client(self): return httpx.AsyncClient(verify=True,proxy=self.proxy,timeout=60,follow_redirects=True)
    def _uuid(self):
        positions=[2,7,11,14,18,21,25,28]; stamp=f"{int(time.time()):08x}"[-8:]; mapping=dict(zip(positions,stamp)); chars="0123456789abcdef"
        value="".join("1" if i==5 else "4" if i==12 else random.choice("89ab") if i==16 else mapping[i] if i in mapping else random.choice(chars) for i in range(32))
        return f"{value[:8]}-{value[8:12]}-{value[12:16]}-{value[16:20]}-{value[20:]}"
    async def _key(self,refresh=False):
        cached=self._sign_keys.get(self.platform["key"])
        if not refresh and cached and cached[1]>time.monotonic(): return cached[0]
        async with self._client() as c: r=await c.get(self.base+"/chat/sign-key")
        r.raise_for_status(); key=r.text.strip().strip('"')
        if not key: raise RuntimeError("Tabbit returned an empty signing key")
        self._sign_keys[self.platform["key"]]=(key,time.monotonic()+600); return key
    async def _headers(self,account,body,accept,extra=None):
        key=await self._key(); ts=str(int(time.time()*1000)); sig=str(uuid.uuid4())
        nonce=hmac.new(key.encode(),f"{ts}.{sig}.{hashlib.sha256(body.encode()).hexdigest()}".encode(),hashlib.sha256).hexdigest()
        headers={"Cookie":account["credential"],"trace-id":str(uuid.uuid4()),"x-timestamp":ts,"x-signature":sig,"x-nonce":nonce,"unique-uuid":self._uuid(),"x-req-ctx":base64.b64encode(VERSION.encode()).decode(),"Accept":accept,"Origin":self.base,"Referer":self.base+"/","User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36"}
        if body: headers["Content-Type"]="application/json"
        if extra: headers.update(extra)
        return headers
    async def _request(self,account,method,path,body="",accept="application/json",extra=None,retry=True):
        headers=await self._headers(account,body,accept,extra)
        async with self._client() as c: r=await c.request(method,self.base+path,content=body.encode() if body else None,headers=headers)
        if r.status_code==499 and retry:
            await self._key(True); return await self._request(account,method,path,body,accept,extra,False)
        r.raise_for_status(); return r
    async def check(self,account):
        user=(await self._request(account,"GET","/api/v0/user/base-info")).json()
        if not user.get("success"): return {"status":"expired","status_msg":str(user.get("message") or user.get("error") or "Authentication failed"),"user_info":user}
        quota=(await self._request(account,"GET","/api/commerce/quota/v1/usage")).json(); pct=quota.get("usage_percentage","0%")
        if isinstance(pct,str): pct=float(re.sub(r"[^0-9.\-]","",pct) or 0)
        return {"status":"active","status_msg":"","member_level":quota.get("member_level",""),"quota_pct":float(pct),"quota_json":quota,"user_info":user.get("user_info") or {}}
    async def models(self,account):
        cached=self._models.get(account["id"])
        if cached and cached[1]>time.monotonic(): return cached[0]
        response=await self._request(account,"GET","/proxy/v1/model_config/models?a=0&scene=chat")
        names=[item.get("display_name") for item in response.json().get("models",[]) if item.get("display_name")]
        self._models[account["id"]]=(names,time.monotonic()+60); return names
    async def _session_id(self, account):
            cached = self._sessions.get(account["id"])
            if cached and cached[1] > time.monotonic(): return cached[0]
            h = {"accept": "text/x-component", "content-type": "text/plain;charset=UTF-8", "next-action": SESSION_ACTION, "next-router-state-tree": ROUTER_STATE}
            try:
                r = await self._request(account, "POST", "/newtab", '["$undefined",{"page":1,"size":20}]', "text/x-component", h)
                match = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", r.text, re.I)
                if match:
                    sid = match.group(0)
                    self._sessions[account["id"]] = (sid, time.monotonic() + 300)
                    return sid
            except Exception:
                pass
            # 无现存会话：返回 None → _body 传 chat_session_id:null，服务端自动创建
            return None
    @staticmethod
    def _prompt(messages): return "\n\n".join(f"[{m.get('role','user').capitalize()}]\n{m.get('content','')}" for m in messages)
    async def _body(self,account,model,messages):
        session=await self._session_id(account); content=self._prompt(messages)
        return json.dumps({"chat_session_id":session,"message_id":None,"content":content,"selected_model":model,"parallel_group_id":None,"task_name":"chat","agent_mode":False,"metadatas":{"html_content":f"<p>{escape(content)}</p>"},"references":[],"entity":{"key":"d41d8cd98f00b204e9800998ecf8427e","extras":{"type":"tab","url":""}}},ensure_ascii=False,separators=(",",":"))
    async def complete(self,account,model,messages,stream=False,temperature=None):
        body=await self._body(account,model,messages)
        if stream: return self._stream(account,body)
        response=await self._request(account,"POST","/api/v1/chat/completion",body,"text/event-stream")
        return self._parse_sse(response.text)
    async def _stream(self,account,body):
        headers=await self._headers(account,body,"text/event-stream"); headers["Content-Type"]="application/json"
        async with self._client() as c:
            async with c.stream("POST",self.base+"/api/v1/chat/completion",content=body.encode(),headers=headers) as r:
                if r.status_code==499:
                    await self._key(True); raise RuntimeError("Tabbit signing key expired during streaming request; retry the request")
                r.raise_for_status(); event_name=""
                async for line in r.aiter_lines():
                    if line.startswith("event:"): event_name=line[6:].strip()
                    elif line.startswith("data:"):
                        raw=line[5:].strip()
                        try: payload=json.loads(raw)
                        except json.JSONDecodeError: continue
                        yield json.dumps({"type":event_name,"data":payload},ensure_ascii=False)
                        event_name=""
    @staticmethod
    def _parse_sse(text):
        chunks=[]; event_name=""
        for line in text.splitlines():
            if line.startswith("event:"): event_name=line[6:].strip()
            elif line.startswith("data:"):
                try: payload=json.loads(line[5:].strip())
                except json.JSONDecodeError: continue
                if event_name=="message_chunk": chunks.append(payload.get("content",""))
                elif payload.get("type")=="message_chunk": chunks.append((payload.get("data") or {}).get("content",""))
                event_name=""
        return "".join(chunks)
