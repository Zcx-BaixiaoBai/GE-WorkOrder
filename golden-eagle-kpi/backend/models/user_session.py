"""金鹰工单KPI管理 - 用户会话模型"""
from sqlalchemy import Column, Integer, String, DateTime
from backend.database import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(64), nullable=False, unique=True)
    employee_id = Column(String(10), nullable=False)
    name = Column(String(50))
    role = Column(String(30), comment="admin / project_manager / staff")
    project_id = Column(Integer, comment="非管理员关联的项目")
    account = Column(String(100), comment="OA账号（用于爬虫认证）")
    login_at = Column(DateTime, default=lambda: __import__("datetime").datetime.now())
    expires_at = Column(DateTime)

    def to_dict(self):
        return {
            "token": self.token,
            "id": self.employee_id,
            "name": self.name,
            "role": self.role,
            "projectId": str(self.project_id) if self.project_id else None,
        }
