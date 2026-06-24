"""金鹰工单KPI管理 - BI爬虫客户端

封装 Playwright 自动化流程：
1. OA登录 → BI系统 → 选择报表 → 填日期 → 导出Excel
2. 下载文件存入 downloads/ 目录
3. 返回下载的Excel文件路径列表

调用方式：
    client = BiClient(account="xxx", password="xxx")
    files = await client.fetch_all()  # -> ["path/to/工单明细.xlsx", "path/to/随手拍.xlsx"]
"""
import asyncio
import os
import sys
import glob
import time as time_mod
from datetime import datetime
from pathlib import Path
from typing import Optional

# 确保 stdout/stderr 支持 UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


class BiClient:
    """BI系统客户端：自动化下载工单和随手拍Excel"""

    # 报表配置
    REPORTS = [
        {"name": "工单明细查询表", "wait_longer": False},
        {"name": "随手拍工单统计明细表", "wait_longer": True},
    ]

    def __init__(self, account: str, password: str, download_dir: str = None):
        self.account = account
        self.password = password
        if download_dir:
            self.download_dir = download_dir
        else:
            # PyInstaller打包后用exe旁边的data/downloads，源码运行用项目根目录/downloads
            if getattr(sys, 'frozen', False):
                base = Path(sys.executable).parent
                self.download_dir = str(base / "data" / "downloads")
            else:
                self.download_dir = str(Path(__file__).parent.parent.parent / "downloads")
        os.makedirs(self.download_dir, exist_ok=True)

    async def fetch_all(self) -> list[str]:
        """抓取所有报表，返回下载的Excel文件路径列表"""
        async with self._create_browser() as (browser, ctx):
            try:
                page = await self._login(ctx)
                bi_page = await self._enter_bi(page)
                if not bi_page:
                    raise RuntimeError("无法进入BI系统")

                downloaded_files = []
                for report in self.REPORTS:
                    rname = report["name"]
                    wait_long = report["wait_longer"]

                    ok = await self._select_report(bi_page, rname)
                    if ok:
                        await self._fill_dates(bi_page, rname, wait_long)
                        file_path = await self._export_excel(bi_page, rname, wait_long)
                        if file_path:
                            downloaded_files.append(file_path)

                return downloaded_files
            except Exception as e:
                print(f"[爬虫] 抓取异常: {e}")
                raise

    async def fetch_tickets(self) -> Optional[str]:
        """仅抓取工单明细表，返回Excel文件路径"""
        async with self._create_browser() as (_, ctx):
            try:
                page = await self._login(ctx)
                bi_page = await self._enter_bi(page)
                if not bi_page:
                    return None

                ok = await self._select_report(bi_page, "工单明细查询表")
                if ok:
                    await self._fill_dates(bi_page, "工单明细查询表")
                    return await self._export_excel(bi_page, "工单明细查询表")
                return None
            except Exception:
                raise

    async def fetch_snapshots(self) -> Optional[str]:
        """仅抓取随手拍表，返回Excel文件路径"""
        async with self._create_browser() as (_, ctx):
            try:
                page = await self._login(ctx)
                bi_page = await self._enter_bi(page)
                if not bi_page:
                    return None

                ok = await self._select_report(bi_page, "随手拍工单统计明细表")
                if ok:
                    await self._fill_dates(bi_page, "随手拍工单统计明细表", wait_longer=True)
                    return await self._export_excel(bi_page, "随手拍工单统计明细表", wait_longer=True)
                return None
            except Exception:
                raise

    # ============================================================
    # 内部方法
    # ============================================================

    def _detect_browser_path(self) -> tuple[str | None, str | None]:
        """检测可用的浏览器路径，返回 (channel, executable_path)
        
        优先使用 executable_path 明确指定浏览器位置，
        避免 Playwright 的 channel 模式在不同环境下路径不一致的问题。
        """
        import shutil, winreg
        from pathlib import Path

        # Chrome 候选路径（按优先级排序）
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            shutil.which("chrome"),
            shutil.which("google-chrome"),
        ]
        # 注册表 HKLM Chrome
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
            path, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
            if path:
                chrome_paths.append(path)
        except Exception:
            pass
        # 注册表 HKCU Chrome
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
            path, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
            if path:
                chrome_paths.append(path)
        except Exception:
            pass

        for p in chrome_paths:
            if p and Path(p).exists():
                return ("chrome", str(Path(p).resolve()))

        # Edge 候选路径
        edge_paths = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            shutil.which("msedge"),
            os.path.expandvars(r"%PROGRAMFILES(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
        ]
        for p in edge_paths:
            if p and Path(p).exists():
                return ("msedge", str(Path(p).resolve()))

        return (None, None)

    def _create_browser(self):
        """创建浏览器上下文（异步上下文管理器）"""
        from playwright.async_api import async_playwright

        class BrowserContext:
            def __init__(self, client):
                self.client = client
                self.pw = None
                self.browser = None
                self.ctx = None

            async def __aenter__(self):
                self.pw = await async_playwright().start()

                # 检测可用浏览器：优先 Chrome，降级 Edge
                channel, executable_path = self.client._detect_browser_path()
                if not channel:
                    raise RuntimeError(
                        "未检测到浏览器。需要 Google Chrome 或 Microsoft Edge。\n"
                        "请安装任一浏览器后重试：\n"
                        "  Chrome: https://www.google.com/chrome/\n"
                        "  Edge: https://www.microsoft.com/edge"
                    )

                browser_name = "Chrome" if channel == "chrome" else "Microsoft Edge"
                print(f"[爬虫] 使用浏览器: {browser_name} ({executable_path})")

                # 使用系统浏览器（只用 executable_path，不指定 channel）
                # channel 模式会让 Playwright 按预设路径搜索，与实际路径冲突
                # executable_path 直接指定浏览器位置，最可靠
                self.browser = await self.pw.chromium.launch(
                    executable_path=executable_path,
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-gpu",
                        "--disable-dev-shm-usage",
                        "--window-size=1536,864",
                        "--headless=new",
                    ]
                )
                self.ctx = await self.browser.new_context(
                    viewport={"width": 1536, "height": 864},
                    accept_downloads=True,
                    locale="zh-CN",
                )
                await self.ctx.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
                )
                return self.browser, self.ctx

            async def __aexit__(self, *args):
                # 捕获 TargetClosedError：浏览器在下载完成后可能已被系统关闭
                # （尤其是在下载大文件后），不影响已下载的文件
                from playwright._impl._errors import TargetClosedError
                try:
                    if self.ctx:
                        await self.ctx.close()
                except TargetClosedError:
                    print("[爬虫] 浏览器上下文已关闭，跳过清理")
                except Exception as e:
                    print(f"[爬虫] 清理上下文异常（非致命）: {e}")
                try:
                    if self.browser:
                        await self.browser.close()
                except Exception as e:
                    print(f"[爬虫] 关闭浏览器异常（非致命）: {e}")
                try:
                    if self.pw:
                        await self.pw.stop()
                except Exception as e:
                    print(f"[爬虫] 停止playwright异常（非致命）: {e}")

        return BrowserContext(self)

    @staticmethod
    def _daterange():
        t = datetime.now()
        return t.replace(month=1, day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d")

    # ---- Step 1: 登录OA ----
    async def _login(self, ctx):
        """登录OA系统"""
        print("[爬虫] 登录OA...")
        page = await ctx.new_page()
        await page.goto(
            "http://ecbpm.jinying.com:8090/wui/index.html?#/?_key=66mc5g",
            wait_until="networkidle", timeout=30000
        )
        await asyncio.sleep(3)

        await page.locator("#loginid").click(force=True)
        await page.locator("#loginid").fill(self.account)
        await page.locator("#userpassword").click(force=True)
        await page.locator("#userpassword").fill(self.password)
        await asyncio.sleep(0.3)

        # 点击登录按钮
        login_clicked = False
        for locator in ["#submit", "text=登陆", "text=登录"]:
            try:
                await page.locator(locator).first.click(timeout=5000)
                login_clicked = True
                break
            except Exception:
                continue

        if not login_clicked:
            raise RuntimeError("未找到登录按钮")

        # 等待登录完成
        try:
            await page.wait_for_selector("#loginid", state="hidden", timeout=20000)
            print("[爬虫] OA登录成功")
        except Exception:
            print("[爬虫] 登录状态不确定，继续...")

        await asyncio.sleep(5)
        return page

    # ---- Step 2: 进入BI ----
    async def _enter_bi(self, page):
        """进入BI决策系统"""
        print("[爬虫] 进入BI决策系统...")

        bi_clicked = False

        # 方法1: 主页面找
        try:
            el = page.locator("text=BI决策系统").first
            if await el.count() > 0 and await el.is_visible():
                await el.click()
                bi_clicked = True
        except Exception:
            pass

        # 方法2: iframe中找
        if not bi_clicked:
            for f in page.frames:
                try:
                    el = f.locator("text=BI决策系统").first
                    if await el.count() > 0:
                        await el.click()
                        bi_clicked = True
                        break
                except Exception:
                    pass

        # 方法3: JS搜索
        if not bi_clicked:
            clicked = await page.evaluate("""() => {
                const iframes = document.querySelectorAll('iframe');
                for (const iframe of iframes) {
                    try {
                        const doc = iframe.contentDocument || iframe.contentWindow.document;
                        const els = doc.querySelectorAll('*');
                        for (const el of els) {
                            if (el.textContent && el.textContent.trim() === 'BI决策系统' &&
                                el.children.length === 0 && el.offsetParent !== null) {
                                el.click();
                                return true;
                            }
                        }
                    } catch(e) {}
                }
                const mainEls = document.querySelectorAll('*');
                for (const el of mainEls) {
                    if (el.textContent && el.textContent.trim() === 'BI决策系统' &&
                        el.children.length === 0 && el.offsetParent !== null) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
            bi_clicked = bool(clicked)

        if not bi_clicked:
            print("[爬虫] 未找到'BI决策系统'，尝试坐标兜底")
            await page.mouse.click(1412, 686)

        # 等待新窗口
        bi_page = None
        for _ in range(20):
            await asyncio.sleep(2)
            for pg in page.context.pages:
                if pg != page and 'bii.jinying.com' in pg.url:
                    bi_page = pg
                    break
            if bi_page:
                break

        if bi_page:
            await bi_page.bring_to_front()
            await asyncio.sleep(5)
            print("[爬虫] 进入BI成功")
        else:
            print("[爬虫] 未找到BI窗口")

        return bi_page

    # ---- Step 3: 选择报表 ----
    async def _select_report(self, bi_page, report_name: str) -> bool:
        """选择报表"""
        print(f"[爬虫] 选择报表: {report_name}")

        # 展开"金鹰物业"
        expanded = await bi_page.evaluate("""() => {
            const nodes = document.querySelectorAll('.ant-tree-treenode');
            for (const n of nodes) {
                const t = n.querySelector('.ant-tree-title');
                if (t && t.textContent.trim().includes('金鹰物业')) {
                    const s = n.querySelector('.ant-tree-switcher');
                    if (s && !s.classList.contains('ant-tree-switcher_open')) {
                        s.click();
                        return 'clicked_switcher';
                    }
                    return 'already_open';
                }
            }
            return 'not_found';
        }""")
        print(f"  金鹰物业展开: {expanded}")
        await asyncio.sleep(2)

        if expanded == 'not_found':
            try:
                await bi_page.locator("text=金鹰物业").first.click(timeout=10000)
                await asyncio.sleep(2)
            except Exception:
                print("  找不到'金鹰物业'")
                return False

        # 点击报表名
        clicked = False
        strategies = [
            lambda: bi_page.locator(f".ant-tree-title:has-text('{report_name}')").first.click(timeout=5000),
            lambda: bi_page.locator(f"text={report_name}").first.click(timeout=5000),
        ]

        # 关键词策略
        keywords = []
        if "随手拍" in report_name:
            keywords = ["随手拍", "随手拍工单"]
        elif "工单明细" in report_name:
            keywords = ["工单明细查询", "工单明细"]

        for kw in keywords:
            strategies.append(lambda kw=kw: bi_page.locator(f".ant-tree-title:has-text('{kw}')").first.click(timeout=5000))
            strategies.append(lambda kw=kw: bi_page.locator(f"text={kw}").first.click(timeout=5000))

        for strategy in strategies:
            try:
                await strategy()
                clicked = True
                break
            except Exception:
                continue

        # JS兜底
        if not clicked:
            js_result = await bi_page.evaluate(f"""() => {{
                const nodes = document.querySelectorAll('.ant-tree-title');
                for (const n of nodes) {{
                    const t = n.textContent.trim();
                    if (t.includes('{report_name}')) {{
                        n.click();
                        return t;
                    }}
                }}
                return '';
            }}""")
            if js_result:
                clicked = True

        if not clicked:
            print(f"  找不到'{report_name}'")
            return False

        await asyncio.sleep(5)
        print(f"  报表已选择: {report_name}")
        return True

    # ---- Step 4: 填写日期 ----
    async def _fill_dates(self, bi_page, report_name: str, wait_longer: bool = False):
        """填写日期筛选"""
        print(f"[爬虫] 填写日期: {report_name}")
        s_date, e_date = self._daterange()

        for label_text, fill_val in [("开始时间", s_date), ("结束时间", e_date),
                                      ("开始日期", s_date), ("结束日期", e_date)]:
            filled = False
            try:
                # 找label旁的input
                input_info = await bi_page.evaluate(f"""() => {{
                    const labels = Array.from(document.querySelectorAll('*')).filter(el => {{
                        const t = (el.textContent||'').trim();
                        return t === "{label_text}" && el.children.length === 0 && el.offsetParent !== null;
                    }});
                    for (const label of labels) {{
                        const r = label.getBoundingClientRect();
                        const inputs = Array.from(document.querySelectorAll('input')).filter(inp => {{
                            const ir = inp.getBoundingClientRect();
                            return inp.offsetParent !== null && ir.width > 80 &&
                                   Math.abs(ir.y - r.y) < 50 && ir.x > r.x;
                        }});
                        if (inputs.length > 0) {{
                            const inp = inputs[0];
                            const ir = inp.getBoundingClientRect();
                            return {{
                                found: true,
                                x: Math.round(ir.x + ir.width/2),
                                y: Math.round(ir.y + ir.height/2),
                                val: inp.value
                            }};
                        }}
                    }}
                    return {{ found: false }};
                }}""")

                if input_info.get('found'):
                    ix, iy = input_info['x'], input_info['y']
                    await bi_page.mouse.click(ix, iy)
                    await asyncio.sleep(0.8)
                    await bi_page.keyboard.press("Control+a")
                    await asyncio.sleep(0.2)
                    await bi_page.keyboard.type(fill_val, delay=30)
                    await asyncio.sleep(0.3)
                    await bi_page.keyboard.press("Enter")
                    await asyncio.sleep(0.5)
                    filled = True
                    print(f"  {label_text}={fill_val}")
            except Exception as e:
                print(f"  文字定位{label_text}异常: {e}")

            if not filled:
                # 顺序定位
                date_inputs = await bi_page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('input')).filter(el => {
                        const r = el.getBoundingClientRect();
                        return el.offsetParent !== null && r.width > 80 && r.x > 250 &&
                               el.type === 'text' &&
                               (el.placeholder === '请选择' || el.value.match(/\\d{4}-\\d{2}-\\d{2}/));
                    }).map(el => ({
                        x: Math.round(el.getBoundingClientRect().x),
                        y: Math.round(el.getBoundingClientRect().y),
                        w: Math.round(el.getBoundingClientRect().width),
                        h: Math.round(el.getBoundingClientRect().height),
                    }));
                }""")
                idx = 0 if "开始" in label_text else 1
                if date_inputs and idx < len(date_inputs):
                    d = date_inputs[idx]
                    await bi_page.mouse.click(d['x'] + d['w']//2, d['y'] + d['h']//2)
                    await asyncio.sleep(0.8)
                    await bi_page.keyboard.press("Control+a")
                    await asyncio.sleep(0.2)
                    await bi_page.keyboard.type(fill_val, delay=30)
                    await asyncio.sleep(0.3)
                    await bi_page.keyboard.press("Enter")
                    await asyncio.sleep(0.5)
                    print(f"  {label_text}={fill_val}(顺序定位)")

        # 等待数据准备
        wait_sec = 30 if wait_longer else 5
        print(f"  等待{wait_sec}s数据加载...")
        await asyncio.sleep(wait_sec)

    # ---- Step 5: 导出Excel ----
    async def _export_excel(self, bi_page, report_name: str, wait_longer: bool = False) -> Optional[str]:
        """导出Excel并返回文件路径"""
        print(f"[爬虫] 导出Excel: {report_name}")

        # 关闭残留弹窗
        try:
            close_btns = await bi_page.evaluate("""() => {
                return Array.from(document.querySelectorAll('.ant-modal-close, [aria-label="Close"]')).filter(el => {
                    return el.offsetParent !== null;
                }).map(el => ({
                    x: Math.round(el.getBoundingClientRect().x + el.getBoundingClientRect().width/2),
                    y: Math.round(el.getBoundingClientRect().y + el.getBoundingClientRect().height/2)
                }));
            }""")
            for b in close_btns:
                await bi_page.mouse.click(b['x'], b['y'])
                await asyncio.sleep(1)
        except Exception:
            pass

        # 5a: 点击"导出"
        export_clicked = False
        try:
            el = bi_page.locator("text=导出").first
            if await el.count() > 0 and await el.is_visible():
                await el.click(timeout=5000)
                export_clicked = True
        except Exception:
            pass

        if not export_clicked:
            # 坐标兜底
            export_btns = await bi_page.evaluate("""() => {
                return Array.from(document.querySelectorAll('*')).filter(el => {
                    const r = el.getBoundingClientRect();
                    const t = (el.textContent||'').trim();
                    return t === '导出' && r.y < 150 && r.x > 800 &&
                           r.width > 10 && r.height > 10 && el.children.length === 0;
                }).map(el => ({
                    x: Math.round(el.getBoundingClientRect().x + el.getBoundingClientRect().width/2),
                    y: Math.round(el.getBoundingClientRect().y + el.getBoundingClientRect().height/2),
                }));
            }""")
            if export_btns:
                await bi_page.mouse.click(export_btns[0]['x'], export_btns[0]['y'])
                export_clicked = True

        if not export_clicked:
            print("  未找到'导出'按钮")
            return None

        await asyncio.sleep(2)

        # 5b: 点击"批量导出Excel"
        batch_clicked = False
        for text in ["批量导出Excel", "批量导出excel"]:
            try:
                el = bi_page.locator(f"text={text}").first
                if await el.count() > 0 and await el.is_visible():
                    await el.click(timeout=5000)
                    batch_clicked = True
                    break
            except Exception:
                continue

        if not batch_clicked:
            # 下拉菜单兜底
            items = await bi_page.evaluate("""() => {
                const items = document.querySelectorAll('.ant-dropdown-menu-item, [role="menuitem"]');
                return Array.from(items).filter(el => {
                    const t = (el.textContent||'').trim();
                    return t.includes('Excel') && el.offsetParent !== null;
                }).map(el => ({
                    x: Math.round(el.getBoundingClientRect().x + el.getBoundingClientRect().width/2),
                    y: Math.round(el.getBoundingClientRect().y + el.getBoundingClientRect().height/2),
                }));
            }""")
            if items:
                await bi_page.mouse.click(items[0]['x'], items[0]['y'])
                batch_clicked = True

        if not batch_clicked:
            print("  未找到'批量导出Excel'")
            return None

        await asyncio.sleep(2)

        # 5c: 选择表格本体
        try:
            checkbox_info = await bi_page.evaluate("""() => {
                const checkboxes = document.querySelectorAll('.ant-checkbox, input[type="checkbox"], .ant-checkbox-wrapper');
                return Array.from(checkboxes).filter(el => {
                    const r = el.getBoundingClientRect();
                    return el.offsetParent !== null && r.width > 5;
                }).map(el => ({
                    x: Math.round(el.getBoundingClientRect().x + el.getBoundingClientRect().width/2),
                    y: Math.round(el.getBoundingClientRect().y + el.getBoundingClientRect().height/2),
                }));
            }""")
            if checkbox_info:
                await bi_page.mouse.click(checkbox_info[0]['x'], checkbox_info[0]['y'])
                await asyncio.sleep(1)
        except Exception:
            pass

        # 5d: 再次点击"批量导出Excel"
        batch2_clicked = False
        for selector in ["button:has-text('批量导出Excel')", ".ant-btn-primary:has-text('批量导出')"]:
            try:
                el = bi_page.locator(selector).first
                if await el.count() > 0 and await el.is_visible():
                    await el.click(timeout=5000)
                    batch2_clicked = True
                    break
            except Exception:
                continue

        if not batch2_clicked:
            # 兜底找蓝色按钮
            primary_btns = await bi_page.evaluate("""() => {
                return Array.from(document.querySelectorAll('.ant-btn-primary, button')).filter(el => {
                    const r = el.getBoundingClientRect();
                    const t = (el.textContent||'').trim();
                    return el.offsetParent !== null && r.width > 30 &&
                           (t.includes('批量') || t.includes('导出') || t.includes('确定') || t.includes('确认'));
                }).map(el => ({
                    x: Math.round(el.getBoundingClientRect().x + el.getBoundingClientRect().width/2),
                    y: Math.round(el.getBoundingClientRect().y + el.getBoundingClientRect().height/2),
                }));
            }""")
            if primary_btns:
                await bi_page.mouse.click(primary_btns[0]['x'], primary_btns[0]['y'])
                batch2_clicked = True

        await asyncio.sleep(2)

        # 5e: 点击蓝色"确定"
        confirm_clicked = False
        for selector in ["button:has-text('确定')", "text=确定"]:
            try:
                el = bi_page.locator(selector).first
                if await el.count() > 0 and await el.is_visible():
                    await el.click(timeout=5000)
                    confirm_clicked = True
                    break
            except Exception:
                continue

        if not confirm_clicked:
            try:
                primary_ok = bi_page.locator(".ant-btn-primary").last
                if await primary_ok.count() > 0 and await primary_ok.is_visible():
                    await primary_ok.click(timeout=5000)
                    confirm_clicked = True
            except Exception:
                pass

        await asyncio.sleep(2)

        # 关闭残留弹窗
        try:
            await bi_page.evaluate("""() => {
                document.querySelectorAll('.ant-modal-close, [aria-label="Close"]').forEach(el => {
                    if (el.offsetParent !== null) el.click();
                });
                document.querySelectorAll('button').forEach(el => {
                    const t = (el.textContent||'').trim();
                    if ((t === '取消' || t === '关闭') && el.offsetParent !== null) el.click();
                });
            }""")
            await asyncio.sleep(2)
        except Exception:
            pass

        # 5f: 等待下载
        print("  等待下载...")
        timeout_sec = 600 if wait_longer else 90
        existing_xlsx = set(glob.glob(os.path.join(self.download_dir, "*.xlsx")))
        start_time = time_mod.time()
        downloaded_file = None

        # 双保险：download事件 + 文件轮询
        download_event = None

        async def wait_download():
            nonlocal download_event
            try:
                download_event = await bi_page.wait_for_event("download", timeout=timeout_sec * 1000)
            except Exception:
                pass

        download_task = asyncio.create_task(wait_download())

        while time_mod.time() - start_time < timeout_sec:
            await asyncio.sleep(3)
            elapsed = int(time_mod.time() - start_time)

            # 检查download事件
            if download_event:
                try:
                    fn = download_event.suggested_filename or f"{report_name}.xlsx"
                    path = os.path.join(self.download_dir, fn)
                    await download_event.save_as(path)
                    fsize = os.path.getsize(path)
                    if fsize > 10000:
                        print(f"  下载成功(download事件): {fn} ({fsize} bytes)")
                        downloaded_file = path
                        break
                except Exception:
                    download_event = None

            # 检查新文件
            current_xlsx = set(glob.glob(os.path.join(self.download_dir, "*.xlsx")))
            new_files = current_xlsx - existing_xlsx
            for f in new_files:
                fsize = os.path.getsize(f)
                if fsize > 10000:
                    print(f"  下载成功(文件轮询): {os.path.basename(f)} ({fsize} bytes)")
                    downloaded_file = f
                    break
            if downloaded_file:
                break

            if elapsed % 30 < 3:
                print(f"  ...等待中({elapsed}s)")

        if not download_task.done():
            download_task.cancel()

        # 清理弹窗
        try:
            await bi_page.evaluate("""() => {
                document.querySelectorAll('.ant-modal-close, [aria-label="Close"]').forEach(el => {
                    if (el.offsetParent !== null) el.click();
                });
                document.querySelectorAll('button').forEach(el => {
                    const t = (el.textContent||'').trim();
                    if ((t === '取消' || t === '关闭') && el.offsetParent !== null) el.click();
                });
            }""")
            await asyncio.sleep(2)
        except Exception:
            pass

        return downloaded_file


async def verify_login(account: str, password: str) -> bool:
    """验证OA账号密码"""
    try:
        client = BiClient(account, password)
        async with client._create_browser() as (browser, ctx):
            page = await client._login(ctx)
            # 如果没抛异常，说明登录成功
            await browser.close()
            return True
    except Exception as e:
        print(f"[爬虫] 登录验证失败: {e}")
        return False
