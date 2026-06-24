"""金鹰工单KPI管理 - 模型：项目负责人"""
from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.database import Base


class ProjectManager(Base):
    """项目负责人表"""
    __tablename__ = "projects_manager_list"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False, index=True)
    manager_name = Column(String(50), nullable=False)
    
    # 关系
    project = relationship("Project", back_populates="manager_list")
    
    __table_args__ = (
        UniqueConstraint('project_id', name='uix_project_manager'),
    )
