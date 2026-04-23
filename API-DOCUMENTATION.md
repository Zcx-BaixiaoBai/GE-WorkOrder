# 金鹰工单KPI管理 API 文档

## 基础信息

- **基础URL**: `http://localhost:8765` (本地FastAPI服务)
- **数据格式**: JSON
- **编码**: UTF-8
- **认证**: Bearer Token (在请求头中携带)

## 权限控制

### 数据访问范围
| 用户角色 | 可访问项目 | 说明 |
|----------|-----------|------|
| 项目负责人 | 所属项目 | 只能查看自己负责的项目数据 |
| 部门管理 | 所属项目 | 只能查看自己所在项目数据 |
| 一线员工 | 所属项目 | 只能查看自己所在项目数据 |
| 外包 | 所属项目 | 只能查看自己所在项目数据 |
| 系统管理员 | 所有项目 | 可查看所有项目，也可指定项目查询 |

### 项目过滤规则
- **普通用户**: 后端自动从Token解析用户所属项目，无需传递 projectId 参数
- **管理员**: 可通过 `projectId` 查询参数指定要查看的项目，不传则返回所有项目汇总
- **跨项目访问**: 普通用户尝试访问非所属项目数据时返回 403 权限不足错误

## 全局配置

```javascript
const CONFIG = {
    API_BASE_URL: 'http://localhost:8765',
    USE_MOCK: false,  // 关闭模拟数据，使用真实API
};
```

## 接口列表

### 1. 用户登录

**接口**: `POST /auth/login`

**描述**: 用户登录验证，OA账号用于数据同步认证，工号用于角色权限查询

**请求体**:
```json
{
    "account": "zhangsan",
    "password": "******",
    "employeeId": "037001",
    "projectId": "1118"
}
```

**请求参数说明**:
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| account | string | 是 | OA账号，用于后续数据同步认证 |
| password | string | 是 | OA密码，用于验证用户身份 |
| employeeId | string | 是 | 工号，用于查询用户在项目中的角色权限 |
| projectId | string | 是 | 项目ID，指定要访问的项目 |

**响应示例**:
```json
{
    "success": true,
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "user": {
        "id": "037001",
        "account": "zhangsan",
        "name": "张三",
        "role": "项目负责人",
        "projectId": "1118",
        "projectName": "南京珠江壹号"
    }
}
```

**后端角色查询流程**:

```
1. 接收请求参数 (account, password, employeeId, projectId)
2. 验证OA账号密码 → 失败返回 401
3. 验证工号是否存在于人力清单 → 失败返回 404
4. 从人力清单获取员工职务信息
5. 查询角色映射配置，将职务映射为系统角色
6. 返回用户信息（包含角色）
```

**数据结构示例**:

*人力清单表*:
| 工号 | 姓名 | 职务 | 项目ID |
|------|------|------|--------|
| 037001 | 张三 | 项目总监 | 1118 |
| 037002 | 李四 | 工程主管 | 1118 |
| 037003 | 王五 | 维修技工 | 1118 |

*角色映射配置*:
| 职务 | 系统角色 |
|------|----------|
| 项目总监 | 项目负责人 |
| 工程主管 | 部门管理 |
| 客服经理 | 部门管理 |
| IT管理员 | 系统管理员 |
| 维修技工 | 一线员工 |
| 安保员 | 一线员工 |
| 外包保洁 | 外包 |
| 外包保安 | 外包 |

**查询逻辑**:
- 先通过 `employeeId` 在人力清单中查找员工记录
- 获取员工的 `职务` 字段
- 在角色映射配置中查找该职务对应的 `系统角色`
- 如未找到映射，默认返回 `一线员工`
- 最终返回的 `role` 字段用于前端权限控制

**角色枚举**:
| 角色 | 权限说明 |
|------|----------|
| 系统管理员 | 所有权限，可查看所有项目 |
| 项目负责人 | 管理本项目，可查看配置、触发同步 |
| 部门管理 | 查看部门数据，部分配置权限 |
| 一线员工 | 仅查看个人相关数据 |
| 外包 | 仅查看个人相关数据 |

**错误码**:
| 状态码 | 说明 |
|--------|------|
| 400 | 缺少必填参数（account/password/employeeId/projectId） |
| 401 | OA账号或密码错误 |
| 403 | 该工号无权限访问指定项目 |
| 404 | 工号不存在于人力清单中 |

**Token使用**: 登录成功后，后续请求需在请求头携带 `Authorization: Bearer {token}`

---

### 2. 获取项目列表

**接口**: `GET /projects`

**描述**: 获取所有项目数据（用于配置管理和下拉选择）

**响应示例**:
```json
[
    {
        "id": "1118",
        "name": "南京珠江壹号",
        "area": 15.50,
        "outsourcingTarget": 310
    },
    {
        "id": "1136",
        "name": "南京金鹰世界",
        "area": 23.00,
        "outsourcingTarget": 460
    }
]
```

**字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 公司代码 |
| name | string | 项目名称 |
| area | number | 项目面积(万平方米) |
| outsourcingTarget | number | 外包目标工单数 |

---

### 3. 添加项目

**接口**: `POST /projects`

**请求体**:
```json
{
    "id": "1145",
    "name": "南京新街口",
    "area": 18.00,
    "outsourcingTarget": 360
}
```

**响应示例**:
```json
{
    "success": true,
    "message": "项目添加成功",
    "data": {
        "id": "1145",
        "name": "南京新街口",
        "area": 18.00,
        "outsourcingTarget": 360
    }
}
```

---

### 4. 更新项目

**接口**: `PUT /projects/:id`

**请求体**:
```json
{
    "name": "南京新街口",
    "area": 20.00,
    "outsourcingTarget": 400
}
```

---

### 5. 删除项目

**接口**: `DELETE /projects/:id`

**响应示例**:
```json
{
    "success": true,
    "message": "项目删除成功"
}
```

---

### 6. 获取角色映射列表

**接口**: `GET /roles`

**描述**: 获取人员角色映射配置

**响应示例**:
```json
[
    {
        "id": "037001",
        "name": "张三",
        "position": "项目总监",
        "projectId": "1118",
        "role": "项目负责人"
    },
    {
        "id": "025259",
        "name": "李四",
        "position": "工程主管",
        "projectId": "1118",
        "role": "部门管理"
    }
]
```

**角色枚举**:
| 值 | 说明 |
|----|------|
| 项目负责人 | 项目最高负责人 |
| 部门管理 | 部门主管/经理 |
| 一线员工 | 普通员工 |
| 外包 | 外包人员 |

---

### 7. 添加角色映射

**接口**: `POST /roles`

**请求体**:
```json
{
    "id": "039999",
    "name": "王五",
    "position": "工程师",
    "projectId": "1118",
    "role": "一线员工"
}
```

---

### 8. 更新角色映射

**接口**: `PUT /roles/:id`

**请求体**:
```json
{
    "position": "高级工程师",
    "projectId": "1136",
    "role": "部门管理"
}
```

---

### 9. 删除角色映射

**接口**: `DELETE /roles/:id`

---

### 10. 获取KPI配置

**接口**: `GET /config/kpi`

**描述**: 获取绩效考核配置参数

**响应示例**:
```json
{
    "completionRate": {
        "target": 95,
        "weight": 40
    },
    "timelinessRate": {
        "target": 90,
        "weight": 30
    },
    "satisfactionScore": {
        "target": 4.5,
        "weight": 30
    },
    "deductionRules": [
        {"type": "超时", "points": 5},
        {"type": "投诉", "points": 10},
        {"type": "返工", "points": 8}
    ]
}
```

---

### 11. 保存KPI配置

**接口**: `POST /config/kpi`

**请求体**:
```json
{
    "completionRate": {
        "target": 95,
        "weight": 40
    },
    "timelinessRate": {
        "target": 90,
        "weight": 30
    },
    "satisfactionScore": {
        "target": 4.5,
        "weight": 30
    },
    "deductionRules": [
        {"type": "超时", "points": 5},
        {"type": "投诉", "points": 10}
    ]
}
```

---

### 12. 获取驾驶舱统计数据

**接口**: `GET /dashboard/stats`

**描述**: 获取首页KPI卡片和趋势图表所需统计数据

**请求头**:
```
Content-Type: application/json
Authorization: Bearer {token}
```

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| projectId | string | 否 | 项目ID，管理员可指定，普通用户自动使用所属项目 |
| month | string | 否 | 月份 YYYY-MM，不传则当月 |

**响应示例**:
```json
{
    "projectId": "1118",
    "projectName": "南京珠江壹号",
    "total": 1234,
    "pending": 56,
    "completed": 1098,
    "rate": 89.2,
    "trend": [980, 1120, 1050, 1180, 1234, 1234]
}
```

**字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| projectId | string | 项目ID |
| projectName | string | 项目名称 |
| total | number | 工单总数 |
| pending | number | 待处理工单数 |
| completed | number | 已完成工单数 |
| rate | number | 完成率(%) |
| trend | array | 近6期趋势数据 |

---

### 13. 搜索工单列表

**接口**: `GET /tickets/search`

**描述**: 获取工单数据，支持前端筛选排序分页。普通用户自动过滤所属项目，管理员可查看所有项目或指定项目。

**请求头**:
```
Content-Type: application/json
Authorization: Bearer {token}
```

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| projectId | string | 否 | 项目ID，管理员专用，不传则所有项目 |
| status | string | 否 | 状态筛选: pending/processing/auditing/completed/closed |
| keyword | string | 否 | 关键词搜索(工单号/发起人) |
| startDate | string | 否 | 开始日期 YYYY-MM-DD |
| endDate | string | 否 | 结束日期 YYYY-MM-DD |
| page | number | 否 | 页码，默认1 |
| pageSize | number | 否 | 每页条数，默认10 |

**响应示例**:
```json
{
    "total": 156,
    "page": 1,
    "pageSize": 10,
    "projectId": "1118",
    "items": [
        {
            "id": "WP-20260408-001",
            "projectId": "1118",
            "projectName": "南京珠江壹号",
            "type": "设备报修",
            "creator": "张三",
            "creatorId": "037001",
            "handler": "王五",
            "createTime": "2026-04-08 09:30:00",
            "status": "completed",
            "score": 5
        }
    ]
}
```

**字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 工单号，格式: WP-YYYYMMDD-XXX |
| project | string | 所属项目 |
| type | string | 工单类型 |
| creator | string | 发起人姓名 |
| creatorId | string | 发起人ID |
| handler | string | 处理人姓名 |
| createTime | string | 创建时间，格式: YYYY-MM-DD HH:mm:ss |
| status | string | 状态: pending/processing/auditing/completed/closed |
| score | number | 评分(1-5)，未完成工单为0 |

**状态枚举**:
| 值 | 中文 | 说明 |
|----|------|------|
| pending | 待处理 | 等待分配 |
| processing | 处理中 | 正在处理 |
| auditing | 待审核 | 等待审核 |
| completed | 已完成 | 处理完成 |
| closed | 已关闭 | 工单关闭 |

---

### 14. 获取人力清单

**接口**: `GET /personnel/list`

**描述**: 获取人员统计列表，用于人力清单页面。普通用户仅返回所属项目人员，管理员可查看所有项目或指定项目。

**请求头**:
```
Content-Type: application/json
Authorization: Bearer {token}
```

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| projectId | string | 否 | 项目ID，管理员专用 |
| role | string | 否 | 角色筛选: 项目负责人/部门管理/一线员工/外包 |
| keyword | string | 否 | 关键词搜索(姓名/工号) |
| month | string | 否 | 月份 YYYY-MM |
| page | number | 否 | 页码，默认1 |
| pageSize | number | 否 | 每页条数，默认10 |

**响应示例**:
```json
{
    "total": 45,
    "page": 1,
    "pageSize": 10,
    "projectId": "1118",
    "projectName": "南京珠江壹号",
    "items": [
        {
            "id": "031000",
            "name": "张三",
            "position": "总监",
            "role": "项目负责人",
            "projectId": "1118",
            "count": 3,
            "target": 50,
            "actual": 65,
            "deduction": 10,
            "achievementRate": 130
        }
    ]
}
```

**字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 人员编号 |
| name | string | 姓名 |
| position | string | 职位 |
| role | string | 角色: 项目负责人/部门管理/一线员工/外包 |
| count | number | 负责工单数 |
| target | number | 目标工单数 |
| actual | number | 实际完成数 |
| deduction | number | 扣分 |

---

### 15. 获取同步状态

**接口**: `GET /sync/status`

**描述**: 获取数据同步状态

**请求头**:
```
Content-Type: application/json
Authorization: Bearer {token}
```

**响应示例**:
```json
{
    "status": "idle",
    "lastSync": "14:32",
    "progress": 0,
    "message": "等待同步"
}
```

**字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 状态: idle/syncing/error |
| lastSync | string | 上次同步时间，格式: HH:mm |
| progress | number | 同步进度 0-100 |
| message | string | 当前步骤描述 |

---

### 16. 触发数据同步

**接口**: `POST /sync/trigger`

**描述**: 手动触发BI数据同步（随手拍统计表 + 工单明细表）。普通用户仅同步所属项目数据，管理员可指定项目。

**请求体**:
```json
{
    "projectId": "1118",
    "force": false,
    "dateRange": {
        "start": "2026-04-01",
        "end": "2026-04-09"
    }
}
```

**字段说明**:
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| projectId | string | 否 | 项目ID，管理员可指定，普通用户自动使用所属项目 |
| force | boolean | 否 | 是否强制重新同步（忽略缓存） |
| dateRange | object | 否 | 日期范围，不传则同步当月 |
| dateRange.start | string | 否 | 开始日期 YYYY-MM-DD |
| dateRange.end | string | 否 | 结束日期 YYYY-MM-DD |

**响应示例**:
```json
{
    "success": true,
    "syncId": "sync-20260409-150245",
    "message": "同步任务已启动"
}
```

---

### 17. 获取同步历史

**接口**: `GET /sync/history`

**描述**: 获取数据同步历史记录。普通用户仅返回所属项目的同步记录，管理员可查看所有项目或指定项目。

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| projectId | string | 否 | 项目ID，管理员可指定，普通用户自动使用所属项目 |
| limit | number | 否 | 返回条数，默认10 |
| offset | number | 否 | 偏移量，默认0 |

**响应示例**:
```json
{
    "total": 25,
    "items": [
        {
            "syncId": "sync-20260409-150245",
            "status": "success",
            "startTime": "2026-04-09 15:02:45",
            "endTime": "2026-04-09 15:04:12",
            "duration": 87,
            "recordsProcessed": 1256,
            "message": "成功导入随手拍统计表和工单明细表"
        }
    ]
}
```

---

### 18. 获取四层级发起统计

**接口**: `GET /stats/initiation-by-level`

**描述**: 获取项目负责人、部门管理、一线员工、外包保安保洁四个层级的发起统计（PRD 4.1节）

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| projectId | string | 否 | 项目ID，管理员可指定，普通用户自动使用所属项目 |
| month | string | 否 | 月份 YYYY-MM，不传则当月 |

**响应示例**:
```json
{
    "totalInitiated": 856,
    "totalTarget": 1200,
    "achievementRate": 71.3,
    "levels": [
        {
            "level": "项目负责人",
            "count": 5,
            "initiated": 145,
            "target": 150,
            "targetPerPerson": 30,
            "achievementRate": 96.7
        },
        {
            "level": "部门管理",
            "count": 8,
            "initiated": 420,
            "target": 480,
            "targetPerPerson": 60,
            "achievementRate": 87.5
        },
        {
            "level": "一线员工",
            "count": 25,
            "initiated": 180,
            "target": 750,
            "targetPerPerson": 30,
            "achievementRate": 24.0
        },
        {
            "level": "外包保安保洁",
            "count": null,
            "initiated": 111,
            "target": 460,
            "targetPerPerson": null,
            "achievementRate": 24.1,
            "note": "目标按项目面积×20计算"
        }
    ]
}
```

**字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| totalInitiated | number | 项目总发起数 |
| totalTarget | number | 项目总目标数 |
| achievementRate | number | 总达成率(%) |
| levels | array | 四层级统计 |
| levels[].level | string | 层级名称 |
| levels[].count | number | 人数（外包为null） |
| levels[].initiated | number | 实际发起数 |
| levels[].target | number | 目标数 |
| levels[].targetPerPerson | number | 人均目标（外包为null） |
| levels[].achievementRate | number | 达成率(%) |

---

### 19. 获取预警清单

**接口**: `GET /stats/warnings`

**描述**: 获取预警人员清单（PRD 4.1节 - 达成率<100%的人员）

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| projectId | string | 否 | 项目ID，管理员可指定，普通用户自动使用所属项目 |
| level | string | 否 | 筛选层级：项目负责人/部门管理/一线员工/外包保安保洁 |
| threshold | number | 否 | 预警阈值(%)，默认100 |
| month | string | 否 | 月份 YYYY-MM |

**响应示例**:
```json
{
    "total": 23,
    "severe": 15,
    "normal": 8,
    "items": [
        {
            "id": "037001",
            "name": "张三",
            "level": "项目负责人",
            "position": "项目总监",
            "initiated": 18,
            "target": 30,
            "targetDynamic": 21,
            "achievementRate": 85.7,
            "warningType": "normal",
            "daysPassed": 21,
            "daysInMonth": 30
        }
    ]
}
```

**预警类型**:
| 类型 | 条件 |
|------|------|
| severe | 达成率 < 70% |
| normal | 70% ≤ 达成率 < 100% |

---

### 20. 获取完成情况统计

**接口**: `GET /stats/completion`

**描述**: 获取工单完成情况统计（PRD 4.2节）

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| projectId | string | 否 | 项目ID，管理员可指定，普通用户自动使用所属项目 |
| month | string | 否 | 月份 YYYY-MM |

**响应示例**:
```json
{
    "totalTickets": 1234,
    "completed": 1098,
    "pending": 56,
    "processing": 80,
    "completionRate": 89.0,
    "timelyCompleted": 1050,
    "timelyRate": 85.1,
    "avgProcessDays": 5.2,
    "overdueTickets": 184
}
```

**字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| totalTickets | number | 总工单数 |
| completed | number | 已完成数 |
| pending | number | 待处理数 |
| processing | number | 处理中数 |
| completionRate | number | 完成率(%) |
| timelyCompleted | number | 及时完成数（≤7天） |
| timelyRate | number | 及时完成率(%) |
| avgProcessDays | number | 平均处理天数 |
| overdueTickets | number | 超期工单数 |

---

### 21. 获取综合评分

**接口**: `GET /stats/score`

**描述**: 获取项目综合评分（PRD 4.3节）

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| projectId | string | 否 | 项目ID，管理员可指定，普通用户自动使用所属项目 |
| month | string | 否 | 月份 YYYY-MM |

**响应示例**:
```json
{
    "overallScore": 8.7,
    "completionScore": 8.9,
    "timelinessScore": 8.5,
    "initiationScore": 8.6,
    "weights": {
        "completion": 30,
        "timeliness": 30,
        "initiation": 40
    },
    "grade": "A"
}
```

**评分等级**:
| 等级 | 分数范围 |
|------|----------|
| S | 9.0 - 10.0 |
| A | 8.0 - 8.9 |
| B | 7.0 - 7.9 |
| C | 6.0 - 6.9 |
| D | < 6.0 |

---

### 22. 获取预警阈值配置

**接口**: `GET /config/thresholds`

**描述**: 获取预警阈值设置（PRD 6.2节）

**响应示例**:
```json
{
    "warning": {
        "enabled": true,
        "threshold": 100,
        "severeThreshold": 70
    },
    "notification": {
        "enabled": true,
        "channels": ["app", "email"],
        "frequency": "daily"
    }
}
```

---

### 23. 保存预警阈值配置

**接口**: `POST /config/thresholds`

**请求体**:
```json
{
    "warning": {
        "enabled": true,
        "threshold": 100,
        "severeThreshold": 70
    },
    "notification": {
        "enabled": true,
        "channels": ["app", "email"],
        "frequency": "daily"
    }
}
```

---

### 24. 获取管理层岗位清单

**接口**: `GET /config/management-positions`

**描述**: 获取管理层岗位清单（PRD第9节）

**响应示例**:
```json
{
    "positions": [
        "安全经理", "安全主管", "副经理", "副总监", "副总经理",
        "高级工程经理", "高级经理", "高级物业经理", "工程副经理",
        "工程副总监", "工程经理", "工程主管", "工程总监",
        "管培生", "经理", "客服副经理", "客服经理", "客服主管",
        "物业副经理", "物业经理", "物业主管", "现场主管",
        "消防主管", "主管", "综合经理", "综合主管", "总监", "总经理"
    ],
    "updatedAt": "2026-04-08 10:00:00"
}
```

---

### 25. 更新管理层岗位清单

**接口**: `POST /config/management-positions`

**请求体**:
```json
{
    "positions": ["安全经理", "安全主管", "副经理"]
}
```

---

### 26. 获取BI项目对照表

**接口**: `GET /config/bi-projects`

**描述**: 获取BI项目名称对照表（PRD 5.3节）

**响应示例**:
```json
[
    {
        "biName": "金鹰珠江壹号",
        "standardName": "南京珠江壹号",
        "projectId": "1118",
        "area": 15.50
    },
    {
        "biName": "金鹰世界",
        "standardName": "南京金鹰世界",
        "projectId": "1136",
        "area": 23.00
    }
]
```

---

### 27. 更新BI项目对照

**接口**: `PUT /config/bi-projects/:projectId`

**请求体**:
```json
{
    "biName": "金鹰新街口",
    "standardName": "南京新街口",
    "area": 18.00
}
```

---

### 28. 导入人力清单

**接口**: `POST /personnel/import`

**描述**: 通过Excel导入人力清单（PRD 6.2节）

**请求**: `Content-Type: multipart/form-data`

**参数**:
| 字段 | 类型 | 说明 |
|------|------|------|
| file | File | Excel文件（.xlsx） |
| mode | string | 导入模式：replace（替换）/append（追加） |

**响应示例**:
```json
{
    "success": true,
    "imported": 156,
    "updated": 12,
    "skipped": 3,
    "errors": [
        {"row": 45, "message": "工号格式错误"}
    ]
}
```

---

## 前端筛选说明

系统采用前端筛选方案，搜索接口返回完整数据，前端实现:

### 筛选字段
- `project`: 项目名称
- `status`: 工单状态
- `keyword`: 关键词(匹配工单号、发起人)

### 排序字段
- `id`: 工单号
- `initiator`: 发起人
- `createTime`: 创建时间
- `score`: 评分

### 分页参数
- `page`: 当前页码(从1开始)
- `pageSize`: 每页条数(默认10)

## 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 401 | 未授权，请检查Token |
| 403 | 权限不足 |
| 404 | 接口不存在 |
| 500 | 服务器内部错误 |

## 调用示例

```javascript
// ========== 认证 ==========
// 登录
const loginResult = await API.request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ account: '037001', password: '***', projectId: '1118' })
});

// ========== 项目管理 ==========
// 获取项目列表
const projects = await API.request('/projects');

// 添加项目
await API.request('/projects', {
    method: 'POST',
    body: JSON.stringify({ id: '1145', name: '南京新街口', area: 18.0, outsourcingTarget: 360 })
});

// 更新项目
await API.request('/projects/1145', {
    method: 'PUT',
    body: JSON.stringify({ area: 20.0, outsourcingTarget: 400 })
});

// 删除项目
await API.request('/projects/1145', { method: 'DELETE' });

// ========== 角色管理 ==========
// 获取角色映射
const roles = await API.request('/roles');

// 添加角色映射
await API.request('/roles', {
    method: 'POST',
    body: JSON.stringify({ id: '039999', name: '王五', position: '工程师', projectId: '1118', role: '一线员工' })
});

// 更新角色
await API.request('/roles/039999', {
    method: 'PUT',
    body: JSON.stringify({ role: '部门管理' })
});

// 删除角色
await API.request('/roles/039999', { method: 'DELETE' });

// ========== KPI配置 ==========
// 获取KPI配置
const kpiConfig = await API.request('/config/kpi');

// 保存KPI配置
await API.request('/config/kpi', {
    method: 'POST',
    body: JSON.stringify(kpiConfig)
});

// ========== 业务数据 ==========
// 获取统计数据
const stats = await API.request('/dashboard/stats');

// 获取工单列表
const tickets = await API.request('/tickets/search');

// 获取人力清单
const personnel = await API.request('/personnel/list');

// 获取同步状态
const syncStatus = await API.request('/sync/status');
```

## 接口权限要求

| 接口 | 所需角色 | 说明 |
|------|----------|------|
| POST /auth/login | 无需登录 | 登录获取Token |
| GET /projects | 任意已登录用户 | 查看项目列表 |
| POST /projects | 系统管理员 | 创建新项目 |
| PUT /projects/:id | 系统管理员 | 修改项目 |
| DELETE /projects/:id | 系统管理员 | 删除项目 |
| GET /roles | 项目负责人/管理员 | 查看角色映射 |
| POST /roles | 项目负责人/管理员 | 添加角色映射 |
| PUT /roles/:id | 项目负责人/管理员 | 修改角色 |
| DELETE /roles/:id | 项目负责人/管理员 | 删除角色 |
| GET /config/kpi | 项目负责人/管理员 | 查看KPI配置 |
| POST /config/kpi | 项目负责人/管理员 | 保存KPI配置 |
| GET /config/thresholds | 项目负责人/管理员 | 查看预警阈值 |
| POST /config/thresholds | 项目负责人/管理员 | 保存预警阈值 |
| GET /config/management-positions | 系统管理员 | 查看管理层岗位 |
| POST /config/management-positions | 系统管理员 | 更新管理层岗位 |
| GET /config/bi-projects | 系统管理员 | 查看BI项目对照 |
| PUT /config/bi-projects/:id | 系统管理员 | 更新BI项目对照 |
| GET /dashboard/stats | 任意已登录用户 | 查看统计数据（自动过滤项目） |
| GET /tickets/search | 任意已登录用户 | 搜索工单（自动过滤项目） |
| GET /personnel/list | 任意已登录用户 | 查看人力清单（自动过滤项目） |
| POST /personnel/import | 项目负责人/管理员 | 导入人力清单 |
| GET /stats/initiation-by-level | 任意已登录用户 | 四层级统计 |
| GET /stats/warnings | 任意已登录用户 | 预警清单 |
| GET /stats/completion | 任意已登录用户 | 完成情况 |
| GET /stats/score | 任意已登录用户 | 综合评分 |
| GET /sync/status | 任意已登录用户 | 查看同步状态 |
| POST /sync/trigger | 项目负责人/管理员 | 触发数据同步 |
| GET /sync/history | 任意已登录用户 | 查看同步历史 |

## 接口汇总

### 认证
| 序号 | 接口 | 方法 | 说明 |
|------|------|------|------|
| 1 | /auth/login | POST | 用户登录 |

### 项目管理
| 序号 | 接口 | 方法 | 说明 |
|------|------|------|------|
| 2 | /projects | GET | 获取项目列表 |
| 3 | /projects | POST | 添加项目 |
| 4 | /projects/:id | PUT | 更新项目 |
| 5 | /projects/:id | DELETE | 删除项目 |

### 角色管理
| 序号 | 接口 | 方法 | 说明 |
|------|------|------|------|
| 6 | /roles | GET | 获取角色映射 |
| 7 | /roles | POST | 添加角色映射 |
| 8 | /roles/:id | PUT | 更新角色映射 |
| 9 | /roles/:id | DELETE | 删除角色映射 |

### KPI配置
| 序号 | 接口 | 方法 | 说明 |
|------|------|------|------|
| 10 | /config/kpi | GET | 获取KPI配置 |
| 11 | /config/kpi | POST | 保存KPI配置 |
| 12 | /config/thresholds | GET | 获取预警阈值 |
| 13 | /config/thresholds | POST | 保存预警阈值 |
| 14 | /config/management-positions | GET | 获取管理层岗位 |
| 15 | /config/management-positions | POST | 更新管理层岗位 |
| 16 | /config/bi-projects | GET | 获取BI项目对照 |
| 17 | /config/bi-projects/:id | PUT | 更新BI项目对照 |

### 业务数据
| 序号 | 接口 | 方法 | 说明 |
|------|------|------|------|
| 18 | /dashboard/stats | GET | 驾驶舱统计 |
| 19 | /tickets/search | GET | 工单搜索 |
| 20 | /personnel/list | GET | 人力清单 |
| 21 | /personnel/import | POST | 导入人力清单(Excel) |

### KPI统计
| 序号 | 接口 | 方法 | 说明 |
|------|------|------|------|
| 22 | /stats/initiation-by-level | GET | 四层级发起统计 |
| 23 | /stats/warnings | GET | 预警清单 |
| 24 | /stats/completion | GET | 完成情况统计 |
| 25 | /stats/score | GET | 综合评分 |

### 数据同步
| 序号 | 接口 | 方法 | 说明 |
|------|------|------|------|
| 26 | /sync/status | GET | 同步状态 |
| 27 | /sync/trigger | POST | 触发同步 |
| 28 | /sync/history | GET | 同步历史 |

## 注意事项

1. **认证**: 除登录接口外，所有接口需在请求头携带 `Authorization: Bearer {token}`
2. **时间格式**: 所有时间字段统一使用北京时间(CST)，格式 `YYYY-MM-DD HH:mm:ss`
3. **工单号格式**: `WP-YYYYMMDD-NNN`
4. **分页**: 工单和人力列表建议每页10-20条
5. **权限控制**: 
   - 项目负责人: 可查看所有数据，管理本项目配置
   - 部门管理: 可查看部门数据，管理角色映射
   - 普通员工: 仅查看个人相关数据
