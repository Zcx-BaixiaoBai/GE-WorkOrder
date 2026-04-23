"""金鹰工单KPI管理 - API路由：工单"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from backend.database import get_db
from backend.services.ticket_service import TicketService

router = APIRouter(prefix="/api/tickets", tags=["工单"])


def _parse_list(v: Optional[str]) -> Optional[List[str]]:
    if not v:
        return None
    return [x.strip() for x in v.split(',') if x.strip()]


@router.get("")
def list_tickets(
    projectId: int = Query(None),
    status: str = Query(None),
    keyword: str = Query(None),
    startDate: str = Query(None),
    endDate: str = Query(None),
    source: str = Query(None),
    month: str = Query(None),
    ticketType: str = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100000),
    db: Session = Depends(get_db),
):
    """工单列表（分页）"""
    return TicketService.search_tickets(
        project_id=projectId,
        status=_parse_list(status),
        keyword=keyword,
        start_date=startDate,
        end_date=endDate,
        source=source,
        month=month,
        ticket_type=_parse_list(ticketType),
        page=page,
        page_size=pageSize,
        db=db,
    )


@router.get("/search")
def search_tickets(
    projectId: int = Query(None),
    status: str = Query(None),
    keyword: str = Query(None),
    startDate: str = Query(None),
    endDate: str = Query(None),
    source: str = Query(None),
    month: str = Query(None),
    ticketType: str = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100000),
    db: Session = Depends(get_db),
):
    """搜索工单列表"""
    return TicketService.search_tickets(
        project_id=projectId,
        status=_parse_list(status),
        keyword=keyword,
        start_date=startDate,
        end_date=endDate,
        source=source,
        month=month,
        ticket_type=_parse_list(ticketType),
        page=page,
        page_size=pageSize,
        db=db,
    )


@router.get("/overdue/list")
def get_overdue_tickets(
    projectId: int = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """获取逾期工单"""
    return TicketService.get_overdue_tickets(projectId, page, pageSize, db)


# ⚠️ 注意：/{ticket_id} 必须放在 /search 和 /overdue/list 之后
# 因为 FastAPI 按定义顺序匹配，参数路由会"吞掉"精确路径
@router.get("/{ticket_id}")
def get_ticket_detail(ticket_id: str, db: Session = Depends(get_db)):
    """获取工单详情"""
    result = TicketService.get_ticket_detail(ticket_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="工单不存在")
    return result
