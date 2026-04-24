"""金鹰工单KPI v0.0.9 - 发布包构建脚本

将 PyInstaller 产出 + 现有数据库 + 文档 打包为最终发布包
"""
import shutil
import zipfile
import sqlite3
from pathlib import Path

PROJECT = Path(__file__).parent
DIST = PROJECT / "dist" / "金鹰工单KPI"
RELEASE = PROJECT / "releases"
RELEASE_PKG = RELEASE / "金鹰工单KPI-v0.0.9"
SRC_DB = PROJECT / "data" / "golden_eagle_kpi.db"

# 清理旧发布
if RELEASE_PKG.exists():
    shutil.rmtree(RELEASE_PKG)
RELEASE_PKG.mkdir(parents=True, exist_ok=True)

# 0. 将正确数据库先复制到 DIST（exe 运行时读取的位置），在 step1 之前
print("[0/7] 准备正确数据库到 dist...")
DIST_DATA = DIST / "data"
DIST_DATA.mkdir(parents=True, exist_ok=True)
if SRC_DB.exists():
    # 先 checkpoint WAL，确保主文件包含所有数据
    _conn = sqlite3.connect(str(SRC_DB))
    try:
        _conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        _conn.close()
    # 复制主库 + WAL + SHM（如果有）
    shutil.copy2(SRC_DB, DIST_DATA / "golden_eagle_kpi.db")
    for _suf in ("-wal", "-shm"):
        _wal = SRC_DB.parent / (SRC_DB.name + _suf)
        if _wal.exists():
            shutil.copy2(_wal, DIST_DATA / ("golden_eagle_kpi.db" + _suf))
    print(f"  已将 {SRC_DB.stat().st_size/1024/1024:.1f} MB 数据库放入 dist")
else:
    print("  [警告] 源数据库不存在")

# 1. 复制 PyInstaller 产出（整个目录）
print("[1/7] 复制 exe 和运行时...")
for item in DIST.iterdir():
    if item.name == "data":
        # 跳过 PyInstaller 创建的空 data 目录，后面手动复制数据库
        continue
    if item.is_dir():
        shutil.copytree(item, RELEASE_PKG / item.name)
    else:
        shutil.copy2(item, RELEASE_PKG / item.name)

# 2. 删除 Playwright 自带浏览器（我们用 channel="chrome" 调用系统Chrome）
print("[2/7] 清理 Playwright 浏览器二进制...")
browsers_dir = RELEASE_PKG / "_internal" / "playwright" / "driver" / "package" / ".local-browsers"
if browsers_dir.exists():
    browser_size = sum(f.stat().st_size for f in browsers_dir.rglob("*") if f.is_file())
    shutil.rmtree(browsers_dir, ignore_errors=True)
    print(f"  已删除浏览器: {browser_size/1024/1024:.1f} MB")
else:
    print("  无浏览器目录（已是精简版）")

# 注意：不再清理 driver/package 下的其他目录
# playwright driver (node.exe + JS) 是必须的，不能删除
# 只删除 .local-browsers（chromium/firefox/webkit 完整浏览器二进制）

# 3. 复制现有数据库（开盒即有数据）
print("[3/7] 复制数据库...")
db_src = PROJECT / "data" / "golden_eagle_kpi.db"
data_dir = RELEASE_PKG / "data"
data_dir.mkdir(exist_ok=True)
if db_src.exists():
    # 先 checkpoint WAL 模式，确保主文件包含所有数据，再复制
    import sqlite3
    _tmp_conn = sqlite3.connect(str(db_src))
    try:
        _tmp_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        _tmp_conn.close()
    shutil.copy2(db_src, data_dir / "golden_eagle_kpi.db")
    # 也复制 WAL 和 SHM（如果存在）
    for _suffix in ["-wal", "-shm"]:
        _wal_src = db_src.parent / (db_src.name + _suffix)
        if _wal_src.exists():
            shutil.copy2(_wal_src, data_dir / ("golden_eagle_kpi.db" + _suffix))
    print(f"  数据库: {db_src.stat().st_size / 1024 / 1024:.1f} MB")
else:
    print("  [警告] 数据库文件不存在，用户首次启动将创建空数据库")

# 创建 exports 和 logs 目录
(data_dir / "exports").mkdir(exist_ok=True)
(data_dir / "logs").mkdir(exist_ok=True)

# 4. 复制工具脚本（供高级用户使用）
print("[4/7] 复制工具脚本...")
tools_dir = RELEASE_PKG / "tools"
tools_dir.mkdir(exist_ok=True)

tool_scripts = [
    "migrate_db.py",
    "backfill_data.py",
    "sync_data.py",
    "add_admin.py",
    "import_personnel.py",
    "import_snapshots.py",
    "import_manager_list.py",
    "create_kpi_thresholds.py",
]
for script in tool_scripts:
    src = PROJECT / script
    if src.exists():
        shutil.copy2(src, tools_dir / script)

# 复制 requirements.txt（供高级用户 pip install）
req_src = PROJECT / "requirements.txt"
if req_src.exists():
    shutil.copy2(req_src, RELEASE_PKG / "requirements.txt")

# 5. 写更新日志 CHANGELOG.txt
print("[5/7] 生成更新日志...")
changelog = RELEASE_PKG / "CHANGELOG.txt"
changelog.write_text(
    "金鹰工单KPI管理系统 更新日志\n"
    "============================\n"
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

# 6. 写 README.txt（面向普通用户的简明说明）
print("[6/7] 生成说明文件...")
readme = RELEASE_PKG / "README.txt"
readme.write_text(
    "金鹰工单KPI管理系统 v0.0.9\n"
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
    "  Node.js 已内置在程序中，无需额外安装\n"
    "\n"
    "[目录说明]\n"
    "  金鹰工单KPI.exe     主程序（双击启动）\n"
    "  _internal/           运行时文件（请勿修改）\n"
    "  data/                数据存储（数据库、导出文件、日志）\n"
    "  tools/               高级工具脚本（数据库维护等）\n"
    "\n"
    "[版本] v0.0.9 | 2026-04-24\n"
    "[更新说明]\n"
    "  本次更新修复了随手拍数据同步丢失的严重Bug，\n"
    "  修复后统计数量与BI原始数据一致\n",
    encoding="utf-8",
)

# 7. 打 zip
print("[7/7] 打包压缩...")
zip_path = RELEASE / "金鹰工单KPI-v0.0.9.zip"
if zip_path.exists():
    zip_path.unlink()

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for file in sorted(RELEASE_PKG.rglob("*")):
        if file.is_file():
            arcname = f"金鹰工单KPI-v0.0.9/{file.relative_to(RELEASE_PKG)}"
            zf.write(file, arcname)

zip_size = zip_path.stat().st_size / 1024 / 1024
pkg_count = sum(1 for _ in RELEASE_PKG.rglob("*") if _.is_file())
print(f"\n[完成] 发布包: {zip_path}")
print(f"  文件数: {pkg_count}")
print(f"  压缩后: {zip_size:.1f} MB")
print(f"  解压后: {sum(f.stat().st_size for f in RELEASE_PKG.rglob('*') if f.is_file()) / 1024 / 1024:.1f} MB")
