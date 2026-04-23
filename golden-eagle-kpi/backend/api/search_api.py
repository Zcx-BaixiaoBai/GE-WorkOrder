"""金鹰工单KPI管理 - API路由：综合搜索"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from backend.database import get_db
from backend.models.personnel import Personnel
from backend.models.work_ticket import WorkTicket

router = APIRouter(prefix="/api/search", tags=["搜索"])


@router.get("")
def global_search(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    projectId: int = Query(None),
    db: Session = Depends(get_db),
):
    """
    综合搜索：工单 + 人员
    前端调用: GET /api/search?q=关键词&projectId=1
    """
    results = {"tickets": [], "personnel": [], "total": 0}

    # 搜索工单（工单号、发起人姓名、工号）
    ticket_query = db.query(
        WorkTicket.ticket_no,
        WorkTicket.source,
        WorkTicket.order_status,
        WorkTicket.initiator_name,
        WorkTicket.create_time,
    )
    if projectId:
        ticket_query = ticket_query.filter(WorkTicket.project_id == projectId)

    ticket_query = ticket_query.filter(
        or_(
            WorkTicket.ticket_no.contains(q),
            func.ifnull(WorkTicket.initiator_name, "").contains(q),
            WorkTicket.initiator_id.contains(q),
        )
    )
    tickets = ticket_query.limit(20).all()
    results["tickets"] = [
        {
            "id": t.ticket_no,
            "type": t.source or "随手拍",
            "status": t.order_status,
            "initiator": t.initiator_name or "",
            "createTime": str(t.create_time) if t.create_time else "",
        }
        for t in tickets
    ]

    # 搜索人员（工号、姓名）
    person_query = db.query(
        Personnel.employee_id,
        Personnel.name,
        Personnel.role,
    )
    if projectId:
        person_query = person_query.filter(Personnel.project_id == projectId)

    person_query = person_query.filter(
        or_(
            Personnel.employee_id.contains(q),
            Personnel.name.contains(q),
        )
    )
    persons = person_query.limit(20).all()
    results["personnel"] = [
        {
            "id": p.employee_id,
            "name": p.name,
            "role": p.role,
        }
        for p in persons
    ]

    results["total"] = len(results["tickets"]) + len(results["personnel"])
    return results
