"""
OA BI报表导出 v17 - 全文字定位版
严格按用户指令操作：
1. OA登录（账号密码+点"登陆"）
2. 点"BI决策系统"→新窗口
3. 点树"金鹰物业"展开 → 选报表
4. 找"开始日期"/"结束日期"文字定位填日期
5. 等5s → 点"导出" → "批量导出excel" → 选表格 → "批量导出excel" → "确定"
6. 第二张表同理，等更久（大文件几十MB）
"""
import asyncio, os, sys, glob, time as time_mod
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

DL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
os.makedirs(DL, exist_ok=True)

USERNAME = "zhangchenxi"
PASSWORD = "YOUR_SCRAPER_PASSWORD_HERE"

SNAP_COUNTER = 0


def daterange():
    t = datetime.now()
    return t.replace(month=1, day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d")


async def snap(page, name):
    """截图并打印"""
    global SNAP_COUNTER
    SNAP_COUNTER += 1
    fname = f"v17_{SNAP_COUNTER:02d}_{name}.png"
    try:
        await page.screenshot(path=os.path.join(DL, fname), full_page=False)
        print(f"    📸 {fname}")
    except Exception as e:
        print(f"    📸失败 {fname}: {e}")


async def dump_visible_text(page, label=""):
    """打印页面可见文字元素，用于调试"""
    items = await page.evaluate("""() => {
        const results = [];
        // 所有可见文字节点
        const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
        while (walk.nextNode()) {
            const t = walk.currentNode.textContent.trim();
            if (!t || t.length < 2 || t.length > 30) continue;
            const parent = walk.currentNode.parentElement;
            if (!parent || parent.offsetParent === null) continue;
            const r = parent.getBoundingClientRect();
            if (r.width < 10 || r.height < 5) continue;
            results.push({
                text: t,
                tag: parent.tagName,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height)
            });
        }
        return results.slice(0, 60);
    }""")
    if label:
        print(f"  [{label}] 可见文字({len(items)}个):")
    for it in items:
        print(f"    <{it['tag']}> ({it['x']},{it['y']}) {it['w']}x{it['h']} '{it['text']}'")


# ============================================================
# Step 1: 登录OA
# ============================================================
async def login(ctx):
    print("\n[1] 登录OA")
    page = await ctx.new_page()
    await page.goto(
        "http://ecbpm.jinying.com:8090/wui/index.html?#/?_key=66mc5g",
        wait_until="networkidle", timeout=30000
    )
    await asyncio.sleep(3)
    await snap(page, "oa_login_page")

    # OA登录框有id，直接用id更可靠
    await page.locator("#loginid").click(force=True)
    await page.locator("#loginid").fill(USERNAME)
    await page.locator("#userpassword").click(force=True)
    await page.locator("#userpassword").fill(PASSWORD)
    await asyncio.sleep(0.3)

    # 点"登陆"按钮 — 先试id，再试文字
    login_clicked = False
    try:
        await page.locator("#submit").click(timeout=5000)
        login_clicked = True
        print("  点击'登陆'(id定位)")
    except:
        pass
    if not login_clicked:
        try:
            await page.locator("text=登陆").first.click(timeout=5000)
            login_clicked = True
            print("  点击'登陆'(文字定位)")
        except:
            pass
    if not login_clicked:
        try:
            await page.locator("text=登录").first.click(timeout=5000)
            login_clicked = True
            print("  点击'登录'(文字定位)")
        except:
            pass
    if not login_clicked:
        print("  ✗ 未找到登录按钮")

    # 等待登录完成
    try:
        await page.wait_for_selector("#loginid", state="hidden", timeout=20000)
        print("  ✓ 登录成功!")
    except:
        print("  登录状态不确定，继续...")
    await asyncio.sleep(5)
    await snap(page, "oa_after_login")
    return page


# ============================================================
# Step 2: 进入BI系统
# ============================================================
async def enter_bi(page):
    print("\n[2] 进入BI决策系统")

    # 找"BI决策系统"文字，在OA首页的iframe中
    # 先看所有frame
    print(f"  OA页面frames: {len(page.frames)}个")
    for f in page.frames:
        print(f"    frame: name={f.name!r} url={f.url[:80]}")

    # 在OA主页面或iframe中找"BI决策系统"
    bi_clicked = False

    # 方法1: 在主页面直接找
    try:
        el = page.locator("text=BI决策系统").first
        if await el.count() > 0 and await el.is_visible():
            await el.click()
            print("  ✓ 在主页面点击'BI决策系统'")
            bi_clicked = True
    except:
        pass

    # 方法2: 在iframe中找
    if not bi_clicked:
        for f in page.frames:
            try:
                el = f.locator("text=BI决策系统").first
                if await el.count() > 0:
                    await el.click()
                    print(f"  ✓ 在iframe({f.name})点击'BI决策系统'")
                    bi_clicked = True
                    break
            except:
                pass

    # 方法3: 用JS在所有frame中搜索并点击
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
            // 主页面也找
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
        if clicked:
            print("  ✓ 通过JS点击'BI决策系统'")
            bi_clicked = True

    if not bi_clicked:
        print("  ✗ 未找到'BI决策系统'，尝试坐标兜底")
        # 之前的坐标
        await page.mouse.click(1412, 686)

    # 等待新窗口打开 bii.jinying.com
    print("  等待BI新窗口...")
    bi_page = None
    for attempt in range(20):
        await asyncio.sleep(2)
        for pg in page.context.pages:
            if pg == page:
                continue
            if 'bii.jinying.com' in pg.url:
                bi_page = pg
                print(f"  ✓ BI窗口: {pg.url}")
                break
        if bi_page:
            break

    if not bi_page:
        print("  ✗ 未找到BI窗口")
        return None

    await bi_page.bring_to_front()
    await asyncio.sleep(5)
    await snap(bi_page, "bi_overview")
    return bi_page


# ============================================================
# Step 3: 选择报表（展开树 + 点击报表名）
# ============================================================
async def select_report(bi_page, report_name):
    print(f"\n  选择报表: {report_name}")

    # 如果不在BI首页，先回到首页（树在首页）
    current_url = bi_page.url
    if '/page/overview' not in current_url and '/page/fa' not in current_url:
        # 如果URL包含具体报表ID，说明在报表页面，需要回去
        pass

    # 确保左侧树可见 — 如果在报表页面，树应该还在左侧
    # 先尝试直接在当前页面操作
    
    # 方法1: 用JS展开"金鹰物业"（更可靠）
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

    # 如果JS找不到金鹰物业，尝试文字定位
    if expanded == 'not_found':
        try:
            await bi_page.locator("text=金鹰物业").first.click(timeout=10000)
            print("  ✓ 点击'金鹰物业'(文字定位)")
            await asyncio.sleep(2)
        except:
            print("  ✗ 找不到'金鹰物业'")
            await snap(bi_page, "no_jinying")
            return False

    await snap(bi_page, f"jinying_expanded")

    # 打印当前树节点，用于调试
    tree_nodes = await bi_page.evaluate("""() => {
        return Array.from(document.querySelectorAll('.ant-tree-title')).map(el => ({
            text: el.textContent.trim(),
            x: Math.round(el.getBoundingClientRect().x),
            y: Math.round(el.getBoundingClientRect().y)
        }));
    }""")
    print(f"  树节点({len(tree_nodes)}个):")
    for n in tree_nodes:
        print(f"    ({n['x']},{n['y']}) '{n['text']}'")

    # 点击报表名 — 用多种策略
    clicked = False
    
    # 策略1: 精确匹配
    if not clicked:
        try:
            el = bi_page.locator(f".ant-tree-title:has-text('{report_name}')").first
            if await el.count() > 0:
                await el.click(timeout=5000)
                print(f"  ✓ 点击'{report_name}'(精确匹配)")
                clicked = True
        except:
            pass

    # 策略2: 宽泛文字匹配
    if not clicked:
        try:
            el = bi_page.locator(f"text={report_name}").first
            if await el.count() > 0:
                await el.click(timeout=5000)
                print(f"  ✓ 点击'{report_name}'(文字匹配)")
                clicked = True
        except:
            pass

    # 策略3: 部分关键词匹配
    if not clicked:
        # 提取关键词
        keywords = []
        if "随手拍" in report_name:
            keywords = ["随手拍", "随手拍工单"]
        elif "工单明细" in report_name:
            keywords = ["工单明细查询", "工单明细"]
        
        for kw in keywords:
            try:
                el = bi_page.locator(f".ant-tree-title:has-text('{kw}')").first
                if await el.count() > 0:
                    await el.click(timeout=5000)
                    print(f"  ✓ 点击'{kw}'(关键词匹配)")
                    clicked = True
                    break
            except:
                pass
            try:
                el = bi_page.locator(f"text={kw}").first
                if await el.count() > 0:
                    await el.click(timeout=5000)
                    print(f"  ✓ 点击'{kw}'(文字关键词)")
                    clicked = True
                    break
            except:
                pass

    # 策略4: 用JS在树节点中查找
    if not clicked:
        js_result = await bi_page.evaluate(f"""() => {{
            const nodes = document.querySelectorAll('.ant-tree-title');
            for (const n of nodes) {{
                const t = n.textContent.trim();
                if (t.includes('{report_name}') || t.includes('随手拍') && '{report_name}'.includes('随手拍')) {{
                    n.click();
                    return t;
                }}
            }}
            return '';
        }}""")
        if js_result:
            print(f"  ✓ 点击'{js_result}'(JS匹配)")
            clicked = True

    if not clicked:
        print(f"  ✗ 找不到'{report_name}'")
        await snap(bi_page, f"no_{report_name[:4]}")
        return False

    await asyncio.sleep(5)
    await snap(bi_page, f"{report_name[:4]}_selected")

    # 验证进入了报表页
    title = await bi_page.title()
    url = bi_page.url
    print(f"  标题: {title!r}")
    print(f"  URL: {url}")
    return True


# ============================================================
# Step 4: 填写日期（用"开始日期""结束日期"文字定位）
# ============================================================
async def fill_dates(bi_page, report_name, wait_longer=False):
    print(f"\n  填写日期")
    s_date, e_date = daterange()
    print(f"    开始日期={s_date}, 结束日期={e_date}")

    # 先打印所有日期相关文字，辅助调试
    date_labels = await bi_page.evaluate("""() => {
        const results = [];
        const keywords = ['日期', '开始', '结束', '时间', '起', '止', '从', '至'];
        document.querySelectorAll('*').forEach(el => {
            const t = (el.textContent||'').trim();
            if (t.length >= 2 && t.length <= 10 && el.children.length === 0 && el.offsetParent !== null) {
                const r = el.getBoundingClientRect();
                if (r.width > 10 && r.y < 400 && r.y > 100) {
                    for (const kw of keywords) {
                        if (t.includes(kw)) {
                            results.push({text: t, tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y)});
                            break;
                        }
                    }
                }
            }
        });
        return results;
    }""")
    print(f"  日期相关文字({len(date_labels)}个):")
    for d in date_labels:
        print(f"    <{d['tag']}> ({d['x']},{d['y']}) '{d['text']}'")

    # 方法1: 找"开始时间"/"结束时间"文字旁边的input
    # 观远BI的日期筛选器label是"开始时间""结束时间"（不是"日期"）
    for label_text, fill_val in [("开始时间", s_date), ("结束时间", e_date), ("开始日期", s_date), ("结束日期", e_date)]:
        filled = False

        # 先用文字找label，然后找关联的input
        try:
            # 找label文字元素
            label_el = bi_page.locator(f"text={label_text}").first
            if await label_el.count() > 0:
                # 尝试多种方式找到相邻的input
                # 方法A: label的下一个兄弟是input容器
                # 方法B: label的父元素内有input
                # 方法C: 直接通过label的for属性
                input_info = await bi_page.evaluate(f"""() => {{
                    // 找所有包含"{label_text}"文字的元素
                    const labels = Array.from(document.querySelectorAll('*')).filter(el => {{
                        const t = (el.textContent||'').trim();
                        return t === "{label_text}" && el.children.length === 0 && el.offsetParent !== null;
                    }});
                    
                    for (const label of labels) {{
                        const r = label.getBoundingClientRect();
                        // 在label右侧或下方找input
                        const inputs = Array.from(document.querySelectorAll('input')).filter(inp => {{
                            const ir = inp.getBoundingClientRect();
                            return inp.offsetParent !== null && ir.width > 80 &&
                                   // input在label右侧或同一行
                                   Math.abs(ir.y - r.y) < 50 && ir.x > r.x;
                        }});
                        if (inputs.length > 0) {{
                            const inp = inputs[0];
                            const ir = inp.getBoundingClientRect();
                            return {{
                                found: true,
                                x: Math.round(ir.x + ir.width/2),
                                y: Math.round(ir.y + ir.height/2),
                                w: Math.round(ir.width),
                                h: Math.round(ir.height),
                                ph: inp.placeholder,
                                val: inp.value
                            }};
                        }}
                    }}
                    return {{ found: false }};
                }}""")

                if input_info.get('found'):
                    ix, iy = input_info['x'], input_info['y']
                    print(f"    {label_text}: input@({ix},{iy}) ph={input_info['ph']!r} old={input_info['val']!r}")
                    # 点击input
                    await bi_page.mouse.click(ix, iy)
                    await asyncio.sleep(0.8)
                    # 清空+填入
                    await bi_page.keyboard.press("Control+a")
                    await asyncio.sleep(0.2)
                    await bi_page.keyboard.type(fill_val, delay=30)
                    await asyncio.sleep(0.3)
                    await bi_page.keyboard.press("Enter")
                    await asyncio.sleep(0.5)
                    print(f"    ✓ {label_text}={fill_val}")
                    filled = True
                    await snap(bi_page, f"{report_name[:4]}_{label_text}")
        except Exception as e:
            print(f"    文字定位{label_text}异常: {e}")

        # 方法2: 如果文字定位失败，按顺序定位日期框
        if not filled:
            print(f"    文字定位'{label_text}'失败，用顺序定位")
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
                    ph: el.placeholder,
                    val: el.value
                }));
            }""")

            idx = 0 if label_text == "开始日期" else (1 if len(date_inputs) > 1 else 0)
            if date_inputs and idx < len(date_inputs):
                d = date_inputs[idx]
                cx = d['x'] + d['w']//2
                cy = d['y'] + d['h']//2
                print(f"    顺序定位{label_text}: ({cx},{cy}) ph={d['ph']!r} val={d['val']!r}")
                await bi_page.mouse.click(cx, cy)
                await asyncio.sleep(0.8)
                await bi_page.keyboard.press("Control+a")
                await asyncio.sleep(0.2)
                await bi_page.keyboard.type(fill_val, delay=30)
                await asyncio.sleep(0.3)
                await bi_page.keyboard.press("Enter")
                await asyncio.sleep(0.5)
                print(f"    ✓ {label_text}={fill_val}")
                filled = True

        if not filled:
            print(f"    ✗ {label_text}填写失败!")

    # 等待数据准备
    # 报表2数据量大，需要更长时间加载
    wait_sec = 30 if wait_longer else 5
    print(f"  等待{wait_sec}s准备数据...")
    await asyncio.sleep(wait_sec)
    await snap(bi_page, f"{report_name[:4]}_data_ready")
    # 等待完成后截图+打印当前页面文字，确认数据加载成功
    if wait_longer:
        await dump_visible_text(bi_page, f"{report_name[:4]}_after_wait")


# ============================================================
# Step 5: 导出Excel
# 用户指令流程：
#   点"导出" → 下拉"批量导出excel" → 选表格本体 → "批量导出excel" → 蓝色"确定"
# ============================================================
async def export_excel(bi_page, report_name, wait_longer=False):
    print(f"\n  导出Excel: {report_name}")

    # 先关闭可能残留的弹窗（上一个报表下载后可能还有弹窗没关）
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
            print(f"  关闭残留弹窗: ({b['x']},{b['y']})")
            await asyncio.sleep(1)
    except:
        pass

    # ---- 5a: 点击"导出" ----
    print("  [5a] 点击'导出'")
    export_clicked = False
    try:
        # 优先用文字定位
        export_el = bi_page.locator("text=导出").first
        if await export_el.count() > 0 and await export_el.is_visible():
            await export_el.click(timeout=5000)
            print("  ✓ 点击'导出'(文字定位)")
            export_clicked = True
    except Exception as e:
        print(f"  文字定位'导出'失败: {e}")

    if not export_clicked:
        # 兜底：找顶部工具栏的导出按钮
        export_btns = await bi_page.evaluate("""() => {
            return Array.from(document.querySelectorAll('*')).filter(el => {
                const r = el.getBoundingClientRect();
                const t = (el.textContent||'').trim();
                return t === '导出' && r.y < 150 && r.x > 800 &&
                       r.width > 10 && r.height > 10 && el.children.length === 0;
            }).map(el => ({
                tag: el.tagName, text: (el.textContent||'').trim(),
                x: Math.round(el.getBoundingClientRect().x),
                y: Math.round(el.getBoundingClientRect().y),
                w: Math.round(el.getBoundingClientRect().width),
                h: Math.round(el.getBoundingClientRect().height)
            }));
        }""")
        if export_btns:
            b = export_btns[0]
            await bi_page.mouse.click(b['x']+b['w']//2, b['y']+b['h']//2)
            print(f"  ✓ 点击'导出'(坐标兜底)")
            export_clicked = True

    if not export_clicked:
        print("  ✗ 未找到'导出'按钮")
        await snap(bi_page, f"{report_name[:4]}_no_export")
        # 打印页面上所有文字元素，辅助调试
        await dump_visible_text(bi_page, f"{report_name[:4]}_no_export")
        return False

    await asyncio.sleep(2)
    await snap(bi_page, f"{report_name[:4]}_export_dropdown")

    # ---- 5b: 点击下拉列表的"批量导出excel" ----
    print("  [5b] 点击'批量导出excel'")
    batch_clicked = False
    try:
        batch_el = bi_page.locator("text=批量导出Excel").first
        if await batch_el.count() > 0 and await batch_el.is_visible():
            await batch_el.click(timeout=5000)
            print("  ✓ 点击'批量导出Excel'(文字定位)")
            batch_clicked = True
    except Exception as e:
        print(f"  文字定位'批量导出Excel'失败: {e}")

    if not batch_clicked:
        # 兜底：在下拉菜单中找
        batch_items = await bi_page.evaluate("""() => {
            const items = document.querySelectorAll('.ant-dropdown-menu-item, [role="menuitem"]');
            return Array.from(items).filter(el => {
                const t = (el.textContent||'').trim();
                return t.includes('Excel') && el.offsetParent !== null;
            }).map(el => ({
                text: (el.textContent||'').trim(),
                x: Math.round(el.getBoundingClientRect().x),
                y: Math.round(el.getBoundingClientRect().y),
                w: Math.round(el.getBoundingClientRect().width),
                h: Math.round(el.getBoundingClientRect().height)
            }));
        }""")
        if batch_items:
            e = batch_items[0]
            await bi_page.mouse.click(e['x']+e['w']//2, e['y']+e['h']//2)
            print(f"  ✓ 点击'批量导出Excel'(兜底)")
            batch_clicked = True

    if not batch_clicked:
        print("  ✗ 未找到'批量导出Excel'")
        await snap(bi_page, f"{report_name[:4]}_no_batch")
        await dump_visible_text(bi_page, f"{report_name[:4]}_no_batch")
        return False

    await asyncio.sleep(2)
    await snap(bi_page, f"{report_name[:4]}_after_batch_click")

    # ---- 5c: 点击选择下方的表格本体 ----
    print("  [5c] 选择表格本体")
    await snap(bi_page, f"{report_name[:4]}_before_table_select")
    # 观远BI批量导出时，需要选择要导出的表格（图表/组件）
    # 通常会出现一个选择面板，显示所有可导出的组件
    table_selected = False

    # 找到表格/图表组件（通常是checkbox或可点击的卡片）
    try:
        # 尝试找表格本体 — 可能是一个checkbox、一个卡片、或者一个table元素
        # 先看看有没有checkbox
        checkbox_info = await bi_page.evaluate("""() => {
            const checkboxes = document.querySelectorAll('.ant-checkbox, input[type="checkbox"], .ant-checkbox-wrapper');
            return Array.from(checkboxes).filter(el => {
                const r = el.getBoundingClientRect();
                return el.offsetParent !== null && r.width > 5;
            }).map(el => ({
                tag: el.tagName,
                cls: (el.className||'').toString().substring(0, 40),
                x: Math.round(el.getBoundingClientRect().x),
                y: Math.round(el.getBoundingClientRect().y),
                w: Math.round(el.getBoundingClientRect().width),
                h: Math.round(el.getBoundingClientRect().height),
                text: (el.textContent||el.parentElement?.textContent||'').trim().substring(0, 30)
            }));
        }""")

        print(f"  checkbox: {len(checkbox_info)}个")
        for c in checkbox_info:
            print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} text={c['text']!r}")

        if checkbox_info:
            # 点击第一个checkbox（全选或表格本体）
            c = checkbox_info[0]
            await bi_page.mouse.click(c['x']+c['w']//2, c['y']+c['h']//2)
            print(f"  ✓ 点击checkbox: {c['text']!r}")
            table_selected = True
            await asyncio.sleep(1)
    except Exception as e:
        print(f"  checkbox选择异常: {e}")

    if not table_selected:
        # 尝试找表格组件卡片
        try:
            # 找"表格"文字或table相关元素
            table_el = bi_page.locator("text=表格").first
            if await table_el.count() > 0 and await table_el.is_visible():
                await table_el.click(timeout=5000)
                print("  ✓ 点击'表格'")
                table_selected = True
        except:
            pass

    if not table_selected:
        # 尝试点击导出面板中的第一个可选元素
        panel_items = await bi_page.evaluate("""() => {
            // 找批量导出面板中的可选项
            const panel = document.querySelector('.ant-modal, .ant-popover, [class*=export-panel], [class*=batch]');
            if (!panel) return [];
            const items = panel.querySelectorAll('.ant-card, .ant-list-item, [class*=chart-item], [class*=component-item], tr, [class*=selectable]');
            return Array.from(items).filter(el => {
                const r = el.getBoundingClientRect();
                return el.offsetParent !== null && r.width > 50 && r.height > 20;
            }).slice(0, 5).map(el => ({
                tag: el.tagName,
                text: (el.textContent||'').trim().substring(0, 40),
                x: Math.round(el.getBoundingClientRect().x),
                y: Math.round(el.getBoundingClientRect().y),
                w: Math.round(el.getBoundingClientRect().width),
                h: Math.round(el.getBoundingClientRect().height)
            }));
        }""")
        if panel_items:
            p = panel_items[0]
            await bi_page.mouse.click(p['x']+p['w']//2, p['y']+p['h']//2)
            print(f"  ✓ 点击面板项: {p['text'][:20]!r}")
            table_selected = True

    await asyncio.sleep(1)
    await snap(bi_page, f"{report_name[:4]}_table_selected")

    # ---- 5d: 再次点击"批量导出excel"按钮 ----
    print("  [5d] 再次点击'批量导出excel'")
    await snap(bi_page, f"{report_name[:4]}_before_batch2")
    batch2_clicked = False
    try:
        # 此时"批量导出Excel"变成了一个确认按钮
        batch2_el = bi_page.locator("button:has-text('批量导出Excel')").first
        if await batch2_el.count() > 0 and await batch2_el.is_visible():
            await batch2_el.click(timeout=5000)
            print("  ✓ 点击'批量导出Excel'按钮(文字定位)")
            batch2_clicked = True
    except Exception as e:
        print(f"  文字定位batch2失败: {e}")

    if not batch2_clicked:
        # 兜底：找primary按钮
        try:
            primary_btn = bi_page.locator(".ant-btn-primary:has-text('批量导出')").first
            if await primary_btn.count() > 0 and await primary_btn.is_visible():
                await primary_btn.click(timeout=5000)
                print("  ✓ 点击primary'批量导出'按钮")
                batch2_clicked = True
        except:
            pass

    if not batch2_clicked:
        # 最后兜底：找所有蓝色(ant-btn-primary)按钮
        primary_btns = await bi_page.evaluate("""() => {
            return Array.from(document.querySelectorAll('.ant-btn-primary, button')).filter(el => {
                const r = el.getBoundingClientRect();
                const t = (el.textContent||'').trim();
                return el.offsetParent !== null && r.width > 30 &&
                       (t.includes('批量') || t.includes('导出') || t.includes('确定') || t.includes('确认')) &&
                       r.y > 50;
            }).map(el => ({
                text: (el.textContent||'').trim().substring(0, 20),
                cls: (el.className||'').toString().substring(0, 40),
                x: Math.round(el.getBoundingClientRect().x),
                y: Math.round(el.getBoundingClientRect().y),
                w: Math.round(el.getBoundingClientRect().width),
                h: Math.round(el.getBoundingClientRect().height)
            }));
        }""")
        if primary_btns:
            b = primary_btns[0]
            await bi_page.mouse.click(b['x']+b['w']//2, b['y']+b['h']//2)
            print(f"  ✓ 点击按钮(兜底): {b['text']!r}")
            batch2_clicked = True

    await asyncio.sleep(2)
    await snap(bi_page, f"{report_name[:4]}_after_batch2")

    # ---- 5e: 点击蓝色"确定" ----
    print("  [5e] 点击蓝色'确定'")
    await snap(bi_page, f"{report_name[:4]}_before_confirm")
    # 先打印所有按钮，辅助调试
    all_btns = await bi_page.evaluate("""() => {
        return Array.from(document.querySelectorAll('button, .ant-btn')).filter(el => {
            return el.offsetParent !== null;
        }).map(el => ({
            text: (el.textContent||'').trim().substring(0, 20),
            cls: (el.className||'').toString().substring(0, 40),
            x: Math.round(el.getBoundingClientRect().x),
            y: Math.round(el.getBoundingClientRect().y)
        }));
    }""")
    print(f"  当前可见按钮({len(all_btns)}个):")
    for b in all_btns:
        print(f"    ({b['x']},{b['y']}) '{b['text']}' cls={b['cls'][:30]}")
    confirm_clicked = False
    try:
        # 用文字定位"确定"
        confirm_el = bi_page.locator("button:has-text('确定')").first
        if await confirm_el.count() > 0 and await confirm_el.is_visible():
            await confirm_el.click(timeout=5000)
            print("  ✓ 点击'确定'(文字定位)")
            confirm_clicked = True
    except Exception as e:
        print(f"  文字定位'确定'失败: {e}")

    if not confirm_clicked:
        try:
            confirm_el = bi_page.locator("text=确定").first
            if await confirm_el.count() > 0 and await confirm_el.is_visible():
                await confirm_el.click(timeout=5000)
                print("  ✓ 点击'确定'(宽泛文字定位)")
                confirm_clicked = True
        except:
            pass

    if not confirm_clicked:
        # 兜底：找蓝色(ant-btn-primary)确定按钮
        try:
            primary_ok = bi_page.locator(".ant-btn-primary").last
            if await primary_ok.count() > 0 and await primary_ok.is_visible():
                await primary_ok.click(timeout=5000)
                print("  ✓ 点击primary按钮(兜底)")
                confirm_clicked = True
        except:
            pass

    await asyncio.sleep(2)
    await snap(bi_page, f"{report_name[:4]}_after_confirm")

    # 确认弹窗已关闭 — 检查是否还有modal存在
    modal_check = await bi_page.evaluate("""() => {
        const modals = document.querySelectorAll('.ant-modal');
        return Array.from(modals).filter(m => m.offsetParent !== null).length;
    }""")
    print(f"  剩余弹窗数: {modal_check}")
    if modal_check > 0:
        print("  ⚠ 弹窗未关闭！再尝试关闭")
        await snap(bi_page, f"{report_name[:4]}_modal_still_open")
        # 再点一次确定
        try:
            await bi_page.locator("button:has-text('确定')").first.click(timeout=3000)
            print("  再次点击'确定'")
            await asyncio.sleep(2)
        except:
            pass

    # ---- 5f: 等待下载 ----
    # 双保险：Playwright download事件 + 文件轮询
    print(f"  [5f] 等待下载...")
    timeout_sec = 600 if wait_longer else 90
    downloaded = False

    # 记录当前已有的xlsx文件
    existing_xlsx = set(glob.glob(os.path.join(DL, "*.xlsx")))

    start_time = time_mod.time()
    download_event = None

    # 异步等download事件
    async def wait_download():
        nonlocal download_event
        try:
            download_event = await bi_page.wait_for_event("download", timeout=timeout_sec * 1000)
        except:
            pass

    download_task = asyncio.create_task(wait_download())

    # 文件轮询
    while time_mod.time() - start_time < timeout_sec:
        await asyncio.sleep(3)
        elapsed = int(time_mod.time() - start_time)

        # 检查download事件
        if download_event:
            try:
                fn = download_event.suggested_filename or f"{report_name}.xlsx"
                path = os.path.join(DL, fn)
                await download_event.save_as(path)
                fsize = os.path.getsize(path)
                print(f"  ✓✓✓ 下载成功(download事件): {fn} ({fsize} bytes)")
                downloaded = True
                break
            except Exception as e:
                print(f"  download事件保存失败: {e}")
                download_event = None

        # 检查新文件
        current_xlsx = set(glob.glob(os.path.join(DL, "*.xlsx")))
        new_files = current_xlsx - existing_xlsx
        for f in new_files:
            fsize = os.path.getsize(f)
            if fsize > 10000:
                fn = os.path.basename(f)
                print(f"  ✓✓✓ 下载成功(文件轮询): {fn} ({fsize} bytes)")
                downloaded = True
                break
        if downloaded:
            break

        if elapsed % 30 < 3:
            print(f"  ...等待中({elapsed}s)")

    if not download_task.done():
        download_task.cancel()
        try:
            await download_task
        except:
            pass

    if not downloaded:
        await snap(bi_page, f"{report_name[:4]}_download_failed")
        # 打印当前所有按钮
        btns = await bi_page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button, .ant-btn')).filter(el => {
                return el.offsetParent !== null;
            }).map(el => ({
                text: (el.textContent||'').trim().substring(0, 20),
                cls: (el.className||'').toString().substring(0, 40),
                x: Math.round(el.getBoundingClientRect().x),
                y: Math.round(el.getBoundingClientRect().y)
            }));
        }""")
        print(f"  当前可见按钮({len(btns)}个):")
        for b in btns:
            print(f"    ({b['x']},{b['y']}) '{b['text']}' cls={b['cls'][:30]}")

    # 下载结束后强制关闭所有弹窗，防止影响下一个报表
    print("  清理弹窗...")
    closed = await bi_page.evaluate("""() => {
        let count = 0;
        // 点击所有关闭按钮
        document.querySelectorAll('.ant-modal-close, [aria-label="Close"]').forEach(el => {
            if (el.offsetParent !== null) {
                el.click();
                count++;
            }
        });
        // 点击所有取消按钮
        document.querySelectorAll('button').forEach(el => {
            const t = (el.textContent||'').trim();
            if ((t === '取消' || t === '关闭') && el.offsetParent !== null) {
                el.click();
                count++;
            }
        });
        return count;
    }""")
    if closed > 0:
        print(f"  关闭了{closed}个弹窗/按钮")
        await asyncio.sleep(2)
    else:
        print("  无残留弹窗")

    return downloaded


# ============================================================
# 主流程
# ============================================================
async def main():
    print("=" * 60)
    print("  OA BI报表导出 v17 - 全文字定位版")
    print(f"  日期: {daterange()[0]} ~ {daterange()[1]}")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome",
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--window-size=1536,864",
                "--headless=new",
            ]
        )
        ctx = await browser.new_context(
            viewport={"width": 1536, "height": 864},
            accept_downloads=True,
            locale="zh-CN",
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )

        try:
            # Step 1: 登录
            page = await login(ctx)

            # Step 2: 进入BI
            bi_page = await enter_bi(page)
            if not bi_page:
                print("✗ 无法进入BI，退出")
                return

            results = {}

            # ====== 报表1: 工单明细查询表 ======
            print("\n" + "=" * 60)
            print("  报表1: 工单明细查询表")
            print("=" * 60)

            ok = await select_report(bi_page, "工单明细查询表")
            if ok:
                await fill_dates(bi_page, "工单明细查询表")
                ok2 = await export_excel(bi_page, "工单明细查询表", wait_longer=False)
                results["工单明细查询表"] = ok2
            else:
                results["工单明细查询表"] = False

            # ====== 报表2: 随手拍工单统计明细表 ======
            print("\n" + "=" * 60)
            print("  报表2: 随手拍工单统计明细表")
            print("=" * 60)

            ok = await select_report(bi_page, "随手拍工单统计明细表")
            if ok:
                await fill_dates(bi_page, "随手拍工单统计明细表", wait_longer=True)
                ok2 = await export_excel(bi_page, "随手拍工单统计明细表", wait_longer=True)
                results["随手拍工单统计明细表"] = ok2
            else:
                results["随手拍工单统计明细表"] = False

            # 汇总
            print("\n" + "=" * 60)
            xlsx_files = glob.glob(os.path.join(DL, "*.xlsx"))
            if xlsx_files:
                print(f"  ✓ xlsx文件:")
                for f in xlsx_files:
                    print(f"    {os.path.basename(f)} ({os.path.getsize(f)} bytes)")
            else:
                print(f"  ✗ 没有xlsx文件")
            for r, ok in results.items():
                print(f"  {'✓' if ok else '✗'} {r}")
            print("=" * 60)
            await asyncio.sleep(10)
        except Exception as e:
            print(f"\n✗ 错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
