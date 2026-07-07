"""金鹰工单KPI管理 - 配置管理"""
import os
import sys
from pathlib import Path


def _env(key: str, default: str = "") -> str:
    """读取环境变量，支持 .env 文件（需安装 python-dotenv）"""
    val = os.environ.get(key)
    if val is not None:
        return val
    # 尝试从 .env 文件加载
    _load_dotenv()
    return os.environ.get(key, default)


def _load_dotenv() -> None:
    """懒加载 .env 文件（只执行一次）"""
    if getattr(_load_dotenv, "_loaded", False):
        return
    _load_dotenv._loaded = True
    # frozen(exe)模式下，.env在exe同级目录；源码模式在项目根目录
    if getattr(sys, 'frozen', False):
        dotenv_path = Path(sys.executable).parent / ".env"
    else:
        dotenv_path = Path(__file__).resolve().parent.parent / ".env"
    if dotenv_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path)
        except ImportError:
            # 无 python-dotenv 时手动解析 .env
            _parse_dotenv(dotenv_path)


def _parse_dotenv(path: Path) -> None:
    """手动解析简单的 KEY=VALUE .env 文件（无 python-dotext 时的降级方案）"""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"").strip()
            if key and key not in os.environ:  # 不覆盖已有环境变量
                os.environ[key] = value
    except Exception:
        pass


class AppConfig:
    """应用配置（单例模式，敏感值从环境变量读取）"""

    # 基础路径
    _frozen = getattr(sys, 'frozen', False)
    if _frozen:
        # frozen(exe)模式下：源码/前端在 _MEIPASS(_internal)，数据在exe旁边持久化
        BASE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
        DATA_DIR = Path(sys.executable).resolve().parent / "data"
    else:
        BASE_DIR = Path(__file__).resolve().parent.parent
        DATA_DIR = BASE_DIR / "data"
    EXPORTS_DIR = DATA_DIR / "exports"
    LOGS_DIR = DATA_DIR / "logs"
    DB_PATH = DATA_DIR / "golden_eagle_kpi.db"
    FRONTEND_DIR = BASE_DIR / "frontend"

    # 服务配置
    HOST = "127.0.0.1"
    PORT = 8765

    # JWT配置 (环境变量: JWT_SECRET，生产必须设置)
    JWT_SECRET = _env("JWT_SECRET")  # 无默认值，缺失时报错
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_HOURS = 8

    # 开发模式 (DEV_MODE=1 时允许认证降级，生产环境必须为0)
    DEV_MODE = _env("DEV_MODE", "0") == "1"

    # 服务器模式
    SERVER_HOST = _env("SERVER_HOST", "127.0.0.1")
    SERVER_PORT = int(_env("SERVER_PORT", "8765"))

    # BI系统配置
    BI_LOGIN_URL = "http://bi.jinyeaglegroup.com/xxx"
    BI_EXPORT_URL_TICKETS = "http://bi.jinyeaglegroup.com/xxx"
    BI_EXPORT_URL_SNAPSHOTS = "http://bi.jinyeaglegroup.com/xxx"

    # 分页默认
    DEFAULT_PAGE_SIZE = 10
    MAX_PAGE_SIZE = 100

    @classmethod
    def ensure_dirs(cls):
        """确保所有必要目录存在"""
        for d in [cls.DATA_DIR, cls.EXPORTS_DIR, cls.LOGS_DIR]:
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_db_url(cls) -> str:
        """获取数据库连接URL"""
        return f"sqlite:///{cls.DB_PATH}"
