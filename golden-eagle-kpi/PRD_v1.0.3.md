# 金鹰工单KPI管理系统 v1.0.3 产品需求文档

> **版本**: v1.0.3  
> **状态**: 已发布  
> **日期**: 2026-06-25  
> **维护**: 金鹰国际物业集团信息化团队

---

## 一、产品概述

### 1.1 产品定位

金鹰工单KPI管理系统是面向金鹰国际物业集团的**一站式工单绩效管理平台**，整合三大业务数据源（BI工单系统、筹建专项计划、IPMS设备管理），提供从数据采集、KPI考核到AI智能分析的完整业务闭环。

### 1.2 核心价值

- **数据聚合**：自动采集三个独立业务系统的数据，消除信息孤岛
- **绩效考核**：基于四层级模型（项目负责人/部门管理/一线员工/外包）的量化考核体系
- **实时监控**：驾驶舱式数据看板，支持多维度筛选和预警
- **智能分析**：内置AI助手，支持自然语言查询和SQL数据分析
- **轻量部署**：单EXE文件打包，无需服务器，Windows桌面直接运行

### 1.3 技术架构

```
┌─────────────────────────────────────────────────────┐
│                   前端 (单HTML文件)                    │
│  Codex极简风格 · 左侧导航 · 响应式布局                  │
│  ECharts图表 · 拖拽式AI浮球 · 暗色模式                  │
└─────────────────────────────────────────────────────┘
                          ↓ HTTP API
┌─────────────────────────────────────────────────────┐
│              后端 (FastAPI + SQLAlchemy)               │
│  JWT认证 · 16个API模块 · APScheduler定时任务            │
│  Playwright爬虫 · AI对话(NVIDIA API)                  │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│                 SQLite 本地数据库                       │
│  12个数据模型 · 40个项目 · 全量历史数据                  │
└─────────────────────────────────────────────────────┘
```

### 1.4 部署方式

- **打包工具**: PyInstaller
- **运行环境**: Windows 10/11, 无需Python环境
- **分发方式**: GitHub Release (ZIP压缩包)
- **更新机制**: Gitee API版本检测 + 自动下载覆盖

---

## 二、数据源与采集

### 2.1 BI工单系统

#### 数据来源
- **系统**: BI报表平台 (bi.jinyeaglegroup.com)
- **采集方式**: Playwright浏览器自动化
- **采集内容**: 
  - 工单明细表 (work_tickets)
  - 随手拍工单表 (snapshots)
- **触发方式**: 
  - 定时: 每日 08:00, 13:30, 17:00 (APScheduler)
  - 手动: 前端"同步"页面按钮

#### 数据模型

**work_tickets (工单明细)**
```python
class WorkTicket(Base):
    id: int  # 主键
    ticket_no: str  # 工单号 (唯一)
    project_id: int  # 项目ID (外键)
    source: str  # 数据来源 (BI/随手拍)
    order_status: str  # 工单状态
    initiator_id: str  # 发起人工号
    initiator_name: str  # 发起人姓名
    create_time: datetime  # 创建时间
    complete_time: datetime  # 完成时间
    deadline: datetime  # 截止时间
    # ... 其他字段
```

**snapshots (随手拍工单)**
```python
class Snapshot(Base):
    id: int
    snapshot_id: str  # 唯一标识
    project_id: int
    initiator_id: str
    initiator_name: str
    create_time: datetime
    # ... 其他字段
```

### 2.2 筹建专项计划 (WY)

#### 数据来源
- **系统**: 筹建专项管理系统 (58.213.109.123:8181)
- **采集方式**: HTTP API (requests库)
- **认证**: Token + MD5密码
- **采集内容**: 专项计划列表及明细
- **触发方式**: 
  - 定时: 每日 08:00, 13:30, 17:00
  - 手动: 前端"同步"页面按钮

#### 数据模型

```python
class SpecialPlan(Base):
    id: int
    special_plan_id: str  # 专项ID (唯一)
    project_id: int
    project_name: str  # 项目名称
    plan_name: str  # 计划名称
    plan_type: str  # 计划类型
    responsible_person: str  # 负责人
    plan_start_date: date  # 计划开始
    plan_end_date: date  # 计划结束
    actual_start_date: date  # 实际开始
    actual_end_date: date  # 实际结束
    status: str  # 状态
    progress: int  # 进度百分比
    # ... 其他字段
```

### 2.3 IPMS设备管理

#### 数据来源
- **系统**: IPMS设备管理系统 (ipms.jinying.com)
- **采集方式**: HTTP API (requests库)
- **认证**: Bearer Token
- **采集内容**: 
  - 巡检任务 (patrol)
  - 维保任务 (maintain)
- **触发方式**: 
  - 定时: 每日 08:00, 13:30, 17:00
  - 手动: 前端"同步"页面按钮

#### 数据模型

```python
class IPMSTask(Base):
    id: int
    task_id: str  # 任务ID (唯一)
    project_id: int
    task_type: str  # patrol/maintain
    task_name: str
    executor: str  # 执行人
    start_time: datetime
    end_time: datetime
    status: str
    result: str
    # ... 其他字段
```

---

## 三、功能模块

### 3.1 认证与权限

#### API端点
```
POST /api/auth/login      # 登录
POST /api/auth/logout     # 登出
GET  /api/auth/me         # 获取当前用户信息
```

#### 登录流程
1. 用户输入OA账号、密码、工号
2. 选择所属项目 (40个项目列表)
3. 后端验证并生成JWT Token (8小时有效期)
4. 前端存储Token到localStorage
5. 后续请求携带 `Authorization: Bearer <token>`

#### 角色体系
- **系统管理员**: 全部权限
- **项目负责人**: 查看本项目数据 + 人员管理
- **部门管理**: 查看本项目数据
- **一线员工**: 查看个人数据

### 3.2 概览驾驶舱

#### 功能说明
驾驶舱是系统的核心看板，提供项目级KPI数据的实时展示。

#### 数据展示

**KPI卡片 (4个)**
```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│  累计工单数   │  待处理工单   │  已完成工单   │  及时完成率   │
│    13,636    │     2,479    │    11,157    │    81.8%     │
│              │              │              │   ↑2.3%      │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

**项目概览卡片 (3个)**
- 金鹰PLAN: 37项任务 (即将开始/进行中/逾期报警/已逾期/已暂停)
- 巡检任务: 10,851项 (进行中/已完成/已逾期)
- 维保任务: 517项 (进行中/已完成/已逾期)

**趋势图表 (2个)**
- 工单趋势: 按月统计工单数量折线图
- 角色分布: 四层级人员数量及完成率柱状图

**预警清单**
- 按达成率排序的预警人员列表
- 显示: 姓名、角色、已发起、目标、达成率、预警级别、项目排名

#### API端点
```
GET /api/stats/months                    # 可用月份列表
GET /api/stats/dashboard                 # 驾驶舱KPI数据
GET /api/stats/initiation                # 四层级发起统计
GET /api/stats/warnings                  # 预警清单
GET /api/stats/completion                # 完成率统计
GET /api/stats/score                     # 综合评分
```

### 3.3 工单管理

#### 功能说明
提供工单的多维度查询、筛选、导出和详情查看。

#### 查询维度
- **项目筛选**: 单项目/多项目/全部项目
- **状态筛选**: 待处理/处理中/已完成/已关闭
- **时间筛选**: 按月份筛选
- **类型筛选**: 物业维修/保洁报修/秩序报修等
- **关键词搜索**: 工单号、描述、处理人

#### 数据表格
```
┌──────┬──────┬──────┬────────┬──────┬────────┬──────┬────────┬──────┐
│工单号│ 项目 │ 类型 │ 报修描述│处理人│创建时间 │ 状态 │KPI状态 │ 操作 │
├──────┼──────┼──────┼────────┼──────┼────────┼──────┼────────┼──────┤
│832446│金鹰世│物业维│c32施工 │  -   │2026-06-│处理中│ 进行中 │ 查看 │
│      │  界  │  修  │  巡检  │      │22 17:28│      │        │      │
└──────┴──────┴──────┴────────┴──────┴────────┴──────┴────────┴──────┘
```

#### 详情弹窗
点击"查看"按钮，右侧滑出详情面板，显示:
- 工单基本信息 (工单号、项目、类型、状态)
- 时间信息 (创建、截止、完成)
- 处理流程 (发起→接单→处理→完成)
- 报修描述和处理结果

#### API端点
```
GET /api/tickets/search                  # 搜索工单列表
GET /api/tickets/{ticket_id}             # 工单详情
GET /api/tickets/overdue/list            # 逾期工单列表
```

### 3.4 人力管理

#### 功能说明
管理人员清单，支持Excel导入、角色映射、KPI统计。

#### 核心功能
1. **人员列表**: 分页展示，支持搜索和筛选
2. **Excel导入**: 批量导入人员数据 (追加/覆盖模式)
3. **角色映射**: 将Excel中的职务映射为系统角色
4. **KPI统计**: 按角色统计发起数和达成率

#### 角色分类
- **项目负责人**: 1人 (来自project_managers表)
- **部门管理**: 35人 (职务含"经理/主管/副总监")
- **一线员工**: 46人 (其他在职人员)
- **外包人员**: 不参与内部KPI考核

#### API端点
```
GET  /api/personnel                      # 人员列表
GET  /api/personnel/list                 # 人员列表 (别名)
POST /api/personnel/create               # 新增人员
PUT  /api/personnel/{id}                 # 更新人员
DELETE /api/personnel/{id}               # 删除人员
POST /api/personnel/import               # Excel导入
```

### 3.5 计划管理

#### 功能说明
整合三大计划类型，提供统一的计划视图和甘特图。

#### 三个子模块

**1. 金鹰PLAN (筹建专项)**
- 数据源: WY系统
- 视图: 甘特图 + 表格
- 筛选: 年份、月份、状态、任务名称
- 状态: 即将开始/进行中/即将到期/到期预警/逾期报警/已逾期/已完成/已暂停

**2. 巡检任务**
- 数据源: IPMS系统 (patrol)
- 视图: 统计卡片 + 表格
- 筛选: 月份、状态、执行人

**3. 维保任务**
- 数据源: IPMS系统 (maintain)
- 视图: 统计卡片 + 表格
- 筛选: 月份、状态、执行人

#### 甘特图
```
任务名称          1月    2月    3月    4月    5月    6月
─────────────────────────────────────────────────────
防火门换新        ████████████████████████████████████
卫生间隔断        ████████████████████████████████████
地毯更换          ████████████████████████████████████
```

#### API端点
```
GET /api/wy/plans                        # 专项计划列表
GET /api/wy/stats                        # 专项统计
GET /api/wy/warnings                     # 专项预警
GET /api/wy/persons                      # 专项人员绩效

GET /api/ipms/tasks                      # IPMS任务列表
GET /api/ipms/stats                      # IPMS统计
GET /api/ipms/warnings                   # IPMS预警
GET /api/ipms/persons                    # IPMS人员绩效
```

### 3.6 系统配置

#### 功能说明
系统级配置管理，包含五个Tab页。

#### Tab 1: 人力清单配置
- **原表结构**: 显示Excel模板的列定义
- **字段映射**: 配置Excel列到数据库字段的映射
- **导入操作**: 选择Excel文件，执行导入

#### Tab 2: 项目配置
- **项目列表**: 40个项目的CRUD管理
- **项目属性**: 名称、面积、外包目标、KPI阈值
- **新增项目**: 表单创建新项目

#### Tab 3: 角色映射
- **映射规则**: Excel职务 → 系统角色
- **示例映射**: 
  - "工程经理" → "部门管理"
  - "综合维修工" → "一线员工"

#### Tab 4: 项目名称映射
- **BI名称**: BI系统中的项目名称
- **系统名称**: 本系统中的项目名称
- **映射目的**: 解决不同系统间项目名称不一致问题

#### Tab 5: 项目负责人
- **负责人列表**: 每个项目指定一名负责人
- **统计作用**: 用于四层级KPI考核的第一层级
- **虚拟占位**: 负责人可不在人员表中，系统自动创建虚拟记录

#### API端点
```
GET    /api/config/projects              # 项目列表
POST   /api/config/projects              # 创建项目
PUT    /api/config/projects/{id}         # 更新项目
DELETE /api/config/projects/{id}         # 删除项目

GET    /api/config/role-mappings         # 角色映射列表
POST   /api/config/role-mappings         # 创建映射
PUT    /api/config/role-mappings/{id}    # 更新映射
DELETE /api/config/role-mappings/{id}    # 删除映射

GET    /api/config/name-mappings         # 名称映射列表
POST   /api/config/name-mappings         # 创建映射

GET    /api/project-managers             # 负责人列表
POST   /api/project-managers             # 新增负责人
PUT    /api/project-managers/{id}        # 更新负责人
DELETE /api/project-managers/{id}        # 删除负责人
```

### 3.7 数据同步

#### 功能说明
手动触发三大系统的数据同步，实时显示同步状态和进度。

#### 同步流程

**1. BI系统同步**
```
启动Playwright浏览器
  ↓
登录BI平台 (OA账号密码)
  ↓
进入报表页面
  ↓
选择项目 + 设置日期范围
  ↓
点击导出按钮
  ↓
等待Excel下载完成
  ↓
解析Excel并写入数据库
  ↓
关闭浏览器
```

**2. WY系统同步**
```
HTTP POST 登录 (Token + MD5密码)
  ↓
获取专项计划列表
  ↓
遍历并写入数据库
```

**3. IPMS系统同步**
```
HTTP POST 登录 (Bearer Token)
  ↓
获取巡检任务列表
  ↓
获取维保任务列表
  ↓
写入数据库
```

#### 同步状态
- **环形进度条**: 显示整体同步进度
- **分项状态**: 分别显示BI/WY/IPMS的同步状态
- **日志查看**: 展开查看详细同步日志

#### API端点
```
POST /api/sync/start                     # 启动同步
GET  /api/sync/status                    # 同步状态
GET  /api/sync/logs                      # 同步日志

POST /api/sync_wy/start                  # 单独同步WY
POST /api/sync_ipms/start                # 单独同步IPMS
```

### 3.8 AI智能助手

#### 功能说明
内置AI对话助手，支持自然语言查询和SQL数据分析。

#### 技术实现
- **模型**: NVIDIA API (qwen/qwen3.5-122b)
- **接口**: Streaming Response (流式输出)
- **能力**: 
  - 自然语言理解
  - SQL生成和执行
  - 数据分析和可视化建议

#### 交互设计
- **浮球入口**: 右下角可拖拽的圆形按钮
- **智能定位**: 根据浮球位置计算弹窗方向
  - 浮球在下半屏 → 弹窗向上展开
  - 浮球在左半屏 → 弹窗向右展开
- **对话界面**: 380x520px 固定尺寸弹窗
- **消息气泡**: 区分用户消息和AI回复
- **输入框**: 支持Enter发送，Shift+Enter换行

#### 系统提示词
AI被配置为"项目数据分析专家"，具备以下能力:
- 理解工单、KPI、人员等业务术语
- 生成SQL查询数据库
- 解释查询结果
- 提供业务建议

#### API端点
```
POST /api/ai/chat                        # AI对话 (流式)
```

### 3.9 数据导出

#### 功能说明
将查询结果导出为Excel文件。

#### 导出类型
1. **人力清单导出**: 按项目/月份筛选的人员列表
2. **工单明细导出**: 按筛选条件的工单列表
3. **KPI报表导出**: 综合KPI考核报表

#### API端点
```
GET /api/export/personnel                # 导出人力清单
GET /api/export/tickets                  # 导出工单明细
GET /api/export/kpi                      # 导出KPI报表
GET /api/export/download/{filename}      # 下载导出文件
```

### 3.10 版本更新

#### 功能说明
检测Gitee上的新版本，支持一键更新。

#### 更新流程
1. 前端点击"检查更新"
2. 调用Gitee API获取最新Release
3. 比较版本号 (当前: v1.0.3)
4. 显示Release Notes
5. 用户确认后下载ZIP
6. 解压覆盖本地文件
7. 重启应用

#### API端点
```
GET  /api/update/check                   # 检查更新
POST /api/update/apply                   # 应用更新
```

---

## 四、KPI考核体系

### 4.1 四层级模型

系统采用四层级KPI考核模型，针对不同角色设定不同的考核标准。

#### 层级定义

| 层级 | 角色 | 来源 | 考核指标 |
|------|------|------|----------|
| 1 | 项目负责人 | project_managers表 | 团队整体达成率 |
| 2 | 部门管理 | 职务含"经理/主管/副总监" | 部门工单发起数 |
| 3 | 一线员工 | 其他在职人员 | 个人工单发起数 |
| 4 | 外包人员 | 不参与内部考核 | - |

### 4.2 考核指标

#### 1. 工单发起数 (权重40%)
- **目标值**: 按角色设定月度目标
  - 项目负责人: 30条/月
  - 部门管理: 60条/月
  - 一线员工: 30条/月
- **达成率**: 实际发起数 / 目标值 × 100%
- **数据来源**: snapshots表 (按initiator_id统计)

#### 2. 工单完成率 (权重30%)
- **定义**: 已完成工单数 / 总工单数 × 100%
- **数据来源**: work_tickets表 (source='detail')
- **完成状态**: order_status IN ('已完成', '已关闭', '已解决')

#### 3. 及时完成率 (权重30%)
- **定义**: 及时完成的工单数 / 已完成工单数 × 100%
- **及时标准**: complete_time <= deadline
- **数据来源**: work_tickets表 (有deadline的记录)

### 4.3 综合评分

```
综合评分 = (完成率×30% + 及时率×30% + 发起达成率×40%) / 10

评分等级:
- A (优秀): ≥ 9.0
- B (良好): ≥ 7.5
- C (合格): ≥ 6.0
- D (待改进): < 6.0
```

### 4.4 预警机制

#### 预警规则
- **严重预警** (红色): 达成率 < 70%
- **一般预警** (黄色): 达成率 70% ~ 阈值

#### 预警展示
- 驾驶舱预警清单: 按达成率升序排列
- 人员列表预警标记: 显示预警级别和颜色

---

## 五、前端设计

### 5.1 设计风格

**Codex极简风格**
- **色彩**: 黑白灰基调，状态色使用深色系 (绿/红/蓝/黄)
- **排版**: 系统字体栈，13px正文，11px大写标签
- **组件**: 无阴影，极简边框，扁平设计
- **密度**: 高信息密度，紧凑布局

### 5.2 导航结构

**左侧边栏 (200px)**
```
┌─────────────────┐
│ 工单KPI v1.0.3  │
│ 南京金鹰世界     │
├─────────────────┤
│ 📊 概览         │ ← 当前页面高亮
│ 📋 工单         │
│ 👥 人力         │
│ 📅 计划         │
│ ⚙️ 系统         │
│ 🔄 同步         │
├─────────────────┤
│ 🔄 同步数据     │
│ 🌓 主题 📺 大屏 │
│ 🚪 退出         │
├─────────────────┤
│ 吴明飞          │
└─────────────────┘
```

### 5.3 圆角系统

```css
--radius: 8px;      /* 按钮、输入框、下拉框 */
--radius-sm: 6px;   /* 标签、小组件 */
--radius-lg: 12px;  /* 卡片、弹窗 */
--radius-xl: 16px;  /* 登录卡片、Toast */
```

### 5.4 AI浮球交互

**拖拽功能**
- mousedown → 记录起始位置
- mousemove → 实时更新位置 (带边界限制)
- mouseup → 区分拖拽和点击
- 拖拽后不触发点击事件

**智能定位**
```javascript
if (浮球Y > 屏幕高度/2) {
  弹窗向上展开 (pos-top)
} else {
  弹窗向下展开 (pos-bottom)
}

if (浮球X > 屏幕宽度/2) {
  弹窗向左对齐 (right: 20px)
} else {
  弹窗向右对齐 (left: 20px)
}
```

### 5.5 暗色模式

**CSS变量切换**
```css
body {
  --bg: #FAFAFA;
  --bg-card: #FFFFFF;
  --text: #111111;
}

body.dark {
  --bg: #0A0A0A;
  --bg-card: #141414;
  --text: #ECECEC;
}
```

---

## 六、API接口规范

### 6.1 通用规范

**请求头**
```
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json
```

**响应格式**
```json
{
  "code": 200,
  "message": "success",
  "data": { ... }
}
```

**分页参数**
```
page: int (页码, 从1开始)
pageSize: int (每页数量, 默认10, 最大10000)
```

### 6.2 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未认证或Token过期 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 422 | 参数校验失败 |
| 500 | 服务器内部错误 |

### 6.3 完整API清单

```
认证模块 (3个)
  POST /api/auth/login
  POST /api/auth/logout
  GET  /api/auth/me

统计模块 (7个)
  GET /api/stats/months
  GET /api/stats/dashboard
  GET /api/stats/initiation
  GET /api/stats/warnings
  GET /api/stats/completion
  GET /api/stats/score
  GET /api/stats/trends

工单模块 (4个)
  GET /api/tickets
  GET /api/tickets/search
  GET /api/tickets/{ticket_id}
  GET /api/tickets/overdue/list

人力模块 (6个)
  GET  /api/personnel
  GET  /api/personnel/list
  POST /api/personnel/create
  PUT  /api/personnel/{id}
  DELETE /api/personnel/{id}
  POST /api/personnel/import

专项模块 (4个)
  GET /api/wy/plans
  GET /api/wy/stats
  GET /api/wy/warnings
  GET /api/wy/persons

IPMS模块 (4个)
  GET /api/ipms/tasks
  GET /api/ipms/stats
  GET /api/ipms/warnings
  GET /api/ipms/persons

配置模块 (12个)
  GET    /api/config/projects
  POST   /api/config/projects
  PUT    /api/config/projects/{id}
  DELETE /api/config/projects/{id}
  GET    /api/config/role-mappings
  POST   /api/config/role-mappings
  PUT    /api/config/role-mappings/{id}
  DELETE /api/config/role-mappings/{id}
  GET    /api/config/name-mappings
  POST   /api/config/name-mappings
  GET    /api/project-managers
  POST   /api/project-managers

同步模块 (5个)
  POST /api/sync/start
  GET  /api/sync/status
  GET  /api/sync/logs
  POST /api/sync_wy/start
  POST /api/sync_ipms/start

AI模块 (1个)
  POST /api/ai/chat

导出模块 (4个)
  GET /api/export/personnel
  GET /api/export/tickets
  GET /api/export/kpi
  GET /api/export/download/{filename}

更新模块 (2个)
  GET  /api/update/check
  POST /api/update/apply

其他 (3个)
  GET  /api/search
  GET  /api/websocket
  POST /api/shutdown

总计: 55个API端点
```

---

## 七、数据库设计

### 7.1 数据模型概览

```
projects (40个项目)
  ├── work_tickets (工单明细)
  ├── snapshots (随手拍工单)
  ├── special_plans (专项计划)
  ├── ipms_tasks (IPMS任务)
  ├── personnel (人员清单)
  └── project_managers (项目负责人)

config表
  ├── role_mappings (角色映射)
  ├── project_name_mappings (名称映射)
  └── kpi_config (KPI配置)

系统表
  ├── user_sessions (用户会话)
  └── sync_logs (同步日志)
```

### 7.2 核心表结构

**projects**
```sql
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) UNIQUE,
    area DECIMAL(10,2),
    outsourcing_target DECIMAL(10,2),
    kpi_completion_rate DECIMAL(5,2),
    kpi_timely_rate DECIMAL(5,2)
);
```

**work_tickets**
```sql
CREATE TABLE work_tickets (
    id INTEGER PRIMARY KEY,
    ticket_no VARCHAR(50) UNIQUE,
    project_id INTEGER,
    source VARCHAR(20),
    order_status VARCHAR(50),
    initiator_id VARCHAR(50),
    initiator_name VARCHAR(100),
    create_time DATETIME,
    complete_time DATETIME,
    deadline DATETIME,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
```

**personnel**
```sql
CREATE TABLE personnel (
    id INTEGER PRIMARY KEY,
    employee_id VARCHAR(50) UNIQUE,
    name VARCHAR(100),
    project_id INTEGER,
    department VARCHAR(100),
    position VARCHAR(100),
    role VARCHAR(50),
    status VARCHAR(20),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
```

### 7.3 索引设计

```sql
-- 工单查询优化
CREATE INDEX idx_tickets_project ON work_tickets(project_id);
CREATE INDEX idx_tickets_create_time ON work_tickets(create_time);
CREATE INDEX idx_tickets_initiator ON work_tickets(initiator_id);

-- 人员查询优化
CREATE INDEX idx_personnel_project ON personnel(project_id);
CREATE INDEX idx_personnel_employee_id ON personnel(employee_id);

-- 计划查询优化
CREATE INDEX idx_plans_project ON special_plans(project_id);
CREATE INDEX idx_plans_end_date ON special_plans(plan_end_date);
```

---

## 八、部署与运维

### 8.1 打包流程

```bash
# 1. 清理旧构建
rmdir /s /q dist

# 2. PyInstaller打包
pyinstaller golden_eagle.spec

# 3. 复制数据库
copy data\golden_eagle_kpi.db dist\金鹰工单KPI\data\

# 4. 复制前端
copy frontend\index.html dist\金鹰工单KPI\_internal\frontend\

# 5. 创建Release ZIP
powershell Compress-Archive -Path dist\金鹰工单KPI\* -DestinationPath releases\golden-eagle-kpi-v1.0.3.zip
```

### 8.2 发布流程

```bash
# 1. 创建Git标签
git tag v1.0.3
git push github v1.0.3

# 2. 创建GitHub Release
# - 上传ZIP文件 (239MB)
# - 填写Release Notes

# 3. 同步到Gitee
git push gitee v1.0.3
# - 手动上传ZIP到Gitee Release
```

### 8.3 更新检查

系统启动时自动检查更新:
1. 调用Gitee API获取最新Release
2. 比较版本号 (v1.0.3 vs v1.0.4)
3. 有新版本时显示更新提示
4. 用户确认后自动下载并更新

### 8.4 日志管理

**日志位置**: `data/logs/app.log`

**日志级别**: INFO (生产环境)

**日志内容**:
- 启动信息
- API请求记录
- 同步任务日志
- 错误堆栈信息
- 爬虫运行状态

---

## 九、已知问题与优化方向

### 9.1 当前版本已知问题

1. **BI同步稳定性**: Playwright爬虫偶尔因页面加载超时失败
2. **SQLite并发**: 多用户同时写入时可能出现锁表
3. **离线模式**: 离线模式下部分功能受限 (projectId=offline导致422错误)

### 9.2 未来优化方向

#### 功能增强
- [ ] 支持多项目对比分析
- [ ] 增加工单处理时效统计
- [ ] 支持自定义KPI考核规则
- [ ] 增加数据可视化图表类型
- [ ] 支持工单评论和附件

#### 性能优化
- [ ] 数据库迁移到PostgreSQL/MySQL
- [ ] 实现数据缓存机制
- [ ] 优化大数据量查询性能
- [ ] 前端代码拆分和懒加载

#### 用户体验
- [ ] 移动端适配
- [ ] 国际化支持 (多语言)
- [ ] 更丰富的主题定制
- [ ] 快捷键支持
- [ ] 操作引导和帮助文档

#### 运维改进
- [ ] 自动化测试覆盖
- [ ] CI/CD流水线
- [ ] Docker容器化部署
- [ ] 监控告警系统
- [ ] 数据备份策略

---

## 十、附录

### 10.1 项目列表 (40个)

```
南京金鹰中心, 南京汉中新城, 南京珠江壹号, 南京湖滨天地,
江宁金鹰天地, 南京金鹰世界, 上海金鹰国际, 芜湖金鹰商城,
芜湖金鹰国际, 宿迁金鹰天地, 马鞍山金鹰天地, 丹阳金鹰天地,
昆山金鹰天地, 泰州金鹰天地, 昆明金鹰天地, 苏州金鹰国际,
盐城金鹰国际, 盐城金鹰奥莱, 盐城金鹰天地, 南通金鹰中心,
扬州新城市中心, 扬州文昌金鹰国际, 扬州京华金鹰国际,
徐州彭城金鹰国际, 徐州人民金鹰国际, 淮安金鹰国际,
西安金鹰国际, 淮北金鹰国际, 溧阳店, 南通人民路店,
昆山住宅, 连云港住宅, 南通金鹰世界, 长春金鹰世界,
南京金鹰花园, 南通八仙城, 上海金鹰华庭, 宿迁金鹰花园,
常州凯悦中心花园, 江都文昌华府
```

### 10.2 技术栈清单

**后端**
- Python 3.11
- FastAPI 0.104.1
- SQLAlchemy 2.0.23
- SQLite 3
- Playwright 1.40.0
- APScheduler 3.10.4
- JWT (PyJWT 2.8.0)
- httpx 0.25.2 (AI对话)

**前端**
- HTML5 + CSS3 + JavaScript (原生)
- ECharts 5.4.3
- 单文件架构 (~7294行)

**打包**
- PyInstaller 6.3.0
- Windows 10/11

**版本控制**
- Git 2.43.0
- GitHub + Gitee 双仓库

### 10.3 联系方式

- **项目仓库**: https://github.com/Zcx-BaixiaoBai/GE-WorkOrder
- **Gitee镜像**: https://gitee.com/Zcx-BaixiaoBai/g-ai
- **问题反馈**: GitHub Issues

---

**文档版本**: v1.0.3  
**最后更新**: 2026-06-25  
**维护者**: 金鹰国际物业集团信息化团队
