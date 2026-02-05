# FastAPI 应用入口
"""
Go-Stock Python 后端主入口
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db, close_db
from app.api.router import api_router
from app.tasks.scheduler import startup_scheduler, shutdown_scheduler


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    await init_db()
    # 初始化并启动定时任务（多 worker 场景下自动选主，避免重复执行）
    await startup_scheduler()
    yield
    # 关闭时清理资源
    shutdown_scheduler()
    # 关闭数据源 HTTP 客户端连接池，避免进程退出时出现未关闭告警
    try:
        from app.datasources.manager import get_datasource_manager
        await get_datasource_manager().close_all()
    except Exception:
        pass
    await close_db()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Go-Stock Python 后端 API",
    lifespan=lifespan,
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    """根路径"""
    return {"message": "Go-Stock Python Backend", "version": "1.0.0"}


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}
