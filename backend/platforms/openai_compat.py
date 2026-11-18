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
        ids = []
        try:
            payload = r.json()
            data = payload.get("data") if isinstance(payload, dict) else payload
            data = data or []
            ids = [m.get("id") for m in data if isinstance(m, dict) and m.get("id")]
            count = len(ids)  # 只计有效模型 id:否则 count>0 却 chat_probe=skip:no-models 自相矛盾
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
        # 真探活:仅 /models 返回 200 无法发现"模型列表能拉、对话全挂"(如上游 relay 无凭据)。
        # 发一条 max_tokens=1 的最小 completion;失败即判"上游对话不可用"。
        probe = self._pick_probe_model(ids)
        if not probe:
            # 上游 /models 返回空列表(如 relay 冷缓存):无法探活,不静默判绿,在 status_msg 里说明。
            quota["chat_probe"] = "skip:no-models"
        else:
            try:
                async with self._client() as c:
                    cr = await c.post(self.base + "/chat/completions", headers=self._headers(account),
                                      json={"model": probe, "max_tokens": 1, "stream": False,
                                            "messages": [{"role": "user", "content": "ping"}]},
                                      timeout=60)
            except Exception as e:
                quota["chat_probe"] = "conn:%s" % e.__class__.__name__
                return {"status": "error", "status_msg": "上游对话不可用(连接失败:%s)" % e.__class__.__name__,
                        "member_level": "openai", "quota_pct": None, "quota_json": quota, "user_info": {}}
            if cr.status_code >= 400:
                detail = self._err_text(cr)
                quota["chat_probe"] = "HTTP %s %s" % (cr.status_code, detail)
                return {"status": "error",
                        "status_msg": "上游对话不可用(HTTP %s%s)" % (cr.status_code, (" " + detail) if detail else ""),
                        "member_level": "openai", "quota_pct": None, "quota_json": quota, "user_info": {}}
            if not self._has_choices(cr):
                quota["chat_probe"] = "empty-choices:%s" % probe
                return {"status": "error", "status_msg": "上游对话返回空响应(无 choices)",
                        "member_level": "openai", "quota_pct": None, "quota_json": quota, "user_info": {}}
            quota["chat_probe"] = "ok:%s" % probe
        return {"status": "active", "status_msg": "" if probe else "模型清单为空,未做对话探活",
                "member_level": "openai", "quota_pct": None, "quota_json": quota, "user_info": {}}

    @staticmethod
    def _pick_probe_model(ids):
        """挑最便宜可用的探活模型:优先 flash/mini/lite/small 等小模型。"""
        if not ids:
            return ""
        for kw in ("flash", "mini", "lite", "small", "nano", "haiku"):
            for i in ids:
                if kw in i.lower():
                    return i
        return ids[0]

    @staticmethod
    def _err_text(resp):
        """从上游错误响应里提炼一句话(截断),用于 status_msg。"""
        try:
            t = resp.text or ""
        except Exception:
            return ""
        try:
            j = resp.json()
            if isinstance(j, dict):
                e = j.get("error")
                if isinstance(e, dict):
                    t = e.get("message") or e.get("type") or t
                elif isinstance(e, str):
                    t = e
                elif j.get("detail"):
                    t = j["detail"] if isinstance(j["detail"], str) else json.dumps(j["detail"], ensure_ascii=False)
        except Exception:
            pass
        return " ".join(str(t).split())[:160]

    @staticmethod
    def _has_choices(resp):
        try:
            j = resp.json()
        except Exception:
            return False
        return bool(isinstance(j, dict) and j.get("choices"))

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