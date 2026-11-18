#!/usr/bin/env python3
"""UI 页面 DOM 断言验收工具(硬门禁版)。

用法:
  python3 ui_check.py <url> [--widths 1440,768] [--sel .kpi,.card] [--admin-key KEY]
                       [--routes '#/, #/accounts, ...'] [--strict]
必须用 /usr/bin/python3(只有它装了 playwright;`python3` 在本机指向 Hermes venv)。

检查: 登录是否真的成功(login+me 双 200)、逐路由遍历、每个路由必须被 vue-router 真正匹配
      (错 hash 在生产构建下无 console error,只能查 __vue_app__.$router.currentRoute.matched)、
      不得出现未登录门、各视口无横向溢出、页面非空(空列表页需带空状态文案)、console 不得有 error。
      --strict 时有任一失败即 exit 1(旧版无论 consoleErrors 是否非空都 exit 0,不是门禁)。
"""
import sys, json, argparse, subprocess, time, socket, re

CHROME = os.environ.get("CHROME_BIN", "")  # 留空=playwright 默认浏览器

# 默认豁免:留空表示零容忍。仅在明确知道某类是预期噪声时用 --allow 传入。
DEFAULT_ALLOW = []

VIEW_JS = r"""(sels) => {
  const de = document.documentElement;
  const found = {};
  for (const s of sels) found[s] = document.querySelectorAll(s).length;
  const lowContrast = [];
  const els = [...document.querySelectorAll('h1,h2,h3,p,span,td,th,button,a,label')].slice(0, 400);
  for (const el of els) {
    const st = getComputedStyle(el);
    const txt = (el.textContent || '').trim();
    if (!txt || st.display === 'none' || st.visibility === 'hidden') continue;
    const m = st.color.match(/\d+/g);
    const bgEl = el.closest('[class]');
    const bg = bgEl ? getComputedStyle(bgEl).backgroundColor : 'rgb(255,255,255)';
    const mb = bg.match(/\d+/g);
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
    hasEmptyState: /暂无|没有|无数据|尚无|No data/.test(document.body.innerText || ''),
    appCards: document.querySelectorAll('#app .card, #app .kpi').length,
    routeMatched: (() => {
      const el = document.querySelector('#app');
      const app = el && el.__vue_app__;
      if (!app) return null;
      try {
        const c = app.config.globalProperties.$router.currentRoute.value;
        return { matched: c.matched.length, name: String(c.name || ''), fullPath: c.fullPath };
      } catch (e) { return null; }
    })(),
    loggedOutGate: [...document.querySelectorAll('input')].some(i => (i.placeholder || '').includes('panel key')),
    found, lowContrastCount: lowContrast.length,
    lowContrastSample: lowContrast.slice(0, 5),
  };
}"""

LOGIN_JS = r"""async (k) => {
  try {
    const r = await fetch('/api/admin/login', {method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify({key:k})});
    if (!r.ok) return {login: r.status, me: null};
    const me = await fetch('/api/admin/me');
    return {login: r.status, me: me.status};
  } catch (e) { return {login: 'error', me: null, error: String(e)}; }
}"""


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _allowed(text, allow):
    return any(re.search(pat, text) for pat in allow)


def run(url, widths, sels, serve_dir=None, admin_key=None, routes=None, allow=None):
    if serve_dir:
        port = free_port()
        proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port),
                                 "--bind", "127.0.0.1", "--directory", serve_dir],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.2)
        url = f"http://127.0.0.1:{port}/" + url.lstrip("/")
    from playwright.sync_api import sync_playwright
    base = url.rstrip("/")
    routes = routes or [""]
    allow = list(DEFAULT_ALLOW if allow is None else allow)
    out = {"url": url, "served": bool(serve_dir), "routes": routes, "login": None,
           "views": {}, "failures": []}
    try:
        with sync_playwright() as p:
            launch_kw = {"headless": True, "args": ["--no-sandbox"]}
            if CHROME:
                launch_kw["executable_path"] = CHROME
            b = p.chromium.launch(**launch_kw)
            # 同一个 context:登录 cookie 对所有页面共享(用 b.new_page() 会每次新建 context,导致实测的是未登录门)
            ctx = b.new_context(viewport={"width": widths[0], "height": 900})
            if admin_key:
                lp = ctx.new_page()
                lp.goto(base + "/", wait_until="domcontentloaded", timeout=25000)
                out["login"] = lp.evaluate(LOGIN_JS, admin_key)
                lp.close()
                if not (isinstance(out["login"], dict) and out["login"].get("me") == 200):
                    out["failures"].append("login failed: %s" % json.dumps(out["login"], ensure_ascii=False))
            for w in widths:
                for route in routes:
                    pg = ctx.new_page()
                    pg.set_viewport_size({"width": w, "height": 900})
                    errs = []
                    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
                    target = (base + "/" + route) if route else base + "/"
                    pg.goto(target, wait_until="domcontentloaded", timeout=25000)
                    pg.wait_for_timeout(1200)
                    res = pg.evaluate(VIEW_JS, sels)
                    res["consoleErrors"] = errs[:5]
                    res["route"] = route or "/"
                    res["width"] = w
                    key = "%s@%d" % (route or "/", w)
                    out["views"][key] = res
                    if res["horizontalOverflow"]:
                        out["failures"].append("horizontal overflow %s" % key)
                    if res["bodyLen"] < 50:
                        out["failures"].append("empty body %s" % key)
                    if admin_key and res["bodyLen"] < 200 and not (
                            res.get("hasEmptyState") and res.get("appCards", 0) >= 1):
                        # 视图真的挂载 + 明确的空状态文案 ⇒ 空列表页是正常的(如 request_log 清空后)
                        # 错 hash 路由只有 ~79 字符的空壳、无空状态文案,仍会命中这条
                        out["failures"].append("too little content %s (bodyLen=%d)" % (key, res["bodyLen"]))
                    if admin_key:
                        rm = res.get("routeMatched")
                        if not isinstance(rm, dict) or rm.get("matched", 0) < 1:
                            # vue-router 未匹配 ⇒ 该 hash 路由不存在(生产构建下无 console error,只能这样判)
                            out["failures"].append("route not matched %s (%s)" % (key, json.dumps(rm, ensure_ascii=False)))
                    if admin_key and res.get("loggedOutGate"):
                        out["failures"].append("not logged in (login gate shown) %s" % key)
                    for e in errs:
                        if _allowed(e, allow):
                            continue
                        out["failures"].append("console error %s: %s" % (key, e[:160]))
                    pg.close()
            ctx.close()
            b.close()
    finally:
        if serve_dir:
            proc.terminate()
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="URL 或 HTML 相对路径(配合 --serve-dir)")
    ap.add_argument("--serve-dir", default=None)
    ap.add_argument("--widths", default="1440,768")
    ap.add_argument("--sel", default="h1,h2,.kpi,.card")
    ap.add_argument("--admin-key", default=None, help="面板登录密钥(面板已启用鉴权时传入)")
    ap.add_argument("--routes", default="", help="逗号分隔的 hash 路由,如 '#/, #/accounts';留空=只测入口页")
    ap.add_argument("--allow", default="", help="console error 豁免正则(逗号分隔);默认零容忍")
    ap.add_argument("--strict", action="store_true", help="有失败项时 exit 1(硬门禁)")
    a = ap.parse_args()
    widths = [int(x) for x in a.widths.split(",")]
    routes = [r.strip() for r in a.routes.split(",") if r.strip()] or [""]
    allow = [x for x in (p.strip() for p in a.allow.split(",")) if x]
    result = run(a.target, widths, a.sel.split(","), a.serve_dir, a.admin_key, routes, allow)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if a.strict and result["failures"]:
        sys.exit(1)
