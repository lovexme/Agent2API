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
from .workbuddy_login_api import router as workbuddy_login_router


@asynccontextmanager
async def lifespan(app):
    db.init_db()
    yield


app = FastAPI(title="AAM Panel", lifespan=lifespan)
app.include_router(auth_router)       # /api/admin/*（登录入口/会话）
app.include_router(api_router)      # /api/*
app.include_router(gateway_router)  # /v1/*
app.include_router(trae_login_router)  # /api/trae-login/*
app.include_router(novnc_router)       # /novnc/* (noVNC 代理)
app.include_router(loomy_login_router)  # /api/login/loomy/* (发短信添加账号)
app.include_router(tabbit_login_router)  # /api/login/tabbit/* (发短信添加账号)
app.include_router(workbuddy_login_router)  # /api/login/workbuddy/* (OAuth 授权)

static = Path(__file__).resolve().parent / "static"
if static.exists():
    # 前端构建产物挂到根，html=True 直接返回 index.html（hash 路由无需回退）
    app.mount("/", StaticFiles(directory=static, html=True), name="spa")
