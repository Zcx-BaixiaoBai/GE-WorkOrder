"""金鹰工单KPI管理 - 角色映射模型"""
from sqlalchemy import Column, Integer, String
from backend.database import Base


class RoleMapping(Base):
    __tablename__ = "role_mapping"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_role = Column(String(50), nullable=False, unique=True, comment="原始角色名/职务")
    target_role = Column(String(50), nullable=False, comment="映射后系统角色")
    category = Column(String(50), comment="角色分类")

    def to_dict(self):
        return {
            "id": self.id,
            "sourceRole": self.source_role,
            "targetRole": self.target_role,
            "category": self.category,
        }
