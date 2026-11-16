"""通用 OpenAI 兼容 adapter — 对接任何 OpenAI 协议上游（含社区网关项目）。

适用：Trae2api / WorkBuddy2api / new-api / one-api 等已把各平台转成 OpenAI 的网关，
或任何自建 OpenAI 兼容服务。

credential = 上游 API Key（Bearer）。
platform.base_url 例: http://127.0.0.1:8770/v1
"""
import json

import httpx

from .base import PlatformAdapter


class OpenAICompatAdapter(PlatformAdapter):
    def __init__(self, platform):
        self.platform = platform
        self.base = (platform.get("base_url") or "").rstrip("/")
        self.proxy = platform.get("proxy") or None

    def _client(self):
        return httpx.AsyncClient(verify=True, proxy=self.proxy, timeout=120, follow_redirects=True)

    def _headers(self, account, stream=False):
        key = (account.get("credential") or "").strip()
        h = {"Content-Type": "application/json", "Accept": "text/event-stream" if stream else "application/json"}
        if key and key.lower() not in ("none", "-"):
            h["Authorization"] = f"Bearer {key}"
        return h

    async def check(self, account):
        """用 /models 探活；顺带尝试常见配额端点（存在则取，不存在忽略）。"""
        try:
            async with self._client() as c:
                r = await c.get(self.base + "/models", headers=self._headers(account), timeout=30)
        except httpx.TransportError as e:
            return {"status": "error", "status_msg": "连接失败: %s" % e.__class__.__name__,
                    "member_level": "", "quota_pct": None, "quota_json": {}, "user_info": {}}
        if r.status_code in (401, 403):
            return {"status": "expired", "status_msg": "API Key 无效（HTTP %s）" % r.status_code,
                    "member_level": "", "quota_pct": None, "quota_json": {}, "user_info": {}}
        if r.status_code != 200:
            return {"status": "error", "status_msg": "HTTP %s" % r.status_code,
                    "member_level": "", "quota_pct": None, "quota_json": {}, "user_info": {}}
        count = 0
        try:
            payload = r.json()
            data = payload.get("data") if isinstance(payload, dict) else payload
            count = len(data or [])
        except Exception:
            pass
        quota = {"models": count, "openai_compat": True}
        # 尝试常见配额/余额端点（不强制）
        for path in ("/dashboard/billing/credit_grants", "/credits", "/quota", "/api/credits"):
            try:
                async with self._client() as c:
                    qr = await c.get(self.base + path, headers=self._headers(account), timeout=8)
                if qr.status_code == 200:
                    quota["extra"] = qr.json()
                    break
            except Exception:
                continue
        return {"status": "active", "status_msg": "", "member_level": "openai",
                "quota_pct": None, "quota_json": quota, "user_info": {}}

    async def models(self, account):
        async with self._client() as c:
            r = await c.get(self.base + "/models", headers=self._headers(account), timeout=60)
        r.raise_for_status()
        payload = r.json()
        data = payload.get("data") if isinstance(payload, dict) else payload
        return [m.get("id") for m in (data or []) if isinstance(m, dict) and m.get("id")]

    async def complete(self, account, model, messages, stream=False, temperature=None):
        body = {"model": model, "messages": messages, "stream": bool(stream)}
        if temperature is not None:
            body["temperature"] = temperature
        if stream:
            return self._stream(account, body)
        async with self._client() as c:
            r = await c.post(self.base + "/chat/completions", headers=self._headers(account), json=body, timeout=180)
        if r.status_code in (401, 403):
            raise RuntimeError("上游 API Key 无效（HTTP %s）" % r.status_code)
        if r.status_code != 200:
            raise RuntimeError("上游 HTTP %s: %s" % (r.status_code, r.text[:200]))
        payload = r.json()
        try:
            return payload["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("上游响应异常: %s" % json.dumps(payload, ensure_ascii=False)[:200])

    async def _stream(self, account, body):
        async with self._client() as c:
            async with c.stream("POST", self.base + "/chat/completions",
                                headers=self._headers(account, stream=True), json=body) as r:
                if r.status_code != 200:
                    text = ""
                    try:
                        text = (await r.aread()).decode("utf-8", "replace")
                    except Exception:
                        pass
                    yield json.dumps({"type": "error", "data": {"message": "上游 HTTP %s: %s" % (r.status_code, text[:200])}}, ensure_ascii=False)
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
                        err = chunk["error"]
                        msg = err.get("message") if isinstance(err, dict) else str(err)
                        yield json.dumps({"type": "error", "data": {"message": msg}}, ensure_ascii=False)
                        continue
                    try:
                        delta = chunk["choices"][0].get("delta") or {}
                        content = delta.get("content") or ""
                    except (KeyError, IndexError, TypeError):
                        content = ""
                    if content:
                        yield json.dumps({"type": "message_chunk", "data": {"content": content}}, ensure_ascii=False)