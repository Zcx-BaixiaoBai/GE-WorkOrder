"""金鹰工单KPI管理 - 桌面应用启动器

双击运行此文件即可启动系统。
自动打开浏览器访问 http://localhost:8765
"""
import sys
import os
import webbrowser
import threading
from pathlib import Path


def check_dependencies():
    """检查并安装依赖"""
    required = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn[standard]"),
        ("sqlalchemy", "sqlalchemy"),
        ("pyjwt", "PyJWT"),
        ("openpyxl", "openpyxl"),
        ("pandas", "pandas"),
    ]

    missing = []
    for module, package in required:
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if missing:
        print(f"[安装] 缺少依赖: {', '.join(missing)}")
        print(f"[安装] 正在安装...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing, 
                             stdout=subprocess.DEVNULL)
        print("[安装] 依赖安装完成")


def open_browser():
    """延迟3秒后打开浏览器"""
    import time
    time.sleep(3)
    webbrowser.open("http://localhost:8765")


def main():
    print("=" * 50)
    print("    金鹰工单KPI管理系统 v0.0.5")
    print("    Golden Eagle Ticket KPI Management")
    print("=" * 50)
    print()

    # 添加项目根目录到Python路径
    project_root = Path(__file__).parent
    sys.path.insert(0, str(project_root))

    # 检查依赖
    check_dependencies()

    # 初始化数据库
    print("[启动] 初始化数据库...")
    from backend.database import init_database
    init_database()
    print("[启动] 数据库就绪")

    # 启动浏览器
    threading.Thread(target=open_browser, daemon=True).start()

    # 启动FastAPI服务
    print("[启动] 启动HTTP服务...")
    print("[启动] 访问地址: http://localhost:8765")
    print("[启动] 按 Ctrl+C 停止服务")
    print()

    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
