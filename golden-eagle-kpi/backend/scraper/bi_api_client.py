"""金鹰工单KPI管理 - BI API客户端（观远BI全接口直取）

完整API链路（无需模拟UI操作）：
1. OA登录(5秒) → SSO获取BI cookie
2. POST /api/batchExportCardExcel → 创建导出任务
3. GET /api/task/{taskId} → 轮询直到FINISHED
4. POST /api/export/file/common/{taskId} → 下载完整Excel

报表配置:
- 工单明细查询表: pgId=fa668851413cd49e2b7dae32, cdId=ud9c0144043584dc19dedbcb
  日期参数: 开始时间(m6a3e11c4043b470fa5f2107), 结束时间(u8ec55ee779a0405c9e89ff7)
- 随手拍: pgId=nbf2c0836d10941bc88000fb, cdId需动态获取
"""
import asyncio, os, sys, json, time
from datetime import datetime
from pathlib import Path
from typing import Optional
import httpx


class BiApiClient:
    BI_BASE = "https://bii.jinying.com"
    OA_LOGIN_URL = "http://ecbpm.jinying.com:8090/wui/index.html?#/?_key=66mc5g"
    
    REPORTS = {
        "工单明细查询表": {
            "pgId": "fa668851413cd49e2b7dae32",
            "cdId": "ud9c0144043584dc19dedbcb",
            "params": [
                {"dpId": "m6a3e11c4043b470fa5f2107", "name": "开始时间", "valueType": "DATE", "defaultValue": "", "customize": False, "multiple": False, "optionValue": [""], "sourceCdId": "i1704bf31e38f49cbbef54e8"},
                {"dpId": "u8ec55ee779a0405c9e89ff7", "name": "结束时间", "valueType": "DATE", "defaultValue": "", "customize": False, "multiple": False, "optionValue": [""], "sourceCdId": "l238a6920804444c1b815764"},
            ],
        },
        "随手拍工单统计明细表": {
            "pgId": "nbf2c0836d10941bc88000fb",
            "cdId": None,  # 动态获取
            "params": None,  # 动态获取
        },
    }

    def __init__(self, account: str, password: str, download_dir: str = None):
        self.account = account
        self.password = password
        self.download_dir = download_dir or str(
            (Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent.parent.parent) / "downloads"
        )
        os.makedirs(self.download_dir, exist_ok=True)

    async def fetch_all(self) -> list[str]:
        try:
            print("[BI-API] 全接口直取方案...")
            files = await self._fetch_via_api()
            if files:
                print(f"[BI-API] 成功，{len(files)} 个文件")
                return files
            print("[BI-API] 无结果，降级Playwright")
        except Exception as e:
            print(f"[BI-API] 失败: {e}，降级Playwright")
        from backend.scraper.bi_client import BiClient
        return await BiClient(self.account, self.password, self.download_dir).fetch_all()

    async def _fetch_via_api(self) -> list[str]:
        cookies = await self._login_sso()
        if not cookies: raise RuntimeError("未获取到BI cookie")
        print(f"[BI-API] {len(cookies)} 个cookie")
        
        headers = {
            "Cookie": "; ".join(f"{k}={v}" for k,v in cookies.items()),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 Chrome/120.0.0.0",
            "Origin": self.BI_BASE,
            "Referer": f"{self.BI_BASE}/page/overview",
        }
        
        s_date, e_date = self._date_range()
        files = []
        
        async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
            for name, cfg in self.REPORTS.items():
                print(f"\n[BI-API] 报表: {name}")
                
                # 动态获取cdId和params（对于随手拍）
                cd_id = cfg["cdId"]
                params = cfg["params"]
                if not cd_id:
                    cd_id, params = await self._get_card_info(client, headers, cfg["pgId"])
                    if not cd_id:
                        print(f"  无法获取cardId，跳过")
                        continue
                
                # 设置日期参数
                if params:
                    for p in params:
                        if "开始" in p.get("name", ""): p["defaultValue"] = s_date
                        elif "结束" in p.get("name", ""): p["defaultValue"] = e_date
                
                # Step1: 创建导出任务
                print(f"  创建导出任务...")
                export_body = {
                    "pgId": cfg["pgId"],
                    "cards": [{
                        "cdId": cd_id,
                        "saveFilters": False,
                        "filters": [],
                        "treeFilters": [],
                        "dynamicParams": params or [],
                        "dynamicFieldFilters": [],
                        "combinationFilters": [],
                        "layerTreeFilters": [],
                    }],
                    "exportType": "PIVOT",
                    "saveType": "MANY_SHEET",
                }
                resp = await client.post(f"{self.BI_BASE}/api/batchExportCardExcel", headers=headers, json=export_body)
                if resp.status_code != 200:
                    print(f"  创建任务失败: {resp.status_code}")
                    continue
                
                resp_data = resp.json()
                task_info = resp_data.get("response", resp_data)
                task_id = task_info.get("taskId")
                if not task_id:
                    print(f"  无taskId: {resp_data}")
                    continue
                print(f"  taskId: {task_id}")
                
                # Step2: 轮询任务状态
                print(f"  轮询任务...")
                for attempt in range(300):
                    await asyncio.sleep(1)
                    task_resp = await client.get(f"{self.BI_BASE}/api/task/{task_id}", headers=headers)
                    if task_resp.status_code != 200: continue
                    task_data = task_resp.json()  # status在顶层，不在response里
                    status = task_data.get("status", "")
                    duration = task_data.get("runningDuration", 0)
                    if attempt % 10 == 0:
                        print(f"  [{attempt}s] status={status} duration={duration}")
                    if status == "FINISHED":
                        print(f"  任务完成! ({duration}秒)")
                        break
                    if status in ("FAILED", "ERROR"):
                        print(f"  任务失败: {task_data}")
                        break
                else:
                    print(f"  轮询超时(300秒)")
                    continue
                
                # Step3: 下载文件
                print(f"  下载Excel...")
                now_iso = datetime.now().isoformat(timespec='seconds') + '+08:00'
                file_resp = await client.post(
                    f"{self.BI_BASE}/api/export/file/common/{task_id}",
                    headers=headers,
                    json={"time": now_iso, "fileNameWithTime": True},
                )
                if file_resp.status_code == 200 and len(file_resp.content) > 10000:
                    filename = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                    filepath = os.path.join(self.download_dir, filename)
                    with open(filepath, "wb") as f:
                        f.write(file_resp.content)
                    fsize = len(file_resp.content)
                    print(f"  下载成功: {filename} ({fsize/1024/1024:.1f} MB)")
                    files.append(filepath)
                else:
                    print(f"  下载失败: {file_resp.status_code} ({len(file_resp.content)} bytes)")
        
        return files

    async def _get_card_info(self, client, headers, pg_id) -> tuple:
        """从页面元数据获取cardId和dynamicParams"""
        resp = await client.get(f"{self.BI_BASE}/api/page/{pg_id}", headers=headers)
        if resp.status_code != 200:
            return None, None
        data = resp.json()
        layout = data.get("meta", {}).get("layout", [])
        cd_id = layout[0]["i"] if layout else None
        # 从第一次数据请求获取params
        if cd_id:
            data_resp = await client.post(
                f"{self.BI_BASE}/api/card/{cd_id}/data",
                headers=headers,
                json={"filters":[],"treeFilters":[],"dynamicParams":[],"drillDown":False,"preview":False},
            )
            if data_resp.status_code == 200:
                cm = data_resp.json().get("chartMain", {})
                params = cm.get("meta", {}).get("dynamicParameters", [])
                return cd_id, params
        return cd_id, None

    async def _login_sso(self) -> dict:
        """OA登录→SSO→获取BI cookie"""
        from playwright.async_api import async_playwright
        cookies = {}
        async with async_playwright() as pw:
            bp = self._detect_browser()
            if not bp: raise RuntimeError("未检测到浏览器")
            browser = await pw.chromium.launch(executable_path=bp, headless=True, args=["--no-sandbox","--headless=new"])
            ctx = await browser.new_context(viewport={"width":1536,"height":864}, locale="zh-CN")
            page = await ctx.new_page()
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
            print("[BI-API] SSO跳转...")
            for f in page.frames:
                try:
                    el = f.locator("text=BI决策系统").first
                    if await el.count() > 0: await el.click(); break
                except: continue
            await asyncio.sleep(8)
            for c in await ctx.cookies():
                if "bii" in c.get("domain",""): cookies[c["name"]] = c["value"]
            await browser.close()
        return cookies

    def _detect_browser(self) -> Optional[str]:
        for p in [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]:
            if Path(p).exists(): return p
        return None

    @staticmethod
    def _date_range():
        t = datetime.now()
        return t.replace(month=1, day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d")
