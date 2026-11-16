#!/usr/bin/env python3
"""UI 原型/页面 DOM 断言验收工具。
用法: python ui_check.py <url> [--widths 1440,768] [--sel .kpi,.account-card]
检查: 各视口无横向溢出、关键选择器存在、标题渲染; 可选深色对比度扫描。
"""
import os
import sys, json, argparse, subprocess, time, socket

import shutil as _shutil
CHROME = (os.environ.get("CHROME_BIN") if os.environ.get("CHROME_BIN") else None) or _shutil.which("google-chrome") or _shutil.which("chromium") or _shutil.which("chromium-browser") or "/usr/bin/google-chrome"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def run(url, widths, sels, serve_dir=None, admin_key=None):
    if serve_dir:
        port = free_port()
        proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port),
                                 "--bind", "127.0.0.1", "--directory", serve_dir],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.2)
        url = f"http://127.0.0.1:{port}/" + url.lstrip("/")
    from playwright.sync_api import sync_playwright
    out = {"url": url, "served": bool(serve_dir), "views": {}}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
            for w in widths:
                pg = b.new_page(viewport={"width": w, "height": 900})
                errs = []
                pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
                pg.goto(url, wait_until="domcontentloaded", timeout=25000)
                if admin_key:
                    pg.evaluate("""async (k) => {
                        await fetch('/api/admin/login', {method:'POST',
                            headers:{'Content-Type':'application/json'},
                            body: JSON.stringify({key:k})});
                    }""", admin_key)
                    pg.goto(url, wait_until="domcontentloaded", timeout=25000)
                pg.wait_for_timeout(1200)
                res = pg.evaluate("""(sels) => {
                  const de = document.documentElement;
                  const found = {};
                  for (const s of sels) found[s] = document.querySelectorAll(s).length;
                  const lowContrast = [];
                  const els = [...document.querySelectorAll('h1,h2,h3,p,span,td,th,button,a,label')].slice(0, 400);
                  for (const el of els) {
                    const st = getComputedStyle(el);
                    const txt = (el.textContent || '').trim();
                    if (!txt || st.display === 'none' || st.visibility === 'hidden') continue;
                    const m = st.color.match(/\\d+/g);
                    const bgEl = el.closest('[class]');
                    const bg = bgEl ? getComputedStyle(bgEl).backgroundColor : 'rgb(255,255,255)';
                    const mb = bg.match(/\\d+/g);
                    if (m && mb && mb.length >= 3) {
                      const lum = (c) => (parseInt(c[0]) * 0.299 + parseInt(c[1]) * 0.587 + parseInt(c[2]) * 0.114);
                      const diff = Math.abs(lum(m) - lum(mb));
                      if (diff < 30 && !(mb[3] && parseInt(mb[3]) < 50)) lowContrast.push(txt.slice(0, 25));
                    }
                  }
                  return {
                    scrollW: de.scrollWidth, clientW: de.clientWidth,
                    horizontalOverflow: de.scrollWidth > de.clientWidth + 2,
                    title: document.title,
                    bodyLen: (document.body.innerText || '').length,
                    found, lowContrastCount: lowContrast.length,
                    lowContrastSample: lowContrast.slice(0, 5),
                  };
                }""", sels)
                res["consoleErrors"] = errs[:5]
                out["views"][str(w)] = res
                pg.close()
            b.close()
    finally:
        if serve_dir:
            proc.terminate()
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="URL 或 HTML 相对路径（配合 --serve-dir）")
    ap.add_argument("--serve-dir", default=None)
    ap.add_argument("--widths", default="1440,768")
    ap.add_argument("--sel", default="h1,h2,.kpi,.card")
    ap.add_argument("--admin-key", default=None, help="面板登录密钥（面板已启用鉴权时传入）")
    a = ap.parse_args()
    widths = [int(x) for x in a.widths.split(",")]
    print(json.dumps(run(a.target, widths, a.sel.split(","), a.serve_dir, a.admin_key), ensure_ascii=False, indent=1))