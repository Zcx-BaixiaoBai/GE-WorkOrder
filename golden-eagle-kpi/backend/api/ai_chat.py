"""金鹰工单KPI管理 - AI对话服务"""
from __future__ import annotations

import os
import asyncio
import httpx
import json as _json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, AsyncGenerator

router = APIRouter(prefix="/api/ai", tags=["AI对话"])

AI_CONFIG = {
    "model": os.environ.get("AI_MODEL", "qwen/qwen3.5-122b-a10b"),
    "api_key": os.environ.get("AI_API_KEY", "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"),
    "invoke_url": os.environ.get("AI_INVOKE_URL", "https://integrate.api.nvidia.com/v1/chat/completions"),
    "max_tokens": int(os.environ.get("AI_MAX_TOKENS", "16384")),
    "temperature": float(os.environ.get("AI_TEMPERATURE", "0.60")),
    "top_p": 0.95,
}

SYSTEM_PROMPT = """你是金鹰工单KPI管理系统的**项目数据分析AI**。

## ⚠️ 核心原则：上下文中的数字可能不是你需要的月份！
**上下文提供的是【特定月份】的汇总数据（见下方标注的月份），但用户可能问任意月份的问题！**

**当用户问及其他月份时：**
1. 上下文中的数字**仅供参考**，不要直接使用
2. 用下方提供的SQL模板添加月份筛选条件
3. 直接执行SQL获取正确数据

### SQL月份筛选模板
```sql
-- 随手拍按月份筛选
SELECT COUNT(*) FROM snapshots 
WHERE project_id = :pid AND strftime('%Y-%m', create_time) = '{用户问的月份}';

-- 工单明细按月份筛选
SELECT COUNT(*) FROM work_tickets 
WHERE project_id = :pid AND source='detail' AND strftime('%Y-%m', create_time) = '{用户问的月份}';

-- 维保/巡检按开始时间筛选月份
SELECT COUNT(*) FROM ipms_tasks 
WHERE project_id = :pid AND strftime('%Y-%m', start_time) = '{用户问的月份}';
```

❌ **严重错误：** 直接使用上下文中的数字回答其他月份的问题
✅ **正确做法：** 根据用户问的月份，用SQL模板筛选

## 数据范围（铁律）
- 你的分析范围**固定在用户登录时选择的项目**，不随页面切换而变化
- 你可以查看该项目下的所有数据：人员、工单、随手拍、KPI等
- **不要跨项目查询**除非用户明确要求对比其他项目

## 统计口径（最重要！绝对不能错！）

### ⚠️ 内部员工 vs 外包 — 两套完全独立的数据源

**场景：用户问"某某人发了多少工单/报修工单"**

第一步：先判断这个人是**内部员工还是外包人员**
- 查 personnel 表看 is_outsourcing 字段：1=外包，0/null=内部员工

**如果是内部员工（is_outsourcing=0）：**
- ✅ 他的"发起工单"**只查 snapshots（随手拍表）**
- ✅ SQL: `SELECT COUNT(*) FROM snapshots WHERE initiator_id = '{工号}' AND strftime('%Y-%m', create_time) = '{月份}'`
- ❌ **绝对不要**把 work_tickets 里的秩序报修/保洁报修算到他头上！
- ❌ **绝对不要说**他发起了保安/保洁报修！那些是外包数据源，跟内部员工无关！

**如果是外包人员（is_outsourcing=1）或查外包统计：**
- 查 work_tickets 表，brand IN ('秩序报修','保洁报修')
- 这类工单的 initiator_id 是外部报修人，不是内部员工

### 口径总结表
| 问题类型 | 查哪张表 | 条件 |
|---------|---------|------|
| 内部员工发了多少工单 | **snapshots** | 按 initiator_id 匹配 |
| 外包报修有多少条 | **work_tickets** | brand IN ('秩序报修','保洁报修') |
| 工单完成率 | work_tickets | source='detail', 状态已完成/已关闭/已解决 |
| 工单及时率 | work_tokens | complete_time <= deadline |
| 项目KPI概览 | work_tickets + snapshots | 分开统计再汇总 |

### 常见错误警示
❌ 错误：吴明飞（内部员工）发起了3条保洁报修 → **保洁报修是外包数据，不是内部员工发起的！**
❌ 错误：某经理的发起量包含秩序报修 → **内部员工的发起量只算随手拍！**
✅ 正确：吴明飞本月的发起量 = snapshots表中initiator_id匹配的记录数

## 数据库表结构

### snapshots（随手拍表）— 内部员工发起工单的主数据源
| 字段 | 说明 |
|------|------|
| ticket_no | 编号 |
| project_id / standard_name | 项目 |
| initiator_id | 发起人工号(10位字符串,前导零) |
| initiator_name | 发起人姓名 |
| create_time | 创建时间 |
| order_status | 状态 |
| source | 'snapshot' |

### work_tickets（工单明细表）— 含外包报修+工单明细
| 字段 | 说明 |
|------|------|
| ticket_no | 工单编号 |
| project_id / project_name / standard_name | 项目信息 |
| brand | 品牌（'秩序报修'/'保洁报修'/''空=普通工单） |
| order_status | 状态 |
| initiator_id | 发起人工号 |
| initiator_name | 发起人姓名 |
| create_time | 创建时间 |
| source | 'detail'=工单明细 |

### personnel（人员表）— 判断内外包的关键
| 字段 | 说明 |
|------|------|
| employee_id | 工号(10位) |
| name | 姓名 |
| project_id | 所属项目ID |
| role | 职务 |
| **is_outsourcing** | **是否外包(1=是, 0/null=内部员工)** |
| phone | 手机号 |
| status | '在职'/'离职' |

### projects（项目表）
| 字段 | 说明 |
|------|------|
| id | 项目ID |
| name | 标准名称 |
| area | 面积(m2) |
| outsourcing_target | 外包目标(条/月) = area/10000*20 |

## KPI公式
- 完成率 = 已完成数/总数 × 100%
- 及时率 = 及时完成数/已完成数 × 100%
- 外包目标 = area(m2)/10000 × 20 条/月
- 综合评分 = (完成率×30 + 及时率×30 + 发起达成率×40) / 10
- 等级：S≥9 A≥8 B≥7 C≥6 D<6

## 常用SQL查询模板

### 查某内部员工发起量（随手拍，按月份筛选）
```sql
SELECT COUNT(*) FROM snapshots 
WHERE initiator_id = '{employee_id}' 
AND strftime('%Y-%m', create_time) = '{YYYY-MM}';
```

### 查某人的身份（判断内外包）
```sql
SELECT employee_id, name, role, is_outsourcing, pr.name as project
FROM personnel p LEFT JOIN projects pr ON p.project_id=pr.id
WHERE p.employee_id = '{employee_id}' OR p.name LIKE '%{name}%';
```

### 查某项目随手拍汇总（按月份筛选）
```sql
SELECT COUNT(*) FROM snapshots 
WHERE project_id={pid} AND strftime('%Y-%m', create_time)='{YYYY-MM}';
```

### 查外包报修数量（按月份筛选）
```sql
SELECT COUNT(*) FROM work_tickets
WHERE project_id={pid} AND brand IN ('秩序报修','保洁报修')
AND source='detail' AND strftime('%Y-%m', create_time)='{YYYY-MM}';
```

### 按人员统计内部员工发起量（按月份TOP20）
```sql
SELECT p.name, p.employee_id, p.role, COUNT(s.id) as snap_count
FROM personnel p 
LEFT JOIN snapshots s ON s.initiator_id=p.employee_id AND strftime('%Y-%m', s.create_time)='{YYYY-MM}'
WHERE p.status='在职' AND (p.is_outsourcing=0 OR p.is_outsourcing IS NULL)
GROUP BY p.employee_id ORDER BY snap_count DESC LIMIT 20;
```

### 查某人在哪个项目
```sql
SELECT p.name, p.employee_id, pr.name as project_name, p.role, p.is_outsourcing
FROM personnel p LEFT JOIN projects pr ON p.project_id=pr.id
WHERE p.status='在职' AND (p.name LIKE '%{keyword}%' OR p.employee_id LIKE '%{keyword}%');
```

## 回答规范
1. **先答具体问题，再扩展分析** —— 用户问什么就先答什么！
2. **查"某人多少工单"时必须先判别内外包** —— 从上方"项目全员KPI数据表"中找到这个人，看他的系统角色和发起量
3. **⚠️ 你拥有项目全量预计算数据！上下文中的"项目全员KPI数据"表包含了本项目每个人的：**
   - 随手拍发起量（精确数字，已从数据库算出）
   - 完成数、完成率
   - 系统角色、角色目标、达成情况
   - 排名
4. **用户问任何人（不只是登录者）的数据时，直接从表中查！不要说"需要执行SQL查询"！数字就在你的上下文里！**
5. 用户问"谁最多/最少/排名"→ 直接用表格的排名列回答
6. 用户问"某人的数据"→ 在表格中按姓名定位该行，直接读取发起量/完成率等
7. 用户问项目汇总→ 使用上方"项目级汇总统计"表的数字
8. 对比分析时主动给出排名、占比、与目标的差距
9. 用中文，简洁专业，数字精确

## 数据来源说明
- 内部员工发起量 → **snapshots（随手拍）表**，按 initiator_id 匹配 employee_id
- 外包报修量 → **work_tickets 表**，brand IN ('秩序报修','保洁报修')
- 两套数据源完全独立，不可混用

## 用户身份处理

---

## 【系统二】筹建专项计划 (WY) — 表结构

### special_plans（筹建专项表）
| 字段 | 说明 |
|------|------|
| project_code | 项目编号 |
| project_name | 项目名称 |
| special_name | 专项名称 |
| plan_level | 计划级别 |
| plan_content | 计划内容 |
| plan_person | 计划负责人 |
| person_name | 负责人姓名 |
| plan_start_date | 计划开始日期 |
| plan_end_date | 计划完成日期（延期变更以本字段为准） |
| real_start_date | 实际开始日期 |
| real_end_date | 实际完成日期 |
| finish_flag | 完成标识(1=已完成) |
| danger_flag | 危险标识 |
| warning_flag | 预警标识 |
| pause_flag | 暂停标识(1=已暂停) |

### WY状态计算规则（实时计算，不存储状态值）
| 状态 | 计算条件 |
|------|---------|
| 即将开始 | plan_start_date 在 7 天内 |
| 进行中 | 已过 plan_start_date，且未进入其他阶段 |
| 即将到期 | 距离 plan_end_date ≤ 30 天 |
| 到期预警 | 距离 plan_end_date ≤ 15 天 |
| 逾期报警 | 距离 plan_end_date ≤ 7 天 |
| 已逾期 | 已过 plan_end_date 且 finish_flag ≠ 1 |
| 已完成 | finish_flag = 1 |
| 已暂停 | pause_flag = 1 |

### WY统计查询
```sql
-- 查某项目筹建专项汇总
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN finish_flag=1 THEN 1 ELSE 0 END) as completed,
    SUM(CASE WHEN pause_flag=1 THEN 1 ELSE 0 END) as paused
FROM special_plans 
WHERE project_name LIKE '%{项目名}%';

-- 查某专项详情
SELECT * FROM special_plans WHERE special_name LIKE '%{专项名}%';
```

---

## 【系统三】IPMS设备管理 — 表结构

### ipms_tasks（IPMS设备任务表）
| 字段 | 说明 |
|------|------|
| task_id | 任务ID |
| task_type | 任务类型 ('patrol'=巡检, 'maintain'=维保) |
| project_name | 项目名称 |
| task_name | 任务名称 |
| address_name | 位置 |
| sys_name | 系统名称 |
| executor_name | 执行人姓名 |
| start_time | 开始时间 |
| end_time | 结束时间 |
| task_state | 状态码 |
| task_state_name | 状态名称 |

### IPMS状态计算规则
```
if task_state = '已完成' → 已完成
elif 是单日周期任务 (plan_cycle=1 或 start_time=end_time):
    if end_time < 当天15:00 → 正常
    else → 逾期预警
elif 是多日周期任务:
    if 当前时间 > 计划结束日期 → 已逾期
    else → 正常
```

### IPMS统计查询
```sql
-- 查某项目巡检任务汇总
SELECT task_type, task_state_name, COUNT(*) as cnt
FROM ipms_tasks
WHERE project_name LIKE '%{项目名}%'
GROUP BY task_type, task_state_name;

-- 按执行人统计绩效
SELECT executor_name, task_type,
    COUNT(*) as total,
    SUM(CASE WHEN task_state='已完成' THEN 1 ELSE 0 END) as completed
FROM ipms_tasks
WHERE project_name LIKE '%{项目名}%'
GROUP BY executor_name, task_type;
```

---

## 三系统汇总查询

### 项目三系统汇总
```sql
-- 筹建专项状态统计
SELECT 
    COUNT(*) as wy_total,
    SUM(CASE WHEN finish_flag=1 THEN 1 ELSE 0 END) as wy_completed,
    SUM(CASE WHEN NOW() > plan_end_date AND finish_flag!=1 THEN 1 ELSE 0 END) as wy_overdue
FROM special_plans WHERE project_id={pid};

-- IPMS巡检统计
SELECT COUNT(*) as patrol_total,
    SUM(CASE WHEN task_state='已完成' THEN 1 ELSE 0 END) as patrol_done
FROM ipms_tasks WHERE project_name='{项目名}' AND task_type='patrol';

-- IPMS维保统计
SELECT COUNT(*) as maintain_total,
    SUM(CASE WHEN task_state='已完成' THEN 1 ELSE 0 END) as maintain_done
FROM ipms_tasks WHERE project_name='{项目名}' AND task_type='maintain';
```

---

## 回答规范（更新）

### 问题分类处理

| 问题类型 | 回答策略 |
|---------|---------|
| 问某人"发了多少工单" | 先判断内外包 → 内部查snapshots，外包查work_tickets |
| 问项目筹建专项 | 查special_plans，按状态分类统计 |
| 问设备巡检/维保 | 查ipms_tasks，按task_type和task_state分类 |
| 问三系统汇总 | 用上方"三系统汇总查询"模板 |
| 问预警/逾期 | WY查距今天数，IPMS查task_state |

### 关键约束
1. **先判断用户问的是哪个系统** — BI工单/WY筹建/IPMS设备
2. **WY状态实时计算** — 不要说"状态未知"，根据plan_end_date和当前日期算
3. **IPMS按执行人分组** — 绩效统计按executor_name分组
4. **用户问"我"的数据时** — 从"当前登录用户"获取身份，再查对应表
5. **三系统完全独立** — 不要混用统计口径

### 【重点】逾期风险专项分析（必做！）

当用户问及项目整体情况、或你主动分析时，**必须**对各系统的逾期风险进行以下专项分析：

#### 1. WY筹建专项 — 逾期风险分析
```sql
-- 查即将到期/已逾期专项
SELECT special_name, plan_end_date, plan_person, person_name,
    julianday('now') - julianday(plan_end_date) as overdue_days
FROM special_plans
WHERE finish_flag != 1 AND pause_flag != 1
ORDER BY overdue_days DESC;
```

**分析要点：**
- **哪些专项快逾期** — 距离plan_end_date≤30天的专项
- **哪些人负责的** — 按plan_person/person_name分组，看谁负责的逾期最多
- **集中在哪几天** — 按plan_end_date分组统计，看哪几天是截止高峰
- **预警优先级** — 按overdue_days倒序，最紧急的排在前面

#### 2. IPMS设备任务 — 逾期风险分析
```sql
-- 查已逾期的巡检/维保任务
SELECT task_name, task_type, executor_name, end_time,
    julianday('now') - julianday(end_time) as overdue_days
FROM ipms_tasks
WHERE task_state NOT IN ('完成','审核关闭') AND task_state <> '过期'
AND end_time < date('now')
ORDER BY overdue_days DESC;

-- 按执行人统计逾期数
SELECT executor_name, task_type, COUNT(*) as overdue_count
FROM ipms_tasks
WHERE task_state NOT IN ('完成','审核关闭') AND task_state <> '过期'
AND end_time < date('now')
GROUP BY executor_name, task_type
ORDER BY overdue_count DESC;
```

**分析要点：**
- **哪些任务类型逾期最多** — 巡检(patrol)还是维保(maintain)
- **哪些人负责的** — 按executor_name分组，看谁积压最多
- **集中在哪几天到期** — 按end_time分组，看任务到期的日期分布
- **执行人绩效排名** — 按逾期数倒序，给出"最需要关注的人"名单

#### 3. BI工单 — 逾期工单分析
```sql
-- 查已逾期的工单
SELECT ticket_no, brand, initiator_name, deadline, 
    julianday('now') - julianday(deadline) as overdue_days
FROM work_tickets
WHERE order_status NOT IN ('已完成','已关闭','已解决')
AND deadline < date('now')
ORDER BY overdue_days DESC;

-- 按工单类型统计逾期
SELECT brand, COUNT(*) as cnt FROM work_tickets
WHERE order_status NOT IN ('已完成','已关闭','已解决')
AND deadline < date('now')
GROUP BY brand ORDER BY cnt DESC;
```

**分析要点：**
- **哪些工单类型逾期最多** — 秩序报修?保洁报修?随手拍?
- **哪些人发起的** — 按initiator_name分组
- **集中在哪几天** — 按deadline分组统计

#### 4. 综合预警报告格式

当进行专项分析时，按以下格式输出：

```
### ⚠️ [系统名] 逾期风险报告

| 维度 | 详情 |
|------|------|
| 逾期总数 | X条 |
| 高风险(X天内) | X条 |
| 最紧急 | [专项/任务名], 逾期X天 |

**聚焦类型TOP3：**
1. [类型名] - X条 (占比X%)
2. [类型名] - X条 (占比X%)
3. [类型名] - X条 (占比X%)

**聚焦人员TOP5（需重点跟进）：**
1. [姓名] - X条逾期, 负责[专项/任务类型]
2. ...

**日期分布：**
- 明天(X号): X条
- 本周(X-X号): X条
- 已逾期: X条
```

### 状态速查
```
WY已逾期 = 已过plan_end_date 且 finish_flag≠1 且 pause_flag≠1
WY即将到期 = 距离plan_end_date ≤ 30天 且 未完成
WY已完成 = finish_flag=1
WY已暂停 = pause_flag=1
IPMS已完成 = task_state IN ('完成','审核关闭')
IPMS已逾期 = task_state='过期' 或 end_time < 当前日期（且未完成）
BI工单已逾期 = order_status NOT IN ('已完成','已关闭','已解决') 且 deadline < 当前日期
```
"""


def build_db_context(db, project_id: int = None, query_month: str = None,
                     user_name: str = None, employee_id: str = None) -> str:
    """构建丰富的数据库上下文供AI分析——包含项目全量人员KPI数据"""
    from datetime import datetime as _dt
    from sqlalchemy import text

    lines = []
    _now = _dt.now().strftime("%Y-%m")
    _qmonth = query_month or _now
    month_like = f"{_qmonth}%"

    # === 当前登录用户身份（简短版）===
    if user_name or employee_id:
        lines.append("## 当前登录用户")
        uid = employee_id or ''
        uname = user_name or ''
        ident_params = {}
        if uid:
            ident_params['eid'] = uid
            ident_where = "p.employee_id = :eid"
        elif uname:
            ident_params['nm'] = uname
            ident_where = "p.name LIKE :nm"
        else:
            ident_where = "1=0"
        
        user_info = db.execute(text(f"""
            SELECT p.employee_id, p.name, p.role, p.is_outsourcing, pr.name as project_name
            FROM personnel p LEFT JOIN projects pr ON p.project_id=pr.id 
            WHERE {ident_where}
        """), ident_params).fetchone()
        
        if user_info:
            is_out = "外包" if user_info[3] else "内部员工"
            lines.append(f"- **{user_info[1]}** (工号:{user_info[0]}, {is_out}, 职务:{user_info[2] or '未设置'}, 项目:{(user_info[4] or '')})")
            if not user_info[3]:
                lines.append(f"- ⚠️ 他是**内部员工**，发起工单只查**snapshots表（随手拍）**，不要查work_tickets的秩序报修/保洁报修！")
        else:
            lines.append(f"- **{uname or uid}** (人员表中未找到)")
        lines.append("")

    # === 系统全貌 ===
    total_projects = db.execute(text("SELECT COUNT(*) FROM projects")).scalar() or 0
    total_personnel = db.execute(text("SELECT COUNT(*) FROM personnel WHERE status='在职'")).scalar() or 0
    all_tickets = db.execute(text("SELECT COUNT(*) FROM work_tickets WHERE source='detail'")).scalar() or 0
    all_snapshots = db.execute(text("SELECT COUNT(*) FROM snapshots")).scalar() or 0

    lines.append(f"## 系统全貌")
    lines.append(f"- 项目总数: {total_projects} | 在职人员: {total_personnel}人 | 工单明细: {all_tickets:,}条 | 随手拍: {all_snapshots:,}条")

    # ================================================================
    # 核心改动：当前项目全量数据（所有人员的原始数据 + 计算结果）
    # ================================================================
    if project_id:
        proj = db.execute(
            text("SELECT name, area FROM projects WHERE id = :pid"), {"pid": project_id}
        ).fetchone()
        if proj:
            area = proj[1] or 0
            target = area / 10000 * 20
            lines.append(f"\n## 当前项目: {proj[0]} (ID:{project_id})")
            lines.append(f"- 面积: {area:,.0f}m² | 外包目标: {target:.0f}条/月")

            # ---- 项目级汇总统计（按月份筛选）----
            params = {"pid": project_id, "m": _qmonth}
            
            # 工单明细(work_tickets, source='detail')
            wt_total = db.execute(text("SELECT COUNT(*) FROM work_tickets WHERE project_id=:pid AND source='detail' AND strftime('%Y-%m', create_time)=:m"), params).scalar() or 0
            wt_done = db.execute(text("SELECT COUNT(*) FROM work_tickets WHERE project_id=:pid AND source='detail' AND strftime('%Y-%m', create_time)=:m AND order_status IN ('已完成','已关闭','已解决')"), params).scalar() or 0
            wt_timely = db.execute(text("SELECT COUNT(*) FROM work_tickets WHERE project_id=:pid AND source='detail' AND strftime('%Y-%m', create_time)=:m AND order_status IN ('已完成','已关闭','已解决') AND deadline IS NOT NULL AND complete_time IS NOT NULL AND complete_time <= deadline"), params).scalar() or 0
            
            # 外包报修(brand IN 秩序报修,保洁报修)
            out_cnt = db.execute(text("SELECT COUNT(*) FROM work_tickets WHERE project_id=:pid AND source='detail' AND brand IN ('秩序报修','保洁报修') AND strftime('%Y-%m', create_time)=:m"), params).scalar() or 0

            # 随手拍(snapshots)
            snap_month = db.execute(text("SELECT COUNT(*) FROM snapshots WHERE project_id=:pid AND strftime('%Y-%m', create_time)=:m"), params).scalar() or 0
            snap_done_month = db.execute(text("SELECT COUNT(*) FROM snapshots WHERE project_id=:pid AND strftime('%Y-%m', create_time)=:m AND order_status IN ('已完成','已关闭','已解决')"), params).scalar() or 0
            snap_all = db.execute(text("SELECT COUNT(*) FROM snapshots WHERE project_id=:pid"), {"pid": project_id}).scalar() or 0

            # 人员
            staff_cnt = db.execute(text("SELECT COUNT(*) FROM personnel WHERE project_id=:pid AND status='在职'"), {"pid": project_id}).scalar() or 0
            internal_cnt = db.execute(text("SELECT COUNT(*) FROM personnel WHERE project_id=:pid AND status='在职' AND (is_outsourcing=0 OR is_outsourcing IS NULL)"), {"pid": project_id}).scalar() or 0
            out_staff_cnt = db.execute(text("SELECT COUNT(*) FROM personnel WHERE project_id=:pid AND status='在职' AND is_outsourcing=1"), {"pid": project_id}).scalar() or 0

            wt_cr = round(wt_done*100/wt_total, 1) if wt_total else 0
            wt_tr = round(wt_timely*100/wt_done, 1) if wt_done else 0
            snap_cr = round(snap_done_month*100/snap_month, 1) if snap_month else 0

            lines.append(f"\n### 项目级汇总统计 ({_qmonth}月)")
            lines.append(f"| 指标 | 数值 | 计算逻辑 |")
            lines.append(f"|------|------|----------|")
            lines.append(f"| 工单明细总数 | {wt_total:,}条 | work_tokens表 source='detail', project_id={project_id} |")
            lines.append(f"| 工单完成数 | {wt_done:,}条 | 状态 IN ('已完成','已关闭','已解决') |")
            lines.append(f"| 工单完成率 | {wt_cr}% | 完成/总数×100 |")
            lines.append(f"| 工单及时完成数 | {wt_timely:,}条 | complete_time <= deadline |")
            lines.append(f"| 工单及时率 | {wt_tr}% | 及时完成/完成数×100 |")
            lines.append(f"| 外包报修(本月) | {out_cnt:,}条 | brand IN ('秩序报修','保洁报修') 本月 |")
            lines.append(f"| 随手拍总量(全历史) | {snap_all:,}条 | snapshots表 project_id={project_id} |")
            lines.append(f"| 随手拍发起量(本月) | {snap_month:,}条 | snapshots表 本月create_time |")
            lines.append(f"| 随手拍完成(本月) | {snap_done_month:,}条 | snapshots状态已完成/关闭/解决 |")
            lines.append(f"| 随手拍完成率(本月) | {snap_cr}% | 完成/发起×100 |")
            lines.append(f"| 在职人员总计 | {staff_cnt}人 | 其中内部{internal_cnt}人 / 外包{out_staff_cnt}人 |")

            # ---- 全量人员KPI数据表（核心！）----
            lines.append(f"\n### 项目全员KPI数据 ({_qmonth}月) ← AI回答任何人的问题时必须直接使用这些数字！")
            lines.append(f"以下是本项目**每个内部员工**的本月随手拍发起量、完成情况、角色目标和排名：")
            lines.append("")
            
            # 查询本项目所有在职内部员工的完整KPI数据（按月份筛选）
            full_kpi_sql = text(
                "SELECT p.employee_id, p.name, p.role, "
                "COALESCE(s.cnt, 0) as snap_count, COALESCE(s.done_cnt, 0) as done_count, "
                "CASE WHEN COALESCE(s.cnt, 0) > 0 THEN ROUND(COALESCE(s.done_cnt, 0)*100.0/s.cnt, 1) ELSE 0 END as done_rate, "
                "CASE WHEN pm.id IS NOT NULL THEN '项目负责人' "
                "WHEN p.role LIKE '%外包%' THEN '外包' "
                "WHEN p.role LIKE '%总监%' AND p.role NOT LIKE '%副%' THEN '项目负责人' "
                "WHEN p.role LIKE '%副总监%' OR p.role LIKE '%副经理%' OR p.role LIKE '%副总经理%' "
                     "OR p.role LIKE '%高级经理%' OR p.role LIKE '%经理%' OR p.role LIKE '%主管%' "
                     "OR p.role LIKE '%物业经理%' OR p.role LIKE '%客服经理%' OR p.role LIKE '%工程经理%' THEN '部门管理' "
                "ELSE '一线员工' END as sys_role "
                "FROM personnel p "
                "LEFT JOIN (SELECT initiator_id, COUNT(*) as cnt, SUM(CASE WHEN order_status IN ('已完成','已关闭','已解决') THEN 1 ELSE 0 END) as done_cnt "
                    "FROM snapshots WHERE project_id = :pid AND strftime('%Y-%m', create_time) = :m GROUP BY initiator_id) s "
                    "ON s.initiator_id = p.employee_id "
                "LEFT JOIN projects_manager_list pm ON pm.project_id = p.project_id AND pm.manager_name = p.name "
                "WHERE p.project_id = :pid AND p.status = '在职' AND (p.is_outsourcing = 0 OR p.is_outsourcing IS NULL) "
                "ORDER BY COALESCE(s.cnt, 0) DESC"
            )
            kpi_rows = db.execute(full_kpi_sql, {"pid": project_id, "m": _qmonth}).fetchall()

            ROLE_TARGET = {"项目负责人": 30, "部门管理": 60, "一线员工": 30, "外包": 0}

            lines.append("| 排名 | 姓名 | 工号 | 职务 | 系统角色 | 发起量(本月) | 完成数 | 完成率 | 角色目标 | 达成情况 |")
            lines.append("|------|------|------|------|----------|-------------|--------|--------|----------|----------|")

            for idx, r in enumerate(kpi_rows, 1):
                eid, name, role, snap_cnt, done_cnt, done_rate, sys_role = r
                tgt = ROLE_TARGET.get(sys_role, 30)
                diff = int(snap_cnt) - tgt
                if diff >= 0:
                    achieve = f"✅+{diff}"
                else:
                    achieve = f"❌{diff}"
                lines.append(
                    f"| {idx} | {name or ''} | {eid or ''} | {(role or '')[:10]} | {sys_role} "
                    f"| {int(snap_cnt)}条 | {int(done_cnt)}条 | {float(done_rate)}% "
                    f"| {tgt}条/月 | {achieve} |"
                )

            # 统计摘要
            total_initiated = sum(int(r[3]) for r in kpi_rows)
            avg_per_person = round(total_initiated / len(kpi_rows), 1) if kpi_rows else 0
            achieved_count = sum(1 for r in kpi_rows if int(r[3]) >= ROLE_TARGET.get(r[6], 30))
            lines.append(f"\n**汇总**: 共{len(kpi_rows)}位内部员工 | 总发起量: {total_initiated}条 | 人均: {avg_per_person}条 | 达标人数: {achieved_count}人")

            # ---- TOP10和BOTTOM10高亮 ----
            if len(kpi_rows) > 0:
                top5 = kpi_rows[:5]
                bottom5 = kpi_rows[-5:] if len(kpi_rows) >= 5 else kpi_rows[max(0, len(kpi_rows)-5):]
                lines.append(f"\n**🏆 发起量TOP5**: " + "、".join([f"{r[1]}({int(r[3])}条)" for r in top5]))
                lines.append(f"**⚠️ 发起量后5位**: " + "、".join([f"{r[1]}({int(r[3])}条)" for r in reversed(bottom5)]))

            # ---- 外包人员数据（如果有）----
            out_sql = text(
                "SELECT p.employee_id, p.name, p.role, COALESCE(wt.cnt, 0) as out_ticket_count "
                "FROM personnel p "
                "LEFT JOIN (SELECT initiator_id, COUNT(*) as cnt FROM work_tickets "
                    "WHERE project_id = :pid AND source = 'detail' AND brand IN ('秩序报修', '保洁报修') "
                    "GROUP BY initiator_id) wt ON wt.initiator_id = p.employee_id "
                "WHERE p.project_id = :pid AND p.status = '在职' AND p.is_outsourcing = 1 "
                "ORDER BY COALESCE(wt.cnt, 0) DESC"
            )
            out_rows = db.execute(out_sql, {"pid": project_id}).fetchall()
            if out_rows:
                lines.append(f"\n### 外包人员数据（全量）")
                lines.append("| 姓名 | 工号 | 职务 | 外包报修关联数 |")
                lines.append("|------|------|------|----------------|")
                for r in out_rows:
                    lines.append(f"| {r[1] or ''} | {r[0] or ''} | {(r[2] or '')[:10]} | {int(r[3])}条 |")

            # ---- 原始数据样本（随手拍最近20条）----
            sample_sql = text(
                "SELECT ticket_no, initiator_id, initiator_name, create_time, order_status "
                "FROM snapshots WHERE project_id = :pid ORDER BY rowid DESC LIMIT 20"
            )
            samples = db.execute(sample_sql, {"pid": project_id}).fetchall()
            if samples:
                lines.append(f"\n### 随手拍原始数据样本(最近20条)")
                lines.append("| 编号 | 发起人工号 | 发起人 | 创建时间 | 状态 |")
                lines.append("|------|-----------|--------|---------|------|")
                for s in samples:
                    lines.append(f"| {s[0] or ''} | {s[1] or ''} | {s[2] or ''} | {str(s[3]) or ''} | {s[4] or ''} |")

    # === 全局人员索引（非本项目人员也列出）===
    personnel_rows = db.execute(text(
        "SELECT p.employee_id, p.name, pr.name as proj_name, p.role, p.is_outsourcing "
        "FROM personnel p LEFT JOIN projects pr ON p.project_id=pr.id "
        "WHERE p.status='在职' ORDER BY p.name LIMIT 300"
    )).fetchall()

    if personnel_rows:
        lines.append(f"\n## 全系统在职人员索引({len(personnel_rows)}人)")
        lines.append("| 工号 | 姓名 | 项目 | 职务 | 外包 |")
        lines.append("|------|------|------|------|------|")
        for emp in personnel_rows:
            out = "是" if emp[4] else ""
            lines.append(f"| {emp[0]} | {emp[1] or ''} | {(emp[2] or '')[:20]} | {emp[3] or ''} | {out} |")

    # === 项目列表索引 ===
    projs = db.execute(text("SELECT id, name, area, area/10000*20 as target FROM projects ORDER BY name LIMIT 50")).fetchall()
    if projs:
        lines.append(f"\n## 项目列表({len(projs)}个)")
        lines.append("| ID | 项目名 | 面积(m²) | 外包目标(条/月) |")
        lines.append("|----|--------|----------|---------------|")
        for p in projs:
            lines.append(f"| {p[0]} | {p[1]} | {p[2]:,.0f} | {p[3]:.0f} |")

    # === 筹建专项汇总 (WY) ===
    try:
        wy_total = db.execute(text("SELECT COUNT(*) FROM special_plans")).scalar() or 0
        wy_completed = db.execute(text("SELECT COUNT(*) FROM special_plans WHERE finish_flag=1")).scalar() or 0
        wy_paused = db.execute(text("SELECT COUNT(*) FROM special_plans WHERE pause_flag=1")).scalar() or 0
        if wy_total > 0:
            lines.append(f"\n## 筹建专项汇总(WY)")
            lines.append(f"- 总专项数: {wy_total} | 已完成: {wy_completed} | 已暂停: {wy_paused}")
            
            # 按项目统计WY
            wy_by_proj = db.execute(text("""
                SELECT pr.name, COUNT(*) as total, 
                    SUM(CASE WHEN sp.finish_flag=1 THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN sp.pause_flag=1 THEN 1 ELSE 0 END) as paused
                FROM special_plans sp LEFT JOIN projects pr ON sp.project_name=pr.name
                GROUP BY pr.name HAVING pr.name IS NOT NULL
                ORDER BY total DESC LIMIT 10
            """)).fetchall()
            if wy_by_proj:
                lines.append("\n### 筹建专项-按项目TOP10")
                lines.append("| 项目 | 总数 | 已完成 | 已暂停 |")
                lines.append("|------|------|--------|-------|")
                for wp in wy_by_proj:
                    lines.append(f"| {wp[0][:20]} | {wp[1]} | {wp[2]} | {wp[3]} |")
    except Exception as e:
        lines.append(f"\n## 筹建专项(WY) - 暂无可用数据")

    # === IPMS设备任务汇总 ===
    try:
        from backend.models.ipms_task import IPMSTask
        ipms_total = db.query(IPMSTask).count()
        if ipms_total > 0:
            ipms_patrol = db.query(IPMSTask).filter(IPMSTask.task_type == 'patrol').count()
            ipms_maintain = db.query(IPMSTask).filter(IPMSTask.task_type == 'maintain').count()
            ipms_done = db.query(IPMSTask).filter(IPMSTask.task_state_name.in_(['完成', '审核关闭'])).count()
            lines.append(f"\n## IPMS设备任务汇总")
            lines.append(f"- 总任务数: {ipms_total} | 巡检: {ipms_patrol} | 维保: {ipms_maintain} | 已完成: {ipms_done}")
            
            # 按执行人统计TOP15
            from sqlalchemy import func
            ipms_by_person = db.query(
                IPMSTask.executor_name,
                IPMSTask.task_type,
                func.count(IPMSTask.id).label('total'),
            ).filter(
                IPMSTask.executor_name.isnot(None),
                IPMSTask.executor_name != ''
            ).group_by(IPMSTask.executor_name, IPMSTask.task_type).order_by(func.count(IPMSTask.id).desc()).limit(15).all()
            
            if ipms_by_person:
                lines.append("\n### IPMS执行人绩效TOP15")
                lines.append("| 执行人 | 类型 | 总数 | 已完成 |")
                lines.append("|--------|------|------|--------|")
                for ip in ipms_by_person:
                    done_cnt = db.query(IPMSTask).filter(
                        IPMSTask.executor_name == ip[0],
                        IPMSTask.task_type == ip[1],
                        IPMSTask.task_state_name.in_(['完成', '审核关闭'])
                    ).count()
                    lines.append(f"| {ip[0]} | {ip[1]} | {ip[2]} | {done_cnt} |")
    except Exception as e:
        lines.append(f"\n## IPMS设备任务 - 暂无可用数据")

    # === 逾期风险专项数据 ===
    try:
        # WY即将到期/已逾期专项
        wy_at_risk = db.execute(text("""
            SELECT special_name, plan_end_date, plan_person, person_name,
                CAST(julianday('now') - julianday(plan_end_date) AS INTEGER) as overdue_days
            FROM special_plans
            WHERE finish_flag != 1 AND pause_flag != 1
            ORDER BY overdue_days DESC LIMIT 20
        """)).fetchall()
        if wy_at_risk and wy_at_risk[0]:
            lines.append(f"\n## WY筹建专项-逾期风险TOP20")
            lines.append("| 专项名称 | 截止日期 | 负责人 | 逾期天数 |")
            lines.append("|----------|----------|--------|----------|")
            for w in wy_at_risk:
                days = w[4] if w[4] else 0
                marker = "⚠️" if days > 0 else "🔔"
                lines.append(f"| {marker} {w[0][:30]} | {w[1]} | {w[3] or w[2] or '-'} | {days}天 |")
        
        # WY按负责人统计逾期
        wy_by_person = db.execute(text("""
            SELECT person_name, plan_person, COUNT(*) as cnt
            FROM special_plans
            WHERE finish_flag != 1 AND pause_flag != 1
            AND julianday('now') - julianday(plan_end_date) > 0
            GROUP BY person_name ORDER BY cnt DESC LIMIT 10
        """)).fetchall()
        if wy_by_person and wy_by_person[0]:
            lines.append(f"\n### WY逾期专项-按负责人TOP10")
            lines.append("| 负责人 | 逾期专项数 |")
            lines.append("|--------|-----------|")
            for wp in wy_by_person:
                lines.append(f"| {wp[0] or wp[1] or '-'} | {wp[2]} |")
        
        # WY按日期统计到期
        wy_by_date = db.execute(text("""
            SELECT date(plan_end_date) as dd, COUNT(*) as cnt
            FROM special_plans
            WHERE finish_flag != 1 AND pause_flag != 1
            AND plan_end_date >= date('now', '-30 days')
            GROUP BY dd ORDER BY dd LIMIT 15
        """)).fetchall()
        if wy_by_date and wy_by_date[0]:
            lines.append(f"\n### WY专项-未来30天到期分布")
            lines.append("| 日期 | 数量 |")
            lines.append("|------|------|")
            for wd in wy_by_date:
                lines.append(f"| {wd[0]} | {wd[1]} |")
    except Exception as e:
        pass  # 忽略错误，不影响主功能

    try:
        from datetime import datetime
        now = datetime.now()
        
        # IPMS已逾期任务（用ORM查询）
        ipms_overdue = db.query(IPMSTask).filter(
            IPMSTask.task_state_name.notin_(['完成', '审核关闭']),
            IPMSTask.task_state_name != '过期',
            IPMSTask.end_time < now
        ).order_by(IPMSTask.end_time.asc()).limit(20).all()
        
        if ipms_overdue:
            lines.append(f"\n## IPMS任务-逾期风险TOP20")
            lines.append("| 任务名称 | 类型 | 执行人 | 截止时间 | 逾期天数 |")
            lines.append("|----------|------|--------|----------|----------|")
            for io in ipms_overdue:
                days = (now - io.end_time).days if io.end_time else 0
                lines.append(f"| {str(io.task_name)[:25]} | {io.task_type} | {io.executor_name or '-'} | {io.end_time} | {days}天 |")
        
        # IPMS按类型统计逾期
        from sqlalchemy import func
        ipms_overdue_by_type = db.query(
            IPMSTask.task_type,
            func.count(IPMSTask.id).label('cnt')
        ).filter(
            IPMSTask.task_state_name.notin_(['完成', '审核关闭']),
            IPMSTask.task_state_name != '过期',
            IPMSTask.end_time < now
        ).group_by(IPMSTask.task_type).order_by(func.count(IPMSTask.id).desc()).all()
        
        if ipms_overdue_by_type:
            lines.append(f"\n### IPMS逾期-按类型分布")
            lines.append("| 类型 | 逾期数 |")
            lines.append("|------|--------|")
            for iot in ipms_overdue_by_type:
                lines.append(f"| {iot[0]} | {iot[1]} |")
        
        # IPMS按执行人统计逾期
        ipms_overdue_by_person = db.query(
            IPMSTask.executor_name,
            IPMSTask.task_type,
            func.count(IPMSTask.id).label('cnt')
        ).filter(
            IPMSTask.task_state_name.notin_(['完成', '审核关闭']),
            IPMSTask.task_state_name != '过期',
            IPMSTask.end_time < now
        ).group_by(IPMSTask.executor_name, IPMSTask.task_type).order_by(func.count(IPMSTask.id).desc()).limit(10).all()
        if ipms_overdue_by_person:
            lines.append(f"\n### IPMS逾期-按执行人TOP10")
            lines.append("| 执行人 | 类型 | 逾期数 |")
            lines.append("|--------|------|--------|")
            for iop in ipms_overdue_by_person:
                lines.append(f"| {iop[0] or '-'} | {iop[1]} | {iop[2]} |")
    except Exception as e:
        pass  # 忽略错误

    return "\n".join(lines)


async def _call_nvidia_streaming(messages: list) -> AsyncGenerator[str, None]:
    """
    在线程池里用 httpx 发起异步流式请求，不阻塞事件循环。
    httpx.AsyncClient 在独立线程里处理网络IO，不会冻住 FastAPI 的事件循环。
    """
    import json

    headers = {
        "Authorization": f"Bearer {AI_CONFIG['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_CONFIG["model"],
        "messages": messages,
        "max_tokens": AI_CONFIG["max_tokens"],
        "temperature": AI_CONFIG["temperature"],
        "top_p": AI_CONFIG["top_p"],
        "stream": True,
    }

    async def _fetch_in_thread():
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
            async with client.stream(
                "POST",
                AI_CONFIG["invoke_url"],
                headers=headers,
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        yield line

    loop = asyncio.get_event_loop()
    async for chunk in _fetch_in_thread():
        yield chunk


class ChatRequest(BaseModel):
    message: str
    project_id: Optional[int] = None
    month: Optional[str] = None
    conversation_id: Optional[str] = None
    # 当前登录用户信息（用于身份识别）
    user_name: Optional[str] = None
    employee_id: Optional[str] = None


# ============================================================
# 流式对话接口
# ============================================================
async def _generate_stream(req: ChatRequest):
    """生成SSE流式数据"""
    from backend.database import get_session_local

    def think_event(msg: str):
        return f"data: {_json.dumps({'think': msg}, ensure_ascii=False)}\n\n"

    # 构建上下文
    db = get_session_local()()
    try:
        yield think_event("分析数据库...")
        db_context = build_db_context(db, req.project_id, req.month,
                                       user_name=req.user_name, employee_id=req.employee_id)
        yield think_event("数据就绪，AI推理中，请稍候...")
    finally:
        db.close()

    full_system = f"{SYSTEM_PROMPT}\n\n{db_context}"
    messages = [
        {"role": "system", "content": full_system},
        {"role": "user", "content": req.message}
    ]

    try:
        async for raw_line in _call_nvidia_streaming(messages):
            if raw_line.startswith("data: "):
                data_str = raw_line[6:]
                if data_str.strip() == "[DONE]":
                    yield "data: [DONE]\n\n"
                    break
                try:
                    data = _json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield f"data: {_json.dumps({'content': content}, ensure_ascii=False)}\n\n"
                except (_json.JSONDecodeError, KeyError, IndexError):
                    continue
    except httpx.HTTPStatusError as e:
        yield f"data: {_json.dumps({'error': f'AI服务请求失败：{e.response.status_code}'}, ensure_ascii=False)}\n\n"
    except httpx.TimeoutException:
        yield f"data: {_json.dumps({'error': 'AI响应超时，请稍后重试'}, ensure_ascii=False)}\n\n"
    except httpx.RequestError as e:
        yield f"data: {_json.dumps({'error': f'AI服务连接失败：{str(e)}'}, ensure_ascii=False)}\n\n"
    except Exception as e:
        yield f"data: {_json.dumps({'error': f'AI异常：{str(e)}'}, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """流式AI对话 - 返回SSE格式"""
    return StreamingResponse(
        _generate_stream(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================
# 非流式对话接口（备用）
# ============================================================
@router.post("/chat")
async def chat_non_stream(req: ChatRequest):
    """非流式AI对话"""
    import json
    from backend.database import get_session_local

    db = get_session_local()()
    try:
        db_context = build_db_context(db, req.project_id, req.month,
                                       user_name=req.user_name, employee_id=req.employee_id)
        full_system = f"{SYSTEM_PROMPT}\n\n{db_context}"
    finally:
        db.close()

    messages = [
        {"role": "system", "content": full_system},
        {"role": "user", "content": req.message}
    ]

    headers = {
        "Authorization": f"Bearer {AI_CONFIG['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_CONFIG["model"],
        "messages": messages,
        "max_tokens": AI_CONFIG["max_tokens"],
        "temperature": AI_CONFIG["temperature"],
        "top_p": AI_CONFIG["top_p"],
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
            resp = await client.post(AI_CONFIG["invoke_url"], headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"reply": content}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"AI服务请求失败：{e.response.status_code}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI响应超时，请稍后重试")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI异常：{str(e)}")


# ============================================================
# 调试端点
# ============================================================
@router.post("/debug-context")
async def debug_context(req: ChatRequest):
    """返回 AI 上下文内容"""
    from backend.database import get_session_local
    db = get_session_local()()
    try:
        ctx = build_db_context(db, req.project_id, req.month,
                                user_name=req.user_name, employee_id=req.employee_id)
        return {"success": True, "context": ctx}
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e), "trace": traceback.format_exc()}
    finally:
        db.close()
