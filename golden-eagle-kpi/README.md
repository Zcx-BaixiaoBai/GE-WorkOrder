# 金鹰工单KPI管理系统 v1.1.0

金鹰国际物业集团的工单绩效管理平台，整合三大业务数据源（BI工单、筹建专项、IPMS设备），提供数据采集、KPI考核到AI智能分析的完整业务闭环。

## 功能概览

- **概览驾驶舱**：KPI卡片、趋势图表、预警清单、角色分布
- **工单管理**：多维度筛选、分页表格、详情侧滑、Excel导出
- **人力管理**：人员CRUD、Excel导入、四层级角色筛选、KPI统计
- **计划管理**：金鹰PLAN甘特图（按天精确定位）、巡检/维保任务、8种状态
- **系统配置**：7个Tab（人力清单/角色映射/项目面积/KPI/数据字典/项目负责人/定时任务+AI配置）
- **数据同步**：三通道并发同步（BI/WY/IPMS）、实时进度、日志查看
- **AI助手**：可拖拽浮球、流式对话、自然语言查询数据库
- **定时任务**：任务制CRUD、可视化时间选择、APScheduler动态读取
- **权限分层**：系统管理员（全项目）/ 项目管理员（本项目）/ 普通用户（只读）

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | React 18 + Vite + React Router 6 + ECharts + Axios |
| 后端 | Python 3.11+ / FastAPI / SQLAlchemy / SQLite |
| 爬虫 | Playwright（OA登录）+ httpx（观远BI API直取） |
| AI | NVIDIA API (qwen3.5-122b) / SSE流式输出 |
| 调度 | APScheduler（动态配置） |
| 认证 | JWT + 三角色权限分层 |

## 快速部署

### 环境要求

- Python 3.11+
- Chrome 或 Edge 浏览器（BI爬虫用）
- Node.js 18+（仅前端构建时需要）

### 步骤

```bash
# 1. 克隆仓库
git clone https://github.com/Zcx-BaixiaoBai/GE-WorkOrder.git
cd GE-WorkOrder

# 2. 安装后端依赖
pip install -r requirements.txt
python -m playwright install chromium

# 3. 构建前端（如需修改前端）
cd frontend-react
npm install
npm run build
cp -r dist/* ../frontend/react-dist/
cd ..

# 4. 启动
python -m uvicorn main:app --host 0.0.0.0 --port 8765
```

首次启动会自动生成 `.env` 配置文件（DEV_MODE=1），打开浏览器访问 `http://localhost:8765`。

### 首次登录

1. 用任意工号登录（DEV_MODE=1 时空库可登录为系统管理员）
2. 进入「系统配置 > 人力清单」导入Excel
3. 进入「系统配置 > AI配置」填写API Key
4. 修改 `.env` 中 `DEV_MODE=0` 进入生产模式
5. 重启服务

## 配置说明

所有敏感配置在 `.env` 文件中（首次启动自动生成）：

```env
SERVER_HOST=0.0.0.0        # 0.0.0.0=外网访问, 127.0.0.1=仅本机
SERVER_PORT=8765
DEV_MODE=0                  # 1=开发模式(允许空库登录), 0=生产模式
JWT_SECRET=                 # JWT密钥(自动生成)
AI_API_KEY=                 # NVIDIA API Key
AI_MODEL=qwen/qwen3.5-122b-a10b
SCRAPER_ACCOUNT=            # BI爬虫OA账号
SCRAPER_PASSWORD=           # BI爬虫OA密码
WY_USERNAME=                # WY筹建系统账号
WY_PASSWORD=                # WY筹建系统密码
IPMS_USERNAME=              # IPMS设备系统账号
IPMS_PASSWORD=              # IPMS设备系统密码
```

AI配置和定时任务也可在前端「系统配置」页面直接修改，保存即生效。

## 数据源

| 数据源 | 采集方式 | API |
|--------|---------|-----|
| BI工单 | 观远BI API直取 | POST /api/batchExportCardExcel → 轮询 → 下载 |
| WY筹建 | HTTP API | Token + MD5密码登录 |
| IPMS设备 | HTTP API | Bearer Token认证 |

## API端点

共 55+ 个API端点，主要模块：

- `/api/auth/*` — 登录/登出/用户信息
- `/api/stats/*` — 驾驶舱统计（月度/概览/趋势/分布/预警）
- `/api/tickets/*` — 工单查询/详情
- `/api/personnel/*` — 人员CRUD/导入
- `/api/wy/*` — 筹建专项计划
- `/api/ipms/*` — IPMS巡检/维保
- `/api/config/*` — 项目/角色映射/定时任务/AI配置
- `/api/sync_all/*` — 三通道并发同步
- `/api/ai/chat/stream` — AI流式对话
- `/api/export/*` — Excel导出
- `/api/health` — 健康检查

## 项目结构

```
GE-WorkOrder/
├── main.py                  # FastAPI入口
├── backend/
│   ├── api/                 # 16个API路由模块
│   ├── models/              # SQLAlchemy数据模型
│   ├── services/            # 业务逻辑层
│   └── scraper/             # 爬虫客户端(BI/WY/IPMS)
├── frontend/
│   ├── index.html           # 旧版前端(降级用)
│   ├── echarts.min.js       # ECharts本地化
│   └── react-dist/          # React构建产物
├── frontend-react/          # React源码
│   ├── src/
│   │   ├── components/      # Layout/AIFloat/SyncScheduleTab/AIConfigTab/Toast
│   │   ├── pages/           # Login/Dashboard/Tickets/Personnel/Plans/Settings/Sync
│   │   ├── services/        # api.js(axios) + auth.jsx(AuthProvider)
│   │   └── styles/          # global.css(Codex极简风格)
│   └── vite.config.js
├── data/
│   └── golden_eagle_kpi.db  # 初始数据库(40项目+900人员)
├── .env.example             # 配置模板
└── requirements.txt
```

## 系统支持

| 系统 | 支持 | 说明 |
|------|------|------|
| Windows 10/11 | ✅ | 主要开发环境 |
| Windows Server | ✅ | 可作为后台服务运行 |
| Ubuntu/Debian | ✅ | 需安装Chrome |
| macOS | ✅ | 需安装Chrome |

## 浏览器兼容

前端支持现代浏览器：Chrome 90+ / Edge 90+ / Firefox 90+ / Safari 15+

## License

私有项目，金鹰国际物业集团内部使用。
