"""金鹰工单KPI管理 - 项目配置模型"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import relationship
from backend.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, comment="标准项目名称")
    bi_names = Column(Text, comment="BI项目名列表（JSON数组）")
    area = Column(Float, comment="项目面积（㎡）")
    outsourcing_target = Column(Float, comment="外包编制=面积×20")
    manager_id = Column(String(10), comment="项目负责人工号")
    manager_name = Column(String(50), comment="项目负责人姓名")
    kpi_completion_rate = Column(Float, default=95.0, comment="KPI完成率目标(%)")
    kpi_timely_rate = Column(Float, default=90.0, comment="KPI及时率目标(%)")
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=lambda: __import__("datetime").datetime.now())
    updated_at = Column(DateTime, default=lambda: __import__("datetime").datetime.now(), onupdate=lambda: __import__("datetime").datetime.now())

    # 关系
    tickets = relationship("WorkTicket", back_populates="project")
    snapshots = relationship("Snapshot", back_populates="project")
    personnel = relationship("Personnel", back_populates="project")
    manager_list = relationship("ProjectManager", back_populates="project")

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "biNames": self.bi_names,
            "area": self.area,
            "outsourcingTarget": self.outsourcing_target or (self.area * 20 if self.area else None),
            "managerId": self.manager_id,
            "managerName": self.manager_name,
            "kpiCompletionRate": self.kpi_completion_rate,
            "kpiTimelyRate": self.kpi_timely_rate,
            "status": self.status,
        }
