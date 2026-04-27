"""金鹰工单KPI管理系统 - 桌面启动器

双击即启动，自动打开浏览器，系统托盘控制退出。
支持 PyInstaller 打包为单个 exe。
"""
import sys
import os
import webbrowser
import threading
import time
import socket
from pathlib import Path


def get_base_dir() -> Path:
    """获取应用根目录（兼容 PyInstaller 打包和源码运行）"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent


def is_port_in_use(port: int) -> bool:
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def wait_for_server(port: int, timeout: float = 15.0) -> bool:
    """等待服务器启动就绪"""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.3)
    return False


def open_browser_when_ready(port: int):
    """等待服务器就绪后自动打开浏览器"""
    if wait_for_server(port):
        time.sleep(0.5)
        try:
            webbrowser.open(f"http://127.0.0.1:{port}")
        except Exception:
            pass
    else:
        try:
            print(f"[警告] 服务器未就绪，请手动访问 http://127.0.0.1:{port}")
        except Exception:
            pass


def _setup_win_tray(port: int):
    """Windows 系统托盘：双击/右键"打开"，右键菜单"退出"""
    import win32gui
    import struct

    # Windows 消息常量（整型）
    WM_USER           = 0x0400
    WM_COMMAND        = 0x0111
    WM_DESTROY        = 0x0002
    WM_NULL           = 0x0000
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP      = 0x0205
    MF_STRING         = 0x0000
    MF_SEPARATOR      = 0x00000800
    TPM_LEFTALIGN     = 0x0000
    NIM_ADD           = 0x00000000
    NIM_DELETE        = 0x00000002
    NIF_MESSAGE       = 0x00000001
    NIF_ICON         = 0x00000002
    NIF_TIP           = 0x00000004
    IDI_APPLICATION   = 0x7F00

    state = {'port': port, 'running': True, 'hwnd': None}

    def wnd_proc(hwnd, msg, wp, lp):
        if msg == WM_COMMAND:
            if wp == 1:
                try:
                    webbrowser.open(f"http://127.0.0.1:{state['port']}")
                except Exception:
                    pass
            elif wp == 2:
                state['running'] = False
                try:
                    win32gui.DestroyWindow(hwnd)
                except Exception:
                    pass
        elif msg == WM_DESTROY:
            state['running'] = False
        return win32gui.DefWindowProc(hwnd, msg, wp, lp)

    try:
        wc = win32gui.WNDCLASSEX()
        wc.lpfnWndProc = wnd_proc
        wc.lpszClassName = "JY_KPI_TRAY"
        wc.hInstance = None
        win32gui.RegisterClassEx(wc)
    except Exception:
        pass

    hwnd = win32gui.CreateWindow(
        "JY_KPI_TRAY", None, 0, 0, 0, 0, 0, 0, 0, None, None, None, None)
    state['hwnd'] = hwnd

    hicon = win32gui.LoadIcon(None, IDI_APPLICATION)

    # NOTIFYICONDATA（Vista+ 936字节）
    NID_SIZE = 936
    nid = bytearray(NID_SIZE)
    struct.pack_into('I', nid, 0, NID_SIZE)
    struct.pack_into('I', nid, 4, hwnd)
    struct.pack_into('I', nid, 8, 1)
    struct.pack_into('I', nid, 12, NIF_MESSAGE | NIF_ICON | NIF_TIP)
    struct.pack_into('I', nid, 16, WM_USER + 1)
    struct.pack_into('I', nid, 20, hicon)
    tip = "金鹰工单KPI  双击打开  右键菜单"
    for i, ch in enumerate(tip.encode('gbk')):
        if i < 128:
            nid[24 + i] = ch

    try:
        win32gui.Shell_NotifyIcon(NIM_ADD, nid)
    except Exception:
        pass

    def show_menu():
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, MF_STRING, 1, "打开管理界面")
        win32gui.AppendMenu(menu, MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, MF_STRING, 2, "退出")
        x, y = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(hwnd)
        win32gui.TrackPopupMenu(menu, TPM_LEFTALIGN, x, y, 0, hwnd, None)
        win32gui.PostMessage(hwnd, WM_NULL, 0, 0)

    while state['running']:
        try:
            msg = win32gui.GetMessage(None, 0, 0, 0)
            if msg[1] == 0:
                break
            m = msg[1].message
            if m == WM_USER + 1:
                if msg[1].lParam == WM_LBUTTONDBLCLK:
                    try:
                        webbrowser.open(f"http://127.0.0.1:{state['port']}")
                    except Exception:
                        pass
                elif msg[1].lParam == WM_RBUTTONUP:
                    show_menu()
            elif m == WM_COMMAND:
                wnd_proc(msg[1].hwnd, m, msg[1].wParam, msg[1].lParam)
            elif m == WM_DESTROY:
                state['running'] = False
            else:
                win32gui.TranslateMessage(msg[1])
                win32gui.DispatchMessage(msg[1])
        except Exception:
            break

    try:
        win32gui.Shell_NotifyIcon(NIM_DELETE, nid)
    except Exception:
        pass
    try:
        win32gui.DestroyWindow(hwnd)
    except Exception:
        pass


def setup_tray_icon(port: int):
    """系统托盘入口（纯 win32gui，无需 PIL）"""
    try:
        _setup_win_tray(port)
    except Exception:
        pass


def _ensure_node_in_path(base_dir: Path):
    """确保 Playwright 自带的 node.exe 在 PATH 中（PyInstaller 打包后）"""
    if not getattr(sys, 'frozen', False):
        return  # 源码运行不需要
    # playwright driver 目录下有 node.exe
    node_dirs = [
        base_dir / "_internal" / "playwright" / "driver" / "package",
        base_dir / "_internal" / "playwright" / "driver",
    ]
    for nd in node_dirs:
        node_exe = nd / "node.exe"
        if node_exe.exists():
            # 将该目录加入 PATH（当前进程）
            current_path = os.environ.get("PATH", "")
            nd_str = str(nd)
            if nd_str not in current_path:
                os.environ["PATH"] = nd_str + os.pathsep + current_path
                print(f"[PATH] 已注入内置 Node.js: {nd_str}")
            return


def main():
    base_dir = get_base_dir()
    port = 8765

    os.environ.setdefault('GOLDEN_EAGLE_BASE_DIR', str(base_dir))

    # 将内置 node.exe 加入 PATH（Playwright 爬虫依赖）
    _ensure_node_in_path(base_dir)

    if getattr(sys, 'frozen', False):
        sys.path.insert(0, sys._MEIPASS)
    else:
        sys.path.insert(0, str(base_dir))

    try:
        from backend.config import AppConfig
        AppConfig.BASE_DIR = base_dir
        AppConfig.DATA_DIR = base_dir / "data"
        AppConfig.EXPORTS_DIR = base_dir / "data" / "exports"
        AppConfig.LOGS_DIR = base_dir / "data" / "logs"
        AppConfig.DB_PATH = base_dir / "data" / "golden_eagle_kpi.db"
        if getattr(sys, 'frozen', False):
            AppConfig.FRONTEND_DIR = Path(sys._MEIPASS) / "frontend"
        else:
            AppConfig.FRONTEND_DIR = base_dir / "frontend"
    except ImportError:
        pass

    if is_port_in_use(port):
        try:
            print(f"[提示] 端口 {port} 已被占用，正在打开浏览器...")
            webbrowser.open(f"http://127.0.0.1:{port}")
        except Exception:
            pass
        return

    from backend.database import init_database
    init_database()

    threading.Thread(target=open_browser_when_ready, args=(port,), daemon=True).start()
    threading.Thread(target=setup_tray_icon, args=(port,), daemon=True).start()

    # PyInstaller 打包后 sys.stdout 可能为 None，导致 uvicorn 初始化日志失败
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")

    from main import app
    import uvicorn
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",
    )


if __name__ == "__main__":
    main()
