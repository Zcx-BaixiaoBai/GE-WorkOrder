"""金鹰工单KPI管理 - 随手拍工单模型"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.database import Base


class Snapshot(Base):
    __tablename__ = "snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_no = Column(String(50), nullable=False, unique=True, comment="工单编号")
    project_name = Column(String(100), nullable=False, comment="BI项目名称")
    standard_name = Column(String(100), comment="标准项目名称")
    project_id = Column(Integer, ForeignKey("projects.id"), comment="关联标准项目")
    order_type = Column(String(50), comment="工单类型")
    order_status = Column(String(20), comment="工单状态")
    initiator_id = Column(String(10), nullable=False, comment="发起人工号")
    initiator_name = Column(String(50), comment="发起人姓名")
    handler_id = Column(String(10), comment="处理人工号")
    handler_name = Column(String(50), comment="处理人姓名")
    create_time = Column(DateTime, comment="创建时间")
    accept_time = Column(DateTime, comment="接单时间")
    complete_time = Column(DateTime, comment="完工时间")
    deadline = Column(DateTime, comment="规定时限")
    area_name = Column(String(50), comment="区域")
    description = Column(Text, comment="工单描述")
    photo_count = Column(Integer, default=0, comment="照片数")
    source = Column(String(20), default="snapshot", comment="数据来源: snapshot")
    sync_batch_id = Column(Integer, ForeignKey("sync_logs.id"), comment="同步批次")
    created_at = Column(DateTime, default=lambda: __import__("datetime").datetime.now())
    updated_at = Column(DateTime, default=lambda: __import__("datetime").datetime.now(), onupdate=lambda: __import__("datetime").datetime.now())

    project = relationship("Project", back_populates="snapshots")

    __table_args__ = (
        Index("idx_snapshots_project", "project_id"),
        Index("idx_snapshots_initiator", "initiator_id"),
        Index("idx_snapshots_create_time", "create_time"),
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
            "handler_id": self.handler_id,
            "handler_name": self.handler_name,
            "create_time": self.create_time.isoformat() if self.create_time else None,
            "complete_time": self.complete_time.isoformat() if self.complete_time else None,
            "photo_count": self.photo_count,
        }
