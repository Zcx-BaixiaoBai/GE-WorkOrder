"""金鹰工单KPI管理 - FastAPI应用入口"""
import os
import sys
import logging
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

# frozen(exe)模式下配置文件日志，解决pythonw无控制台输出的问题
if getattr(sys, 'frozen', False):
    AppConfig.ensure_dirs()
    _log_file = AppConfig.LOGS_DIR / "app.log"
    _file_handler = logging.FileHandler(_log_file, encoding="utf-8")
    _file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.root.addHandler(_file_handler)
    logging.root.setLevel(logging.INFO)
    # 不替换sys.stdout，避免uvicorn的formatter调用isatty()崩溃
    # print输出仍然写入日志文件（通过logging handler已覆盖大部分）
    # 爬虫的print通过下面的print hook捕获
    _original_stdout = sys.stdout
    _original_stderr = sys.stderr
    class _TeeToLog:
        """同时写入原始stdout和日志文件，保留isatty等属性"""
        def __init__(self, original, log_file):
            self._original = original
            self._log_file = log_file
        def write(self, msg):
            if self._original is not None:
                self._original.write(msg)
            if msg and msg.strip():
                with open(self._log_file, "a", encoding="utf-8") as f:
                    import datetime
                    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"{ts} {msg}")
                    if not msg.endswith("\n"):
                        f.write("\n")
        def flush(self):
            if self._original is not None:
                self._original.flush()
        def __getattr__(self, name):
            # 代理所有其他属性（isatty, encoding等）给原始stdout
            if self._original is None:
                raise AttributeError(name)
            return getattr(self._original, name)
    sys.stdout = _TeeToLog(_original_stdout, _log_file)
    sys.stderr = _TeeToLog(_original_stderr, _log_file)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    print("[启动] 初始化数据库...")
    init_database()
    print("[启动] 数据库初始化完成")

    # 确保导出目录存在
    AppConfig.ensure_dirs()

    # 启动 APScheduler 定时同步（WY + IPMS，BI 需要浏览器不纳入定时）
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    # 每天 08:00 / 13:30 / 17:00 触发 WY + IPMS 同步
    for hour, minute in [(8, 0), (13, 30), (17, 0)]:
        scheduler.add_job(
            _run_scheduled_sync,
            CronTrigger(hour=hour, minute=minute, timezone="Asia/Shanghai"),
            id=f"sync_wy_ipms_{hour}{minute}",
            replace_existing=True,
            kwargs={"systems": ["wy", "ipms"]},
        )
    scheduler.start()
    app.state.scheduler = scheduler
    print(f"[定时] APScheduler 已启动，WY/IPMS 同步时间: 08:00 / 13:30 / 17:00")

    print(f"[启动] 金鹰工单KPI管理系统已启动")
    print(f"[启动] 访问地址: http://{AppConfig.HOST}:{AppConfig.PORT}")
    yield

    # 关闭时清理
    scheduler.shutdown(wait=False)
    print("[关闭] APScheduler 已关闭")
    print("[关闭] 金鹰工单KPI管理系统已停止")


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    app = FastAPI(
        title="金鹰工单KPI管理",
        description="金鹰物业工单KPI管理系统后端API",
        version="0.0.10",
        lifespan=lifespan,
    )

    # CORS（允许前端本地访问）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
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
    from backend.api.sync_wy import router as sync_wy_router
    from backend.api.sync_ipms import router as sync_ipms_router
    from backend.api.sync_all import router as sync_all_router
    from backend.api.wy import router as wy_router
    from backend.api.ipms import router as ipms_router

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
    app.include_router(sync_wy_router)
    app.include_router(sync_ipms_router)
    app.include_router(sync_all_router)
    app.include_router(wy_router)
    app.include_router(ipms_router)

    return app


app = create_app()


def _run_scheduled_sync(systems=None):
    """APScheduler 回调：触发 WY / IPMS 同步（线程中运行，不阻塞主线程）"""
    import threading
    from datetime import datetime
    systems = systems or ["wy", "ipms"]

    def _sync_wy():
        from backend.api.sync_all import _trigger_wy
        _trigger_wy()

    def _sync_ipms():
        from backend.api.sync_all import _trigger_ipms
        _trigger_ipms()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[定时同步] 开始 ({now_str})")

    for sys_name in systems:
        if sys_name == "wy":
            t = threading.Thread(target=_sync_wy, daemon=True)
            t.start()
            print("[定时同步] WY 筹建专项已触发")
        elif sys_name == "ipms":
            t = threading.Thread(target=_sync_ipms, daemon=True)
            t.start()
            print("[定时同步] IPMS 巡检/维保已触发")

    print(f"[定时同步] 全部触发完成 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=AppConfig.HOST,
        port=AppConfig.PORT,
        reload=False,
        log_level="info",
    )
