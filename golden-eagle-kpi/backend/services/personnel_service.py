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

        # 预取负责人姓名集合（用于项目负责人/一线员工筛选）
        all_pm_names = {
            r[0] for r in db.query(ProjectManager.manager_name).all()
        }

        if project_id:
            query = query.filter(Personnel.project_id == project_id)
        if role:
            # 系统角色（如"项目负责人"）与 Personnel.role（职务）不是同一字段
            # 需要将系统角色还原为职务关键词逻辑 + 负责人清单来过滤
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

        # 补充不在 personnel 表中的项目负责人（虚拟条目）
        # 场景：role=项目负责人 或 keyword 匹配到负责人姓名
        virtual_managers = _get_virtual_project_managers(project_id, role, keyword, db)
        # 去重：排除已存在于 items 中的姓名
        existing_names = {p.name for p in items}
        virtual_items = [vm for vm in virtual_managers if vm["name"] not in existing_names]
        # 如果当前页不够，补充虚拟条目（保证项目负责人始终可见）
        if virtual_items and (role == "项目负责人" or (keyword and any(vm["name"] == keyword for vm in virtual_items))):
            # 把虚拟条目插入到items前面（优先展示）
            # 模拟 Personnel 对象结构
            class _VirtualPerson:
                def __init__(self, vm):
                    self.employee_id = vm["employee_id"]
                    self.name = vm["name"]
                    self.role = vm["role"]
                    self.project_id = vm["project_id"]
                    self.is_outsourcing = False
                    self.status = "在职"
            for vm in virtual_items:
                items.insert(0, _VirtualPerson(vm))
            total += len(virtual_items)

        # 获取项目名称
        project_names = {}
        for p in db.query(Project).all():
            project_names[p.id] = p.name

        # 角色目标：每月每人发起工单数
        ROLE_TARGET = {"项目负责人": 30, "部门管理": 60, "一线员工": 30, "外包": 0}

        # 计算每人发起工单数
        result_items = []
        for person in items:
            # 虚拟条目（不在 personnel 表中）：无工号，发起数为0
            if person.employee_id is None:
                result_items.append({
                    "id": None,
                    "name": person.name,
                    "position": "项目负责人",
                    "role": "项目负责人",
                    "projectId": str(person.project_id) if person.project_id else None,
                    "projectName": person.project_name if hasattr(person, 'project_name') else project_names.get(person.project_id, ""),
                    "count": 0,
                    "target": 30,
                    "actual": 0,
                    "deduction": 0,
                    "isOutsourcing": False,
                    "status": "在职",
                })
                continue

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


def _get_virtual_project_managers(project_id, role, keyword, db):
    """获取不在 personnel 表中的项目负责人（虚拟条目）

    当负责人姓名在 projects_manager_list 中存在但 personnel 表中无此人时，
    作为虚拟条目补充到人力清单中。
    """
    from sqlalchemy import text

    # 构建查询条件
    conditions = []
    params = {}

    if project_id:
        conditions.append("pm.project_id = :pid")
        params["pid"] = project_id

    if role and role != "项目负责人":
        return []  # 非项目负责人角色不需要虚拟条目

    if keyword:
        conditions.append("pm.manager_name LIKE :kw")
        params["kw"] = f"%{keyword}%"

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sql = text(f"""
        SELECT pm.project_id, pm.manager_name, p.name as proj_name
        FROM projects_manager_list pm
        LEFT JOIN projects p ON pm.project_id = p.id
        {where_clause}
    """)
    rows = db.execute(sql, params).fetchall()

    # 只返回不在 personnel 表中的负责人
    result = []
    for row in rows:
        pid, m_name, proj_name = row
        # 检查是否在 personnel 表中存在
        exists = db.execute(
            text("SELECT 1 FROM personnel WHERE project_id = :pid AND name = :name AND status = '在职'"),
            {"pid": pid, "name": m_name}
        ).fetchone()
        if not exists:
            result.append({
                "employee_id": None,
                "name": m_name,
                "role": "项目负责人",
                "project_id": pid,
                "project_name": proj_name or f"项目{pid}",
            })
    return result
