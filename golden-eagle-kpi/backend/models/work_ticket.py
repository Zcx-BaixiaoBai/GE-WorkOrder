"""金鹰工单KPI管理 - 工单明细模型"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.database import Base


class WorkTicket(Base):
    __tablename__ = "work_tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_no = Column(String(50), nullable=False, unique=True, comment="工单编号")
    project_name = Column(String(100), nullable=False, comment="BI项目名称（原始值）")
    standard_name = Column(String(100), comment="标准项目名称（映射后）")
    project_id = Column(Integer, ForeignKey("projects.id"), comment="关联标准项目")
    order_type = Column(String(50), comment="工单类型")
    order_status = Column(String(20), comment="工单状态")
    initiator_id = Column(String(10), nullable=True, comment="发起人工号（随手拍有，detail表无）")
    initiator_name = Column(String(50), comment="发起人姓名")
    create_time = Column(DateTime, comment="创建时间")
    accept_time = Column(DateTime, comment="接单时间")
    complete_time = Column(DateTime, comment="完工时间")
    deadline = Column(DateTime, comment="规定时限")
    area_name = Column(String(50), comment="区域")
    description = Column(Text, comment="工单描述")
    sync_batch_id = Column(Integer, ForeignKey("sync_logs.id"), comment="同步批次")

    # 新增字段（用于区分工单来源）
    source = Column(String(20), default="bi", comment="数据来源: bi/snapshot/repair")
    ticket_type = Column(String(50), comment="问题类型")
    brand = Column(String(100), comment="品牌字段（随手拍/秩序报修/保洁报修/商户名等）")
    handler_id = Column(String(10), comment="处理人工号")
    handler_name = Column(String(50), comment="处理人姓名")
    status = Column(String(20), comment="工单状态")

    # 注意: is_completed, is_timely, process_days 是数据库生成列，不要在ORM中映射
    # 它们会根据 order_status, complete_time, deadline 自动计算

    created_at = Column(DateTime, default=lambda: __import__("datetime").datetime.now())
    updated_at = Column(DateTime, default=lambda: __import__("datetime").datetime.now(), onupdate=lambda: __import__("datetime").datetime.now())

    # 生成列在SQLite中通过DDL实现，ORM层不映射
    # is_completed, is_timely, process_days 由数据库生成列自动计算

    project = relationship("Project", back_populates="tickets")

    __table_args__ = (
        Index("idx_tickets_project", "project_id"),
        Index("idx_tickets_initiator", "initiator_id"),
        Index("idx_tickets_create_time", "create_time"),
        Index("idx_tickets_status", "order_status"),
        Index("idx_tickets_sync_batch", "sync_batch_id"),
        Index("idx_tickets_brand", "brand"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "ticket_no": self.ticket_no,
            "project_name": self.project_name,
            "standard_name": self.standard_name,
            "project_id": self.project_id,
            "order_type": self.order_type,
            "order_status": self.order_status,
            "initiator_id": self.initiator_id,
            "initiator_name": self.initiator_name,
            "create_time": self.create_time.isoformat() if self.create_time else None,
            "accept_time": self.accept_time.isoformat() if self.accept_time else None,
            "complete_time": self.complete_time.isoformat() if self.complete_time else None,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "area_name": self.area_name,
            "description": self.description,
            "brand": self.brand,
            "handler_id": self.handler_id,
            "handler_name": self.handler_name,
        }
