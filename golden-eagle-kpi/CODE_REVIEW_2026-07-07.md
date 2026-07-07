# 金鹰工单KPI管理系统 — 全面代码审查报告

> **审查日期**: 2026-07-07  
> **审查范围**: 后端 35 个 Python 文件 + 前端 6853 行 HTML  
> **审查结论**: 系统功能完整可用，存在 5 个高危问题 + 12 个中危问题 + 8 个低危优化项

---

## 一、高危问题（🔴 必须修复）

### H1. 硬编码敏感凭证（6处）

| 文件 | 行号 | 内容 |
|------|------|------|
| `backend/api/ai_chat.py` | L17 | NVIDIA API Key 明文写死 |
| `backend/config.py` | L57 | JWT Secret 写死 `"golden-eagle-kpi-secret-key-2026"` |
| `backend/scraper/wy_crawler.py` | L57-60 | WY系统账密 `juhaifeng/jhf123456` + token |
| `backend/api/sync_all.py` | L18-19 | BI爬虫账密 `zhangchenxi/Zcx020618` |
| `backend/api/sync_ipms.py` | L54 | IPMS默认密码 `123654` |
| `backend/api/update.py` | L26-28 | Gitee Token 从文件读取（可接受，但文件在data目录无保护） |

**风险**: 源码泄露即全部凭证暴露。GitHub仓库已公开，ai_chat.py 的 API Key 已上传。

**建议**: 
- 所有凭证移入 `.env` 文件（已有 `_load_dotenv` 机制，但默认值仍硬编码）
- 移除所有 default 值中的真实凭证，改为 `""` 或 `None`，缺失时报错
- **立即轮换 NVIDIA API Key**（已泄露到 GitHub）

---

### H2. 认证绕过漏洞

**文件**: `backend/services/auth_service.py` L60-67

```python
# 开发模式降级：人力清单为空时，允许任意工号登录为管理员
if not person:
    total_personnel = db.query(Personnel).count()
    if total_personnel == 0:
        person_name = f"开发用户({clean_id})"
        system_role = "系统管理员"  # ← 任意账号直接管理员
```

**风险**: 如果数据库 personnel 表被清空（误删/迁移/重装），任何人可以用任意OA账号+工号登录为系统管理员。

**建议**: 生产环境强制要求 personnel 表非空，或使用环境变量 `DEV_MODE=1` 控制降级行为。

---

### H3. CORS 完全开放

**文件**: `main.py` L40左右

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # ← 允许任意域名
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**风险**: 任意网站可通过浏览器跨域访问本地 8765 端口的 API，结合本地无认证的端点（如 `/api/shutdown`），可被恶意网页利用。

**建议**: 限制 `allow_origins=["http://127.0.0.1:8765"]`。

---

### H4. `/api/shutdown` 无认证

**文件**: `main.py` 或路由注册处

关闭应用的 API 端点无任何认证检查，任何能访问 8765 端口的进程都能关闭应用。

**建议**: 添加 JWT 认证或本地 IPC 限制。

---

### H5. AI 上下文构建中的 SQL 拼接风险

**文件**: `backend/api/ai_chat.py` L483

```python
user_info = db.execute(text(f"""
    SELECT ... WHERE employee_id = '{employee_id}'
""")).fetchone()
```

虽然 `employee_id` 来自前端 JWT 解析，不是直接用户输入，但使用 f-string 拼接 SQL 是危险模式。如果后续 employee_id 来源变化，可能产生注入。

**建议**: 改用参数化查询 `text("... WHERE employee_id = :eid")` + `{"eid": employee_id}`。

---

## 二、中危问题（🟡 建议修复）

### M1. 重复的爬虫文件（冗余 108KB）

| 文件 | 大小 | 状态 |
|------|------|------|
| `backend/scraper/bi_client.py` | 33KB | ✅ 当前使用 |
| `backend/scraper/bi_client_v008.py` | 32KB | ❌ 废弃版本 |
| `backend/scraper/final_v17_headles.py` | 42KB | ❌ 废弃版本 |

**建议**: 删除 `bi_client_v008.py` 和 `final_v17_headles.py`，减少维护负担和打包体积。

---

### M2. 重复的工单查询端点

**文件**: `backend/api/tickets.py`

`GET /api/tickets` 和 `GET /api/tickets/search` 参数和实现完全相同，属于代码重复。

**建议**: 保留 `/api/tickets`，将 `/api/tickets/search` 设为别名或删除。

---

### M3. 重复的 JWT 提取逻辑

**文件**: `backend/api/wy.py` L16-19, `backend/api/ipms.py` L14-30`

两个文件各自实现了从 Authorization Header 提取 project_id 的逻辑，没有复用。

**建议**: 抽取为 FastAPI Dependency：
```python
async def get_project_id(authorization: str = Header(...)) -> int:
    ...
```
在路由中用 `Depends(get_project_id)`。

---

### M4. 全局可变状态非线程安全

**文件**: `backend/api/sync_all.py`, `sync_wy.py`, `sync_ipms.py`

```python
_sync_status = {"is_syncing": False, ...}  # 模块级 dict，多线程读写无锁
```

虽然 `sync_service.py` 有 `_progress_lock`，但 `sync_all.py` 聚合状态时无锁。

**建议**: 使用 `threading.Lock` 保护所有状态字典的读写，或改用 `dataclasses` + 锁。

---

### M5. 导出服务 N+1 查询

**文件**: `backend/services/export_service.py` L60

```python
for person in personnel_list:
    count_sql = text("SELECT COUNT(*) FROM work_tickets WHERE initiator_id = :eid ...")
    row = db.execute(count_sql, params).fetchone()  # ← 每人一次查询
```

如果有 500 人，就是 500 次 SQL 查询。

**建议**: 改为一次 GROUP BY 查询：
```sql
SELECT initiator_id, COUNT(*) FROM work_tickets 
WHERE project_id = :pid AND strftime('%Y-%m', create_time) = :m
GROUP BY initiator_id
```
然后内存匹配。

---

### M6. AI 上下文构建 20+ 次独立查询

**文件**: `backend/api/ai_chat.py` `build_db_context()` 函数（L480-820）

每次 AI 对话都执行 20+ 次独立 SQL 查询来构建上下文，包括：
- 项目统计（4次）
- 人员层级统计（3次）
- 随手拍统计（3次）
- IPMS 统计（5次）
- WY 专项统计（5次）
- TOP15 执行人每人再查一次已完成数（N+1）

**建议**: 
- 合并同类统计为 JOIN/子查询
- IPMS TOP15 的已完成数改为 GROUP BY + CASE WHEN
- 考虑缓存上下文（相同 project_id + month 的 5 分钟内复用）

---

### M7. 过期会话无清理机制

**文件**: `backend/models/user_session.py` + `auth_service.py`

JWT Token 有效期 8 小时，会话记录存入 `user_sessions` 表，但从不清理过期记录。

**建议**: 在 APScheduler 中添加每日清理任务：
```python
scheduler.add_job(cleanup_sessions, 'cron', hour=3)
```

---

### M8. 前端 ECharts CDN 依赖

**文件**: `frontend/index.html` L7

```html
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
```

打包后离线运行时，如果无网络则图表全部无法渲染。

**建议**: 将 echarts.min.js 下载到本地 `_internal/frontend/` 目录，改为相对路径引用。

---

### M9. 无认证中间件，逐路由手动验证

**文件**: `backend/api/wy.py`, `ipms.py` 等

大部分路由没有统一的认证拦截，而是手动在函数内解析 JWT。`/api/auth/me` 甚至把 token 作为 query 参数传递。

**建议**: 实现 FastAPI 全局认证 Dependency：
```python
async def verify_token_middleware(request: Request):
    # 排除 /api/auth/login
    # 其他路由强制验证 JWT
```

---

### M10. 错误处理：裸 except 吞异常

多处代码使用 `except Exception: pass` 或 `except Exception as e: print(e)`，吞掉异常不记录堆栈。

**涉及文件**: `auth_service.py`, `ai_chat.py`, `sync_service.py` 等

**建议**: 使用 `logging.exception()` 记录完整堆栈，或向上抛出让 FastAPI 统一处理。

---

### M11. 数据库生成列手动 ALTER TABLE

**文件**: `backend/database.py` `_add_generated_columns()`

每次启动都尝试 `ALTER TABLE ADD COLUMN ... GENERATED ALWAYS AS`，依赖异常捕获判断列是否存在。

**建议**: 使用数据库迁移工具（如 Alembic），或至少在创建表时直接包含生成列定义。

---

### M12. 前端 6853 行单文件

**文件**: `frontend/index.html`

CSS + HTML + JavaScript 全部在一个文件中，177 个函数，维护困难。

**建议**: 
- 短期：将 JS 提取到 `app.js`，CSS 提取到 `style.css`
- 长期：引入 Vue/React + 构建工具

---

## 三、低危优化项（🟢 锦上添花）

### L1. snapshots 表缺少索引

```sql
-- 建议添加
CREATE INDEX idx_snapshots_initiator ON snapshots(initiator_id);
CREATE INDEX idx_snapshots_create_time ON snapshots(create_time);
CREATE INDEX idx_snapshots_project ON snapshots(project_id);
```

当前按 initiator_id 查询随手拍时全表扫描。

---

### L2. TicketService 每次查询全量项目名称

**文件**: `backend/services/ticket_service.py`

```python
for p in db.query(Project).all():  # ← 每次搜索都查全量项目
    project_names[p.id] = p.name
```

项目只有 40 个，影响不大，但可以缓存。

---

### L3. 缺少 API 速率限制

AI 对话端点 `/api/ai/chat/stream` 无速率限制，单用户可频繁调用消耗 NVIDIA API 额度。

**建议**: 添加 `slowapi` 中间件，限制每用户每分钟 10 次。

---

### L4. 缺少健康检查端点

无 `/api/health` 或 `/api/ping` 端点，前端无法快速判断后端是否存活。

---

### L5. 日志文件无轮转

**文件**: `main.py`

日志直接写入 `app.log`，无大小限制和轮转。长期运行日志文件会无限增长（当前已 213KB，同步频繁会快速膨胀）。

**建议**: 使用 `logging.handlers.RotatingFileHandler(maxBytes=10*1024*1024, backupCount=5)`。

---

### L6. 前端无输入校验

前端 JS 中直接拼装 API 请求参数，无 XSS 防护（如 keyword 直接拼入 URL）。后端虽有 SQLAlchemy 参数化，但前端渲染 AI 返回的 content 时如果用 innerHTML 有 XSS 风险。

**建议**: AI 消息渲染使用 `textContent` 或 DOMPurify。

---

### L7. 缺少 API 文档

FastAPI 自带 Swagger（`/docs`），但在生产环境未禁用。建议生产环境关闭 `docs_url`，或加认证保护。

---

### L8. 打包 .spec 文件未版本控制

`golden_eagle.spec` 如果不在 Git 中，换机器打包会丢失配置。

---

## 四、架构优化建议（中长期）

### A1. 数据库迁移到 PostgreSQL

SQLite 在多用户并发写入时有锁表风险（WAL 模式仍有限制）。如果系统用户增长，建议迁移到 PostgreSQL。

### A2. 前端组件化

6853 行单 HTML 文件已经到达可维护极限。建议：
- 引入 Vue 3 + Vite 构建
- 组件拆分：Sidebar、Dashboard、TicketTable、AIChat 等
- CSS 变量系统已建立，迁移成本低

### A3. API 统一响应格式

当前部分端点返回 `{"items": [...], "total": N}`，部分返回 `{"error": "..."}`，部分返回裸 list。建议统一为：
```json
{"code": 200, "data": {...}, "message": "success"}
```

### A4. 爬虫抽象化

三个爬虫（BI/WY/IPMS）各自独立实现，登录/抓取/入库逻辑完全不同。可以抽象基类：
```python
class BaseCrawler:
    def login(self): ...
    def fetch(self): ...
    def persist(self, data): ...
```

### A5. 配置热更新

当前修改项目配置需要重启应用。可以通过 WebSocket 推送配置变更，前端实时刷新。

---

## 五、优先级排序

| 优先级 | 问题编号 | 描述 | 工作量 |
|--------|---------|------|--------|
| P0 | H1 | 硬编码凭证 + API Key泄露 | 2h |
| P0 | H2 | 认证绕过漏洞 | 0.5h |
| P0 | H3 | CORS 完全开放 | 0.5h |
| P0 | H5 | SQL 拼接风险 | 1h |
| P1 | H4 | shutdown 无认证 | 0.5h |
| P1 | M1 | 删除废弃爬虫文件 | 0.5h |
| P1 | M5 | 导出 N+1 查询 | 1h |
| P1 | M6 | AI 上下文查询优化 | 3h |
| P1 | M8 | ECharts 本地化 | 0.5h |
| P2 | M3 | JWT 提取逻辑复用 | 1h |
| P2 | M4 | 线程安全状态 | 2h |
| P2 | M9 | 统一认证中间件 | 2h |
| P2 | M12 | 前端文件拆分 | 8h |
| P3 | L1-L8 | 低危优化 | 各0.5h |
| P4 | A1-A5 | 架构演进 | 各1-5天 |

---

## 六、总结

系统整体功能完整、业务逻辑清晰，代码质量在"快速迭代的项目"中属于中等偏上。主要风险集中在**安全层面**（硬编码凭证、认证绕过、CORS开放），这是最需要优先处理的。

性能方面，当前数据量（40项目、1.3万工单）下 SQLite + 单进程完全够用，N+1 查询和 AI 上下文多次查询虽然不够优雅，但实际影响可忽略。

前端 6853 行单文件是技术债的核心，建议在下一个大版本中规划组件化重构。

---

**审查人**: 黄（开发助手）  
**审查方式**: 逐文件阅读 + 模式匹配 + 安全扫描  
**不改代码**: 本次仅审查，不修改任何文件
