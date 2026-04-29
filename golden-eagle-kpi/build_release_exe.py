# -*- coding: utf-8 -*-
"""金鹰工单KPI v1.0.0 - 发布包构建脚本
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
VERSION = "v1.0.0"
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

    # 5.5 复制 VERSION 文件（供后端 update.py 动态读取）
    print("\n[4.5/8] 复制 VERSION 文件...")
    ver_src = Path("VERSION")
    ver_dst = RELEASE_PKG / "VERSION"
    if ver_src.exists():
        shutil.copy2(ver_src, ver_dst)
        print(f"  VERSION: {ver_src.read_text(encoding='utf-8').strip()}")
    else:
        ver_dst.write_text(VERSION, encoding="utf-8")
        print(f"  [警告] 未找到 VERSION 文件，已生成默认版本 {VERSION}")

    # 6. 创建 CHANGELOG.txt
    print("\n[5/8] 生成 CHANGELOG.txt...")
    changelog = RELEASE_PKG / "CHANGELOG.txt"
    changelog.write_text(
        "金鹰工单KPI管理系统 更新日志\n"
        "========================================\n"
        "\n"
        "【v1.0.0】2026-04-29\n"
        "────────────────────────────────────────\n"
        "\n"
        "◆ 全新UI风格：新拟态（Neumorphism）大改版\n"
        "  ─ 视觉升级：全系统从「液态玻璃」迁移至「新拟态」设计语言\n"
        "  ─ 背景色系：浅色（#E8E8EC）和深色（#1C1C24）双主题\n"
        "  ─ 凸起按钮：box-shadow营造「从背景中浮起」的立体感\n"
        "  ─ 按下状态：box-shadow反转为「凹陷」效果，触觉反馈真实\n"
        "  ─ 阴影层次：5层阴影叠加（亮侧+暗侧+内阴影），质感细腻\n"
        "  ─ 配色体系：薰衣草紫（#B8A8D8）为主色调，冰蓝/橙/绿/红辅助\n"
        "  ─ 动效曲线：cubic-bezier(0.34, 1.56, 0.64, 1)弹簧缓动\n"
        "  ─ 卡片组件：玻璃态改新拟态凸起，圆角28px，hover上移2px+阴影加深\n"
        "  ─ 顶部栏：独立凸起设计，border-radius 28px，投影10px\n"
        "  ─ 输入框/下拉框：新拟态凹陷样式，日期选择器重做\n"
        "  ─ 同步按钮：脉冲动画+旋转光环，进度ring渐变色进度条\n"
        "\n"
        "◆ Phase 2：筹建专项计划管理系统（WY系统）\n"
        "  ─ 数据源：http://58.213.109.123:8181（MD5登录）\n"
        "  ─ 爬虫：wy_crawler.py（Crawler类），HTTP API直连\n"
        "  ─ 模型：SpecialPlan表，字段含project_name/special_name/plan_state等\n"
        "  ─ 8种状态实时计算：即将开始/进行中/即将到期/到期预警/逾期报警/已逾期/已完成/已暂停\n"
        "  ─ 甘特图展示：年月切换，8状态按颜色区分，跨月时间轴\n"
        "  ─ 筹建专项统计：总额/预警数/进行中/已完成，支持项目过滤\n"
        "  ─ 筹建人员绩效：按负责人统计专项完成情况\n"
        "  ─ 筹建预警列表：逾期和即将到期专项明细\n"
        "\n"
        "◆ Phase 2：IPMS设备巡检/维保系统\n"
        "  ─ 数据源：https://ipms.jinying.com（Bearer Token登录）\n"
        "  ─ 爬虫：ipms_crawler.py（IPMSCrawler类）\n"
        "  ─ 模型：IPMSTask表，字段含task_type/task_state_name/start_time等\n"
        "  ─ 任务类型：巡检(patrol)和维保(maintain)分开管理\n"
        "  ─ 4状态实时计算：今日新增/进行中/已完成/已逾期\n"
        "  ─ 月筛选+状态+名称+日期多维查询\n"
        "  ─ IPMS任务统计：各状态数量，支持按项目/类型过滤\n"
        "  ─ IPMS人员绩效：按巡检人员统计任务完成率\n"
        "  ─ IPMS预警列表：已逾期任务明细\n"
        "\n"
        "◆ 聚合同步：一键同步三系统\n"
        "  ─ topbar一键触发：BI工单+筹建专项+IPMS设备同时开始同步\n"
        "  ─ 同步页面重构：左右分栏，左侧流程总览，右侧各系统独立入口\n"
        "  ─ 流程卡片：BI系统(紫)/筹建专项(蓝)/IPMS设备(橙)三色独立进度条\n"
        "  ─ 并发执行：三系统任务并发，总耗时<6分钟\n"
        "  ─ 独立同步：各系统可单独同步，互不影响\n"
        "  ─ 日志查看：按钮整合在流程卡片底部，一键跳转\n"
        "\n"
        "◆ 同步模块全面优化（深度重构）\n"
        "  ─ 浏览器策略：自动检测Chrome/Edge路径，优先Chrome，fallback到Edge\n"
        "  ─ 注册表探测：从HKLM/HKCU两级注册表读取Chrome路径\n"
        "  ─ executable_path直连：绕过Playwright channel模式，避免路径不一致\n"
        "  ─ 不安装Chromium：不再下载约1.2GB冗余浏览器，节省打包体积\n"
        "  ─ 总超时保护：整个BI下载任务5分钟超时，防止挂起\n"
        "  ─ 空文件检测：下载文件<10KB判定为无效，抛异常终止同步\n"
        "  ─ 随手拍两步扫描：普通模式读merged_cells构建span map，read_only流式读取数据\n"
        "  ─ 分批提交：bulk_save_objects每1000条commit一次，防止内存爆炸\n"
        "  ─ 并发入库：工单+随手拍用ThreadPoolExecutor同时写库，WAL锁不冲突\n"
        "  ─ 进度反馈：下载阶段45%→入库阶段45%（工单24%/随手拍21%）→映射刷新10%\n"
        "  ─ Playwright预检：同步前验证node.exe存在，不存在则提前报错\n"
        "\n"
        "◆ IPMS巡检/维保统计修复\n"
        "  ─ 状态判定：完成/过期/未派单逻辑修正\n"
        "  ─ 今日新增：基于start_time而非created_at，更准确反映当日任务\n"
        "  ─ 巡检/维保：分开统计卡片，独立筛选\n"
        "\n"
        "◆ 驾驶舱（首页）全面升级\n"
        "  ─ 左侧：本月工单统计（发起/完成/完成率/及时率）\n"
        "  ─ 右侧：综合评分+预警工单列表\n"
        "  ─ 底部：金鹰PLAN/巡检/维保三系统概览卡片，点击跳转\n"
        "  ─ 甘特图：筹建专项进度可视化，月份切换器\n"
        "  ─ 统计网格：8状态统计（4列均匀），实时计算\n"
        "  ─ 专项明细表：筹建专项列表+筛选\n"
        "\n"
        "◆ 前端API.request白名单\n"
        "  ─ 新增 /wy/* 和 /ipms/* 接口授权\n"
        "  ─ 筹建专项/设备任务接口支持token header项目过滤\n"
        "\n"
        "◆ 系统工具脚本\n"
        "  ─ 同步状态轮询：_poll_ipms.py\n"
        "  ─ 数据库验证：verify_zip.py、verify_zip_import.py\n"
        "  ─ 端到端测试：e2e_verify.py\n"
        "  ─ 全量ZIP测试：test_full_zip.py\n"
        "\n"
        "\n"
        "【v0.0.10】2026-04-27\n"
        "────────────────────────────────────────\n"
        "\n"
        "◆ 同步功能全面修复\n"
        "  ─ 修复 _update_progress 参数不匹配(TypeError导致同步崩溃)\n"
        "  ─ 修复 frozen(exe)路径问题：数据持久化到exe旁边data/目录\n"
        "  ─ 爬虫失败自动截图到data/logs/并记录日志\n"
        "  ─ 空文件检测：下载0字节文件时抛异常\n"
        "  ─ exe(pythonw)无控制台：重定向stdout到data/logs/app.log\n"
        "  ─ 随手拍合并单元格处理优化\n"
        "  ─ 并发入库：工单+随手拍同时写入\n"
        "  ─ 端到端验证：100007工单+76992随手拍导入成功\n"
        "\n"
        "\n"
        "【v0.0.9】2026-04-24\n"
        "────────────────────────────────────────\n"
        "\n"
        "◆ 构建优化（打包体积缩减89%）\n"
        "  ─ 根因：build_release_exe.py中copy_playwright_driver()把chromium（约1.2GB）打包\n"
        "  ─ 修复：改用clean_playwright_driver()，构建后删除playwright/driver\n"
        "  ─ 效果：ZIP从492MB→46MB\n"
        "\n"
        "\n"
        "【v0.0.8】2026-04-22\n"
        "────────────────────────────────────────\n"
        "\n"
        "◆ 发起人→打卡人\n"
        "  ─ 字段名从initiator改为打卡人（clock_user）\n"
        "\n"
        "◆ 版本号显示\n"
        "  ─ 驾驶舱右上角显示当前版本号\n"
        "\n"
        "◆ 搜索后刷新统计\n"
        "  ─ 搜索完成后自动刷新仪表盘统计数据\n"
        "\n"
        "\n"
        "【v0.0.7】2026-04-21\n"
        "────────────────────────────────────────\n"
        "\n"
        "◆ SSE推送修复\n"
        "  ─ 后端SSE流式推送前端进度，实时显示同步状态\n"
        "\n"
        "◆ PyInstaller同步功能修复\n"
        "  ─ main.py frozen模式重定向stdout\n"
        "\n"
        "\n"
        "【v0.0.5 - v0.0.6】\n"
        "────────────────────────────────────────\n"
        "\n"
        "◆ ORM列同步修复\n"
        "  ─ 模型字段变更同步到迁移脚本\n"
        "  ─ bulk_save_objects静默失败问题修复\n"
        "\n",
        encoding="utf-8",
    )

    # 7. 创建 README.txt
    print("\n[6/8] 生成 README.txt...")
    readme = RELEASE_PKG / "README.txt"
    readme.write_text(
        "金鹰工单KPI管理系统 v1.0.0\n"
        "========================================\n"
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
        "  data/                - 数据库和日志存放位置\n"
        "  data/exports/        - 导出文件存放位置\n"
        "  data/downloads/      - 临时下载文件\n"
        "  data/logs/           - 应用运行日志\n"
        "\n"
        "[三大数据系统]\n"
        "  BI工单系统           - 随手拍+内外包工单明细\n"
        "  筹建专项计划（WY）    - 项目筹建专项进度跟踪\n"
        "  IPMS设备管理          - 设备巡检/维保任务\n"
        "\n"
        "[数据同步]\n"
        "  顶部栏同步按钮        - 一键同步全部三系统（BI+WY+IPMS）\n"
        "  同步页面              - 各系统独立同步入口，互不影响\n"
        "  同步需要本机已安装浏览器（优先 Google Chrome，其次 Edge）\n"
        "  不需要额外安装Chromium，使用系统自带浏览器\n"
        "\n"
        "[页面导航]\n"
        "  驾驶舱                - 统计概览、甘特图、三系统卡片\n"
        "  搜索                  - 工单多条件查询、导出Excel\n"
        "  人员                  - 人员绩效、编辑管理\n"
        "  计划                  - 金鹰PLAN/巡检/维保三级分栏\n"
        "  同步                  - 三系统同步状态、启动同步\n"
        "\n"
        "[目录说明]\n"
        "  金鹰工单KPI.exe       主程序（双击启动）\n"
        "  _internal/            运行时文件（请勿修改/删除）\n"
        "  data/                 数据存储（数据库、导出、日志）\n"
        "  tools/                高级工具脚本（数据库维护等）\n"
        "\n"
        "[版本] v1.0.0 | 2026-04-29\n"
        "[核心更新]\n"
        "  ★ UI风格大改：液态玻璃 → 新拟态（Neumorphism）\n"
        "    - 凸起按钮、凹陷输入框、弹簧缓动动画\n"
        "    - 浅色/深色双主题，薰衣草紫主色调\n"
        "  ★ Phase 2全面上线：筹建专项+IPMS设备管理\n"
        "    - 三系统聚合同步，一键触发\n"
        "    - 甘特图+8状态统计+4状态卡片\n"
        "  ★ 同步模块重构：浏览器自动检测+并发入库\n"
        "    - 优先Chrome，其次Edge，不安装Chromium\n"
        "    - 工单+随手拍并发写入，总超时5分钟保护\n"
        "  ★ 打包体积优化：ZIP仅46MB（减少89%）\n",
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
