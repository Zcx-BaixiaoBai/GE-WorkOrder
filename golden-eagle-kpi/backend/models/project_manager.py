"""金鹰工单KPI管理 - 项目负责人清单模型"""
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base


class ProjectManager(Base):
    """项目负责人清单：每个项目的负责人姓名"""
    __tablename__ = "projects_manager_list"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, comment="项目ID")
    manager_name = Column(String(50), nullable=False, comment="负责人姓名")

    project = relationship("Project", back_populates="manager_list")

    def to_dict(self):
        return {
            "projectId": self.project_id,
            "managerName": self.manager_name,
        }
