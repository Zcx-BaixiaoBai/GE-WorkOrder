# 金鹰工单KPI管理 - 架构设计文档

> 部署模式：**本地桌面应用**（客户终端直接运行，无需维护服务器）
> 版本：v2.0（2026-04-10 从服务器方案迁移至本地方案）

---

## 1. 系统架构总览

```
┌─────────────────────────────────────────────────┐
│              金鹰工单KPI管理系统               │
│           (PyInstaller 打包，双击即用)            │
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌──────────┐   localhost:8765   ┌────────────┐ │
│  │  前端UI  │ ◄── HTTP/WebSocket ─► │  FastAPI   │ │
│  │ (HTML/JS)│                     │  后端服务   │ │
│  └──────────┘                     └─────┬──────┘ │
│                                         │        │
│                    ┌────────────────────┼────┐   │
│                    │                    │    │   │
│               ┌────▼────┐  ┌─────▼──┐ ┌▼───▼┐  │
│               │ SQLite  │  │异步任务 │ │爬虫 │  │
│               │ 数据库  │  │ 调度器  │ │引擎 │  │
│               └─────────┘  └────────┘ └─────┘  │
│                                                  │
└─────────────────────────────────────────────────┘
```

### 核心组件

| 组件 | 技术 | 职责 |
|------|------|------|
| **前端** | HTML/CSS/JS (Ant Design风格) | 6模块UI，模拟/真实双层API |
| **后端** | FastAPI (内嵌localhost) | 28个API端点 + WebSocket进度推送 |
| **数据库** | SQLite (单文件) | 工单、人力、配置、统计持久化 |
| **爬虫** | Playwright (无头模式) | BI系统自动抓取工单数据 |
| **调度** | asyncio + APScheduler | 定时同步、后台任务 |
| **打包** | PyInstaller | 单exe分发，零配置运行 |

---

## 2. 项目目录结构

```
golden-eagle-kpi/
├── main.py                    # 应用入口（启动FastAPI + 打开浏览器）
├── build.spec                 # PyInstaller打包配置
├── requirements.txt           # Python依赖
├── README.md                  # 使用说明
│
├── backend/                   # 后端核心
│   ├── __init__.py
│   ├── app.py                 # FastAPI应用工厂
│   ├── config.py              # 配置管理（路径、端口、定时规则）
│   ├── database.py            # SQLite连接、初始化、迁移
│   │
│   ├── api/                   # API路由层
│   │   ├── __init__.py
│   │   ├── auth.py            # 登录/登出 (2端点)
│   │   ├── dashboard.py       # 驾驶舱数据 (4端点)
│   │   ├── tickets.py         # 工单查询/详情 (5端点)
│   │   ├── personnel.py       # 人力清单 (5端点)
│   │   ├── sync.py            # 数据同步 (4端点)
│   │   ├── config_api.py      # 需求配置 (5端点)
│   │   ├── export.py          # 导出 (2端点)
│   │   └── ws.py              # WebSocket进度推送
│   │
│   ├── models/                # 数据模型（SQLAlchemy ORM）
│   │   ├── __init__.py
│   │   ├── work_ticket.py     # 工单明细
│   │   ├── snapshot.py        # 随手拍工单
│   │   ├── personnel.py       # 人力清单
│   │   ├── project.py         # 项目配置
│   │   ├── sync_log.py        # 同步日志
│   │   └── user.py            # 用户会话
│   │
│   ├── services/              # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── auth_service.py    # OA验证 + 工号匹配 + 角色映射
│   │   ├── stats_service.py   # 统计计算（KPI、完成率、及时率）
│   │   ├── ticket_service.py  # 工单查询、过滤、聚合
│   │   ├── personnel_service.py # 人力清单CRUD + 角色映射
│   │   ├── sync_service.py    # 数据同步编排
│   │   ├── export_service.py  # Excel导出
│   │   └── config_service.py  # KPI/面积/映射配置
│   │
│   └── scraper/               # BI爬虫模块
│       ├── __init__.py
│       ├── bi_client.py       # BI系统登录 + Cookie管理
│       ├── ticket_scraper.py  # 工单明细表抓取
│       ├── snapshot_scraper.py # 随手拍表抓取
│       └── parser.py          # Excel解析 + 数据清洗
│
├── frontend/                  # 前端静态文件
│   ├── index.html             # 主页面
│   ├── css/
│   │   └── style.css          # 样式
│   └── js/
│       ├── app.js             # 主应用逻辑
│       ├── api.js             # API服务层（模拟/真实切换）
│       └── modules/           # 各功能模块JS
│
├── data/                      # 运行时数据（gitignore）
│   ├── golden_eagle_kpi.db       # SQLite数据库文件
│   ├── exports/               # 导出文件临时目录
│   └── logs/                  # 应用日志
│
├── migrations/                # 数据库迁移脚本
│   └── versions/
│
└── tests/                     # 测试
    ├── test_api/
    ├── test_services/
    └── test_scraper/
```

---

## 3. SQLite 数据库设计

### 3.1 核心原则

- **工号统一 VARCHAR(10)**，保留前导零，防止科学计数法
- **生成列** 替代触发器，自动计算 is_completed/is_timely/process_days
- **视图** 替代物化视图（SQLite不支持），查询时动态计算统计
- **WAL模式** 提升并发读写性能

### 3.2 表结构

#### work_tickets（工单明细表）

```sql
CREATE TABLE work_tickets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_no       VARCHAR(50) NOT NULL UNIQUE,     -- 工单编号
    project_name    VARCHAR(100) NOT NULL,            -- BI项目名称（原始值）
    standard_name   VARCHAR(100),                     -- 标准项目名称（映射后）
    project_id      INTEGER REFERENCES projects(id),  -- 关联标准项目
    order_type      VARCHAR(50),                      -- 工单类型
    order_status    VARCHAR(20),                      -- 工单状态
    initiator_id    VARCHAR(10) NOT NULL,             -- 发起人工号（强制字符串，补零）
    initiator_name  VARCHAR(50),                      -- 发起人姓名
    create_time     DATETIME,                         -- 创建时间
    accept_time     DATETIME,                         -- 接单时间
    complete_time   DATETIME,                         -- 完工时间
    deadline        DATETIME,                         -- 规定时限
    area_name       VARCHAR(50),                      -- 区域
    description     TEXT,                             -- 工单描述
    sync_batch_id   INTEGER REFERENCES sync_logs(id), -- 同步批次
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- 生成列（自动计算）
    is_completed    INTEGER GENERATED ALWAYS AS (
        CASE WHEN order_status IN ('已完成', '已关闭') THEN 1 ELSE 0 END
    ) STORED,
    is_timely       INTEGER GENERATED ALWAYS AS (
        CASE WHEN complete_time IS NOT NULL AND deadline IS NOT NULL
             AND complete_time <= deadline THEN 1
             ELSE 0 END
    ) STORED,
    process_days    REAL GENERATED ALWAYS AS (
        CASE WHEN create_time IS NOT NULL AND complete_time IS NOT NULL
             THEN ROUND((julianday(complete_time) - julianday(create_time)), 2)
             ELSE NULL END
    ) STORED
);

CREATE INDEX idx_tickets_project ON work_tickets(project_id);
CREATE INDEX idx_tickets_initiator ON work_tickets(initiator_id);
CREATE INDEX idx_tickets_create_time ON work_tickets(create_time);
CREATE INDEX idx_tickets_status ON work_tickets(order_status);
CREATE INDEX idx_tickets_sync_batch ON work_tickets(sync_batch_id);
```

#### snapshots（随手拍工单表）

```sql
CREATE TABLE snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_no       VARCHAR(50) NOT NULL UNIQUE,
    project_name    VARCHAR(100) NOT NULL,
    standard_name   VARCHAR(100),
    project_id      INTEGER REFERENCES projects(id),
    order_type      VARCHAR(50),
    order_status    VARCHAR(20),
    initiator_id    VARCHAR(10) NOT NULL,
    initiator_name  VARCHAR(50),
    create_time     DATETIME,
    accept_time     DATETIME,
    complete_time   DATETIME,
    deadline        DATETIME,
    area_name       VARCHAR(50),
    description     TEXT,
    photo_count     INTEGER DEFAULT 0,               -- 随手拍特有：照片数
    sync_batch_id   INTEGER REFERENCES sync_logs(id),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    is_completed    INTEGER GENERATED ALWAYS AS (
        CASE WHEN order_status IN ('已完成', '已关闭') THEN 1 ELSE 0 END
    ) STORED,
    is_timely       INTEGER GENERATED ALWAYS AS (
        CASE WHEN complete_time IS NOT NULL AND deadline IS NOT NULL
             AND complete_time <= deadline THEN 1 ELSE 0 END
    ) STORED
);

CREATE INDEX idx_snapshots_project ON snapshots(project_id);
CREATE INDEX idx_snapshots_initiator ON snapshots(initiator_id);
CREATE INDEX idx_snapshots_create_time ON snapshots(create_time);
```

#### personnel（人力清单）

```sql
CREATE TABLE personnel (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id     VARCHAR(10) NOT NULL UNIQUE,      -- 工号（补零后）
    name            VARCHAR(50) NOT NULL,
    project_id      INTEGER REFERENCES projects(id),   -- 所属项目
    role            VARCHAR(50),                       -- 角色（主管/领班/保洁等）
    is_outsourcing  INTEGER DEFAULT 0,                 -- 是否外包人员
    phone           VARCHAR(20),
    entry_date      DATE,
    status          VARCHAR(20) DEFAULT '在职',         -- 在职/离职
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_personnel_project ON personnel(project_id);
CREATE INDEX idx_personnel_role ON personnel(role);
```

#### projects（项目配置）

```sql
CREATE TABLE projects (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                VARCHAR(100) NOT NULL UNIQUE,  -- 标准项目名称
    bi_names            TEXT,                           -- BI项目名列表（JSON数组）
    area                REAL,                           -- 项目面积（㎡）
    outsourcing_target  REAL GENERATED ALWAYS AS (area * 20) STORED,  -- 外包编制=面积×20
    manager_id          VARCHAR(10),                    -- 项目负责人工号
    manager_name        VARCHAR(50),                    -- 项目负责人姓名
    kpi_completion_rate REAL DEFAULT 95.0,              -- KPI完成率目标(%)
    kpi_timely_rate     REAL DEFAULT 90.0,              -- KPI及时率目标(%)
    status              VARCHAR(20) DEFAULT 'active',
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### project_name_mapping（BI项目名称对照）

```sql
CREATE TABLE project_name_mapping (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bi_name         VARCHAR(100) NOT NULL,              -- BI系统中的项目名
    standard_name   VARCHAR(100) NOT NULL,              -- 标准项目名
    project_id      INTEGER REFERENCES projects(id),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bi_name)
);
```

#### role_mapping（角色映射表）

```sql
CREATE TABLE role_mapping (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_role     VARCHAR(50) NOT NULL,               -- 原始角色名
    target_role     VARCHAR(50) NOT NULL,               -- 映射后角色名
    category        VARCHAR(50),                        -- 角色分类
    UNIQUE(source_role)
);
```

#### sync_logs（同步日志）

```sql
CREATE TABLE sync_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_type       VARCHAR(30) NOT NULL,               -- tickets / snapshots
    status          VARCHAR(20) NOT NULL,               -- running / completed / failed
    records_fetched INTEGER DEFAULT 0,
    records_inserted INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    file_size_kb    REAL,                               -- 下载文件大小
    duration_sec    REAL,                               -- 耗时(秒)
    error_message   TEXT,
    started_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at     DATETIME
);
```

#### user_sessions（用户会话）

```sql
CREATE TABLE user_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    token           VARCHAR(64) NOT NULL UNIQUE,
    employee_id     VARCHAR(10) NOT NULL,
    name            VARCHAR(50),
    role            VARCHAR(30),                        -- admin / project_manager / staff
    project_id      INTEGER,                            -- 非管理员关联的项目
    login_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at      DATETIME
);
```

### 3.3 统计视图

```sql
-- 月度统计视图（替代物化视图，查询时动态计算）
CREATE VIEW v_monthly_stats AS
SELECT
    p.id AS project_id,
    p.name AS project_name,
    strftime('%Y-%m', wt.create_time) AS month,
    COUNT(*) AS total_count,
    SUM(wt.is_completed) AS completed_count,
    SUM(wt.is_timely) AS timely_count,
    ROUND(AVG(wt.process_days), 2) AS avg_process_days,
    ROUND(SUM(wt.is_completed) * 100.0 / COUNT(*), 2) AS completion_rate,
    ROUND(SUM(wt.is_timely) * 100.0 / NULLIF(SUM(wt.is_completed), 0), 2) AS timely_rate
FROM work_tickets wt
JOIN projects p ON wt.project_id = p.id
WHERE wt.create_time IS NOT NULL
GROUP BY p.id, strftime('%Y-%m', wt.create_time);

-- 随手拍月度统计
CREATE VIEW v_snapshot_monthly_stats AS
SELECT
    p.id AS project_id,
    p.name AS project_name,
    strftime('%Y-%m', s.create_time) AS month,
    COUNT(*) AS total_count,
    SUM(s.is_completed) AS completed_count,
    SUM(s.is_timely) AS timely_count,
    ROUND(SUM(s.is_completed) * 100.0 / COUNT(*), 2) AS completion_rate,
    ROUND(SUM(s.is_timely) * 100.0 / NULLIF(SUM(s.is_completed), 0), 2) AS timely_rate
FROM snapshots s
JOIN projects p ON s.project_id = p.id
WHERE s.create_time IS NOT NULL
GROUP BY p.id, strftime('%Y-%m', s.create_time);

-- 项目人力概览
CREATE VIEW v_project_personnel AS
SELECT
    p.id AS project_id,
    p.name AS project_name,
    p.area,
    p.outsourcing_target,
    COUNT(pm.id) AS headcount,
    SUM(CASE WHEN pm.is_outsourcing = 1 THEN 1 ELSE 0 END) AS outsourcing_count,
    SUM(CASE WHEN pm.is_outsourcing = 0 THEN 1 ELSE 0 END) AS self_count
FROM projects p
LEFT JOIN personnel pm ON p.id = pm.project_id AND pm.status = '在职'
GROUP BY p.id;
```

---

## 4. API端点设计（28个）

> 请求/响应格式详见 `API-DOCUMENTATION.md`，此处仅列出端点清单和本地化适配说明。

### 4.1 认证模块（2端点）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | OA账号验证 → 工号匹配 → 角色映射 → 返回JWT |
| POST | `/api/auth/logout` | 清除会话 |

### 4.2 驾驶舱（4端点）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard/kpi` | KPI卡片数据（完成率、及时率、人均单量） |
| GET | `/api/dashboard/progress` | 月度进度条（各项目vs目标） |
| GET | `/api/dashboard/alerts` | 预警清单（低于KPI目标的项目） |
| GET | `/api/dashboard/completion` | 完成情况分布 |

### 4.3 工单查询（5端点）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tickets` | 工单列表（分页、过滤） |
| GET | `/api/tickets/{id}` | 工单详情 |
| GET | `/api/tickets/search` | 模糊搜索 |
| GET | `/api/tickets/stats` | 工单统计聚合 |
| GET | `/api/tickets/overdue` | 逾期工单列表 |

### 4.4 人力清单（5端点）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/personnel` | 人力清单（分页） |
| POST | `/api/personnel/import` | 导入人力清单Excel |
| GET | `/api/personnel/export` | 导出人力清单 |
| PUT | `/api/personnel/{id}` | 更新人员信息 |
| DELETE | `/api/personnel/{id}` | 删除人员记录 |

### 4.5 数据同步（4端点）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sync/tickets` | 触发工单明细同步 |
| POST | `/api/sync/snapshots` | 触发随手拍同步 |
| GET | `/api/sync/status` | 当前同步状态 |
| GET | `/api/sync/logs` | 同步历史日志 |

### 4.6 需求配置（5端点）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/config/projects` | 项目列表及配置 |
| PUT | `/api/config/projects/{id}` | 更新项目配置（面积、KPI目标） |
| GET | `/api/config/roles` | 角色映射表 |
| PUT | `/api/config/roles` | 更新角色映射 |
| GET | `/api/config/mappings` | BI项目名称映射 |

### 4.7 导出（2端点）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/export/tickets` | 导出工单Excel |
| GET | `/api/export/stats` | 导出统计报表 |

### 4.8 WebSocket

| 路径 | 说明 |
|------|------|
| `/ws/sync` | 同步进度实时推送 |

---

## 5. 爬虫模块设计

### 5.1 架构

```
┌──────────────────────────────────────────┐
│              爬虫执行流程                  │
│                                          │
│  用户触发/定时触发                         │
│       │                                  │
│       ▼                                  │
│  ┌─────────┐   Cookie    ┌────────────┐ │
│  │ BI登录  │ ──────────► │ 抓取数据   │ │
│  │ (OA账密)│             │ (无头浏览器)│ │
│  └─────────┘             └─────┬──────┘ │
│                                │        │
│                          ┌─────▼──────┐ │
│                          │ Excel解析  │ │
│                          │ + 数据清洗 │ │
│                          └─────┬──────┘ │
│                                │        │
│                          ┌─────▼──────┐ │
│                          │ 入库更新   │ │
│                          │ (Upsert)   │ │
│                          └─────┬──────┘ │
│                                │        │
│                          ┌─────▼──────┐ │
│                          │ WebSocket  │ │
│                          │ 进度推送   │ │
│                          └────────────┘ │
└──────────────────────────────────────────┘
```

### 5.2 数据清洗规则（关键！）

```python
class DataCleaner:
    """数据清洗管线 - 解决已知数据质量问题"""

    @staticmethod
    def clean_employee_id(raw_id) -> str:
        """工号处理：科学计数法 → 字符串 → 补零到10位"""
        if isinstance(raw_id, float):
            # 处理 1.00E+03 这种情况
            raw_id = str(int(raw_id))
        raw_id = str(raw_id).strip()
        # 补零：确保10位，保留前导零
        return raw_id.zfill(10)

    @staticmethod
    def map_project_name(bi_name: str, mapping: dict) -> str:
        """BI项目名 → 标准项目名"""
        return mapping.get(bi_name, bi_name)

    @staticmethod
    def parse_datetime(value) -> Optional[str]:
        """统一时间格式解析"""
        # 处理 Excel 日期序列号、各种字符串格式
        ...
```

### 5.3 Upsert策略

```python
# 工单同步使用 INSERT OR REPLACE（基于 ticket_no 唯一键）
# 不删除已有记录，只更新变化字段
# sync_batch_id 标记本批次，可用于后续清理孤立记录
```

### 5.4 性能预期

| 指标 | 工单明细表 | 随手拍表 |
|------|-----------|---------|
| 下载大小 | ~13 MB | ~8 MB |
| 预计行数 | ~3万行 | ~2万行 |
| 解析+入库耗时 | ~15秒 | ~10秒 |
| 内存峰值 | ~200 MB | ~150 MB |

---

## 6. 前端对接方案

### 6.1 切换配置

前端已有 `CONFIG.USE_MOCK` 双层切换机制。本地运行时：

```javascript
const CONFIG = {
    API_BASE_URL: 'http://localhost:8765',  // 本地FastAPI
    USE_MOCK: false,                         // 切换到真实API
    WS_URL: 'ws://localhost:8765/ws/sync',   // WebSocket
};
```

### 6.2 对接清单

| 前端行为 | 后端需实现 |
|---------|-----------|
| `API.request('/auth/login', {username, password})` | OA验证 → 工号查人力清单 → 角色映射 → JWT |
| `API.request('/dashboard/kpi', {projectId})` | 查询v_monthly_stats → 聚合KPI |
| `API.request('/sync/tickets')` | 启动asyncio爬虫任务 → WebSocket推送进度 |
| 自动附加 `projectId` 参数 | 后端从JWT解析角色，非管理员忽略传入的projectId |

---

## 7. 应用启动流程

```python
# main.py 启动流程

def main():
    # 1. 初始化配置
    config = AppConfig.load()

    # 2. 初始化数据库（首次自动创建表+导入初始数据）
    init_database(config.db_path)

    # 3. 创建FastAPI应用
    app = create_app(config)

    # 4. 启动后台调度器（可选的定时同步）
    scheduler = setup_scheduler(config)
    scheduler.start()

    # 5. 启动FastAPI服务
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")

    # 6. 自动打开浏览器
    webbrowser.open("http://localhost:8765")
```

### 首次运行自动初始化

```
首次启动 → 检测到无数据库文件
         → 自动创建 SQLite 数据库
         → 自动创建所有表
         → 提示导入初始化数据（人力清单、项目对照、负责人清单）
         → 或从data/目录自动加载
```

---

## 8. 打包与分发

### 8.1 PyInstaller配置

```python
# build.spec 关键配置
a = Analysis(
    ['main.py'],
    datas=[
        ('frontend', 'frontend'),          # 前端静态文件
        ('migrations', 'migrations'),       # 数据库迁移
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
    ],
)
```

### 8.2 分发物

```
dist/
└── 金鹰工单KPI管理/
    ├── 金鹰工单KPI管理.exe     # 主程序（~80MB，含Python运行时）
    ├── frontend/                # 前端资源
    └── README.txt               # 使用说明
```

### 8.3 运行环境要求

- Windows 10/11（客户终端）
- 无需安装Python、数据库、浏览器
- 首次运行需联网登录BI系统（之后可离线使用已有数据）
- 需有Chrome/Edge浏览器（Playwright依赖，打包时内嵌Chromium）

---

## 9. 安全设计

| 场景 | 方案 |
|------|------|
| OA认证 | 密码不存储，仅用于BI登录验证，验证通过后发JWT |
| JWT Token | 存储在浏览器localStorage，过期时间8小时 |
| 数据库 | 本地SQLite文件，无网络暴露 |
| 爬虫Cookie | 仅内存中保持，不持久化 |
| 导出文件 | 存放在data/exports/，用户手动管理 |

---

## 10. 技术栈汇总

| 层级 | 技术 | 版本 |
|------|------|------|
| 语言 | Python | 3.11+ |
| Web框架 | FastAPI | 0.110+ |
| ASGI | Uvicorn | 0.29+ |
| ORM | SQLAlchemy | 2.0+ |
| 数据库 | SQLite | 3.42+ (Python内嵌) |
| 爬虫 | Playwright | 1.42+ |
| Excel处理 | openpyxl | 3.1+ |
| 定时任务 | APScheduler | 3.10+ |
| JWT | PyJWT | 2.8+ |
| 打包 | PyInstaller | 6.0+ |
| 前端 | 原生HTML/CSS/JS | - |
