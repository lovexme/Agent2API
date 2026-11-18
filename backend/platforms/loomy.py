"""Loomy (讯飞) adapter — 上游本身就是 OpenAI 兼容模型网关。

协议参考（实测逆向）:
- 网关: https://loomyad.xunfei.cn/api/v1  (OpenAI 兼容)
- 认证: useSessionAuth — Bearer <session> + token 头双发, 无 API key
- 必需头: traceparent: 00-<32hex>-<16hex>-01 (缺了上游挂起超时), loomy-version
- 积分: GET /points/records?record_type=all&pageNo=1&pageSize=1
        → data.{balance(永久), dailyBalance(每日赠送), availableBalance}
- 失效: HTTP 200 但 code=100002 "登录已失效" (不能只看 401)
- session 来源: 客户端 userData/auth-session.json 明文; 有效期 14 天, 无 refresh
"""
import json
import secrets
import uuid

import httpx

from .base import PlatformAdapter

GATEWAY_BASE = "https://loomyad.xunfei.cn/api/v1"
LOOMY_VERSION = "0.9.39"


class LoomyAdapter(PlatformAdapter):
    def __init__(self, platform):
        self.platform = platform
        self.base = (platform.get("base_url") or GATEWAY_BASE).rstrip("/")
        self.proxy = platform.get("proxy") or None

    def _client(self):
        return httpx.AsyncClient(verify=True, proxy=self.proxy, timeout=90, follow_redirects=True)

    def _headers(self, account, json_body=True):
        session = account["credential"].strip()
        h = {
            "Accept": "application/json",
            "Authorization": f"Bearer {session}",
            "token": session,
            "traceparent": f"00-{uuid.uuid4().hex}-{uuid.uuid4().hex[:16]}-01",
            "loomy-version": LOOMY_VERSION,
            "User-Agent": "Loomy/Desktop/Electron",
        }
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    async def check(self, account):
        """测活 + 积分余额。"""
        try:
            async with self._client() as c:
                r = await c.get(self.base + "/points/records?record_type=all&pageNo=1&pageSize=1",
                                headers=self._headers(account, json_body=False))
            if r.status_code == 200:
                payload = r.json()
            elif r.status_code in (401, 403):
                return self._expired("session 失效(HTTP %s),请重新登录" % r.status_code)
            else:
                return {"status": "error", "status_msg": "Loomy HTTP %s" % r.status_code,
                        "member_level": "", "quota_pct": None, "quota_json": {}, "user_info": {}}
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                return self._expired("session 失效（HTTP %s），请重新登录" % e.response.status_code)
            raise
        except httpx.TransportError as e:
            return {"status": "error", "status_msg": "网络错误: %s" % e.__class__.__name__,
                    "member_level": "", "quota_pct": None, "quota_json": {}, "user_info": {}}

        # 业务码失效: HTTP 200 但 code=100002
        code = payload.get("code")
        desc = str(payload.get("desc") or "")
        if code == 100002 or "登录已失效" in desc:
            return self._expired("登录已失效，请重新登录")

        data = payload.get("data") or {}
        balance = data.get("balance")
        daily = data.get("dailyBalance")
        available = data.get("availableBalance")
        return {
            "status": "active",
            "status_msg": "",
            "member_level": "loomy",
            "quota_pct": None,
            "quota_json": {
                "balance": balance if balance is not None else 0,
                "daily_balance": daily if daily is not None else 0,
                "available_balance": available if available is not None else (balance or 0),
                "loomy": True,
            },
            "user_info": {"secret_mobile": "", "id": ""},
        }

    @staticmethod
    def _expired(msg):
        return {"status": "expired", "status_msg": msg, "member_level": "",
                "quota_pct": None, "quota_json": {}, "user_info": {}}

    async def models(self, account):
        async with self._client() as c:
            r = await c.get(self.base + "/models", headers=self._headers(account, json_body=False))
        r.raise_for_status()
        payload = r.json()
        items = payload.get("data") if isinstance(payload, dict) else payload
        if isinstance(items, dict):
            items = items.get("data") or []
        return [m.get("id") for m in items if isinstance(m, dict) and m.get("id")]

    async def complete(self, account, model, messages, stream=False, temperature=None, tools=None):
        body = {"model": model, "messages": messages, "stream": bool(stream)}
        if temperature is not None:
            body["temperature"] = temperature
        if stream:
            return self._stream(account, body)
        async with self._client() as c:
            r = await c.post(self.base + "/chat/completions", headers=self._headers(account), json=body)
        if r.status_code == 401 or r.status_code == 403:
            raise RuntimeError("Loomy session 失效，请重新登录")
        r.raise_for_status()
        payload = r.json()
        try:
            return payload["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("Loomy 上游响应异常: %s" % json.dumps(payload, ensure_ascii=False)[:200])

    async def _stream(self, account, body):
        """上游 OpenAI SSE → AAM {type, data} 事件流。"""
        async with self._client() as c:
            async with c.stream("POST", self.base + "/chat/completions",
                                headers=self._headers(account), json=body) as r:
                if r.status_code in (401, 403):
                    yield json.dumps({"type": "error", "data": {"message": "Loomy session 失效，请重新登录"}}, ensure_ascii=False)
                    return
                if r.status_code != 200:
                    text = ""
                    try:
                        text = (await r.aread()).decode("utf-8", "replace")
                    except Exception:
                        pass
                    yield json.dumps({"type": "error", "data": {"message": "Loomy HTTP %s: %s" % (r.status_code, text[:200])}}, ensure_ascii=False)
                    return
                async for line in r.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(chunk, dict) and chunk.get("error"):
                        yield json.dumps({"type": "error", "data": {"message": str(chunk["error"].get("message") or chunk["error"])}}, ensure_ascii=False)
                        continue
                    try:
                        delta = chunk["choices"][0]["delta"]
                        content = delta.get("content") or ""
                    except (KeyError, IndexError, TypeError):
                        content = ""
                    if content:
                        yield json.dumps({"type": "message_chunk", "data": {"content": content}}, ensure_ascii=False)