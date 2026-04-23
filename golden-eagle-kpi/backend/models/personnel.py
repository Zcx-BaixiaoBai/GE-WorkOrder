"""金鹰工单KPI管理 - 人力清单模型"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.database import Base


class Personnel(Base):
    __tablename__ = "personnel"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String(10), nullable=False, unique=True, comment="工号（补零后）")
    name = Column(String(50), nullable=False, comment="姓名")
    project_id = Column(Integer, ForeignKey("projects.id"), comment="所属项目")
    role = Column(String(50), comment="角色（主管/领班/保洁等）")
    is_outsourcing = Column(Integer, default=0, comment="是否外包人员")
    phone = Column(String(20), comment="手机号")
    entry_date = Column(String(20), comment="入职日期")
    status = Column(String(20), default="在职", comment="在职/离职")
    created_at = Column(DateTime, default=lambda: __import__("datetime").datetime.now())
    updated_at = Column(DateTime, default=lambda: __import__("datetime").datetime.now(), onupdate=lambda: __import__("datetime").datetime.now())

    project = relationship("Project", back_populates="personnel")

    __table_args__ = (
        Index("idx_personnel_project", "project_id"),
        Index("idx_personnel_role", "role"),
    )

    def to_dict(self):
        return {
            "id": self.employee_id,
            "name": self.name,
            "projectId": str(self.project_id) if self.project_id else None,
            "role": self.role,
            "isOutsourcing": bool(self.is_outsourcing),
            "phone": self.phone,
            "entryDate": self.entry_date,
            "status": self.status,
        }
