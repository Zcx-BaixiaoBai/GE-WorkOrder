"""金鹰工单KPI管理 - FastAPI应用入口"""
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse

from backend.config import AppConfig
from backend.database import init_database

# PyInstaller 打包后，确保 backend 包可被找到
if getattr(sys, 'frozen', False):
    _meipass = getattr(sys, '_MEIPASS', '')
    if _meipass and _meipass not in sys.path:
        sys.path.insert(0, _meipass)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    print("[启动] 初始化数据库...")
    init_database()
    print("[启动] 数据库初始化完成")

    # 确保导出目录存在
    AppConfig.ensure_dirs()

    print(f"[启动] 金鹰工单KPI管理系统已启动")
    print(f"[启动] 访问地址: http://{AppConfig.HOST}:{AppConfig.PORT}")
    yield

    # 关闭时清理
    print("[关闭] 金鹰工单KPI管理系统已停止")


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    app = FastAPI(
        title="金鹰工单KPI管理",
        description="金鹰物业工单KPI管理系统后端API",
        version="0.0.8post1",
        lifespan=lifespan,
    )

    # CORS（允许前端本地访问）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 根路径重定向到前端
    @app.get("/", include_in_schema=False)
    async def root():
        frontend_dir = AppConfig.FRONTEND_DIR
        if frontend_dir.exists() and (frontend_dir / "index.html").exists():
            with open(frontend_dir / "index.html", "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
        return RedirectResponse(url="/docs")

    # 注册路由
    from backend.api.auth import router as auth_router
    from backend.api.stats import router as stats_router
    from backend.api.tickets import router as tickets_router
    from backend.api.personnel import router as personnel_router
    from backend.api.sync import router as sync_router
    from backend.api.export import router as export_router
    from backend.api.config import router as config_router
    from backend.api.websocket import router as ws_router
    from backend.api.search_api import router as search_router
    from backend.api.ai_chat import router as ai_chat_router
    from backend.api.update import router as update_router

    app.include_router(auth_router)
    app.include_router(stats_router)
    app.include_router(tickets_router)
    app.include_router(personnel_router)
    app.include_router(sync_router)
    app.include_router(export_router)
    app.include_router(config_router)
    app.include_router(ws_router)
    app.include_router(search_router)
    app.include_router(ai_chat_router)
    app.include_router(update_router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=AppConfig.HOST,
        port=AppConfig.PORT,
        reload=False,
        log_level="info",
    )
