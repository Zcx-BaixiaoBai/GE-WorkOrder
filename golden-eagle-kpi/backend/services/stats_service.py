"""金鹰工单KPI管理 - 统计计算服务

核心计算规则（PRD）：
  1. 项目负责人：仅来自负责人清单（projects_manager_list），与岗位无关
  2. 部门管理：职务含"经理/主管/副总监"等（不含正"总监/总经理"）
  3. 一线员工：非上述两类的人员
  4. 外包保安保洁：工单明细表中 brand IN ('秩序报修','保洁报修')
  5. 完成率：仅手工单明细（source='detail'）
  6. 及时率：工单明细中有deadline的完成工单
  7. 发起达成率 = 实际发起 / 目标（按角色×30或×60）
  8. 综合评分 = (完成率×30% + 及时率×30% + 发起达成率×40%) / 10

数据源规则：
  - 内部员工发起统计：随手拍工单明细表(snapshots)，按发起人工号(initiator_id)与人力清单工号索引匹配
  - 外包统计：工单明细表(work_tickets)中 brand IN ('秩序报修','保洁报修')
"""
from datetime import datetime
from sqlalchemy import text, func, case
from sqlalchemy.orm import Session
from backend.models.work_ticket import WorkTicket
from backend.models.personnel import Personnel
from backend.models.project import Project
from backend.models.project_manager import ProjectManager


class StatsService:

    # ============================================================
    # 四层级统计（核心）
    # ============================================================

    @staticmethod
    def get_initiation_by_level(project_id: int, month: str, db: Session) -> dict:
        """四层级发起统计

        规则：
          - 项目负责人：来自 projects_manager_list（姓名精确匹配）
          - 部门管理：职务含"经理/主管/副总监"等
          - 一线员工：非上述两类
          - 外包保安保洁：工单明细表中 brand IN ('秩序报修','保洁报修')

        数据源：
          - 内部员工发起：随手拍工单明细表(snapshots)，按initiator_id匹配人力清单
          - 外包：工单明细表(work_tickets) brand IN ('秩序报修','保洁报修')
        """
        if not month:
            month = datetime.now().strftime("%Y-%m")

        params = {"pid": project_id, "month": month}

        # 项目配置
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return {"error": "项目不存在"}

        area = project.area or 0  # 单位: m²
        outsourcing_target = (area / 10000) * 20  # 条/月

        # 一次性查询所有在职人员（含角色）
        all_personnel_sql = text("""
            SELECT p.employee_id, p.name, p.role
            FROM personnel p
            WHERE p.project_id = :pid
            AND p.status = '在职'
        """)
        all_personnel = db.execute(all_personnel_sql, params).fetchall()

        # 一次性查询该月该项目的内部员工发起工单（从随手拍工单明细表snapshots）
        ticket_sql = text("""
            SELECT s.initiator_id, COUNT(*) as cnt
            FROM snapshots s
            WHERE s.project_id = :pid
            AND strftime('%Y-%m', s.create_time) = :month
            GROUP BY s.initiator_id
        """)
        ticket_rows = db.execute(ticket_sql, params).fetchall()
        # 构建 initiator_id → count 映射
        ticket_map = {row[0]: row[1] for row in ticket_rows}

        # 从 projects_manager_list 获取该项目的负责人姓名列表
        manager_sql = text("""
            SELECT manager_name FROM projects_manager_list
            WHERE project_id = :pid
        """)
        db_manager_names = [row[0] for row in db.execute(manager_sql, {"pid": project_id}).fetchall()]

        # 部门管理岗位关键词（来自管理层岗位清单）
        dept_keywords = {"副总监", "副经理", "副总经理", "工程副总监", "高级经理",
                         "物业经理", "客服经理", "工程经理", "安全经理", "安全主管",
                         "综合主管", "物业主管", "环境主管", "经理", "主管"}

        # 以负责人清单为准，逐人匹配 personnel 表
        all_personnel_by_name = {row[1]: row for row in all_personnel}
        leader_list = []      # 项目负责人
        assigned_ids = set()  # 已被归为负责人的工号

        for m_name in db_manager_names:
            if m_name in all_personnel_by_name:
                emp_id, name, role = all_personnel_by_name[m_name]
                leader_list.append((emp_id, name, role))
                assigned_ids.add(emp_id)
            else:
                # 负责人不在人员清单中，虚拟占位（发起数=0）
                leader_list.append((None, m_name, None))

        # 剩余人员按岗位关键词分类
        dept_list = []        # 部门管理
        staff_list = []       # 一线员工

        for emp_id, name, role in all_personnel:
            if emp_id in assigned_ids:
                continue  # 已在负责人列表
            if role and any(k in role for k in dept_keywords):
                dept_list.append((emp_id, name, role))
            else:
                staff_list.append((emp_id, name, role))

        def count_initiated(person_list):
            """统计列表中人员发起的工单总数（虚拟占位项 emp_id=None 发起数为0）"""
            if not person_list:
                return 0
            total = 0
            for emp_id, _, _ in person_list:
                if emp_id is not None:
                    total += ticket_map.get(emp_id, 0)
            return total

        def build_level(name_list, person_list, per_person_target):
            count = len(person_list)
            initiated = count_initiated(person_list)
            target = count * per_person_target
            ar = round(initiated * 100.0 / target, 1) if target > 0 else 0
            return {
                "level": name_list,
                "count": count,
                "initiated": initiated,
                "target": target,
                "targetPerPerson": per_person_target,
                "achievementRate": ar,
            }

        # 外包保安保洁：来自工单明细表 brand字段
        vendor_sql = text("""
            SELECT COUNT(*) as cnt
            FROM work_tickets
            WHERE project_id = :pid
            AND strftime('%Y-%m', create_time) = :month
            AND brand IN ('秩序报修', '保洁报修')
        """)
        vendor_initiated = db.execute(vendor_sql, params).fetchone()[0] or 0
        vendor_ar = round(vendor_initiated * 100.0 / outsourcing_target, 1) if outsourcing_target > 0 else 0

        total_initiated = (
            count_initiated(leader_list)
            + count_initiated(dept_list)
            + count_initiated(staff_list)
            + vendor_initiated
        )
        total_target = (
            len(leader_list) * 30
            + len(dept_list) * 60
            + len(staff_list) * 30
            + outsourcing_target
        )

        return {
            "totalInitiated": total_initiated,
            "totalTarget": round(total_target, 1),
            "achievementRate": round(total_initiated * 100.0 / total_target, 1) if total_target > 0 else 0,
            "levels": [
                build_level("项目负责人", leader_list, 30),
                build_level("部门管理", dept_list, 60),
                build_level("一线员工", staff_list, 30),
                {
                    "level": "外包保安保洁",
                    "count": None,
                    "initiated": vendor_initiated,
                    "target": round(outsourcing_target, 1),
                    "targetPerPerson": None,
                    "achievementRate": vendor_ar,
                    "note": "目标按项目面积(万m²)×20条计算",
                },
            ],
        }

    # ============================================================
    # 驾驶舱
    # ============================================================

    @staticmethod
    def get_dashboard_stats(project_id: int, month: str, db: Session) -> dict:
        """驾驶舱统计卡片

        规则：
          - total/pending/completed: 仅工单明细（detail是完整母集）
          - rate(完成率): 仅工单明细
          - timely_rate(及时率): 仅工单明细且有deadline的记录
          - trend: 工单明细月度趋势
        """
        params = {}
        pid_cond = "1=1"  # 默认不过滤项目
        month_cond = ""
        if project_id:
            pid_cond = "wt.project_id = :pid"
            params["pid"] = project_id

        # 月份过滤
        if month:
            month_cond = "AND strftime('%Y-%m', wt.create_time) = :month"
            params["month"] = month

        # 总卡片（仅工单明细，工单明细是完整母集）
        total_sql = text(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN wt.order_status IN ('已完成','已关闭','已解决') THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN wt.order_status NOT IN ('已完成','已关闭','已解决') THEN 1 ELSE 0 END) as pending
            FROM work_tickets wt
            WHERE {pid_cond} AND wt.source = 'detail' {month_cond}
        """)
        total_result = db.execute(total_sql, params).fetchone()

        # 完成率/及时率（仅工单明细）
        rate_sql = text(f"""
            SELECT
                COUNT(*) as detail_total,
                SUM(CASE WHEN wt.order_status IN ('已完成','已关闭','已解决') THEN 1 ELSE 0 END) as detail_completed,
                SUM(CASE WHEN wt.order_status IN ('已完成','已关闭','已解决') AND wt.deadline IS NOT NULL AND wt.complete_time IS NOT NULL AND wt.complete_time <= wt.deadline THEN 1 ELSE 0 END) as detail_timely
            FROM work_tickets wt
            WHERE {pid_cond} AND wt.source = 'detail' {month_cond}
        """)
        rate_result = db.execute(rate_sql, params).fetchone()

        completion_rate = 0.0
        timely_rate = 0.0
        if rate_result and rate_result.detail_total:
            completion_rate = round(rate_result.detail_completed * 100.0 / rate_result.detail_total, 1)
            if rate_result.detail_completed > 0:
                timely_rate = round(rate_result.detail_timely * 100.0 / rate_result.detail_completed, 1)

        # 趋势（工单明细月度趋势）
        trend_sql = text(f"""
            SELECT strftime('%Y-%m', wt.create_time) as m, COUNT(*) as cnt
            FROM work_tickets wt
            WHERE {pid_cond} AND wt.source = 'detail'
            GROUP BY strftime('%Y-%m', wt.create_time)
            ORDER BY m DESC LIMIT 6
        """)
        trend_rows = db.execute(trend_sql, params).fetchall()
        trend = [{"month": r[0], "count": r[1]} for r in reversed(trend_rows)]

        # 项目名称
        project_name = None
        if project_id:
            proj = db.query(Project).filter(Project.id == project_id).first()
            project_name = proj.name if proj else None

        return {
            "projectId": str(project_id) if project_id else None,
            "projectName": project_name,
            "total": (total_result.total or 0) if total_result else 0,
            "pending": (total_result.pending or 0) if total_result else 0,
            "completed": (total_result.completed or 0) if total_result else 0,
            "rate": completion_rate,
            "trend": trend,
        }

    # ============================================================
    # 预警清单
    # ============================================================

    
    @staticmethod
    def get_warnings(project_id, level: str, threshold: float, month: str, db: Session) -> dict:
        """预警清单

        规则：
          - 项目负责人：来自负责人清单
          - 部门管理/一线员工：来自岗位关键词（不含外包，外包单独统计）
          - 外包保安保洁：不进入预警（按工单统计，不是人员）
          - projectRank = 该员工在项目内按达成率升序的排名（达成率最低=rank1）
          - 排序：按 projectRank 降序（最差排前面）
        """
        if not month:
            month = datetime.now().strftime("%Y-%m")

        now = datetime.now()
        days_in_month = 30
        days_passed = min(now.day, days_in_month)

        dept_kw = {"副总监", "副经理", "副总经理", "工程副总监", "高级经理",
                   "物业经理", "客服经理", "工程经理", "安全经理", "安全主管",
                   "综合主管", "物业主管", "环境主管", "经理", "主管"}
        target_map = {"项目负责人": 30, "部门管理": 60, "一线员工": 30}

        # 确定要查询的项目
        if project_id:
            target_pids = [project_id]
        else:
            # 无 projectId：查询全部项目
            all_proj_sql = text("SELECT id FROM projects")
            target_pids = [row[0] for row in db.execute(all_proj_sql).fetchall()]

        # 批量构建负责人姓名集合
        manager_names_map = {}
        for pid in target_pids:
            m_sql = text("SELECT manager_name FROM projects_manager_list WHERE project_id = :pid")
            manager_names_map[pid] = {row[0] for row in db.execute(m_sql, {"pid": pid}).fetchall()}

        # 批量查询人员
        placeholders = ','.join([f':p{i}' for i in range(len(target_pids))])
        personnel_sql = text(f"""
            SELECT p.employee_id, p.name, p.role, p.project_id
            FROM personnel p
            WHERE p.project_id IN ({placeholders})
            AND p.status = '在职'
        """)
        personnel_params = {f"p{i}": pid for i, pid in enumerate(target_pids)}
        all_personnel = db.execute(personnel_sql, personnel_params).fetchall()

        # 批量查询人发动单数
        ticket_sql = text(f"""
            SELECT s.initiator_id, s.project_id, COUNT(*) as cnt
            FROM snapshots s
            WHERE s.project_id IN ({placeholders})
            AND strftime('%Y-%m', s.create_time) = :month
            GROUP BY s.initiator_id, s.project_id
        """)
        ticket_params = {f"p{i}": pid for i, pid in enumerate(target_pids)}
        ticket_params["month"] = month
        ticket_rows = db.execute(ticket_sql, ticket_params).fetchall()
        ticket_map = {(row[0], row[1]): row[2] for row in ticket_rows}

        def infer_role(pid, name, role):
            if name in manager_names_map.get(pid, set()):
                return "项目负责人"
            if role and any(k in role for k in dept_kw):
                return "部门管理"
            return "一线员工"

        # 跟踪已通过 personnel 匹配到的负责人
        manager_found = {(pid, name): False for pid in target_pids for name in manager_names_map.get(pid, set())}

        # 第一次遍历：计算每人的达成率
        raw_items = []
        for emp_id, name, role, pid in all_personnel:
            mapped_role = infer_role(pid, name, role)
            if level and mapped_role != level:
                continue
            initiated = ticket_map.get((emp_id, pid), 0)
            base_target = target_map.get(mapped_role, 30)
            target_dynamic = round(base_target * days_passed / days_in_month)
            ar = round(initiated * 100.0 / target_dynamic, 1) if target_dynamic > 0 else 0

            # 标记该负责人已通过人员匹配找到
            if mapped_role == "项目负责人":
                manager_found[(pid, name)] = True

            if ar < threshold:
                warning_type = "severe" if ar < 70 else "normal"
                raw_items.append({
                    "id": emp_id,
                    "name": name,
                    "level": mapped_role,
                    "position": role or "",
                    "initiated": initiated,
                    "target": base_target,
                    "targetDynamic": target_dynamic,
                    "achievementRate": ar,
                    "warningType": warning_type,
                    "daysPassed": days_passed,
                    "daysInMonth": days_in_month,
                    "projectId": pid,
                    "_ar": ar,  # 临时用于排序
                })

        # 补充不在人员清单中的负责人（虚拟占位）
        for (pid, m_name), found in manager_found.items():
            if found:
                continue
            if level and level != "项目负责人":
                continue
            base_target = target_map.get("项目负责人", 30)
            target_dynamic = round(base_target * days_passed / days_in_month)
            ar = 0.0  # 无可发起的工单
            if ar < threshold:
                warning_type = "severe"
                raw_items.append({
                    "id": None,
                    "name": m_name,
                    "level": "项目负责人",
                    "position": "",
                    "initiated": 0,
                    "target": base_target,
                    "targetDynamic": target_dynamic,
                    "achievementRate": ar,
                    "warningType": warning_type,
                    "daysPassed": days_passed,
                    "daysInMonth": days_in_month,
                    "projectId": pid,
                    "_ar": ar,
                })

        # 项目内排名：按达成率升序（最低=rank1）
        from collections import defaultdict
        proj_members = defaultdict(list)
        for item in raw_items:
            proj_members[item["projectId"]].append(item)

        for pid, members in proj_members.items():
            members.sort(key=lambda x: x["_ar"])
            for rank, item in enumerate(members, 1):
                item["projectRank"] = rank

        # 汇总
        items = []
        severe_count = sum(1 for x in raw_items if x["warningType"] == "severe")
        normal_count = sum(1 for x in raw_items if x["warningType"] == "normal")
        for item in raw_items:
            del item["_ar"]  # 去掉临时字段
            items.append(item)

        # 排序：达成率最低（rank=1最差）排前面；同rank按达成率
        items.sort(key=lambda x: (x["projectRank"], x["achievementRate"]))

        return {
            "total": len(items),
            "severe": severe_count,
            "normal": normal_count,
            "items": items,
        }
    # ============================================================

    @staticmethod
    def get_completion(project_id: int, month: str, db: Session) -> dict:
        """完成情况统计

        规则：
          - 完成：order_status IN ('已完成','已关闭','已解决')
          - 及时：完成且 complete_time <= deadline
          - 逾期：完成但 complete_time > deadline
        """
        if not month:
            month = datetime.now().strftime("%Y-%m")

        params = {"pid": project_id, "month": month}

        sql = text("""
            SELECT
                COUNT(*) as total_tickets,
                SUM(CASE WHEN order_status IN ('已完成','已关闭','已解决') THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN order_status = '待处理' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN order_status NOT IN ('已完成','已关闭','已解决','待处理') THEN 1 ELSE 0 END) as processing,
                SUM(CASE WHEN order_status IN ('已完成','已关闭','已解决') AND deadline IS NOT NULL AND complete_time IS NOT NULL AND complete_time <= deadline THEN 1 ELSE 0 END) as timely_completed,
                SUM(CASE WHEN order_status IN ('已完成','已关闭','已解决') AND deadline IS NOT NULL AND complete_time IS NOT NULL AND complete_time > deadline THEN 1 ELSE 0 END) as overdue_tickets
            FROM work_tickets
            WHERE project_id = :pid
            AND strftime('%Y-%m', create_time) = :month
        """)

        row = db.execute(sql, params).fetchone()
        total = (row.total_tickets or 0) if row else 0
        completed = (row.completed or 0) if row else 0
        timely = (row.timely_completed or 0) if row else 0

        return {
            "totalTickets": total,
            "completed": completed,
            "pending": (row.pending or 0) if row else 0,
            "processing": (row.processing or 0) if row else 0,
            "completionRate": round(completed * 100.0 / total, 1) if total > 0 else 0,
            "timelyCompleted": timely,
            "timelyRate": round(timely * 100.0 / completed, 1) if completed > 0 else 0,
            "overdueTickets": (row.overdue_tickets or 0) if row else 0,
        }

    # ============================================================
    # 综合评分
    # ============================================================

    @staticmethod
    def get_score(project_id: int, month: str, db: Session) -> dict:
        """综合评分

        规则：
          - 完成率得分 = min(10, 完成率/10)
          - 及时率得分 = min(10, 及时率/10)
          - 发起达成率得分 = min(10, 达成率/10)
          - 综合得分 = (完成率×30 + 及时率×30 + 发起达成率×40) / 100
          - 等级: S≥9 A≥8 B≥7 C≥6 D<6
        """
        completion = StatsService.get_completion(project_id, month, db)
        initiation = StatsService.get_initiation_by_level(project_id, month, db)

        completion_score = min(10, completion["completionRate"] / 10)
        timeliness_score = min(10, completion["timelyRate"] / 10)
        initiation_rate = initiation.get("achievementRate", 0)
        initiation_score = min(10, initiation_rate / 10)

        weights = {"completion": 30, "timeliness": 30, "initiation": 40}
        overall = (
            completion_score * weights["completion"]
            + timeliness_score * weights["timeliness"]
            + initiation_score * weights["initiation"]
        ) / 100

        if overall >= 9.0:
            grade = "S"
        elif overall >= 8.0:
            grade = "A"
        elif overall >= 7.0:
            grade = "B"
        elif overall >= 6.0:
            grade = "C"
        else:
            grade = "D"

        return {
            "overallScore": round(overall, 1),
            "completionScore": round(completion_score, 1),
            "timelinessScore": round(timeliness_score, 1),
            "initiationScore": round(initiation_score, 1),
            "weights": weights,
            "grade": grade,
        }
