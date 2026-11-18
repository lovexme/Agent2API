from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from . import db
from .api import router as api_router
from .auth import router as auth_router
from .gateway import router as gateway_router
from .trae_login import router as trae_login_router, novnc_router
from .loomy_login_api import router as loomy_login_router
from .tabbit_login_api import router as tabbit_login_router
from .tabbit_login_api import _public as tabbit_public_router
from .workbuddy_login_api import router as workbuddy_login_router
from .assistant_api import router as assistant_router


@asynccontextmanager
async def lifespan(app):
    db.init_db()
    import os
    from . import scheduler
    # 每日 08:00 自动检测(v4/v6 双实例靠 settings 日期戳去重);AAM_DISABLE_SCHEDULER=1 可关闭(测试用)
    if os.environ.get("AAM_DISABLE_SCHEDULER", "").strip().lower() not in ("1", "true", "yes"):
        scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()


app = FastAPI(title="AAM Panel", lifespan=lifespan)

# 静态资源缓存策略：index.html 每次校验（升级后立即生效），assets 哈希文件长缓存
@app.middleware("http")
async def cache_policy(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path == "/" or path.endswith(".html"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response

app.include_router(auth_router)       # /api/admin/*（登录入口/会话）
app.include_router(api_router)      # /api/*
app.include_router(gateway_router)  # /v1/*
app.include_router(trae_login_router)  # /api/trae-login/*
app.include_router(novnc_router)       # /novnc/* (noVNC 代理)
app.include_router(loomy_login_router)  # /api/login/loomy/* (发短信添加账号)
app.include_router(tabbit_login_router)  # /api/login/tabbit/* (发短信添加账号)
app.include_router(tabbit_public_router)  # /api/login/tabbit/google-callback (手机端 Google 回调, 一次性token)
app.include_router(workbuddy_login_router)  # /api/login/workbuddy/* (OAuth 授权)
app.include_router(assistant_router)  # /api/assistant/* (AI 助手，3065 移植)

static = Path(__file__).resolve().parent / "static"
if static.exists():
    # 前端构建产物挂到根，html=True 直接返回 index.html（hash 路由无需回退）
    app.mount("/", StaticFiles(directory=static, html=True), name="spa")
