# 金鹰工单 KPI 管理系统

金鹰物业内部工单 KPI 考核管理系统，支持随手拍工单、外包工单的数据采集、统计与 AI 分析。

## 功能特性

- **工单管理**：随手拍、秩序报修、保洁报修等全类型工单统一管理
- **KPI 驾驶舱**：完成率、及时率、发起达成率等核心指标实时可视化
- **四层级统计**：项目负责人 / 部门管理 / 一线员工 / 外包保安保洁分层考核
- **数据同步**：Playwright 无头浏览器自动从 BI 系统抓取 Excel 数据
- **AI 对话**：基于上下文智能分析工单数据，回答自然语言查询
- **热更新**：内置 Gitee Releases 版本检测，支持一键热更新

## 技术栈

- **后端**：FastAPI + SQLAlchemy + SQLite（WAL 模式）
- **前端**：原生 HTML/CSS/JS，Apple 液态玻璃风格
- **爬虫**：Playwright 无头浏览器自动化
- **打包**：PyInstaller，单 exe 可执行文件

## 快速启动

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python main.py
```

访问 http://localhost:8765

## 版本

当前版本：**v1.0.1**

版本更新请访问 [Gitee Releases](https://gitee.com/Zcx-BaixiaoBai/g-ai/releases)

## 目录结构

```
├── main.py              # FastAPI 应用入口
├── backend/
│   ├── api/            # API 路由（认证/工单/统计/同步/AI对话/更新）
│   ├── models/          # ORM 数据模型
│   ├── services/        # 业务逻辑层
│   └── scraper/         # BI 系统爬虫客户端
├── frontend/
│   └── index.html      # 前端单页应用
├── data/                # 数据库文件（不随源码提交）
├── releases/            # 历史版本打包
└── requirements.txt     # Python 依赖
```
