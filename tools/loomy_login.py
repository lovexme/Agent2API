#!/usr/bin/env python3
"""Loomy 短信登录工具 — 发码 + 换 session + 自动写入 AAM 面板。

用法:
  python loomy_login.py send [手机号]        # 发短信验证码
  python loomy_login.py verify [手机号] [验证码] [msgid]  # 换 session 并建号
参考: platform-refs/loomy2api-xing (signer.py / login_flow.py)
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.parse
import uuid

import requests

ACCOUNT_BASE = "https://account.xfinfr.com"
AK_ID = os.environ.get("LOOMY_AK_ID", "")
AK_SECRET = os.environ.get("LOOMY_AK_SECRET", "")
APPID = os.environ.get("LOOMY_APPID", "GM3LOOMY")
AAM = os.environ.get("AAM_BASE_URL", "http://127.0.0.1:8710")

BASE = {"appid": APPID, "modelid": "Web", "version": "1.0.0",
        "devid": "web", "ua": "Loomy|Desktop|Electron|macOS",
        "traceid": secrets.token_hex(16)}


def escaped_path(path: str) -> str:
    parts = []
    for seg in path.split("/"):
        parts.append(urllib.parse.quote(seg, safe="!()*"))
    return "/".join(parts)


def escaped_query(query) -> str:
    if not query:
        return ""
    return "&".join(f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
                    for k, v in sorted(query.items()))


def content_md5(body: str) -> str:
    return base64.b64encode(hashlib.md5(body.encode()).digest()).decode() if body else ""


def sign_headers(method: str, path: str, body: str, query=None):
    date = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
    nonce = str(uuid.uuid4())
    signed_headers, canonical = "", ""
    string_to_sign = "\n".join([
        method.upper(), escaped_path(path), escaped_query(query),
        content_md5(body), "application/json", date, nonce,
        signed_headers, canonical,
    ])
    sig = base64.b64encode(hmac.new(AK_SECRET.encode(), string_to_sign.encode(), hashlib.sha1).digest()).decode()
    h = {"Authorization": f"account {AK_ID}:{sig}", "Date": date, "Nonce": nonce, "Content-Type": "application/json"}
    md = content_md5(body)
    if md:
        h["Content-MD5"] = md
    return h


def api_post(path: str, param: dict):
    body = json.dumps({"base": BASE, "param": param}, ensure_ascii=False, separators=(",", ":"))
    r = requests.post(ACCOUNT_BASE + path, data=body, headers=sign_headers("POST", path, body), timeout=20)
    try:
        payload = r.json()
    except Exception:
        payload = {"raw": r.text[:300]}
    return payload


def send_code(phone: str):
    payload = api_post("/login/phone/sendMsgCode", {"ccode": "86", "phone": phone, "expire": 300})
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    return payload


def verify_code(phone: str, mcode: str, msgid: str):
    payload = api_post("/login/phone/checkCode", {"ccode": "86", "phone": phone, "mcode": mcode, "msgid": msgid, "expire": 1209600})
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    session = (payload.get("data") or {}).get("session") or payload.get("session")
    if not session:
        print("!! 未取得 session:", payload)
        sys.exit(1)
    # 写入 AAM 面板
    plat = requests.get(f"{AAM}/api/platforms").json()["items"]
    loomy = next((p for p in plat if p["key"] == "loomy"), None)
    if not loomy:
        print("!! AAM 面板没有 loomy 平台"); sys.exit(1)
    acct = requests.post(f"{AAM}/api/accounts", json={
        "platform_id": loomy["id"], "name": f"Loomy-{phone[-4:]}", "credential": session}).json()
    print("═══ AAM 建号结果 ═══")
    print(json.dumps({k: acct.get("item", {}).get(k) for k in ("name", "status", "status_msg", "quota_pct", "quota_json")}, ensure_ascii=False, indent=1))
    return payload


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "send":
        phone = sys.argv[2] if len(sys.argv) > 2 else "13800138000"
        send_code(phone)
    elif cmd == "verify":
        if len(sys.argv) < 5:
            print("用法: verify <phone> <code> <msgid>"); sys.exit(1)
        verify_code(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print(__doc__)