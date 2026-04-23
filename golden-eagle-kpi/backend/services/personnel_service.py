"""金鹰工单KPI管理 - 人力清单服务"""
import io
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text, or_, and_
from backend.models.personnel import Personnel
from backend.models.project import Project
from backend.models.project_manager import ProjectManager


class PersonnelService:
    """人力清单CRUD + 导入导出"""

    @staticmethod
    def get_personnel_list(
        project_id: int = None,
        role: str = None,
        keyword: str = None,
        month: str = None,
        page: int = 1,
        page_size: int = 10,
        db: Session = None,
    ) -> dict:
        """获取人力清单"""
        query = db.query(Personnel)

        if project_id:
            query = query.filter(Personnel.project_id == project_id)
        if role:
            # 系统角色（如"项目负责人"）与 Personnel.role（职务）不是同一字段
            # 需要将系统角色还原为职务关键词逻辑 + 负责人清单来过滤
            # 先预取负责人姓名集合（用于项目负责人/一线员工筛选）
            all_pm_names = set(
                r[0] for r in db.query(ProjectManager.manager_name).all()
            )
            if role == "项目负责人":
                # 两种人：1) 姓名在负责人清单中  2) 职务含总监/总经理但不含副
                query = query.filter(
                    or_(
                        Personnel.name.in_(all_pm_names),
                        and_(
                            Personnel.role.like('%总监%'),
                            ~Personnel.role.like('%副%')
                        )
                    )
                )
            elif role == "部门管理":
                query = query.filter(
                    or_(
                        Personnel.role.like('%副总监%'),
                        Personnel.role.like('%副经理%'),
                        Personnel.role.like('%副总经理%'),
                        Personnel.role.like('%高级经理%'),
                        Personnel.role.like('%经理%'),
                        Personnel.role.like('%主管%')
                    )
                )
            elif role == "一线员工":
                # 非管理层、非外包：排除负责人清单 + 所有管理关键词
                query = query.filter(
                    ~Personnel.name.in_(all_pm_names),
                    ~Personnel.role.like('%总监%'),
                    ~Personnel.role.like('%经理%'),
                    ~Personnel.role.like('%主管%'),
                    ~Personnel.role.like('%外包%'),
                )
            elif role == "外包":
                query = query.filter(
                    or_(
                        Personnel.role.like('%外包%'),
                        Personnel.is_outsourcing == 1
                    )
                )
        if keyword:
            query = query.filter(
                (Personnel.name.contains(keyword)) | (Personnel.employee_id.contains(keyword))
            )

        total = query.count()
        offset = (page - 1) * page_size
        items = query.offset(offset).limit(page_size).all()

        # 获取项目名称
        project_names = {}
        for p in db.query(Project).all():
            project_names[p.id] = p.name

        # 角色目标：每月每人发起工单数
        ROLE_TARGET = {"项目负责人": 30, "部门管理": 60, "一线员工": 30, "外包": 0}

        # 计算每人发起工单数
        result_items = []
        for person in items:
            # 查询该人员发起的随手拍数（从 snapshots 表）
            count_sql = text("""
                SELECT COUNT(*) as cnt FROM snapshots
                WHERE initiator_id = :eid
            """)
            if month:
                count_sql = text("""
                    SELECT COUNT(*) as cnt FROM snapshots
                    WHERE initiator_id = :eid
                    AND strftime('%Y-%m', create_time) = :month
                """)

            params = {"eid": person.employee_id}
            if month:
                params["month"] = month
            row = db.execute(count_sql, params).fetchone()

            sys_role = _map_system_role(person, db)
            count = row.cnt if row else 0
            target = ROLE_TARGET.get(sys_role, 30)
            actual = count  # 发起数即实际达成数
            diff = actual - target
            # 扣分规则：未达标部分按比例扣分（每差1条扣0.5分，上限扣30分）
            deduction = max(0, round(-diff * 0.5, 1)) if diff < 0 else 0

            result_items.append({
                "id": person.employee_id,
                "name": person.name,
                "position": person.role,
                "role": sys_role,
                "projectId": str(person.project_id) if person.project_id else None,
                "projectName": project_names.get(person.project_id, ""),
                "count": count,
                "target": target,
                "actual": actual,
                "deduction": deduction,
                "isOutsourcing": bool(person.is_outsourcing),
                "status": person.status,
            })

        return {
            "total": total,
            "page": page,
            "pageSize": page_size,
            "projectId": str(project_id) if project_id else None,
            "projectName": project_names.get(project_id, "") if project_id else None,
            "items": result_items,
        }

    @staticmethod
    def create_personnel(data: dict, db: Session) -> dict | None:
        """新增人员"""
        raw_id = data.get("employee_id") or data.get("id") or data.get("employeeId")
        if not raw_id:
            return None
        employee_id = _clean_employee_id(raw_id)

        # 检查工号是否已存在
        existing = db.query(Personnel).filter(Personnel.employee_id == employee_id).first()
        if existing:
            return None

        person = Personnel(
            employee_id=employee_id,
            name=str(data.get("name", "")).strip(),
        )
        if "role" in data:
            person.role = str(data["role"]).strip()
        if data.get("projectId"):
            try:
                person.project_id = int(data["projectId"])
            except (ValueError, TypeError):
                pass
        if "phone" in data:
            person.phone = str(data["phone"]).strip()
        if "entryDate" in data or "entry_date" in data:
            person.entry_date = str(data.get("entryDate") or data.get("entry_date", "")).strip()
        if "isOutsourcing" in data or "is_outsourcing" in data:
            person.is_outsourcing = 1 if (data.get("isOutsourcing") or data.get("is_outsourcing")) else 0
        if "status" in data:
            person.status = str(data["status"]).strip() or "在职"

        db.add(person)
        db.commit()
        db.refresh(person)
        return person.to_dict()

    @staticmethod
    def import_personnel(file_bytes: bytes, mode: str, db: Session) -> dict:
        """导入人力清单Excel"""
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
        ws = wb.active

        imported = 0
        updated = 0
        skipped = 0
        errors = []

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            try:
                if not row or len(row) < 3:
                    skipped += 1
                    continue

                # 解析行数据（假设格式：工号、姓名、职务/角色、项目ID、手机号...）
                raw_id = row[0]
                name = str(row[1] or "").strip()
                position = str(row[2] or "").strip()

                if not raw_id or not name:
                    skipped += 1
                    continue

                # 工号处理：科学计数法→字符串→补零
                employee_id = _clean_employee_id(raw_id)

                # 查找或创建
                existing = db.query(Personnel).filter(Personnel.employee_id == employee_id).first()

                if existing:
                    if mode == "replace":
                        existing.name = name
                        existing.role = position
                        if len(row) > 3 and row[3]:
                            try:
                                existing.project_id = int(row[3])
                            except (ValueError, TypeError):
                                pass
                        existing.updated_at = datetime.now()
                        updated += 1
                    else:
                        skipped += 1
                else:
                    person = Personnel(
                        employee_id=employee_id,
                        name=name,
                        role=position,
                    )
                    if len(row) > 3 and row[3]:
                        try:
                            person.project_id = int(row[3])
                        except (ValueError, TypeError):
                            pass
                    if len(row) > 4 and row[4]:
                        person.phone = str(row[4])
                    db.add(person)
                    imported += 1

            except Exception as e:
                errors.append({"row": row_idx, "message": str(e)})

        db.commit()
        wb.close()

        return {
            "success": True,
            "imported": imported,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
        }

    @staticmethod
    def update_personnel(personnel_id: str, data: dict, db: Session) -> dict | None:
        """更新人员信息"""
        person = db.query(Personnel).filter(Personnel.employee_id == personnel_id).first()
        if not person:
            return None

        if "name" in data:
            person.name = data["name"]
        if "role" in data:
            person.role = data["role"]
        if "projectId" in data:
            try:
                person.project_id = int(data["projectId"])
            except (ValueError, TypeError):
                pass
        if "phone" in data:
            person.phone = data["phone"]
        if "status" in data:
            person.status = data["status"]

        person.updated_at = datetime.now()
        db.commit()
        return person.to_dict()

    @staticmethod
    def delete_personnel(personnel_id: str, db: Session) -> bool:
        """删除人员"""
        person = db.query(Personnel).filter(Personnel.employee_id == personnel_id).first()
        if not person:
            return False
        db.delete(person)
        db.commit()
        return True


def _clean_employee_id(raw_id) -> str:
    """工号清洗：科学计数法→字符串→补零到10位"""
    if isinstance(raw_id, float):
        raw_id = str(int(raw_id))
    raw_id = str(raw_id).strip()
    return raw_id.zfill(10)


def _map_system_role(person, db) -> str:
    """人员角色推断：优先用负责人清单匹配姓名，其次岗位关键词"""
    from backend.models.project_manager import ProjectManager

    # 第一优先级：负责人清单（姓名精确匹配项目负责人）
    if person.project_id:
        pm = db.query(ProjectManager).filter(
            ProjectManager.project_id == person.project_id,
            ProjectManager.manager_name == person.name
        ).first()
        if pm:
            return "项目负责人"

    # 第二优先级：岗位关键词
    if not person.role:
        return "一线员工"

    position = person.role
    if "外包" in position:
        return "外包"
    if any(k in position for k in ["总监", "总经理"]) and "副" not in position:
        return "项目负责人"
    if any(k in position for k in ["副总监", "副经理", "副总经理", "工程副总监", "高级经理", "经理", "主管", "物业经理", "客服经理", "工程经理"]):
        return "部门管理"
    return "一线员工"
