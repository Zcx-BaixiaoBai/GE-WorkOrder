"""金鹰工单KPI管理 - API路由：筹建专项查询"""
from fastapi import APIRouter, Depends, Query, Header, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, Integer
from backend.database import get_db
from backend.models.special_plan import SpecialPlan
from backend.services.auth_service import AuthService
from datetime import datetime

router = APIRouter(prefix="/api/wy", tags=["筹建专项"])


def get_current_project_id(authorization: str = Header(None), db: Session = Depends(get_db)) -> int | None:
    """从Token提取当前用户的project_id"""
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "").strip()
    payload = AuthService.verify_token(token)
    if not payload:
        return None
    return payload.get("project_id")


@router.get("/plans")
def get_plans(
    request: Request,
    project_name: str = Query(None, description="项目名称（模糊匹配）"),
    special_name: str = Query(None, description="专项名称（模糊匹配）"),
    plan_state: str = Query(None, description="计划状态（即将开始/进行中/即将到期/到期预警/逾期报警/已逾期/已完成/已暂停）"),
    danger_flag: int = Query(None, description="逾期标识 0/1"),
    finish_flag: int = Query(None, description="完成标识 0/1"),
    person_name: str = Query(None, description="责任人"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    projectId: int = Query(None, description="项目ID（query参数，优先于token）"),
    db: Session = Depends(get_db),
):
    """筹建专项计划列表（支持筛选分页，8种状态实时计算）"""
    from datetime import datetime, timedelta
    from backend.models.project import Project
    import jwt
    from backend.config import AppConfig

    # 优先使用query参数的projectId，其次从token提取
    effective_project_id = projectId
    if not effective_project_id:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(token, AppConfig.JWT_SECRET, algorithms=[AppConfig.JWT_ALGORITHM])
                effective_project_id = payload.get("project_id")
            except Exception:
                pass

    q = db.query(SpecialPlan)

    # 按项目过滤（query参数 > token > project_name模糊）
    if effective_project_id:
        proj = db.query(Project).filter(Project.id == effective_project_id).first()
        if proj:
            q = q.filter(SpecialPlan.project_name == proj.name)
    elif project_name:
        q = q.filter(SpecialPlan.project_name.contains(project_name))
    if special_name:
        q = q.filter(SpecialPlan.special_name.contains(special_name))
    if person_name:
        q = q.filter(SpecialPlan.person_name.contains(person_name))
    if finish_flag is not None:
        q = q.filter(SpecialPlan.finish_flag == finish_flag)
    if pause_flag := Query(None):
        pass

    # 按8种状态筛选（实时计算）
    now = datetime.now()
    in_7_days_before = now + timedelta(days=7)
    in_15_days = now + timedelta(days=15)
    in_30_days = now + timedelta(days=30)

    if plan_state:
        all_rows = q.all()
        filtered = []
        for r in all_rows:
            computed = _compute_wy_state(r, now, in_7_days_before, in_15_days, in_30_days)
            if computed == plan_state:
                filtered.append(r)
        total = len(filtered)
        rows = filtered[(page-1)*page_size : page*page_size]
        items = [r.to_dict() for r in rows]
        # 附加计算后状态
        for item in items:
            item["computed_state"] = _compute_wy_state(
                next((r for r in all_rows if r.id == item["id"]), None),
                now, in_7_days_before, in_15_days, in_30_days
            )
        return {"total": total, "page": page, "page_size": page_size, "items": items}

    total = q.count()
    rows = q.order_by(SpecialPlan.plan_end_date.asc()) \
             .offset((page - 1) * page_size) \
             .limit(page_size) \
             .all()
    items = [r.to_dict() for r in rows]
    # 附加计算后状态
    for item in items:
        r = next((row for row in rows if row.id == item["id"]), None)
        item["computed_state"] = _compute_wy_state(r, now, in_7_days_before, in_15_days, in_30_days) if r else "未知"
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def _compute_wy_state(r, now, in_7_days_before, in_15_days, in_30_days):
    """实时计算筹建专项状态"""
    if r is None:
        return "未知"
    if r.finish_flag == 1:
        return "已完成"
    if r.pause_flag == 1:
        return "已暂停"
    if r.plan_end_date is None:
        return "进行中"
    end_ts = r.plan_end_date.timestamp()
    now_ts = now.timestamp()
    if end_ts < now_ts:
        return "已逾期"
    if end_ts <= in_7_days_before.timestamp():
        return "逾期报警"
    if end_ts <= in_15_days.timestamp():
        return "到期预警"
    if end_ts <= in_30_days.timestamp():
        return "即将到期"
    # 即将开始：plan_start_date在未来（包括7天内和更远的未来）
    if r.plan_start_date:
        start_ts = r.plan_start_date.timestamp()
        if now_ts < start_ts:
            return "即将开始"
    return "进行中"


@router.get("/stats")
def get_wy_stats(
    request: Request,
    projectId: int = Query(None, description="项目ID"),
    db: Session = Depends(get_db),
):
    """筹建专项统计概览（8种状态实时计算，按项目过滤）"""
    from datetime import datetime, timedelta
    from backend.models.project import Project
    import jwt
    from backend.config import AppConfig

    # 优先query参数，其次从token提取
    effective_project_id = projectId
    if not effective_project_id:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(token, AppConfig.JWT_SECRET, algorithms=[AppConfig.JWT_ALGORITHM])
                effective_project_id = payload.get("project_id")
            except Exception:
                pass

    now = datetime.now()
    in_7_days = now + timedelta(days=7)
    in_30_days = now + timedelta(days=30)
    in_15_days = now + timedelta(days=15)
    in_7_days_before = now + timedelta(days=7)

    q = db.query(SpecialPlan)
    # 按项目过滤
    if effective_project_id:
        proj = db.query(Project).filter(Project.id == effective_project_id).first()
        if proj:
            q = q.filter(SpecialPlan.project_name == proj.name)
    rows = q.all()

    # 8种状态实时计算
    starting_soon = 0   # 即将开始：plan_start_date在7天内
    in_progress = 0    # 进行中：已过plan_start_date，未过plan_end_date，不属于其他状态
    expiring = 0        # 即将到期：距离plan_end_date ≤30天
    warning = 0         # 到期预警：距离plan_end_date ≤15天
    danger = 0          # 逾期报警：距离plan_end_date ≤7天
    overdue = 0         # 已逾期：已过plan_end_date且finish_flag≠1
    finished = 0        # 已完成：finish_flag=1
    paused = 0          # 已暂停：pause_flag=1

    for r in rows:
        if r.finish_flag == 1:
            finished += 1
            continue
        if r.pause_flag == 1:
            paused += 1
            continue

        if r.plan_end_date is None:
            in_progress += 1
            continue

        end_ts = r.plan_end_date.timestamp() if r.plan_end_date else 0
        now_ts = now.timestamp()

        # 已逾期
        if end_ts < now_ts:
            overdue += 1
            continue

        # 逾期报警：距结束≤7天
        if end_ts <= in_7_days_before.timestamp():
            danger += 1
            continue

        # 到期预警：距结束≤15天
        if end_ts <= in_15_days.timestamp():
            warning += 1
            continue

        # 即将到期：距结束≤30天
        if end_ts <= in_30_days.timestamp():
            expiring += 1
            continue

        # 即将开始：plan_start_date在未来（包括7天内和更远的未来）
        if r.plan_start_date:
            start_ts = r.plan_start_date.timestamp()
            if now_ts < start_ts:
                starting_soon += 1
                continue

        in_progress += 1

    total = len(rows)
    return {
        "total": total,
        "starting_soon": starting_soon,
        "in_progress": in_progress,
        "expiring": expiring,
        "warning": warning,
        "danger": danger,
        "overdue": overdue,
        "finished": finished,
        "paused": paused,
        "completion_rate": round(finished / total * 100, 1) if total > 0 else 0,
    }


@router.get("/warnings")
def get_wy_warnings(
    request: Request,
    level: str = Query(None, description="严重程度 warn/danger"),
    projectId: int = Query(None, description="项目ID"),
    db: Session = Depends(get_db),
):
    """筹建专项预警列表（按项目过滤）"""
    from backend.models.project import Project
    import jwt
    from backend.config import AppConfig

    # 优先query参数，其次从token提取
    effective_project_id = projectId
    if not effective_project_id:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(token, AppConfig.JWT_SECRET, algorithms=[AppConfig.JWT_ALGORITHM])
                effective_project_id = payload.get("project_id")
            except Exception:
                pass

    q = db.query(SpecialPlan).filter(
        or_(SpecialPlan.danger_flag == 1, SpecialPlan.warning_flag == 1)
    )
    # 按项目过滤
    if effective_project_id:
        proj = db.query(Project).filter(Project.id == effective_project_id).first()
        if proj:
            q = q.filter(SpecialPlan.project_name == proj.name)
    if level == "danger":
        q = q.filter(SpecialPlan.danger_flag == 1)
    elif level == "warning":
        q = q.filter(SpecialPlan.warning_flag == 1)

    rows = q.order_by(SpecialPlan.plan_end_date.asc()).limit(100).all()
    return {
        "items": [r.to_dict() for r in rows],
        "total": len(rows),
    }


@router.get("/persons")
def get_wy_persons(
    request: Request,
    project_name: str = Query(None),
    projectId: int = Query(None, description="项目ID"),
    db: Session = Depends(get_db),
):
    """筹建专项人员绩效（按项目过滤）"""
    from backend.models.project import Project
    import jwt
    from backend.config import AppConfig

    # 优先query参数，其次从token提取
    effective_project_id = projectId
    if not effective_project_id:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(token, AppConfig.JWT_SECRET, algorithms=[AppConfig.JWT_ALGORITHM])
                effective_project_id = payload.get("project_id")
            except Exception:
                pass

    q = db.query(
        SpecialPlan.person_name,
        func.count(SpecialPlan.id).label("total"),
        func.sum(func.cast(SpecialPlan.finish_flag, Integer)).label("finished"),
        func.sum(func.cast(SpecialPlan.danger_flag, Integer)).label("danger"),
        func.sum(func.cast(SpecialPlan.warning_flag, Integer)).label("warning"),
        func.avg(SpecialPlan.score).label("avg_score"),
    ).filter(SpecialPlan.person_name.isnot(None))

    # 按项目过滤（query参数 > token > project_name模糊）
    if effective_project_id:
        proj = db.query(Project).filter(Project.id == effective_project_id).first()
        if proj:
            q = q.filter(SpecialPlan.project_name == proj.name)
    elif project_name:
        q = q.filter(SpecialPlan.project_name.contains(project_name))

    rows = q.group_by(SpecialPlan.person_name).all()
    items = []
    for r in rows:
        total = r.total or 0
        finished = r.finished or 0
        items.append({
            "person_name": r.person_name or "未知",
            "total": total,
            "finished": finished,
            "in_progress": total - finished,
            "danger": r.danger or 0,
            "warning": r.warning or 0,
            "completion_rate": round(finished / total * 100, 1) if total > 0 else 0,
            "avg_score": round(float(r.avg_score or 0), 2),
        })
    items.sort(key=lambda x: x["completion_rate"])
    return {"items": items, "total": len(items)}
