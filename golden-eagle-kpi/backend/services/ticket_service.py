"""金鹰工单KPI管理 - 工单查询服务"""
from datetime import datetime
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session
from backend.models.work_ticket import WorkTicket
from backend.models.project import Project


class TicketService:
    """工单查询、过滤、聚合"""

    @staticmethod
    def search_tickets(
        project_id: int = None,
        status: list = None,
        keyword: str = None,
        start_date: str = None,
        end_date: str = None,
        source: str = None,
        month: str = None,
        ticket_type: list = None,
        page: int = 1,
        page_size: int = 10,
        db: Session = None,
    ) -> dict:
        """搜索工单列表"""
        query = db.query(WorkTicket)

        # 项目过滤（支持单个int或多个int的list）
        if project_id:
            if isinstance(project_id, list):
                query = query.filter(WorkTicket.project_id.in_(project_id))
            else:
                query = query.filter(WorkTicket.project_id == project_id)

        # 来源过滤
        if source:
            query = query.filter(WorkTicket.source == source)

        # 月份过滤
        if month:
            query = query.filter(
                func.strftime('%Y-%m', WorkTicket.create_time) == month
            )

        # 状态过滤（支持多选：传入状态key列表）
        if status:
            status_map = {
                "pending": ["待处理", "未解决"],
                "processing": ["处理中"],
                "auditing": ["待审核"],
                "completed": ["已完成", "已关闭", "已解决", "已评分"],
                "closed": ["已关闭"],
            }
            all_cn = []
            for s in status:
                all_cn.extend(status_map.get(s, [s]))
            query = query.filter(WorkTicket.order_status.in_(all_cn))

        # 工单类型过滤（支持多选）
        if ticket_type:
            query = query.filter(WorkTicket.ticket_type.in_(ticket_type))

        # 关键词搜索
        if keyword:
            query = query.filter(
                or_(
                    WorkTicket.ticket_no.contains(keyword),
                    WorkTicket.initiator_name.contains(keyword),
                    WorkTicket.initiator_id.contains(keyword),
                )
            )

        # 日期范围
        if start_date:
            query = query.filter(WorkTicket.create_time >= start_date)
        if end_date:
            query = query.filter(WorkTicket.create_time <= end_date + " 23:59:59")

        # 统计总数
        total = query.count()

        # 分页
        offset = (page - 1) * page_size
        items = query.order_by(WorkTicket.create_time.desc()).offset(offset).limit(page_size).all()

        # 获取项目名称映射
        project_names = {}
        for p in db.query(Project).all():
            project_names[p.id] = p.name

        # 批量获取处理人姓名（避免N+1查询）
        handler_ids = set(t.handler_id for t in items if t.handler_id)
        handler_names = {}
        if handler_ids:
            from backend.models.personnel import Personnel
            for p in db.query(Personnel).filter(Personnel.employee_id.in_(handler_ids)).all():
                handler_names[p.employee_id] = p.name

        return {
            "total": total,
            "page": page,
            "pageSize": page_size,
            "projectId": str(project_id) if project_id else None,
            "items": [
                {
                    "id": t.ticket_no,
                    "dbId": t.id,
                    "projectId": str(t.project_id) if t.project_id else None,
                    "projectName": project_names.get(t.project_id, t.project_name),
                    "ticketType": t.ticket_type or t.order_type,
                    "creator": t.initiator_name,
                    "creatorId": t.initiator_id,
                    "createTime": t.create_time.strftime("%Y-%m-%d %H:%M:%S") if t.create_time else None,
                    "deadline": t.deadline.strftime("%Y-%m-%d %H:%M:%S") if t.deadline else None,
                    "status": _map_status(t.order_status),
                    "statusText": t.order_status,  # 直接用中文显示
                    "statusClass": _get_status_class(t.order_status),
                    "completeTime": t.complete_time.strftime("%Y-%m-%d %H:%M:%S") if t.complete_time else None,
                    "handler": t.handler_name or (handler_names.get(t.handler_id) if t.handler_id else None),
                    "description": t.description[:100] if t.description else None,
                }
                for t in items
            ],
        }

    @staticmethod
    def get_ticket_detail(ticket_no: str, db: Session) -> dict | None:
        """获取工单详情"""
        ticket = db.query(WorkTicket).filter(WorkTicket.ticket_no == ticket_no).first()
        if not ticket:
            return None
        # 查找处理人姓名
        handler_name = None
        if ticket.handler_id:
            from backend.models.personnel import Personnel
            p = db.query(Personnel).filter(Personnel.employee_id == ticket.handler_id).first()
            handler_name = p.name if p else None
        order_status = ticket.order_status or "处理中"
        return {
            "id": ticket.ticket_no,
            "dbId": ticket.id,
            "projectId": str(ticket.project_id) if ticket.project_id else None,
            "projectName": ticket.project_name or "",
            "ticketType": ticket.ticket_type or ticket.order_type,
            "creator": ticket.initiator_name,
            "creatorId": ticket.initiator_id,
            "handler": ticket.handler_name or handler_name,
            "handlerId": ticket.handler_id,
            "createTime": ticket.create_time.strftime("%Y-%m-%d %H:%M:%S") if ticket.create_time else None,
            "deadline": ticket.deadline.strftime("%Y-%m-%d %H:%M:%S") if ticket.deadline else None,
            "completeTime": ticket.complete_time.strftime("%Y-%m-%d %H:%M:%S") if ticket.complete_time else None,
            "orderStatus": order_status,
            "statusText": order_status,
            "statusClass": _get_status_class(order_status),
            "description": ticket.description,
            "processDays": ticket.process_days if hasattr(ticket, 'process_days') and ticket.process_days else None,
        }

    @staticmethod
    def get_overdue_tickets(project_id: int, page: int, page_size: int, db: Session) -> dict:
        """获取逾期工单"""
        # 逾期：已到期(deadline < now) 且 未完成(order_status不在完成列表)
        query = db.query(WorkTicket).filter(
            WorkTicket.order_status.notin_(["已完成", "已关闭", "已解决", "已评分"]),
            WorkTicket.deadline < datetime.now(),
        )
        if project_id:
            query = query.filter(WorkTicket.project_id == project_id)

        total = query.count()
        offset = (page - 1) * page_size
        items = query.offset(offset).limit(page_size).all()

        # 获取项目名称映射
        project_names = {}
        for p in db.query(Project).all():
            project_names[p.id] = p.name

        return {
            "total": total,
            "page": page,
            "pageSize": page_size,
            "items": [
                {
                    "id": t.ticket_no,
                    "dbId": t.id,
                    "projectId": str(t.project_id) if t.project_id else None,
                    "projectName": project_names.get(t.project_id, t.project_name),
                    "ticketType": t.ticket_type or t.order_type,
                    "creator": t.initiator_name,
                    "creatorId": t.initiator_id,
                    "createTime": t.create_time.strftime("%Y-%m-%d %H:%M:%S") if t.create_time else None,
                    "deadline": t.deadline.strftime("%Y-%m-%d %H:%M:%S") if t.deadline else None,
                    "status": _map_status(t.order_status),
                    "statusText": t.order_status,  # 原始中文状态显示
                    "statusClass": _get_status_class(t.order_status),
                    "completeTime": t.complete_time.strftime("%Y-%m-%d %H:%M:%S") if t.complete_time else None,
                    "handler": None,
                    "description": t.description[:100] if t.description else None,
                }
                for t in items
            ],
        }


def _map_status(cn_status: str) -> str:
    """中文状态→英文状态"""
    mapping = {
        "待处理": "pending",
        "处理中": "processing",
        "待审核": "auditing",
        "已完成": "completed",
        "已关闭": "closed",
        "已解决": "completed",   # 工单明细表/随手拍的"当前节点"
        "未解决": "pending",
        "已评分": "completed",
    }
    return mapping.get(cn_status, cn_status)


def _get_status_class(order_status: str) -> str:
    """获取状态CSS类名"""
    completed = ["已完成", "已关闭", "已解决", "已评分"]
    pending = ["待派单", "待接单", "处理中", "已派遣", "待审核", "待处理"]
    if order_status in completed:
        return "tag-green"
    if order_status in pending:
        return "tag-yellow"
    if order_status == "已退回":
        return "tag-red"
    return "tag-gray"
