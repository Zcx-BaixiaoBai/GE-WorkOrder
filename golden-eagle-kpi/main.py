"""金鹰工单KPI管理 - FastAPI应用入口"""
import os
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
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
    from logging.handlers import RotatingFileHandler
    _file_handler = RotatingFileHandler(_log_file, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
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

    # 启动 APScheduler 定时同步（从数据库动态读取配置）
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.start()
    app.state.scheduler = scheduler

    # 从数据库加载定时任务配置
    _load_sync_schedule(scheduler)
    print(f"[定时] APScheduler 已启动，配置从数据库动态加载")

    # 会话清理定时任务（每日03:00清理过期会话）
    from apscheduler.triggers.cron import CronTrigger as _CT
    def _cleanup_expired_sessions():
        from backend.database import get_session_local
        from backend.models.user_session import UserSession
        from datetime import datetime
        db = get_session_local()()
        try:
            expired = db.query(UserSession).filter(UserSession.expires_at < datetime.now()).all()
            for s in expired:
                db.delete(s)
            db.commit()
            if expired:
                print(f"[会话清理] 清理 {len(expired)} 个过期会话")
        except Exception as e:
            print(f"[会话清理] 失败: {e}")
        finally:
            db.close()
    scheduler.add_job(_cleanup_expired_sessions, _CT(hour=3, minute=0, timezone="Asia/Shanghai"), id="cleanup_sessions", replace_existing=True)

    print(f"[启动] 金鹰工单KPI管理系统已启动")
    print(f"[启动] 访问地址: http://{AppConfig.SERVER_HOST}:{AppConfig.SERVER_PORT}")
    yield

    # 关闭时清理
    scheduler.shutdown(wait=False)
    print("[关闭] APScheduler 已关闭")
    print("[关闭] 金鹰工单KPI管理系统已停止")


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    # CORS 白名单：本地 + 服务器模式下的外网访问
    _cors_origins = [
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    ]
    # 服务器模式：允许所有同源访问（前端和API同端口，CORS实际不拦截同源）
    if AppConfig.SERVER_HOST == "0.0.0.0":
        _cors_origins = ["*"]  # 服务器模式下前端与API同源，CORS不阻拦

    app = FastAPI(
        title="金鹰工单KPI管理",
        description="金鹰物业工单KPI管理系统后端API",
        version="1.1.0",
        lifespan=lifespan,
        # 生产环境关闭 Swagger 文档
        docs_url="/docs" if AppConfig.DEV_MODE else None,
        redoc_url="/redoc" if AppConfig.DEV_MODE else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 客户端IP日志中间件
    @app.middleware("http")
    async def log_client_ip(request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        # 服务器模式下记录外网访问
        if AppConfig.SERVER_HOST == "0.0.0.0" and client_ip not in ("127.0.0.1", "::1", "unknown"):
            print(f"[访问] {client_ip} -> {request.method} {request.url.path}")
        response = await call_next(request)
        return response

    # 挂载前端静态文件目录（echarts.min.js等）
    frontend_dir = AppConfig.FRONTEND_DIR
    # React 构建产物目录（优先使用）
    react_dist = frontend_dir / "react-dist"
    static_dir = react_dist if react_dist.exists() else frontend_dir
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    # React assets 目录
    react_assets = react_dist / "assets"
    if react_assets.exists():
        app.mount("/assets", StaticFiles(directory=str(react_assets)), name="assets")

    # 根路径：优先服务 React 构建产物，降级到旧版 index.html
    @app.get("/", include_in_schema=False)
    async def root():
        # React 构建产物
        react_index = react_dist / "index.html"
        if react_index.exists():
            with open(react_index, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
        # 降级：旧版单文件前端
        old_index = frontend_dir / "index.html"
        if old_index.exists():
            with open(old_index, "r", encoding="utf-8") as f:
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
    from backend.api.project_manager import router as project_manager_router
    from backend.api.sync_schedule_config import router as sync_schedule_router

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
    app.include_router(project_manager_router)
    app.include_router(sync_schedule_router)

    # 关闭应用API（需认证）
    import os
    import signal
    from fastapi import Header
    
    @app.post("/api/shutdown")
    def shutdown_app(authorization: str = Header(None)):
        """关闭应用（需JWT认证）"""
        from backend.services.auth_service import AuthService
        from backend.database import get_session_local
        if not authorization or not authorization.startswith("Bearer "):
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="未授权")
        token = authorization[7:]
        db = get_session_local()()
        try:
            user = AuthService.get_current_user(token, db)
            if not user:
                from fastapi import HTTPException
                raise HTTPException(status_code=401, detail="Token无效或已过期")
        finally:
            db.close()
        print(f"[关闭] 收到关闭请求 (用户: {user.get('name', 'unknown')})")
        pid = os.getpid()
        os.kill(pid, signal.SIGTERM)
        return {"success": True, "message": "应用正在关闭..."}

    # 健康检查端点（无需认证）
    @app.get("/api/health", include_in_schema=False)
    def health_check():
        return {"status": "ok", "version": "1.1.0", "host": AppConfig.SERVER_HOST, "port": AppConfig.SERVER_PORT}

    # SPA catch-all: 所有非API路由返回React index.html（必须在所有API路由之后）
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("static/") or full_path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Not Found")
        react_index = react_dist / "index.html"
        if react_index.exists():
            with open(react_index, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
        old_index = frontend_dir / "index.html"
        if old_index.exists():
            with open(old_index, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
        raise HTTPException(status_code=404, detail="Not Found")

    return app


app = create_app()


# ============================================================
# 定时同步调度（从数据库动态加载配置）
# ============================================================

def _load_sync_schedule(scheduler):
    """从数据库加载定时同步配置到 APScheduler"""
    import json
    from backend.database import get_session_local
    from backend.models.sync_schedule_config import SyncScheduleConfig
    from apscheduler.triggers.cron import CronTrigger

    db = get_session_local()()
    try:
        # 确保默认配置存在
        from backend.api.sync_schedule_config import _ensure_default_configs
        _ensure_default_configs(db)

        configs = db.query(SyncScheduleConfig).all()
        for cfg in configs:
            if not cfg.enabled:
                continue
            times = json.loads(cfg.cron_times) if cfg.cron_times else []
            for time_str in times:
                hour, minute = int(time_str.split(":")[0]), int(time_str.split(":")[1])
                job_id = f"sync_{cfg.channel}_{hour:02d}{minute:02d}"
                scheduler.add_job(
                    _run_scheduled_sync,
                    CronTrigger(hour=hour, minute=minute, timezone="Asia/Shanghai"),
                    id=job_id,
                    replace_existing=True,
                    kwargs={"systems": [cfg.channel]},
                )
            if times:
                print(f"[定时] {cfg.channel.upper()} 通道: {', '.join(times)}")
    finally:
        db.close()


def _reschedule_sync_jobs():
    """重新加载定时任务配置（配置更新后调用）"""
    from backend.database import get_session_local
    from backend.models.sync_schedule_config import SyncScheduleConfig

    # 获取全局 app 的 scheduler
    import main as _main
    scheduler = getattr(_main.app.state, "scheduler", None) if hasattr(_main, "app") else None
    if not scheduler:
        print("[定时] 调度器未启动，跳过重载")
        return

    # 移除所有 sync_ 开头的 job
    for job in scheduler.get_jobs():
        if job.id.startswith("sync_"):
            scheduler.remove_job(job.id)

    # 重新加载
    _load_sync_schedule(scheduler)
    print("[定时] 定时任务配置已重新加载")


def _run_scheduled_sync(systems=None):
    """APScheduler 回调：触发同步（线程中运行，不阻塞主线程）
    
    支持三个通道：bi/wy/ipms，执行后更新数据库中的 last_run_time/last_run_result
    """
    import threading
    from datetime import datetime
    systems = systems or ["wy", "ipms"]

    def _sync_bi():
        from backend.api.sync_all import _trigger_bi
        _trigger_bi()

    def _sync_wy():
        from backend.api.sync_all import _trigger_wy
        _trigger_wy()

    def _sync_ipms():
        from backend.api.sync_all import _trigger_ipms
        _trigger_ipms()

    def _update_run_result(channel, result):
        """更新数据库中的执行结果"""
        try:
            from backend.database import get_session_local
            from backend.models.sync_schedule_config import SyncScheduleConfig
            db = get_session_local()()
            try:
                cfg = db.query(SyncScheduleConfig).filter(SyncScheduleConfig.channel == channel).first()
                if cfg:
                    cfg.last_run_time = datetime.now()
                    cfg.last_run_result = result
                    db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"[定时同步] 更新执行结果失败: {e}")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[定时同步] 开始 ({now_str})")

    for sys_name in systems:
        if sys_name == "bi":
            t = threading.Thread(target=_sync_bi, daemon=True)
            t.start()
            print("[定时同步] BI 工单已触发")
            _update_run_result("bi", "triggered")
        elif sys_name == "wy":
            t = threading.Thread(target=_sync_wy, daemon=True)
            t.start()
            print("[定时同步] WY 筹建专项已触发")
            _update_run_result("wy", "triggered")
        elif sys_name == "ipms":
            t = threading.Thread(target=_sync_ipms, daemon=True)
            t.start()
            print("[定时同步] IPMS 巡检/维保已触发")
            _update_run_result("ipms", "triggered")

    print(f"[定时同步] 全部触发完成 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=AppConfig.SERVER_HOST,
        port=AppConfig.SERVER_PORT,
        reload=False,
        log_level="info",
    )
