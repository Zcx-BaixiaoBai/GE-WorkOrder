"""金鹰工单KPI管理 - BI API客户端（观远BI接口直取）

已发现的真实API：
- 报表列表: GET /api/page-v3
- 页面元数据: GET /api/page/{pageId}
- 数据获取: POST /api/card/{cardId}/data
- 认证: uIdToken cookie (通过OA SSO获取)

报表ID:
- 工单明细查询表: pageId=fa668851413cd49e2b7dae32, cardId=ud9c0144043584dc19dedbcb
- 随手拍工单统计明细表: pageId=nbf2c0836d10941bc88000fb (cardId需动态获取)
"""
import asyncio
import os
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import httpx


class BiApiClient:
    """观远BI客户端：OA登录→SSO→cookie→API直取数据"""

    OA_LOGIN_URL = "http://ecbpm.jinying.com:8090/wui/index.html?#/?_key=66mc5g"
    BI_BASE = "https://bii.jinying.com"
    
    # 报表配置
    REPORTS = {
        "工单明细查询表": {
            "pageId": "fa668851413cd49e2b7dae32",
            "cardId": "ud9c0144043584dc19dedbcb",
        },
        "随手拍工单统计明细表": {
            "pageId": "nbf2c0836d10941bc88000fb",
            "cardId": None,  # 需从页面元数据动态获取
        },
    }
    
    def __init__(self, account: str, password: str, download_dir: str = None):
        self.account = account
        self.password = password
        self.cookies = {}
        
        if download_dir:
            self.download_dir = download_dir
        else:
            if getattr(sys, 'frozen', False):
                self.download_dir = str(Path(sys.executable).parent / "data" / "downloads")
            else:
                self.download_dir = str(Path(__file__).parent.parent.parent / "downloads")
        os.makedirs(self.download_dir, exist_ok=True)

    async def fetch_all(self) -> list[str]:
        """获取所有报表数据：API直取，失败降级Playwright"""
        try:
            print("[BI-API] 接口直取方案...")
            files = await self._fetch_via_api()
            if files:
                print(f"[BI-API] 成功，获取 {len(files)} 个文件")
                return files
            print("[BI-API] 无结果，降级Playwright")
        except Exception as e:
            print(f"[BI-API] 失败: {e}，降级Playwright")
        
        from backend.scraper.bi_client import BiClient
        client = BiClient(self.account, self.password, self.download_dir)
        return await client.fetch_all()

    async def _fetch_via_api(self) -> list[str]:
        """通过观远BI API直接获取数据"""
        # Step 1: OA登录 + SSO获取BI cookie
        cookies = await self._login_and_get_bi_cookies()
        if not cookies:
            raise RuntimeError("未获取到BI cookie")
        print(f"[BI-API] 获取到 {len(cookies)} 个BI cookie")
        
        headers = {
            "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 Chrome/120.0.0.0",
            "Referer": f"{self.BI_BASE}/page/overview",
        }
        
        files = []
        s_date, e_date = self._date_range()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            for report_name, config in self.REPORTS.items():
                print(f"[BI-API] 获取报表: {report_name}")
                
                # 获取cardId（如果未配置，从页面元数据动态获取）
                card_id = config["cardId"]
                if not card_id:
                    card_id = await self._get_card_id(client, headers, config["pageId"])
                    if not card_id:
                        print(f"[BI-API] 无法获取 {report_name} 的cardId，跳过")
                        continue
                
                # 获取动态参数配置
                params = await self._get_dynamic_params(client, headers, config["pageId"])
                
                # 设置日期参数
                for p in params:
                    if "开始时间" in p.get("name", ""):
                        p["defaultValue"] = s_date
                    elif "结束时间" in p.get("name", ""):
                        p["defaultValue"] = e_date
                
                # 调用数据API
                data_resp = await client.post(
                    f"{self.BI_BASE}/api/card/{card_id}/data",
                    headers=headers,
                    json={"filters": [], "treeFilters": [], "dynamicParams": params, "drillDown": False, "preview": False},
                )
                
                if data_resp.status_code != 200:
                    print(f"[BI-API] 数据API返回 {data_resp.status_code}")
                    continue
                
                data = data_resp.json()
                # 转为Excel
                filepath = self._data_to_excel(data, report_name, ts)
                if filepath:
                    files.append(filepath)
                    print(f"[BI-API] 成功: {filepath}")
        
        return files

    async def _login_and_get_bi_cookies(self) -> dict:
        """OA登录→SSO→获取BI cookie"""
        from playwright.async_api import async_playwright
        
        bi_cookies = {}
        async with async_playwright() as pw:
            bp = self._detect_browser()
            if not bp:
                raise RuntimeError("未检测到浏览器")
            
            browser = await pw.chromium.launch(executable_path=bp, headless=True, args=["--no-sandbox","--headless=new"])
            ctx = await browser.new_context(viewport={"width":1536,"height":864}, locale="zh-CN")
            page = await ctx.new_page()
            
            # OA登录
            print("[BI-API] OA登录...")
            await page.goto(self.OA_LOGIN_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)
            await page.locator("#loginid").click(force=True)
            await page.locator("#loginid").fill(self.account)
            await page.locator("#userpassword").click(force=True)
            await page.locator("#userpassword").fill(self.password)
            await asyncio.sleep(0.3)
            await page.locator("#submit").first.click(timeout=5000)
            await asyncio.sleep(5)
            
            # SSO: 点击BI决策系统
            print("[BI-API] SSO跳转...")
            for f in page.frames:
                try:
                    el = f.locator("text=BI决策系统").first
                    if await el.count() > 0:
                        await el.click()
                        break
                except:
                    continue
            await asyncio.sleep(8)
            
            # 获取BI cookie
            all_cookies = await ctx.cookies()
            for c in all_cookies:
                if "bii" in c.get("domain", ""):
                    bi_cookies[c["name"]] = c["value"]
            
            await browser.close()
        
        return bi_cookies

    async def _get_card_id(self, client, headers, page_id) -> Optional[str]:
        """从页面元数据获取cardId"""
        resp = await client.get(f"{self.BI_BASE}/api/page/{page_id}", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            # 从layout中找第一个widget的id
            layout = data.get("meta", {}).get("layout", [])
            if layout:
                return layout[0].get("i")
        return None

    async def _get_dynamic_params(self, client, headers, page_id) -> list:
        """获取页面的动态参数配置"""
        resp = await client.get(f"{self.BI_BASE}/api/page/{page_id}", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            params = data.get("dynamicParams", []) or data.get("meta", {}).get("dynamicParams", [])
            if params:
                return params
        # 返回默认参数结构
        return [
            {"dpId": "m6a3e11c4043b470fa5f2107", "name": "开始时间", "valueType": "DATE", "defaultValue": "", "customize": False, "multiple": False, "optionValue": [""], "sourceCdId": "i1704bf31e38f49cbbef54e8"},
            {"dpId": "u8ec55ee779a0405c9e89ff7", "name": "结束时间", "valueType": "DATE", "defaultValue": "", "customize": False, "multiple": False, "optionValue": [""], "sourceCdId": "l238a6920804444c1b815764"},
        ]

    def _data_to_excel(self, data: dict, report_name: str, ts: str) -> Optional[str]:
        """将API返回的JSON数据转为Excel"""
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = report_name[:30]
        
        # 观远BI数据结构: {data: {headers: [...], rows: [[...],...]} } 或类似
        rows = []
        headers = []
        
        # 尝试多种数据结构
        if isinstance(data, dict):
            d = data.get("data") or data.get("result") or data.get("rows") or data
            if isinstance(d, dict):
                headers = d.get("headers") or d.get("columns") or d.get("fields") or []
                rows = d.get("rows") or d.get("data") or d.get("values") or []
            elif isinstance(d, list) and d:
                if isinstance(d[0], dict):
                    headers = list(d[0].keys())
                    rows = [[item.get(h, "") for h in headers] for item in d]
                elif isinstance(d[0], list):
                    rows = d
        elif isinstance(data, list) and data:
            if isinstance(data[0], dict):
                headers = list(data[0].keys())
                rows = [[item.get(h, "") for h in headers] for item in data]
        
        # 写表头
        if headers:
            ws.append(headers)
        # 写数据
        for row in rows:
            if isinstance(row, list):
                ws.append(row)
        
        if ws.max_row <= 1 and not headers:
            # 如果没解析出数据，保存原始JSON
            ws.append(["原始JSON数据"])
            ws.append([json.dumps(data, ensure_ascii=False)[:32000]])
        
        filename = f"{report_name}_{ts}.xlsx"
        filepath = os.path.join(self.download_dir, filename)
        wb.save(filepath)
        print(f"[BI-API] 生成Excel: {filename} ({len(rows)} rows)")
        return filepath

    def _detect_browser(self) -> Optional[str]:
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
    def _date_range():
        t = datetime.now()
        return t.replace(month=1, day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d")
