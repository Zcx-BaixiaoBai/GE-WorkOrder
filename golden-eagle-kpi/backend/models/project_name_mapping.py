"""金鹰工单KPI管理 - BI项目名称对照模型"""
from sqlalchemy import Column, Integer, String, ForeignKey
from backend.database import Base


class ProjectNameMapping(Base):
    __tablename__ = "project_name_mapping"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bi_name = Column(String(100), nullable=False, comment="BI系统/人力库中的项目名")
    standard_name = Column(String(100), nullable=False, comment="标准项目名")
    project_id = Column(Integer, ForeignKey("projects.id"))
    source = Column(String(10), default="bi", comment="来源: bi/hr")

    def to_dict(self):
        return {
            "id": self.id,
            "biName": self.bi_name,
            "standardName": self.standard_name,
            "projectId": str(self.project_id) if self.project_id else None,
            "source": self.source or "bi",
        }
