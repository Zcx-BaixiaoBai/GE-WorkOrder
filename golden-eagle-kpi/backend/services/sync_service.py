"""金鹰工单KPI管理 - 数据同步服务

流程：启动BI爬虫 → 下载Excel → openpyxl读取 → 清洗 → 暴力覆盖入库（先删后插）
"""
import asyncio
import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.models.sync_log import SyncLog
from backend.models.work_ticket import WorkTicket
from backend.models.snapshot import Snapshot
from backend.models.project_name_mapping import ProjectNameMapping
from backend.models.project import Project
from backend.config import AppConfig
from backend.database import get_session_local


_sync_status = {
    "is_syncing": False,
    "current_task": None,
    "progress": 0,
    "message": "",
    "last_sync_time": None,
    "last_sync_result": None,
}


def _clean_id(raw_id) -> str:
    """工号清洗：科学计数法→字符串→补零到10位"""
    if raw_id is None:
        return "0000000000"
    if isinstance(raw_id, float):
        raw_id = str(int(raw_id))
    raw_id = str(raw_id).strip()
    if not raw_id or raw_id == 'None':
        return "0000000000"
    return raw_id.zfill(10)


def _parse_datetime(val):
    """解析各种日期时间格式"""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    if not s or s in ('None', 'NaT', ''):
        return None
    if len(s) == 14 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d%H%M%S")
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _update_progress(start_pct: int, end_pct: int, internal_pct: float):
    global _sync_status
    p = start_pct + (end_pct - start_pct) * internal_pct
    _sync_status["progress"] = int(min(p, end_pct))


class SyncService:

    @staticmethod
    def get_sync_status() -> dict:
        last_time = _sync_status["last_sync_time"]
        if not last_time:
            db = get_session_local()()
            try:
                last_time = SyncService.get_last_sync_time(db)
            finally:
                db.close()
        return {
            "isSyncing": _sync_status["is_syncing"],
            "currentTask": _sync_status["current_task"],
            "progress": _sync_status["progress"],
            "message": _sync_status["message"],
            "lastSyncTime": last_time,
            "lastSyncResult": _sync_status["last_sync_result"],
            "hasError": _sync_status["last_sync_result"] == "failed",
        }

    @staticmethod
    def get_last_sync_time(db: Session) -> str | None:
        row = db.execute(
            text("SELECT finished_at FROM sync_logs WHERE status='completed' ORDER BY id DESC LIMIT 1")
        ).fetchone()
        return row[0] if row and row[0] else None

    @staticmethod
    async def _run_sync_task(account: str, password: str, project_id: int):
        global _sync_status
        try:
            from backend.scraper.bi_client import BiClient
        except ImportError:
            _sync_status.update({"is_syncing": False, "progress": 0,
                                 "message": "同步功能不可用：缺少Playwright库",
                                 "last_sync_result": "failed", "current_task": None})
            return

        _sync_status.update({"is_syncing": True, "current_task": "初始化...",
                             "progress": 0, "message": ""})

        db = get_session_local()()
        sync_log = SyncLog(sync_type="full", project_id=project_id,
                           status="running", started_at=datetime.now())
        db.add(sync_log)
        db.commit()
        db.refresh(sync_log)
        log_id = sync_log.id

        try:
            client = BiClient(account=account, password=password)
            _sync_status["current_task"] = "登录BI..."
            _sync_status["progress"] = 2
            page = await client._login_context()
            if not page:
                raise RuntimeError("BI登录失败")

            _sync_status["current_task"] = "进入BI报表..."
            bi_page = await client._enter_bi(page)
            if not bi_page:
                raise RuntimeError("无法进入BI系统")

            tickets_file = snapshots_file = None

            _sync_status["current_task"] = "下载工单明细..."
            _sync_status["progress"] = 5
            tickets_file = await client.fetch_tickets()
            if tickets_file:
                _sync_status["message"] = f"工单明细: {Path(tickets_file).name}"

            _sync_status["current_task"] = "下载随手拍..."
            _sync_status["progress"] = 25
            snapshots_file = await client.fetch_snapshots()
            if snapshots_file:
                _sync_status["message"] = f"随手拍: {Path(snapshots_file).name}"

            await client.close()

            _sync_status["current_task"] = "入库工单明细..."
            _sync_status["progress"] = 40
            ticket_result = {"imported": 0, "skipped": 0}
            if tickets_file:
                ticket_result = SyncService._import_tickets_from_excel(
                    tickets_file, log_id, db,
                    lambda p: _update_progress(_sync_status, 40, 80, p))

            _sync_status["current_task"] = "入库随手拍..."
            _sync_status["progress"] = 80
            snapshot_result = {"imported": 0, "skipped": 0}
            if snapshots_file:
                snapshot_result = SyncService._import_snapshots_from_excel(
                    snapshots_file, log_id, db,
                    lambda p: _update_progress(_sync_status, 80, 95, p))

            _sync_status["current_task"] = "刷新映射..."
            _sync_status["progress"] = 95
            SyncService._refresh_name_mappings(db)

            sync_log.finished_at = datetime.now()
            sync_log.status = "completed"
            sync_log.tickets_synced = ticket_result["imported"]
            sync_log.snapshots_synced = snapshot_result["imported"]
            db.commit()

            _sync_status.update({
                "is_syncing": False, "progress": 100,
                "message": f"完成：工单{ticket_result['imported']}条，随手拍{snapshot_result['imported']}条",
                "last_sync_time": sync_log.finished_at.isoformat(),
                "last_sync_result": "success", "current_task": None})

        except Exception as e:
            tb = traceback.format_exc()
            print(f"[同步] 异常: {e}\n{tb}")
            sync_log.finished_at = datetime.now()
            sync_log.status = "failed"
            sync_log.error_message = str(e)[:500]
            db.commit()
            _sync_status.update({"is_syncing": False, "progress": 0,
                                  "message": f"失败: {e}",
                                  "last_sync_result": "failed", "current_task": None})
        finally:
            db.close()

    @staticmethod
    def _import_tickets_from_excel(file_path: str, batch_id: int, db: Session,
                                   progress_cb=None) -> dict:
        import openpyxl
        import json

        print(f"[同步] 读取工单明细: {Path(file_path).name}")
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active

        mappings = db.query(ProjectNameMapping).all()
        name_map = {m.bi_name: m.standard_name for m in mappings}
        projects = db.query(Project).all()
        projects_by_name = {p.name: p.id for p in projects}
        for p in projects:
            if p.bi_names:
                bi_list = json.loads(p.bi_names) if isinstance(p.bi_names, str) else p.bi_names
                for bn in bi_list:
                    if bn not in projects_by_name:
                        projects_by_name[bn] = p.id

        wt_deleted = db.query(WorkTicket).delete()
        db.commit()
        print(f"[同步] 已清除旧工单明细: work_tickets={wt_deleted}")

        total_rows = sum(1 for _ in ws.iter_rows(min_row=2, values_only=True) if _)
        wb.close()
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active

        imported = 0
        skipped = 0
        wt_batch = []

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            try:
                if not row or len(row) < 6:
                    skipped += 1
                    continue
                ticket_no = str(row[0] or "").strip()
                if not ticket_no or ticket_no == 'None':
                    skipped += 1
                    continue

                raw_project = str(row[2] or "").strip()
                standard_name = ""
                project_id = None
                if raw_project:
                    mapped = name_map.get(raw_project)
                    if mapped:
                        standard_name = mapped
                        project_id = projects_by_name.get(standard_name)
                    else:
                        for p in projects:
                            if p.name in raw_project or raw_project in p.name:
                                standard_name = p.name
                                project_id = p.id
                                break

                order_status = str(row[5] or "").strip()
                if order_status == "已解决":
                    order_status = "已完成"

                wt_batch.append(WorkTicket(
                    ticket_no=ticket_no, project_name=raw_project,
                    standard_name=standard_name, project_id=project_id,
                    order_type=str(row[4] or "").strip(),
                    order_status=order_status,
                    initiator_id=None, initiator_name=None,
                    create_time=_parse_datetime(row[1]),
                    accept_time=None,
                    complete_time=_parse_datetime(row[6]) if len(row) > 6 else None,
                    deadline=_parse_datetime(row[7]) if len(row) > 7 else None,
                    area_name=None, description=None,
                    sync_batch_id=batch_id, source="detail",
                    ticket_type=str(row[4] or "").strip(),
                    handler_id=_clean_id(row[8]) if len(row) > 8 and row[8] else None,
                    handler_name=str(row[9] or "").strip() if len(row) > 9 else "",
                    status=order_status,
                    brand=str(row[10] or "").strip() if len(row) > 10 else "",
                ))
                imported += 1
                if len(wt_batch) >= 1000:
                    db.bulk_save_objects(wt_batch)
                    db.commit()
                    wt_batch.clear()
                    if progress_cb:
                        progress_cb(0.1 + 0.8 * imported / total_rows)

            except Exception as e:
                skipped += 1
                if skipped <= 10:
                    print(f"  行{row_idx}异常: {e}")

        if wt_batch:
            db.bulk_save_objects(wt_batch)
            db.commit()
        wb.close()
        if progress_cb:
            progress_cb(1.0)
        print(f"[同步] 工单明细完成: 导入{imported}, 跳过{skipped}")
        return {"imported": imported, "skipped": skipped}

    @staticmethod
    def _import_snapshots_from_excel(file_path: str, batch_id: int, db: Session,
                                     progress_cb=None) -> dict:
        """从随手拍Excel导入，修复合并单元格问题：
        Excel中A-E列存在大量合并单元格（跨多行），
        旧代码 read_only=True 只读首行值，后续成员行emp_id为空 → 统计丢失大量记录。
        现在：对每个合并首行，按其span展开写入span条独立记录。
        """
        import openpyxl
        import json

        print(f"[同步] 读取随手拍: {Path(file_path).name}")

        # Step 1: 普通模式预扫描，构建合并单元格信息
        wb_map = openpyxl.load_workbook(file_path, data_only=True)
        ws_map = wb_map.active

        # row_idx -> span（合并跨行数，1=非合并）
        row_span = {}
        # 成员行（非首行）-> 对应的首行号
        member_to_first = {}

        for mr in ws_map.merged_cells.ranges:
            if mr.max_col >= 1 and mr.min_col <= 5:  # 只处理A-E列
                min_r, max_r = mr.min_row, mr.max_row
                span = max_r - min_r + 1
                row_span[min_r] = span
                for r in range(min_r + 1, max_r + 1):
                    member_to_first[r] = min_r

        # row_idx -> A-E列的值（元组，共5列）
        row_a_to_e = {}
        for row_idx in range(2, ws_map.max_row + 1):
            vals = [ws_map.cell(row_idx, c).value for c in range(1, 6)]
            row_a_to_e[row_idx] = vals

        wb_map.close()
        print(f"[同步] 合并单元格: {len(row_span)}个首行, {len(member_to_first)}个成员行")

        # Step 2: 查询映射配置
        mappings = db.query(ProjectNameMapping).all()
        name_map = {m.bi_name: m.standard_name for m in mappings}
        projects = db.query(Project).all()
        projects_by_name = {p.name: p.id for p in projects}
        for p in projects:
            if p.bi_names:
                bi_list = json.loads(p.bi_names) if isinstance(p.bi_names, str) else p.bi_names
                for bn in bi_list:
                    if bn not in projects_by_name:
                        projects_by_name[bn] = p.id

        # Step 3: 暴力覆盖删除旧数据
        snap_deleted = db.query(Snapshot).delete()
        db.commit()
        print(f"[同步] 已清除旧随手拍: snapshots={snap_deleted}")
        if progress_cb:
            progress_cb(0.05)

        # Step 4: 用 read_only 高效迭代
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active

        imported = 0
        skipped = 0
        snap_batch = []
        # 用于进度：估算展开后的总行数（所有span之和）
        est_total = sum(span for span in row_span.values())

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            try:
                if not row or len(row) < 6:
                    skipped += 1
                    continue

                # 判断该行的类型
                span = row_span.get(row_idx, 1)          # span=1表示非合并
                is_merge_start = row_idx in row_span      # 是否是合并首行
                is_member = row_idx in member_to_first   # 是否是成员行

                if is_member:
                    # 成员行已被首行的展开覆盖，跳过
                    continue

                # 独立行 span=1，合并首行 span>=1
                # 都需要按span展开

                # 获取A-E列值（来自预扫描的row_a_to_e）
                a_to_e = row_a_to_e.get(row_idx, [None] * 5)
                emp_id_raw = a_to_e[0]
                emp_name_raw = a_to_e[1]
                dept_raw = a_to_e[2]

                # 获取F+列值（来自iter_rows，当前行数据）
                time_val = row[5] if len(row) > 5 else None
                problem_type = str(row[6] or "").strip() if len(row) > 6 else ""
                raw_status = str(row[11] or "").strip() if len(row) > 11 else ""
                complete_time_val = row[12] if len(row) > 12 else None
                handler_id_raw = row[13] if len(row) > 13 else None
                handler_name_raw = row[14] if len(row) > 14 else None
                desc_raw = row[7] if len(row) > 7 else None

                if raw_status == "已解决":
                    order_status = "已完成"
                elif raw_status in ("待处理", "未处理"):
                    order_status = "待处理"
                else:
                    order_status = raw_status or "处理中"

                # 解析项目
                raw_project = ""
                standard_name = ""
                project_id = None
                if dept_raw and '/' in str(dept_raw):
                    possible_name = str(dept_raw).split('/')[0].strip()
                    mapped = name_map.get(possible_name)
                    if mapped:
                        raw_project = possible_name
                        standard_name = mapped
                        project_id = projects_by_name.get(standard_name)
                    else:
                        for p in projects:
                            if p.name in possible_name or possible_name in p.name:
                                standard_name = p.name
                                project_id = p.id
                                raw_project = possible_name
                                break

                initiator_id = _clean_id(emp_id_raw)
                initiator_name = str(emp_name_raw or "").strip()
                handler_id = _clean_id(handler_id_raw) if handler_id_raw else None
                handler_name = str(handler_name_raw or "").strip() if handler_name_raw else ""

                # 对每个span，生成一条独立记录
                for seq in range(span):
                    ticket_no = f"S{row_idx:08d}_{seq:02d}"

                    snap_batch.append(Snapshot(
                        ticket_no=ticket_no,
                        project_name=raw_project,
                        standard_name=standard_name,
                        project_id=project_id,
                        order_type=problem_type,
                        order_status=order_status,
                        initiator_id=initiator_id,
                        initiator_name=initiator_name,
                        handler_id=handler_id,
                        handler_name=handler_name,
                        create_time=_parse_datetime(time_val),
                        complete_time=_parse_datetime(complete_time_val),
                        area_name=str(dept_raw)[:50] if dept_raw else None,
                        description=str(desc_raw)[:500] if desc_raw else None,
                        sync_batch_id=batch_id,
                    ))
                    imported += 1

                if len(snap_batch) >= 1000:
                    db.bulk_save_objects(snap_batch)
                    db.commit()
                    snap_batch.clear()
                    if progress_cb and est_total > 0:
                        progress_cb(0.05 + 0.90 * imported / est_total)

            except Exception as e:
                skipped += 1
                if skipped <= 10:
                    print(f"  行{row_idx}异常: {e}")

        if snap_batch:
            db.bulk_save_objects(snap_batch)
            db.commit()

        wb.close()
        if progress_cb:
            progress_cb(1.0)

        print(f"[同步] 随手拍完成: 导入{imported}, 跳过{skipped}")
        return {"imported": imported, "skipped": skipped}

    @staticmethod
    def _refresh_name_mappings(db: Session):
        raw_names = db.execute(text(
            "SELECT DISTINCT project_name FROM work_tickets WHERE project_name IS NOT NULL"
        )).fetchall()
        for (raw_name,) in raw_names:
            existing = db.query(ProjectNameMapping).filter(
                ProjectNameMapping.bi_name == raw_name
            ).first()
            if not existing:
                db.add(ProjectNameMapping(bi_name=raw_name, standard_name=raw_name, source="bi"))
        db.commit()

    @staticmethod
    def get_sync_logs(page: int = 1, page_size: int = 10, db: Session = None) -> dict:
        query = db.query(SyncLog).order_by(SyncLog.started_at.desc())
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        return {
            "total": total,
            "page": page,
            "pageSize": page_size,
            "items": [
                {
                    "id": log.id,
                    "syncType": log.sync_type,
                    "projectId": str(log.project_id) if log.project_id else None,
                    "status": log.status,
                    "startedAt": log.started_at.isoformat() if log.started_at else None,
                    "completedAt": log.finished_at.isoformat() if log.finished_at else None,
                    "ticketsSynced": log.tickets_synced,
                    "snapshotsSynced": log.snapshots_synced,
                    "errorMessage": log.error_message,
                }
                for log in items
            ],
        }
