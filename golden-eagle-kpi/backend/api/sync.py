"""金鹰工单KPI管理 - API路由：数据同步"""

import os
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.database import get_db, get_session_local
from backend.services.sync_service import SyncService, _sync_status

router = APIRouter(prefix="/api/sync", tags=["数据同步"])

# 爬虫账号（从环境变量读取，默认值用于开发）
SCRAPER_ACCOUNT = os.environ.get("SCRAPER_ACCOUNT", "zhangchenxi")
SCRAPER_PASSWORD = os.environ.get("SCRAPER_PASSWORD", "Zcx020618")


class SyncRequest(BaseModel):
    account: str | None = None
    password: str | None = None
    projectId: int | None = None


@router.get("/status")
def get_sync_status():
    """获取同步状态"""
    return SyncService.get_sync_status()


@router.get("/check-env")
def check_sync_env():
    """检测同步所需环境（Playwright + Chrome + Node.js）"""
    result = {"ready": True, "warnings": [], "errors": []}

    # 1. 检测 Playwright 库
    try:
        import playwright
        result["playwright"] = True
    except ImportError:
        result["playwright"] = False
        result["ready"] = False
        result["errors"].append("Playwright库未安装")
        return result

    # 2. 检测 Playwright driver (含node.exe)
    try:
        from playwright._impl._driver import compute_driver_executable
        driver_info = compute_driver_executable()
        # compute_driver_executable 可能返回 tuple 或单个路径
        if isinstance(driver_info, tuple):
            driver_exe, cli_path = driver_info[0], driver_info[1]
        else:
            driver_exe, cli_path = driver_info, None

        node_exists = Path(driver_exe).exists() if driver_exe else False
        cli_exists = Path(cli_path).exists() if cli_path else True  # cli_path可能不存在也行

        if node_exists and cli_exists:
            result["playwrightDriver"] = True
            result["nodePath"] = str(driver_exe)
        else:
            result["playwrightDriver"] = False
            result["ready"] = False
            result["errors"].append(f"Playwright驱动不完整: node={'找到' if node_exists else '未找到(' + str(driver_exe) + ')'}, cli={'找到' if cli_exists else '未找到'}")
    except Exception as e:
        result["playwrightDriver"] = False
        result["ready"] = False
        result["errors"].append(f"Playwright驱动检测失败: {e}")

    # 3. 额外检查Node.js是否在系统PATH中（有些机器node不在playwright目录）
    node_in_path = shutil.which("node") is not None
    result["nodeInPath"] = node_in_path
    if not node_in_path and not result.get("playwrightDriver"):
        # 如果playwright自带的node也没有，且系统也没装node
        result["warnings"].append("系统未安装Node.js，Playwright使用自带Node运行")

    # 4. 检测浏览器（优先 Chrome，降级 Edge）
    browser_channel = None
    browser_path = None

    chrome_candidates = [
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for p in chrome_candidates:
        if p and Path(p).exists():
            browser_channel = "chrome"
            browser_path = p
            break

    if not browser_channel:
        edge_candidates = [
            shutil.which("msedge"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            os.path.expandvars(r"%PROGRAMFILES(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
        ]
        for p in edge_candidates:
            if p and Path(p).exists():
                browser_channel = "msedge"
                browser_path = p
                break

    # 注册表兜底
    if not browser_channel:
        try:
            import winreg
            for reg_root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                for exe_key, ch in [("chrome.exe", "chrome"), ("msedge.exe", "msedge")]:
                    try:
                        key = winreg.OpenKey(reg_root, f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{exe_key}")
                        reg_path, _ = winreg.QueryValueEx(key, "")
                        winreg.CloseKey(key)
                        if reg_path and Path(reg_path).exists():
                            browser_channel = ch
                            browser_path = reg_path
                            raise StopIteration
                    except StopIteration:
                        break
                    except (FileNotFoundError, OSError):
                        continue
        except StopIteration:
            pass
        except Exception:
            pass

    result["browserChannel"] = browser_channel or ""
    result["browserPath"] = browser_path or ""
    result["chrome"] = browser_channel is not None
    if not browser_channel:
        result["ready"] = False
        result["errors"].append(
            "未检测到浏览器。需要 Google Chrome 或 Microsoft Edge。\n"
            "请安装任一浏览器：\n"
            "  Chrome: https://www.google.com/chrome/\n"
            "  Edge: https://www.microsoft.com/edge"
        )
    elif browser_channel == "msedge":
        result["warnings"].append("未检测到Chrome，将使用 Microsoft Edge 作为备用浏览器")

    return result


@router.post("/start")
async def start_sync(req: SyncRequest):
    """启动数据同步（使用后端写死的爬虫账号，立即返回）"""
    import asyncio, traceback

    try:
        # 获取最近成功同步时间（用独立会话）
        db_tmp = get_session_local()()
        try:
            last_time = SyncService.get_last_sync_time(db_tmp)
        finally:
            db_tmp.close()
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": f"数据库初始化失败: {e}"}

    if _sync_status["is_syncing"]:
        return {"success": False, "error": "同步正在进行中，请等待完成"}

    # 立即返回，让前端开始轮询
    _sync_status["is_syncing"] = True
    _sync_status["progress"] = 0
    _sync_status["message"] = "正在启动同步..."
    _sync_status["last_sync_time"] = last_time

    # 启动后台任务（使用运行中的event loop）
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(
            SyncService._run_sync_task(
                SCRAPER_ACCOUNT, SCRAPER_PASSWORD, req.projectId or 1
            )
        )
    except Exception as e:
        traceback.print_exc()
        _sync_status["is_syncing"] = False
        return {"success": False, "error": f"启动后台任务失败: {e}"}

    return {"success": True, "started": True, "lastSyncTime": last_time}


@router.get("/logs")
def get_sync_logs(
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """获取同步日志"""
    return SyncService.get_sync_logs(page, pageSize, db)

