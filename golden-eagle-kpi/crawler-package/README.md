# 金鹰物业KPI考核数据爬取脚本

自动化爬取BI系统和物业系统的工单、随手拍、筹建专项等考核数据。

## 📋 爬虫功能说明

### 1. BI系统爬虫 (bi_client.py)
- **目标系统**: BI报表系统
- **爬取内容**: 
  - 工单明细查询表
  - 随手拍工单统计明细表
- **技术栈**: Playwright + 浏览器自动化
- **输出**: Excel文件

### 2. IPMS系统爬虫 (ipms_crawler.py)
- **目标系统**: IPMS设备管理系统
- **爬取内容**:
  - 巡检任务
  - 维保任务
- **技术栈**: Requests + API调用
- **输出**: Python字典列表

### 3. 物业系统爬虫 (wy_crawler.py)
- **目标系统**: 筹建专项计划管理系统
- **爬取内容**:
  - 专项计划
  - 专项明细
- **技术栈**: Requests + API调用
- **输出**: Python字典列表

## 🚀 部署教程

### 环境要求

- Python 3.8+
- Windows 系统（BI爬虫需要浏览器）
- Chrome 或 Edge 浏览器
- 网络访问权限（需能访问内网系统）

### 安装步骤

#### 1. 安装Python依赖

```bash
pip install -r requirements.txt
```

#### 2. 安装Playwright浏览器驱动（仅BI爬虫需要）

```bash
# 安装playwright
pip install playwright

# 安装Chromium浏览器
playwright install chromium

# 或者自动检测并使用系统浏览器（推荐）
# bi_client.py 已实现自动检测Chrome/Edge的功能
```

#### 3. 配置账号密码

**重要：出于安全考虑，所有账号密码都不应硬编码在脚本中！**

##### 方式一：环境变量（推荐）

```bash
# Windows CMD
set BI_ACCOUNT=你的OA账号
set BI_PASSWORD=你的OA密码
set WY_BASE_URL=http://58.213.109.123:8181
set WY_TOKEN=你的token
set WY_USERNAME=你的用户名
set WY_PASSWORD=你的密码

# Windows PowerShell
$env:BI_ACCOUNT="你的OA账号"
$env:BI_PASSWORD="你的OA密码"
$env:WY_BASE_URL="http://58.213.109.123:8181"
$env:WY_TOKEN="你的token"
$env:WY_USERNAME="你的用户名"
$env:WY_PASSWORD="你的密码"

# Linux/Mac
export BI_ACCOUNT="你的OA账号"
export BI_PASSWORD="你的OA密码"
export WY_BASE_URL="http://58.213.109.123:8181"
export WY_TOKEN="你的token"
export WY_USERNAME="你的用户名"
export WY_PASSWORD="你的密码"
```

##### 方式二：配置文件

创建 `.env` 文件（不要提交到版本库）：

```env
BI_ACCOUNT=你的OA账号
BI_PASSWORD=你的OA密码
WY_BASE_URL=http://58.213.109.123:8181
WY_TOKEN=你的token
WY_USERNAME=你的用户名
WY_PASSWORD=你的密码
```

##### 方式三：代码传参

参考 `example.py` 中的示例代码。

## 📖 使用方法

### 快速开始

```bash
# 1. 配置环境变量（见上文）

# 2. 运行示例脚本
python example.py
```

### BI系统爬取（工单+随手拍）

```python
import asyncio
from bi_client import BiClient

async def fetch_bi():
    client = BiClient(
        account="你的OA账号",
        password="你的OA密码",
        download_dir="./downloads"
    )
    
    # 爬取所有报表
    files = await client.fetch_all()
    print(f"下载了 {len(files)} 个文件")
    
    return files

# 运行
asyncio.run(fetch_bi())
```

### IPMS系统爬取（巡检+维保）

```python
from ipms_crawler import IPMSCrawler

# 创建爬虫
crawler = IPMSCrawler()

# 登录
if crawler.login("用户名", "密码"):
    # 爬取巡检任务
    patrol = crawler.crawl_patrol(year=2026)
    print(f"巡检任务: {len(patrol)} 条")
    
    # 爬取维保任务
    maintain = crawler.crawl_maintain(year=2026)
    print(f"维保任务: {len(maintain)} 条")
```

### 物业系统爬取（筹建专项）

```python
from wy_crawler import Crawler

# 配置
config = {
    'base_url': 'http://58.213.109.123:8181',
    'token': '你的token',
    'username': '你的用户名',
    'password': '你的密码',
}

# 创建爬虫
crawler = Crawler(config=config)

# 登录
if crawler.login():
    # 爬取2026年数据
    data = crawler.crawl(year=2026)
    print(f"专项明细: {len(data)} 条")
```

## 📁 文件结构

```
crawler-package/
├── bi_client.py          # BI系统爬虫（工单+随手拍）
├── ipms_crawler.py       # IPMS系统爬虫（巡检+维保）
├── wy_crawler.py         # 物业系统爬虫（筹建专项）
├── requirements.txt      # Python依赖
├── example.py           # 使用示例
└── README.md            # 本文档
```

## ⚠️ 注意事项

### 安全警告

1. **绝对不要**将账号密码硬编码到脚本中
2. **绝对不要**将包含账号密码的配置文件提交到Git
3. 使用环境变量或加密的配置文件存储敏感信息
4. 定期更换密码

### 网络要求

- BI爬虫需要访问OA系统和BI报表系统
- IPMS爬虫需要访问IPMS设备管理系统
- 物业爬虫需要访问筹建专项系统
- 确保网络稳定，避免爬取过程中断

### 浏览器要求

- BI爬虫使用Playwright自动化浏览器
- 优先使用系统已安装的Chrome或Edge
- 如果系统没有浏览器，需要安装Playwright的Chromium

### 错误处理

```python
try:
    files = await client.fetch_all()
except Exception as e:
    print(f"爬取失败: {e}")
    # 可能的原因：
    # - 账号密码错误
    # - 网络不通
    # - 系统维护
    # - 页面结构变化
```

### 常见问题

**Q: BI爬虫下载的文件在哪里？**  
A: 默认在 `./downloads` 目录，可通过 `download_dir` 参数指定。

**Q: 如何只爬取工单或随手拍？**  
A: 使用 `client.fetch_tickets()` 或 `client.fetch_snapshots()` 方法。

**Q: IPMS爬虫返回什么格式？**  
A: 返回Python字典列表，每个字典代表一条任务记录。

**Q: 物业系统登录失败怎么办？**  
A: 检查token是否过期，重新获取token并更新配置。

## 🔧 高级配置

### BI爬虫超时设置

```python
client = BiClient(
    account="xxx",
    password="xxx",
    timeout=60  # 默认30秒
)
```

### IPMS爬虫日期范围

```python
# 指定日期范围
patrol = crawler.crawl_patrol(
    start_date="2026-01-01",
    end_date="2026-06-30"
)
```

### 物业系统字段映射

`wy_crawler.py` 中已定义了字段映射表（FIELD_MAP），可根据需要修改。

## 📝 更新日志

- 2026-06-24: 删除硬编码账密，改为环境变量配置
- 2026-06-24: 添加完整README和部署教程
- 2026-06-24: 创建示例脚本

## 📞 技术支持

如有问题，请联系开发团队或查看源代码注释。
