"""金鹰工单KPI管理 - API路由：IPMS设备管理查询"""
from fastapi import APIRouter, Depends, Query, Header, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, Integer
from backend.database import get_db
from backend.models.ipms_task import IPMSTask
from backend.services.auth_service import AuthService
from backend.models.project import Project
import jwt
from backend.config import AppConfig

router = APIRouter(prefix="/api/ipms", tags=["IPMS设备"])


def _extract_project_id(request: Request, projectId: int = None) -> int | None:
    """从query参数或token中提取project_id，query参数优先"""
    if projectId is not None:
        return projectId
    if request is None:
        return None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, AppConfig.JWT_SECRET, algorithms=[AppConfig.JWT_ALGORITHM])
            return payload.get("project_id")
        except Exception:
            pass
    return None


@router.get("/tasks")
def get_tasks(
    request: Request,
    project_name: str = Query(None, description="项目名称（模糊匹配）"),
    task_type: str = Query(None, description="任务类型 patrol/maintain"),
    task_state_name: str = Query(None, description="任务状态"),
    user_name: str = Query(None, description="巡检人员"),
    start_date: str = Query(None, description="开始日期筛选 YYYY-MM-DD"),
    end_date: str = Query(None, description="结束日期筛选 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    projectId: int = Query(None, description="项目ID"),
    db: Session = Depends(get_db),
):
    """IPMS任务列表（支持筛选分页，按项目过滤）"""
    effective_project_id = _extract_project_id(request, projectId)
    q = db.query(IPMSTask)

    # 按项目过滤（query参数 > token > project_name模糊）
    if effective_project_id:
        proj = db.query(Project).filter(Project.id == effective_project_id).first()
        if proj:
            q = q.filter(IPMSTask.project_name == proj.name)
    elif project_name:
        q = q.filter(IPMSTask.project_name.contains(project_name))
    if task_type:
        q = q.filter(IPMSTask.task_type == task_type)
    if task_state_name:
        q = q.filter(IPMSTask.task_state_name == task_state_name)
    if user_name:
        q = q.filter(IPMSTask.user_name.contains(user_name))
    if start_date:
        q = q.filter(IPMSTask.start_time >= start_date)
    if end_date:
        q = q.filter(IPMSTask.end_time <= end_date + " 23:59:59")

    total = q.count()
    rows = q.order_by(IPMSTask.end_time.desc()) \
             .offset((page - 1) * page_size) \
             .limit(page_size) \
             .all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [r.to_dict() for r in rows],
    }


@router.get("/stats")
def get_ipms_stats(
    request: Request,
    task_type: str = Query(None, description="任务类型 patrol/maintain"),
    task_state_name: str = Query(None, description="任务原始状态"),
    start_date: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(None, description="结束日期 YYYY-MM-DD"),
    projectId: int = Query(None, description="项目ID"),
    db: Session = Depends(get_db),
):
    """IPMS任务统计概览（4种状态实时计算，支持按项目/类型/原始状态/日期筛选）"""
    from datetime import datetime, timedelta
    from sqlalchemy import extract

    effective_project_id = _extract_project_id(request, projectId)
    now = datetime.now()
    
    # 构建基础查询（用于计数）
    def base_query():
        q = db.query(IPMSTask)
        if effective_project_id:
            proj = db.query(Project).filter(Project.id == effective_project_id).first()
            if proj:
                q = q.filter(IPMSTask.project_name == proj.name)
        if task_type:
            q = q.filter(IPMSTask.task_type == task_type)
        if task_state_name:
            q = q.filter(IPMSTask.task_state_name == task_state_name)
        if start_date:
            q = q.filter(IPMSTask.start_time >= start_date)
        if end_date:
            q = q.filter(IPMSTask.end_time <= end_date + " 23:59:59")
        return q
    
    # 使用SQL直接统计，避免加载所有记录到内存
    # 已完成：状态为"完成"或"审核关闭"
    finished = base_query().filter(
        IPMSTask.task_state_name.in_(["完成", "审核关闭"])
    ).count()
    
    # 已逾期：状态为"过期"
    overdue = base_query().filter(
        IPMSTask.task_state_name == "过期"
    ).count()
    
    # 今日新增：当日开始的任务（start_time.date == today）
    today_new = base_query().filter(
        IPMSTask.start_time != None,
        extract('year', IPMSTask.start_time) == now.year,
        extract('month', IPMSTask.start_time) == now.month,
        extract('day', IPMSTask.start_time) == now.day,
    ).count()
    
    # 进行中：其他未完成且未过期的任务
    in_progress = base_query().filter(
        ~IPMSTask.task_state_name.in_(["完成", "审核关闭", "过期"])
    ).count()
    
    # 总数
    total = base_query().count()
    
    # 按类型统计
    type_stats = base_query().with_entities(
        IPMSTask.task_type,
        func.count(IPMSTask.id).label("total"),
    ).group_by(IPMSTask.task_type).all()
    type_map = {s.task_type: s.total for s in type_stats}

    # 按项目（如果未按项目过滤）
    if effective_project_id:
        project_stats = []
    else:
        # 使用 base_query() 确保应用相同的过滤条件（包括 task_type）
        project_stats = base_query().with_entities(
            IPMSTask.project_name,
            func.count(IPMSTask.id).label("total"),
        ).group_by(IPMSTask.project_name).all()

    return {
        "total": total,
        "today_new": today_new,
        "in_progress": in_progress,
        "finished": finished,
        "overdue": overdue,
        "patrol_count": type_map.get("patrol", 0),
        "maintain_count": type_map.get("maintain", 0),
        "by_project": [{"project_name": p[0] or "未知", "total": p[1]} for p in project_stats],
    }


def _compute_ipms_state(r, now, today_15h):
    """
    实时计算IPMS任务状态（四态）：
    - 今日新增：当日开始的任务
    - 进行中：未完成且未过期的任务
    - 已完成：已完成或审核关闭的任务
    - 已逾期：原始状态为"过期"的任务
    """
    if r is None:
        return "未知"
    
    # 判断是否已逾期（end_time已过）
    is_overdue = r.end_time and now > r.end_time
    
    # 已完成或审核关闭
    if r.task_state_name in ("完成", "审核关闭"):
        return "已完成"
    
    # 已逾期（原始状态为"过期"）
    if r.task_state_name == "过期" or is_overdue:
        return "已逾期"
    
    # 进行中：未完成且未逾期
    return "进行中"


def _is_today_new(r, now):
    """判断是否为今日新增（当日开始的任务）"""
    return r.start_time and r.start_time.date() == now.date()


@router.get("/warnings")
def get_ipms_warnings(
    request: Request,
    projectId: int = Query(None, description="项目ID"),
    db: Session = Depends(get_db),
):
    """IPMS预警列表（超时未完成，按项目过滤）"""
    from datetime import datetime, timedelta

    effective_project_id = _extract_project_id(request, projectId)
    q = db.query(IPMSTask)
    # 按项目过滤
    if effective_project_id:
        proj = db.query(Project).filter(Project.id == effective_project_id).first()
        if proj:
            q = q.filter(IPMSTask.project_name == proj.name)

    threshold = datetime.now() - timedelta(days=7)

    rows = q.filter(
        IPMSTask.task_state_name.in_(["未完成", "过期", "未派单"]),
        IPMSTask.end_time < threshold,
    ).order_by(IPMSTask.end_time.asc()).limit(100).all()

    return {
        "items": [r.to_dict() for r in rows],
        "total": len(rows),
    }


@router.get("/persons")
def get_ipms_persons(
    request: Request,
    project_name: str = Query(None),
    projectId: int = Query(None, description="项目ID"),
    db: Session = Depends(get_db),
):
    """IPMS人员绩效（按项目过滤）"""
    effective_project_id = _extract_project_id(request, projectId)
    q = db.query(
        IPMSTask.user_name,
        IPMSTask.task_type,
        func.count(IPMSTask.id).label("total"),
        func.avg(IPMSTask.working_time).label("avg_working_time"),
    ).filter(IPMSTask.user_name.isnot(None))

    # 按项目过滤（query参数 > token > project_name模糊）
    if effective_project_id:
        proj = db.query(Project).filter(Project.id == effective_project_id).first()
        if proj:
            q = q.filter(IPMSTask.project_name == proj.name)
    elif project_name:
        q = q.filter(IPMSTask.project_name.contains(project_name))

    rows = q.group_by(IPMSTask.user_name, IPMSTask.task_type).all()

    # 按人员汇总
    person_map = {}
    for r in rows:
        name = r.user_name or "未知"
        if name not in person_map:
            person_map[name] = {"person_name": name, "patrol": 0, "maintain": 0, "total": 0}
        person_map[name][r.task_type] = r.total
        person_map[name]["total"] += r.total

    items = list(person_map.values())
    items.sort(key=lambda x: x["total"], reverse=True)
    return {"items": items, "total": len(items)}
