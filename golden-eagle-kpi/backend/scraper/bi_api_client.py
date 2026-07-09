"""金鹰工单KPI管理 - BI API客户端（接口直取方案）

优化思路：
1. Playwright 只用于登录（5秒拿cookie，不操作BI页面）
2. 用 httpx + cookie 直接调 BI 报表接口拿数据
3. 不再模拟点击/选报表/填日期/导出Excel（省去60秒等待+坐标定位）
4. 失败时自动降级到旧版 Playwright 方案

使用方式：
    client = BiApiClient(account="xxx", password="xxx")
    files = await client.fetch_all()  # 先试API，失败降级Playwright
"""
import asyncio
import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
import httpx


class BiApiClient:
    """BI系统客户端：登录拿cookie → 接口直取数据"""

    # OA登录地址
    OA_LOGIN_URL = "http://ecbpm.jinying.com:8090/wui/index.html#/login"
    # BI系统地址（登录后跳转）
    BI_BASE_URL = "http://bii.jinying.com"
    
    def __init__(self, account: str, password: str, download_dir: str = None):
        self.account = account
        self.password = password
        self.cookies = {}
        self.bi_token = None
        
        if download_dir:
            self.download_dir = download_dir
        else:
            if getattr(sys, 'frozen', False):
                self.download_dir = str(Path(sys.executable).parent / "data" / "downloads")
            else:
                self.download_dir = str(Path(__file__).parent.parent.parent / "downloads")
        os.makedirs(self.download_dir, exist_ok=True)

    async def fetch_all(self) -> list[str]:
        """抓取所有报表：先试API方案，失败降级Playwright"""
        try:
            print("[BI-API] 尝试接口直取方案...")
            files = await self._fetch_via_api()
            if files:
                print(f"[BI-API] 接口直取成功，获取 {len(files)} 个文件")
                return files
            print("[BI-API] 接口直取无结果，降级到Playwright")
        except Exception as e:
            print(f"[BI-API] 接口直取失败: {e}，降级到Playwright")
        
        # 降级：使用旧版Playwright方案
        from backend.scraper.bi_client import BiClient
        client = BiClient(self.account, self.password, self.download_dir)
        return await client.fetch_all()

    async def _fetch_via_api(self) -> list[str]:
        """通过API直接获取数据"""
        # Step 1: Playwright登录拿cookie
        cookies = await self._login_get_cookies()
        if not cookies:
            raise RuntimeError("登录失败，未获取到cookie")
        
        print(f"[BI-API] 获取到 {len(cookies)} 个cookie")
        
        # Step 2: 用cookie调BI接口
        files = []
        
        # 工单明细
        ticket_file = await self._fetch_report_via_api(cookies, "工单明细查询表")
        if ticket_file:
            files.append(ticket_file)
        
        # 随手拍
        snapshot_file = await self._fetch_report_via_api(cookies, "随手拍工单统计明细表")
        if snapshot_file:
            files.append(snapshot_file)
        
        return files

    async def _login_get_cookies(self) -> dict:
        """用Playwright登录OA系统，返回所有cookie"""
        from playwright.async_api import async_playwright
        
        cookies = {}
        async with async_playwright() as pw:
            # 检测浏览器
            browser_path = self._detect_browser()
            if not browser_path:
                raise RuntimeError("未检测到Chrome/Edge浏览器")
            
            browser = await pw.chromium.launch(
                executable_path=browser_path,
                headless=True,
                args=["--no-sandbox", "--disable-gpu", "--headless=new"]
            )
            ctx = await browser.new_context(
                viewport={"width": 1536, "height": 864},
                locale="zh-CN",
            )
            
            try:
                page = await ctx.new_page()
                print("[BI-API] 登录OA系统...")
                
                await page.goto(
                    "http://ecbpm.jinying.com:8090/wui/index.html#/login",
                    wait_until="networkidle", timeout=30000
                )
                await asyncio.sleep(3)
                
                # 填写登录表单
                await page.locator("#loginid").fill(self.account)
                await page.locator("#userpassword").fill(self.password)
                await asyncio.sleep(0.3)
                
                # 点击登录
                for locator in ["#submit", "text=登陆", "text=登录"]:
                    try:
                        await page.locator(locator).first.click(timeout=5000)
                        break
                    except:
                        continue
                
                # 等待登录完成
                await asyncio.sleep(5)
                
                # 获取所有cookie
                all_cookies = await ctx.cookies()
                for c in all_cookies:
                    cookies[c['name']] = c['value']
                
                # 尝试访问BI系统获取更多cookie/token
                try:
                    bi_page = await ctx.new_page()
                    await bi_page.goto(self.BI_BASE_URL, wait_until="networkidle", timeout=15000)
                    await asyncio.sleep(3)
                    
                    # 获取BI系统的cookie
                    bi_cookies = await ctx.cookies()
                    for c in bi_cookies:
                        cookies[c['name']] = c['value']
                    
                    # 尝试从页面提取token
                    token = await bi_page.evaluate("""() => {
                        // 常见token位置
                        if (window.localStorage) {
                            for (let key of Object.keys(localStorage)) {
                                if (key.toLowerCase().includes('token') || key.toLowerCase().includes('auth')) {
                                    return localStorage[key];
                                }
                            }
                        }
                        if (window.sessionStorage) {
                            for (let key of Object.keys(sessionStorage)) {
                                if (key.toLowerCase().includes('token')) {
                                    return sessionStorage[key];
                                }
                            }
                        }
                        return null;
                    }""")
                    if token:
                        self.bi_token = token
                        print(f"[BI-API] 获取到BI token: {token[:20]}...")
                    
                except Exception as e:
                    print(f"[BI-API] 访问BI系统获取cookie: {e}")
                
            finally:
                await browser.close()
        
        return cookies

    async def _fetch_report_via_api(self, cookies: dict, report_name: str) -> Optional[str]:
        """用cookie直接调BI接口获取报表数据
        
        这里尝试常见的BI系统API模式（FineBI/自定义）。
        如果BI系统有特定的API，需要根据实际接口调整。
        """
        s_date, e_date = self._daterange()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        headers = {
            "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{self.BI_BASE_URL}/",
        }
        if self.bi_token:
            headers["Authorization"] = f"Bearer {self.bi_token}"
            headers["token"] = self.bi_token
        
        # 尝试几种常见的BI导出API
        api_endpoints = [
            # FineBI风格
            f"{self.BI_BASE_URL}/api/v1/report/export",
            f"{self.BI_BASE_URL}/api/report/exportData",
            # 自定义风格
            f"{self.BI_BASE_URL}/api/bi/export",
            f"{self.BI_BASE_URL}/bi/api/exportReport",
        ]
        
        params = {
            "reportName": report_name,
            "startDate": s_date,
            "endDate": e_date,
            "format": "xlsx",
        }
        
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            for api_url in api_endpoints:
                try:
                    print(f"[BI-API] 尝试接口: {api_url}")
                    resp = await client.post(api_url, headers=headers, json=params)
                    
                    if resp.status_code == 200:
                        content_type = resp.headers.get("content-type", "")
                        
                        # 如果返回的是文件（Excel）
                        if "application/vnd" in content_type or "application/octet-stream" in content_type:
                            filename = f"{report_name}_{timestamp}.xlsx"
                            filepath = os.path.join(self.download_dir, filename)
                            with open(filepath, "wb") as f:
                                f.write(resp.content)
                            print(f"[BI-API] 下载成功: {filename} ({len(resp.content)} bytes)")
                            return filepath
                        
                        # 如果返回的是JSON（可能包含下载URL）
                        if "json" in content_type:
                            data = resp.json()
                            if isinstance(data, dict):
                                # 尝试从JSON中提取下载URL
                                download_url = data.get("downloadUrl") or data.get("url") or data.get("data", {}).get("url")
                                if download_url:
                                    file_resp = await client.get(download_url, headers=headers)
                                    if file_resp.status_code == 200:
                                        filename = f"{report_name}_{timestamp}.xlsx"
                                        filepath = os.path.join(self.download_dir, filename)
                                        with open(filepath, "wb") as f:
                                            f.write(file_resp.content)
                                        print(f"[BI-API] 下载成功(JSON→URL): {filename}")
                                        return filepath
                                
                                # 可能是数据直接返回
                                if data.get("data") or data.get("rows"):
                                    print(f"[BI-API] 接口返回JSON数据，需解析为Excel")
                                    # 这里可以将JSON转为Excel
                                    return self._json_to_excel(data, report_name, timestamp)
                except Exception as e:
                    print(f"[BI-API] 接口 {api_url} 失败: {e}")
                    continue
        
        print(f"[BI-API] 所有接口尝试失败，报表: {report_name}")
        return None

    def _json_to_excel(self, data: dict, report_name: str, timestamp: str) -> str:
        """将API返回的JSON数据转为Excel文件"""
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = report_name[:30]
        
        rows = data.get("data") or data.get("rows") or data.get("list") or []
        if isinstance(rows, list) and rows:
            # 写表头
            if isinstance(rows[0], dict):
                headers = list(rows[0].keys())
                ws.append(headers)
                for row in rows:
                    ws.append([row.get(h, "") for h in headers])
            elif isinstance(rows[0], list):
                for row in rows:
                    ws.append(row)
        
        filename = f"{report_name}_{timestamp}.xlsx"
        filepath = os.path.join(self.download_dir, filename)
        wb.save(filepath)
        print(f"[BI-API] JSON→Excel: {filename} ({len(rows)} rows)")
        return filepath

    def _detect_browser(self) -> Optional[str]:
        """检测Chrome/Edge路径"""
        import shutil
        from pathlib import Path
        
        for p in [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]:
            if Path(p).exists():
                return p
        return None

    @staticmethod
    def _daterange():
        t = datetime.now()
        return t.replace(month=1, day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d")


async def discover_bi_api(account: str, password: str):
    """发现BI系统的API接口（开发调试用）
    
    登录后打开BI系统，捕获所有网络请求，帮助识别可用的API端点。
    """
    from playwright.async_api import async_playwright
    
    api_calls = []
    
    async with async_playwright() as pw:
        browser_path = BiApiClient(account, password)._detect_browser()
        if not browser_path:
            print("未检测到浏览器")
            return
        
        browser = await pw.chromium.launch(executable_path=browser_path, headless=False)
        ctx = await browser.new_context(viewport={"width": 1536, "height": 864})
        page = await ctx.new_page()
        
        # 捕获所有API请求
        def on_request(request):
            url = request.url
            if any(d in url for d in ['api', 'report', 'export', 'data', 'query', 'bi']):
                api_calls.append({
                    "method": request.method,
                    "url": url,
                    "headers": dict(request.headers),
                })
        
        page.on("request", on_request)
        
        # 登录
        client = BiApiClient(account, password)
        await client._login_get_cookies()
        
        # 手动操作BI，观察API调用
        print("\n" + "="*60)
        print("浏览器已打开，请手动操作BI系统：")
        print("1. 进入BI决策系统")
        print("2. 选择工单明细查询表")
        print("3. 设置日期范围")
        print("4. 点击导出")
        print("5. 观察下方输出的API调用")
        print("="*60 + "\n")
        
        # 等待用户操作
        await asyncio.sleep(120)
        
        # 输出捕获的API
        print(f"\n{'='*60}")
        print(f"捕获到 {len(api_calls)} 个API调用：")
        for i, call in enumerate(api_calls):
            print(f"\n[{i+1}] {call['method']} {call['url']}")
            ct = call['headers'].get('content-type', '')
            if ct:
                print(f"    Content-Type: {ct}")
        
        await browser.close()
        
        # 保存到文件
        log_path = os.path.join(Path(__file__).parent.parent.parent, "data", "bi_api_discovery.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(api_calls, f, ensure_ascii=False, indent=2)
        print(f"\nAPI调用已保存到: {log_path}")
