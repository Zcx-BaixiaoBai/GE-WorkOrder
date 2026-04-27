# -*- coding: utf-8 -*-
"""金鹰工单KPI v0.0.10 - 发布包构建脚本
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# ===================== 配置区 =====================
# 注意：正式打包前，VERSION 文件中的版本号必须已经更新！
APP_NAME = "金鹰工单KPI"
VERSION = "v0.0.10"
DIST_DIR = Path("dist") / APP_NAME          # PyInstaller 输出目录
RELEASE = Path("releases")                   # 最终发布目录
RELEASE_PKG = RELEASE / f"{APP_NAME}-{VERSION}"
# =================================================

def get_version():
    try:
        return Path("VERSION").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return VERSION


def copytree(src: Path, dst: Path, ignore=None):
    if dst.exists():
        try:
            shutil.rmtree(dst)
        except PermissionError:
            import subprocess
            subprocess.run(['cmd', '/c', 'rmdir', '/S', '/Q', str(dst)], check=False, capture_output=True)
    if dst.exists():
        print(f"  警告: 无法删除旧目录，使用自定义复制")
        # 手动复制，跳过被锁定的文件
        import shutil as _shutil
        for root, dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            ddir = os.path.join(dst, rel)
            os.makedirs(ddir, exist_ok=True)
            for f in files:
                sfile = os.path.join(root, f)
                dfile = os.path.join(ddir, f)
                try:
                    _shutil.copy2(sfile, dfile)
                except (PermissionError, OSError) as e:
                    print(f"    跳过被锁定文件: {f}")
        return
    shutil.copytree(src, dst, ignore=ignore)


def clean_chromium_from_dist():
    """从 dist 中删除 playwright chromium 浏览器（约 1.2GB）。
    代码使用系统 Chrome（channel="chrome"），不需要这套冗余的浏览器驱动。"""
    lb_dirs = list(DIST_DIR.rglob(".local-browsers"))
    if lb_dirs:
        total_size = sum(
            sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            for d in lb_dirs
        )
        for d in lb_dirs:
            shutil.rmtree(d)
        print(f"  已删除 chromium（.local-browsers，{total_size / 1024 / 1024:.0f} MB）")
    else:
        print("  .local-browsers 不存在，跳过")


def build_release():
    print("=" * 50)
    print(f"开始构建发布包: {APP_NAME} {get_version()}")
    print("=" * 50)

    # 0. 检查 dist 是否存在
    if not DIST_DIR.exists():
        print(f"\n[错误] 未找到 dist 目录: {DIST_DIR}")
        print("请先执行 PyInstaller 打包:")
        print(f"  pyinstaller {APP_NAME}.spec")
        sys.exit(1)

    # 1. 从 dist 中删除 chromium 浏览器（复制前清理，简单直接）
    print("\n[1/8] 清理 dist 中的 chromium 浏览器...")
    clean_chromium_from_dist()

    # 2. 创建发布目录并复制
    if RELEASE_PKG.exists():
        try:
            shutil.rmtree(RELEASE_PKG)
        except PermissionError:
            import subprocess
            subprocess.run(['cmd', '/c', 'rmdir', '/S', '/Q', str(RELEASE_PKG)], check=False)
            if RELEASE_PKG.exists():
                print(f"  警告: 无法删除旧release目录，尝试直接覆盖")
    RELEASE_PKG.mkdir(parents=True, exist_ok=True)

    print("\n[2/8] 复制 PyInstaller dist 输出...")
    copytree(DIST_DIR, RELEASE_PKG)
    size_mb = sum(f.stat().st_size for f in RELEASE_PKG.rglob("*") if f.is_file()) / 1024 / 1024
    print(f"  当前大小: {size_mb:.1f} MB")

    # 4. 复制数据库（空库模板）
    print("\n[3/8] 复制数据库...")
    db_src = Path("data") / "golden_eagle_kpi.db"
    db_dst = RELEASE_PKG / "data" / "golden_eagle_kpi.db"
    if db_src.exists():
        db_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_src, db_dst)
        print(f"  数据库: {db_dst} ({db_dst.stat().st_size / 1024 / 1024:.1f} MB)")
    else:
        print("  [警告] 未找到数据库文件，发布包将不含数据库")

    # 5. 创建 data/exports 目录
    print("\n[4/8] 创建 data/exports 目录...")
    (RELEASE_PKG / "data" / "exports").mkdir(parents=True, exist_ok=True)

    # 6. 创建 CHANGELOG.txt
    print("\n[5/8] 生成 CHANGELOG.txt...")
    changelog = RELEASE_PKG / "CHANGELOG.txt"
    changelog.write_text(
        "金鹰工单KPI管理系统 更新日志\n"
        "============================\n"
        "\n"
        "【v0.0.10】2026-04-27\n"
        "─────────────────────────────────\n"
        "\n"
        "◆ 同步功能全面修复\n"
        "  - 修复 _update_progress 参数不匹配(TypeError导致同步崩溃)\n"
        "  - 修复 frozen(exe)路径问题：数据持久化到exe旁边data/目录\n"
        "  - 修复 圆环进度条display控制\n"
        "  - 爬虫失败自动截图到data/logs/并记录日志\n"
        "  - 新增空文件检测：下载0字节文件时抛异常而非静默通过\n"
        "  - exe(pythonw)无控制台输出：重定向stdout到data/logs/app.log\n"
        "\n"
        "◆ 数据入库优化\n"
        "  - 随手拍导入：普通模式读取处理合并单元格(merged_spans map)\n"
        "  - 工单+随手拍并发入库(ThreadPoolExecutor)\n"
        "  - 暴力覆盖策略：同步时先删旧数据再全量插入\n"
        "\n"
        "\n"
        "【v0.0.9】2026-04-24\n"
        "─────────────────────────────────\n"
        "\n"
        "◆ 缺陷修复（关键）\n"
        "  - 随手拍数据同步丢失：BI导出的Excel中A-E列存在大量合并单元格，\n"
        "    旧代码read_only=True只读首行值，后续成员行emp_id为空被跳过，\n"
        "    导致随手拍统计大量丢失（如李亮4月只统计到25条，实际应为42条）\n"
        "  - 修复方案：两步扫描法 —— 先预扫描构建合并单元格span map，\n"
        "    对每个合并首行按其跨行数展开写入多条独立记录\n"
        "\n"
        "◆ 数据影响\n"
        "  - 修复后随手拍导入量：约74K条 → 约96K条（新增约22K条）\n"
        "  - 修复前发起统计大量偏低，修复后与BI原始数据一致\n"
        "\n"
        "\n"
        "【v0.0.8】2026-04-22\n"
        "─────────────────────────────────\n"
        "\n"
        "◆ 界面优化\n"
        "  - 搜索页\"发起人\"标签改为\"打卡人\"，更贴合实际业务场景\n"
        "\n"
        "◆ 功能完善\n"
        "  - 搜索页点击搜索后自动刷新统计数据\n"
        "  - 设置页同步时间与搜索页保持同步\n"
        "\n"
        "\n"
        "【v0.0.7】2026-04-21\n"
        "─────────────────────────────────\n"
        "\n"
        "◆ 缺陷修复\n"
        "  - AI对话SSE格式修复，解决流式输出被双引号包裹的问题\n"
        "  - PyInstaller打包后同步功能不可用（Playwright driver排除问题）\n"
        "  - ORM模型与数据库列不一致导致的批量导入失败\n"
        "\n"
        "◆ 架构优化\n"
        "  - 移除work_tickets双写逻辑，snapshots与work_tickets完全独立\n"
        "  - 暴力覆盖策略：同步时先删旧数据再全量插入\n"
        "  - AI SYSTEM_PROMPT重构，强调自主分析而非机械引用预计算值\n"
        "\n",
        encoding="utf-8",
    )

    # 7. 创建 README.txt
    print("\n[6/8] 生成 README.txt...")
    readme = RELEASE_PKG / "README.txt"
    readme.write_text(
        "金鹰工单KPI管理系统 v0.0.10\n"
        "============================\n"
        "\n"
        "[快速启动]\n"
        "  双击 [金鹰工单KPI.exe] 即可启动系统\n"
        "  启动后会自动打开浏览器访问管理界面\n"
        "  首次启动可能需要几秒钟，请耐心等待\n"
        "\n"
        "[访问地址]\n"
        "  http://127.0.0.1:8765\n"
        "\n"
        "[关闭系统]\n"
        "  关闭控制台窗口或按 Ctrl+C\n"
        "\n"
        "[数据目录]\n"
        "  data/              - 数据库和日志存放位置\n"
        "  data/exports/      - 导出文件存放位置\n"
        "\n"
        "[数据同步]\n"
        "  在管理界面中点击 [数据同步] 按钮即可\n"
        "  同步功能需要本机已安装浏览器（优先 Google Chrome）\n"
        "  如果未安装 Chrome，系统会自动使用 Microsoft Edge（Windows自带）\n"
        "  同步功能依赖本机 Node.js 环境，请确保已安装\n"
        "\n"
        "[目录说明]\n"
        "  金鹰工单KPI.exe     主程序（双击启动）\n"
        "  _internal/           运行时文件（请勿修改）\n"
        "  data/                数据存储（数据库、导出文件、日志）\n"
        "  tools/               高级工具脚本（数据库维护等）\n"
        "\n"
        "[版本] v0.0.10 | 2026-04-27\n"
        "[更新说明]\n"
        "  同步功能全面修复：解决TypeError崩溃、frozen路径、\n"
        "  爬虫失败截图、空文件检测、日志重定向等问题\n"
        "  随手拍合并单元格处理优化，并发入库提升同步速度\n",
        encoding="utf-8",
    )

    # 8. 创建 tools 目录
    print("\n[7/8] 复制 tools 脚本...")
    tools_src = Path("tools")
    tools_dst = RELEASE_PKG / "tools"
    if tools_src.exists():
        copytree(tools_src, tools_dst)
    else:
        tools_dst.mkdir(parents=True, exist_ok=True)
        (tools_dst / "__init__.py").write_text("", encoding="utf-8")

    # 9. 打包 ZIP
    print("\n[8/8] 打包为 ZIP...")
    zip_path = RELEASE / f"{APP_NAME}-{VERSION}.zip"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(RELEASE_PKG.rglob("*")):
            if file.is_file():
                arcname = f"{APP_NAME}-{VERSION}/{file.relative_to(RELEASE_PKG)}"
                zf.write(file, arcname)

    # 10. 输出统计信息
    total_files = sum(1 for _ in RELEASE_PKG.rglob("*") if _.is_file())
    total_size = sum(f.stat().st_size for f in RELEASE_PKG.rglob("*") if f.is_file())
    zip_size = zip_path.stat().st_size

    print("\n" + "=" * 50)
    print(f"[完成] 发布包已生成: {zip_path}")
    print(f"  文件数量: {total_files}")
    print(f"  解压大小: {total_size / 1024 / 1024:.1f} MB")
    print(f"  ZIP 大小: {zip_size / 1024 / 1024:.1f} MB")
    print("=" * 50)


if __name__ == "__main__":
    build_release()
