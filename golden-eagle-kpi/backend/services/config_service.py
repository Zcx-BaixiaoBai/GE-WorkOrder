"""金鹰工单KPI管理 - 配置管理服务"""
from datetime import datetime
from sqlalchemy.orm import Session
from backend.models.project import Project
from backend.models.role_mapping import RoleMapping
from backend.models.project_name_mapping import ProjectNameMapping
from backend.models.project_manager import ProjectManager


class ConfigService:
    """系统配置：项目、角色映射、项目名称映射、KPI目标"""

    # === 项目管理 ===

    @staticmethod
    def get_projects(db: Session) -> dict:
        """获取所有项目列表"""
        import json as _json
        projects = db.query(Project).order_by(Project.id).all()
        return {
            "items": [
                {
                    "id": p.id,
                    "name": p.name,
                    "area": p.area,
                    "biNames": _json.loads(p.bi_names) if p.bi_names else [],
                    "outsourcingTarget": p.outsourcing_target or (p.area * 20 if p.area else 0),
                    "managerName": p.manager_name,
                    "kpiCompletionRate": p.kpi_completion_rate,
                    "kpiTimelyRate": p.kpi_timely_rate,
                }
                for p in projects
            ]
        }

    @staticmethod
    def create_project(data: dict, db: Session) -> dict:
        """创建项目"""
        import json as _json
        project = Project(
            name=data["name"],
            area=data.get("area"),
            outsourcing_target=data.get("outsourcingTarget") or (data.get("area", 0) * 20 if data.get("area") else None),
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        return {
            "id": project.id,
            "name": project.name,
            "area": project.area,
            "biNames": _json.loads(project.bi_names) if project.bi_names else [],
            "outsourcingTarget": project.outsourcing_target or (project.area * 20 if project.area else 0),
            "managerName": project.manager_name,
            "kpiCompletionRate": project.kpi_completion_rate,
            "kpiTimelyRate": project.kpi_timely_rate,
        }

    @staticmethod
    def update_project(project_id: int, data: dict, db: Session) -> dict | None:
        """更新项目"""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None

        if "name" in data:
            project.name = data["name"]
        if "area" in data:
            project.area = data["area"]
        if "outsourcingTarget" in data:
            project.outsourcing_target = data["outsourcingTarget"]
        if "kpiCompletionRate" in data:
            project.kpi_completion_rate = data["kpiCompletionRate"]
        if "kpiTimelyRate" in data:
            project.kpi_timely_rate = data["kpiTimelyRate"]

        project.updated_at = datetime.now()
        db.commit()

        return {
            "id": project.id,
            "name": project.name,
            "area": project.area,
            "outsourcingTarget": project.outsourcing_target or (project.area * 20 if project.area else 0),
            "kpiCompletionRate": project.kpi_completion_rate,
            "kpiTimelyRate": project.kpi_timely_rate,
        }

    @staticmethod
    def delete_project(project_id: int, db: Session) -> bool:
        """删除项目"""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return False
        db.delete(project)
        db.commit()
        return True

    # === 角色映射 ===

    @staticmethod
    def get_role_mappings(db: Session) -> dict:
        """获取所有角色映射"""
        mappings = db.query(RoleMapping).order_by(RoleMapping.id).all()
        return {
            "items": [
                {
                    "id": m.id,
                    "sourceRole": m.source_role,
                    "targetRole": m.target_role,
                }
                for m in mappings
            ]
        }

    @staticmethod
    def create_role_mapping(data: dict, db: Session) -> dict:
        """创建角色映射"""
        mapping = RoleMapping(
            source_role=data["sourceRole"],
            target_role=data["targetRole"],
        )
        db.add(mapping)
        db.commit()
        db.refresh(mapping)
        return {
            "id": mapping.id,
            "sourceRole": mapping.source_role,
            "targetRole": mapping.target_role,
        }

    @staticmethod
    def update_role_mapping(mapping_id: int, data: dict, db: Session) -> dict | None:
        """更新角色映射"""
        mapping = db.query(RoleMapping).filter(RoleMapping.id == mapping_id).first()
        if not mapping:
            return None

        if "sourceRole" in data:
            mapping.source_role = data["sourceRole"]
        if "targetRole" in data:
            mapping.target_role = data["targetRole"]

        db.commit()
        return {
            "id": mapping.id,
            "sourceRole": mapping.source_role,
            "targetRole": mapping.target_role,
        }

    @staticmethod
    def delete_role_mapping(mapping_id: int, db: Session) -> bool:
        """删除角色映射"""
        mapping = db.query(RoleMapping).filter(RoleMapping.id == mapping_id).first()
        if not mapping:
            return False
        db.delete(mapping)
        db.commit()
        return True

    # === 项目名称映射 ===

    @staticmethod
    def get_name_mappings(db: Session) -> dict:
        """获取所有项目名称映射"""
        mappings = db.query(ProjectNameMapping).order_by(ProjectNameMapping.id).all()
        return {
            "items": [
                {
                    "id": m.id,
                    "biName": m.bi_name,
                    "standardName": m.standard_name,
                    "projectId": str(m.project_id) if m.project_id else None,
                    "source": m.source or "bi",
                }
                for m in mappings
            ]
        }

    @staticmethod
    def create_name_mapping(data: dict, db: Session) -> dict:
        """创建项目名称映射"""
        mapping = ProjectNameMapping(
            bi_name=data["biName"],
            standard_name=data["standardName"],
        )
        db.add(mapping)
        db.commit()
        db.refresh(mapping)
        return {
            "id": mapping.id,
            "biName": mapping.bi_name,
            "standardName": mapping.standard_name,
        }

    @staticmethod
    def update_name_mapping(mapping_id: int, data: dict, db: Session) -> dict | None:
        """更新项目名称映射"""
        mapping = db.query(ProjectNameMapping).filter(ProjectNameMapping.id == mapping_id).first()
        if not mapping:
            return None

        if "biName" in data:
            mapping.bi_name = data["biName"]
        if "standardName" in data:
            mapping.standard_name = data["standardName"]

        db.commit()
        return {
            "id": mapping.id,
            "biName": mapping.bi_name,
            "standardName": mapping.standard_name,
        }

    @staticmethod
    def delete_name_mapping(mapping_id: int, db: Session) -> bool:
        """删除项目名称映射"""
        mapping = db.query(ProjectNameMapping).filter(ProjectNameMapping.id == mapping_id).first()
        if not mapping:
            return False
        db.delete(mapping)
        db.commit()
        return True

    # === 项目负责人清单 ===

    @staticmethod
    def get_projects_manager_list(db: Session) -> dict:
        """获取所有项目负责人清单"""
        items = db.query(ProjectManager).order_by(ProjectManager.project_id).all()
        # 附加项目名称
        project_ids = list(set(i.project_id for i in items))
        proj_map = {p.id: p.name for p in db.query(Project).filter(Project.id.in_(project_ids)).all()}
        return {
            "items": [
                {
                    "id": i.id,
                    "projectId": i.project_id,
                    "projectName": proj_map.get(i.project_id, f"项目{i.project_id}"),
                    "managerName": i.manager_name,
                }
                for i in items
            ]
        }

    # === KPI目标 ===

    @staticmethod
    def get_kpi_targets(project_id: int, db: Session) -> dict:
        """获取KPI目标配置"""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return {"error": "项目不存在"}

        return {
            "projectId": project.id,
            "projectName": project.name,
            "area": project.area,
            "outsourcingTarget": project.outsourcing_target or (project.area * 20 if project.area else 0),
            "kpiCompletionRate": project.kpi_completion_rate,
            "kpiTimelyRate": project.kpi_timely_rate,
            "defaultTargets": {
                "项目负责人": 30,
                "部门管理": 60,
                "一线员工": 30,
                "外包保安保洁": f"{project.area or 0} × 20 = {(project.area or 0) * 20}",
            },
        }

    @staticmethod
    def update_kpi_targets(project_id: int, data: dict, db: Session) -> dict | None:
        """更新KPI目标"""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None

        if "area" in data:
            project.area = data["area"]
        if "outsourcingTarget" in data:
            project.outsourcing_target = data["outsourcingTarget"]
        if "kpiCompletionRate" in data:
            project.kpi_completion_rate = data["kpiCompletionRate"]
        if "kpiTimelyRate" in data:
            project.kpi_timely_rate = data["kpiTimelyRate"]

        project.updated_at = datetime.now()
        db.commit()

        return ConfigService.get_kpi_targets(project_id, db)

    # === KPI全局阈值 ===

    @staticmethod
    def get_kpi_thresholds(db: Session) -> dict:
        """获取全局KPI阈值"""
        from sqlalchemy import text
        rows = db.execute(text(
            "SELECT key, value FROM kpi_thresholds"
        )).fetchall()
        result = {}
        for key, value in rows:
            result[key] = value
        return result

    @staticmethod
    def update_kpi_thresholds(data: dict, db: Session) -> dict:
        """更新全局KPI阈值"""
        from sqlalchemy import text
        for key, value in data.items():
            db.execute(text(
                "INSERT OR REPLACE INTO kpi_thresholds (key, value, updated_at) "
                "VALUES (:k, :v, datetime('now'))"
            ), {'k': key, 'v': value})
        db.commit()
        return ConfigService.get_kpi_thresholds(db)
