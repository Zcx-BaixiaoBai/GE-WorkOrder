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
            _sync_status["current_task"] = "登录BI并下载报表..."
            _sync_status["progress"] = 2
            # 一次登录下载两个报表，比分开调用快一倍
            files = await client.fetch_all()
            tickets_file = files[0] if len(files) > 0 else None
            snapshots_file = files[1] if len(files) > 1 else None
            if tickets_file:
                _sync_status["message"] = f"工单明细: {Path(tickets_file).name}"
            if snapshots_file:
                _sync_status["message"] = f"随手拍: {Path(snapshots_file).name}"

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
        # O(1) 查找：标准名→id
        projects_by_name = {p.name: p.id for p in projects}
        # O(1) 查找：bi别名→id
        for p in projects:
            if p.bi_names:
                bi_list = json.loads(p.bi_names) if isinstance(p.bi_names, str) else p.bi_names
                for bn in bi_list:
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
                        # O(1) 命中 bi 别名
                        project_id = projects_by_name.get(raw_project)
                        if project_id:
                            standard_name = raw_project

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
        """从随手拍Excel导入，使用 zip+XML 直接解析（无需openpyxl加载整个文件）。
        性能：~9s vs 旧版 openpyxl 两遍 35s。
        合并单元格处理：read_only 模式下合并首行有值、成员行为 None，
        通过解析 sheetXML 中的 <mergeCells> 节点获取 span，按 span 展开写入。
        """
        import zipfile
        import xml.etree.ElementTree as ET
        import json
        import re

        print(f"[同步] 读取随手拍: {Path(file_path).name}")

        # ---- 构建映射表（一次DB查询，O(1)查找）----
        mappings = db.query(ProjectNameMapping).all()
        name_map = {m.bi_name: m.standard_name for m in mappings}
        projects = db.query(Project).all()
        projects_by_name = {p.name: p.id for p in projects}
        for p in projects:
            if p.bi_names:
                bi_list = json.loads(p.bi_names) if isinstance(p.bi_names, str) else p.bi_names
                for bn in bi_list:
                    projects_by_name[bn] = p.id

        # ---- 删除旧数据 ----
        snap_deleted = db.query(Snapshot).delete()
        db.commit()
        print(f"[同步] 已清除旧随手拍: snapshots={snap_deleted}")
        if progress_cb:
            progress_cb(0.02)

        # ---- 从 xlsx zip 直接读取 XML（绕过 openpyxl 加载整个文件）----
        shared_strings = []
        with zipfile.ZipFile(file_path, 'r') as z:
            # 加载字符串表
            if 'xl/sharedStrings.xml' in z.namelist():
                with z.open('xl/sharedStrings.xml') as f:
                    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
                    for si in ET.parse(f).getroot().findall(f'{{{ns}}}si'):
                        t = si.find(f'{{{ns}}}t')
                        if t is not None:
                            shared_strings.append(t.text or '')
                        else:
                            parts = [r.find(f'{{{ns}}}t').text or ''
                                     for r in si.findall(f'{{{ns}}}r')
                                     if r.find(f'{{{ns}}}t') is not None]
                            shared_strings.append(''.join(parts))
            # 读取 sheet1
            with z.open('xl/worksheets/sheet1.xml') as f:
                sheet_xml = f.read()

        tree = ET.fromstring(sheet_xml)
        ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'

        # ---- 解析 mergeCells，构建 row_span 和 member_rows ----
        row_span = {}
        member_rows = set()
        merge_el = tree.find(f'.//{{{ns}}}mergeCells')
        if merge_el is not None:
            for mc in merge_el.findall(f'{{{ns}}}mergeCell'):
                ref = mc.get('ref', '')
                if ':' not in ref:
                    continue
                parts = ref.split(':')
                # 解析 A1 -> (1,1), B5 -> (5,2)
                def col_num(c):
                    n = 0
                    for ch in c.upper():
                        n = n * 26 + ord(ch) - 64
                    return n
                def parse_ref(r):
                    m = re.match(r'([A-Z]+)(\d+)', r)
                    return (int(m.group(2)), col_num(m.group(1))) if m else (1, 1)
                r1, c1 = parse_ref(parts[0])
                r2, c2 = parse_ref(parts[1])
                if c2 >= 1 and c1 <= 5:  # 只处理A-E列
                    span = r2 - r1 + 1
                    row_span[r1] = span
                    for r in range(r1 + 1, r2 + 1):
                        member_rows.add(r)

        print(f"[同步] 合并单元格: {len(row_span)}个首行, {len(member_rows)}个成员行")
        if progress_cb:
            progress_cb(0.05)

        # ---- 解析所有单元格，构建 row_data ----
        row_data = {}
        for row_el in tree.findall(f'.//{{{ns}}}row'):
            row_idx = int(row_el.get('r', 0))
            if row_idx < 2:
                continue
            row_dict = {}
            for c_el in row_el.findall(f'{{{ns}}}c'):
                ref = c_el.get('r', '')
                m = re.match(r'([A-Z]+)(\d+)', ref)
                if not m:
                    continue
                col = col_num(m.group(1))
                t_type = c_el.get('t', '')
                v_el = c_el.find(f'{{{ns}}}v')
                if v_el is None or v_el.text is None:
                    row_dict[col] = None
                    continue
                if t_type == 's':
                    row_dict[col] = shared_strings[int(v_el.text)]
                else:
                    row_dict[col] = v_el.text
            row_data[row_idx] = row_dict

        print(f"[同步] 解析行数: {len(row_data)}")
        if progress_cb:
            progress_cb(0.10)

        # ---- 批量写入 ----
        imported = 0
        skipped = 0
        snap_batch = []
        est_total = sum(row_span.values())

        for row_idx in range(2, max(row_data.keys()) + 1):
            if row_idx in member_rows:
                continue
            row = row_data.get(row_idx, {})
            if not row:
                skipped += 1
                continue

            span = row_span.get(row_idx, 1)

            # A-E列
            emp_id_raw = row.get(1)    # A列：工号
            emp_name_raw = row.get(2)  # B列：姓名
            dept_raw = row.get(4)      # D列：部门/项目

            # F+列
            time_val = row.get(6)          # F列：时间
            problem_type = str(row.get(7) or '').strip()  # G列
            desc_raw = row.get(8)                       # H列
            raw_status = str(row.get(12) or '').strip() # L列：状态
            complete_time_val = row.get(13)             # M列
            handler_id_raw = row.get(14)                 # N列
            handler_name_raw = row.get(15)               # O列

            if raw_status == "已解决":
                order_status = "已完成"
            elif raw_status in ("待处理", "未处理"):
                order_status = "待处理"
            else:
                order_status = raw_status or "处理中"

            # O(1) 项目解析
            raw_project = ""
            standard_name = ""
            project_id = None
            if dept_raw and '/' in str(dept_raw):
                possible_name = str(dept_raw).split('/')[0].strip()
                standard_name = name_map.get(possible_name, "")
                if standard_name:
                    project_id = projects_by_name.get(standard_name)
                else:
                    project_id = projects_by_name.get(possible_name)
                    if project_id:
                        standard_name = possible_name
                if project_id:
                    raw_project = possible_name

            initiator_id = _clean_id(emp_id_raw)
            initiator_name = str(emp_name_raw or '').strip()
            handler_id = _clean_id(handler_id_raw) if handler_id_raw else None
            handler_name = str(handler_name_raw or '').strip() if handler_name_raw else ''

            for seq in range(span):
                snap_batch.append(Snapshot(
                    ticket_no=f"S{row_idx:08d}_{seq:02d}",
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
                    progress_cb(0.10 + 0.88 * imported / est_total)

        if snap_batch:
            db.bulk_save_objects(snap_batch)
            db.commit()

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
