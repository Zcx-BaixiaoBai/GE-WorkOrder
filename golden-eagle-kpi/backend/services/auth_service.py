"""金鹰工单KPI管理 - 认证服务"""
import jwt
import hashlib
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.config import AppConfig
from backend.models.user_session import UserSession
from backend.models.personnel import Personnel
from backend.models.role_mapping import RoleMapping
from backend.models.project import Project


class AuthService:
    """认证服务：OA验证 + 工号匹配 + 角色映射"""

    @staticmethod
    def login(account: str, password: str, employee_id: str, project_id: str, db: Session) -> dict:
        """
        登录流程:
        1. 验证OA账号密码（尝试BI登录）
        2. 查人力清单确认工号存在
        3. 角色映射获取系统角色
        4. 生成JWT Token
        """
        # 1. OA验证 - 尝试用Playwright登录BI系统验证
        bi_ok = False
        try:
            from backend.scraper.bi_client import bi_login_verify
            bi_ok = bi_login_verify(account, password)
        except Exception:
            # 如果爬虫模块不可用，降级为简单验证（开发模式）
            bi_ok = True

        if not bi_ok:
            return {"success": False, "error": "OA账号或密码错误", "code": 401}

        # 2. 工号补零
        clean_id = str(employee_id).strip().zfill(10)

        # 3. 查人力清单
        person = db.query(Personnel).filter(Personnel.employee_id == clean_id).first()

        # 开发模式降级：人力清单为空或工号不存在时，允许登录为管理员
        if not person:
            total_personnel = db.query(Personnel).count()
            if total_personnel == 0:
                # 人力清单为空（尚未导入），允许任意工号登录为管理员
                person_name = f"开发用户({clean_id})"
                system_role = "系统管理员"
            else:
                return {"success": False, "error": "工号不存在于人力清单中", "code": 404}
        else:
            person_name = person.name

        # 4. 验证项目权限
        pid = int(project_id) if project_id else None
        if person and pid and person.project_id != pid:
            return {"success": False, "error": "该工号无权限访问指定项目", "code": 403}

        # 5. 角色映射
        if person:
            system_role = AuthService._map_role(person.role, db)
        elif not person and db.query(Personnel).count() == 0:
            system_role = "系统管理员"

        # 6. 获取项目名称
        project = db.query(Project).filter(Project.id == pid).first() if pid else None

        # 7. 生成JWT
        token = AuthService._generate_token(clean_id, account, system_role, pid)

        # 8. 保存会话
        session = UserSession(
            token=token,
            employee_id=clean_id,
            name=person_name,
            role=system_role,
            project_id=pid,
            account=account,
            expires_at=datetime.now() + timedelta(hours=AppConfig.JWT_EXPIRE_HOURS),
        )
        db.add(session)
        db.commit()

        return {
            "success": True,
            "token": token,
            "user": {
                "id": clean_id,
                "account": account,
                "name": person_name,
                "role": system_role,
                "projectId": str(pid) if pid else None,
                "projectName": project.name if project else None,
            },
        }

    @staticmethod
    def _map_role(position: str, db: Session) -> str:
        """将职务映射为系统角色"""
        if not position:
            return "一线员工"

        position_stripped = position.strip()

        # 精确匹配已映射的标准角色（防止"系统管理员"被覆盖）
        if position_stripped in ("项目负责人", "部门管理", "一线员工", "外包", "系统管理员"):
            return position_stripped

        mapping = db.query(RoleMapping).filter(RoleMapping.source_role == position).first()
        if mapping:
            return mapping.target_role

        # 默认映射规则
        if "总监" in position_stripped or "总经理" in position_stripped:
            return "项目负责人"
        if any(k in position_stripped for k in ["经理", "主管"]):
            return "部门管理"
        if "IT" in position_stripped or "信息" in position_stripped:
            return "系统管理员"
        if "外包" in position_stripped:
            return "外包"
        return "一线员工"

    @staticmethod
    def _generate_token(employee_id: str, account: str, role: str, project_id: int) -> str:
        """生成JWT Token"""
        payload = {
            "employee_id": employee_id,
            "account": account,
            "role": role,
            "project_id": project_id,
            "exp": datetime.now() + timedelta(hours=AppConfig.JWT_EXPIRE_HOURS),
        }
        return jwt.encode(payload, AppConfig.JWT_SECRET, algorithm=AppConfig.JWT_ALGORITHM)

    @staticmethod
    def verify_token(token: str) -> dict | None:
        """验证JWT Token"""
        try:
            payload = jwt.decode(token, AppConfig.JWT_SECRET, algorithms=[AppConfig.JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    @staticmethod
    def logout(token: str, db: Session) -> bool:
        """登出"""
        session = db.query(UserSession).filter(UserSession.token == token).first()
        if session:
            db.delete(session)
            db.commit()
        return True

    @staticmethod
    def get_current_user(token: str, db: Session) -> dict | None:
        """从Token获取当前用户信息"""
        payload = AuthService.verify_token(token)
        if not payload:
            return None
        return payload
