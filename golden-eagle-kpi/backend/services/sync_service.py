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


# 同步状态（进程内缓存）
_sync_status = {
    "is_syncing": False,
    "current_task": None,
    "progress": 0,
    "message": "",
    "last_sync_time": None,
    "last_sync_result": None,
}


class SyncService:
    """数据同步：启动爬虫 → 下载Excel → 清洗 → 暴力覆盖入库"""

    @staticmethod
    def get_sync_status() -> dict:
        """获取同步状态"""
        # 如果没有最近时间（服务器重启后），从数据库读取
        last_time = _sync_status["last_sync_time"]
        if not last_time:
            from backend.database import get_session_local
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
        """从数据库获取最近一次成功同步的时间"""
        row = db.execute(
            text("SELECT finished_at FROM sync_logs WHERE status='completed' ORDER BY id DESC LIMIT 1")
        ).fetchone()
        # SQLite存储为TEXT(ISO格式字符串)，直接返回
        return row[0] if row and row[0] else None

    @staticmethod
    async def _run_sync_task(account: str, password: str, project_id: int):
        """后台执行同步任务（不阻塞API响应）

        进度节点（按实际耗时比例分配）：
          0-5%   登录BI系统 (~5s)
          5-25%  下载工单明细 (~30s)
          25-40% 下载随手拍 (~20s)
          40-80% 入库工单明细 (~60s, 内部细分)
          80-95% 入库随手拍 (~30s, 内部细分)
          95-100 刷新映射 (~2s)
        """
        # === 浏览器环境检测 ===
        try:
            from backend.scraper.bi_client import BiClient
        except ImportError as e:
            _sync_status["is_syncing"] = False
            _sync_status["progress"] = 0
            _sync_status["message"] = "同步功能不可用：缺少Playwright库，请联系管理员"
            _sync_status["last_sync_result"] = "failed"
            return
        except Exception as e:
            _sync_status["is_syncing"] = False
            _sync_status["progress"] = 0
            _sync_status["message"] = f"同步功能初始化失败: {e}"
            _sync_status["last_sync_result"] = "failed"
            return

        # 预检 Playwright async_api 能否正常加载（driver 模块可能被排除）
        try:
            from playwright.async_api import async_playwright
            # 进一步检查 driver 是否可用
            from playwright._impl._driver import compute_driver_executable
            _driver_info = compute_driver_executable()
            # 兼容新旧版playwright：返回可能是tuple或单个路径
            if isinstance(_driver_info, tuple):
                driver_exe, cli_path = _driver_info[0], _driver_info[1]
            else:
                driver_exe, cli_path = _driver_info, None
            if not Path(driver_exe).exists():
                raise FileNotFoundError(f"Playwright node 不存在: {driver_exe}")
            if cli_path and not Path(cli_path).exists():
                raise FileNotFoundError(f"Playwright cli.js 不存在: {cli_path}")
        except ImportError as e:
            _sync_status["is_syncing"] = False
            _sync_status["progress"] = 0
            _sync_status["message"] = f"同步功能不可用：Playwright组件缺失({e})"
            _sync_status["last_sync_result"] = "failed"
            return
        except FileNotFoundError as e:
            _sync_status["is_syncing"] = False
            _sync_status["progress"] = 0
            _sync_status["message"] = f"同步功能不可用：Playwright驱动未找到，请重新安装程序"
            _sync_status["last_sync_result"] = "failed"
            return
        except Exception as e:
            _sync_status["is_syncing"] = False
            _sync_status["progress"] = 0
            _sync_status["message"] = f"Playwright环境检查失败: {e}"
            _sync_status["last_sync_result"] = "failed"
            return

        # 检测浏览器（优先 Chrome，降级 Edge）
        import shutil
        _browser_channel = None
        _browser_name = ""

        # Chrome 候选
        chrome_candidates = [
            shutil.which("chrome"),
            shutil.which("google-chrome"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for p in chrome_candidates:
            if p and Path(p).exists():
                _browser_channel = "chrome"
                break

        # Edge 候选（Windows 自带）
        if not _browser_channel:
            edge_candidates = [
                shutil.which("msedge"),
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ]
            for p in edge_candidates:
                if p and Path(p).exists():
                    _browser_channel = "msedge"
                    break

        # 注册表兜底
        if not _browser_channel:
            try:
                import winreg
                for reg_root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                    for exe_key, ch in [("chrome.exe", "chrome"), ("msedge.exe", "msedge")]:
                        try:
                            key = winreg.OpenKey(reg_root, f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{exe_key}")
                            reg_path, _ = winreg.QueryValueEx(key, "")
                            winreg.CloseKey(key)
                            if reg_path and Path(reg_path).exists():
                                _browser_channel = ch
                                raise StopIteration
                        except StopIteration:
                            break
                        except (FileNotFoundError, OSError):
                            continue
            except StopIteration:
                pass
            except Exception:
                pass

        if not _browser_channel:
            _sync_status["is_syncing"] = False
            _sync_status["progress"] = 0
            _sync_status["message"] = (
                "未检测到浏览器。需要 Google Chrome 或 Microsoft Edge。\n"
                "请安装任一浏览器后重试：\n"
                "  Chrome: https://www.google.com/chrome/\n"
                "  Edge: https://www.microsoft.com/edge"
            )
            return

        _browser_name = "Chrome" if _browser_channel == "chrome" else "Microsoft Edge"
        print(f"[同步] 检测到浏览器: {_browser_name}")
        from backend.database import get_session_local
        db = get_session_local()()
        try:
            sync_log = SyncLog(
                sync_type="full",
                project_id=project_id,
                status="running",
                started_at=datetime.now(),
            )
            db.add(sync_log)
            db.commit()
            db.refresh(sync_log)

            _sync_status["current_task"] = sync_log.id
            _sync_status["progress"] = 2
            _sync_status["message"] = "正在登录BI系统..."

            client = BiClient(account, password)

            # === 阶段1: 下载工单明细 (5%-25%) ===
            _sync_status["message"] = "正在下载工单明细(15MB)..."
            _sync_status["progress"] = 5
            tickets_file = await client.fetch_tickets()
            if tickets_file:
                _sync_status["message"] = f"工单明细下载完成: {Path(tickets_file).name}"
                _sync_status["progress"] = 25
            else:
                _sync_status["message"] = "工单明细下载失败"
                _sync_status["progress"] = 25

            # === 阶段2: 下载随手拍 (25%-40%) ===
            _sync_status["message"] = "正在下载随手拍(9MB)..."
            _sync_status["progress"] = 28
            snapshots_file = await client.fetch_snapshots()
            if snapshots_file:
                _sync_status["message"] = f"随手拍下载完成: {Path(snapshots_file).name}"
                _sync_status["progress"] = 40
            else:
                _sync_status["message"] = "随手拍下载失败"
                _sync_status["progress"] = 40

            # === 阶段3: 入库工单明细 (40%-80%) ===
            ticket_result = {"imported": 0, "skipped": 0}
            if tickets_file:
                _sync_status["message"] = "正在入库工单数据（覆盖模式）..."
                _sync_status["progress"] = 42
                ticket_result = SyncService._import_tickets_from_excel(
                    tickets_file, sync_log.id, db,
                    progress_cb=lambda p: _update_progress(40, 80, p)
                )
            _sync_status["progress"] = 80

            # === 阶段4: 入库随手拍 (80%-95%) ===
            snapshot_result = {"imported": 0, "skipped": 0}
            if snapshots_file:
                _sync_status["message"] = "正在入库随手拍数据（覆盖模式）..."
                _sync_status["progress"] = 82
                snapshot_result = SyncService._import_snapshots_from_excel(
                    snapshots_file, sync_log.id, db,
                    progress_cb=lambda p: _update_progress(80, 95, p)
                )
            _sync_status["progress"] = 95

            # === 阶段5: 刷新名称映射 (95%-100%) ===
            _sync_status["message"] = "正在更新项目名称映射..."
            _sync_status["progress"] = 97
            SyncService._refresh_name_mappings(db)
            _sync_status["progress"] = 100
            _sync_status["message"] = "同步完成"
            _sync_status["last_sync_result"] = "completed"

            # 持久化到数据库
            sync_log.status = "completed"
            sync_log.finished_at = datetime.now()
            sync_log.tickets_synced = ticket_result["imported"]
            sync_log.snapshots_synced = snapshot_result["imported"]
            db.commit()

            _sync_status["last_sync_time"] = datetime.now().isoformat()

        except Exception as e:
            _sync_status["message"] = f"同步失败: {str(e)}"
            _sync_status["last_sync_result"] = "failed"
            traceback.print_exc()
            if _sync_status["current_task"]:
                log = db.query(SyncLog).filter(SyncLog.id == _sync_status["current_task"]).first()
                if log:
                    log.status = "failed"
                    log.finished_at = datetime.now()
                    log.error_message = str(e)
                    db.commit()

        finally:
            db.close()  # 关闭独立会话
            _sync_status["is_syncing"] = False
            _sync_status["current_task"] = None
            # 保留 progress 和 message 供前端读取最后一次状态
            # 延迟清零，让前端轮询能读到最终状态
            import asyncio as _aio
            _aio.get_event_loop().call_later(5, _reset_sync_progress)

    @staticmethod
    def _import_tickets_from_excel(file_path: str, batch_id: int, db: Session,
                                    progress_cb=None) -> dict:
        """从下载的Excel文件导入工单数据（暴力覆盖：先删后插）"""
        import openpyxl

        print(f"[同步] 读取工单明细: {Path(file_path).name}")
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active

        # 获取项目名称映射
        mappings = db.query(ProjectNameMapping).all()
        name_map = {m.bi_name: m.standard_name for m in mappings}
        projects = db.query(Project).all()
        projects_by_name = {p.name: p.id for p in projects}

        # === 暴力覆盖：先删除所有工单明细数据 ===
        deleted = db.query(WorkTicket).filter(WorkTicket.source == "detail").delete()
        db.commit()
        print(f"[同步] 已清除旧工单明细 {deleted} 条，开始全量导入...")
        if progress_cb:
            progress_cb(0.05)  # 删完了5%

        # 先数总行数（用于进度计算）
        total_rows = 0
        for _ in ws.iter_rows(min_row=2, values_only=True):
            total_rows += 1
        # 重新打开（read_only模式不能rewind）
        wb.close()
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active

        imported = 0
        skipped = 0
        batch = []

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            try:
                if not row or len(row) < 10:
                    skipped += 1
                    continue

                ticket_no = str(row[2] or "").strip()  # 工单编号id
                if not ticket_no:
                    skipped += 1
                    continue

                raw_project = str(row[1] or "").strip()
                standard_name = name_map.get(raw_project, raw_project)
                project_id = projects_by_name.get(standard_name)

                # 品牌→工单类型
                brand = str(row[4] or "").strip()
                order_type = str(row[7] or "").strip()

                # 当前节点→状态
                current_node = str(row[9] or "").strip()
                if current_node == "已解决":
                    order_status = "已完成"
                elif current_node in ("待处理", "待派单", "待接单"):
                    order_status = "待处理"
                else:
                    order_status = current_node or "处理中"

                initiator_id = _clean_id(row[11])  # 派单人工号
                initiator_name = str(row[12] or "").strip()

                # 处理人（第18/19列）
                handler_id = _clean_id(row[18]) if len(row) > 18 and row[18] else None
                handler_name = str(row[19] or "").strip() if len(row) > 19 else ""

                create_time = _parse_datetime(row[5])
                complete_time = _parse_datetime(row[20])
                deadline = _parse_datetime(row[6])
                accept_time = _parse_datetime(row[14])

                area_name = str(row[3] or "").strip()
                description = str(row[8] or "").strip()

                # 工单类型推断（基于品牌字段）
                ticket_type = None
                if brand == '秩序报修':
                    ticket_type = '秩序报修'
                elif brand == '保洁报修':
                    ticket_type = '保洁报修'

                batch.append(WorkTicket(
                    ticket_no=ticket_no,
                    project_name=raw_project,
                    standard_name=standard_name,
                    project_id=project_id,
                    order_type=order_type,
                    order_status=order_status,
                    initiator_id=initiator_id,
                    initiator_name=initiator_name,
                    handler_id=handler_id,
                    handler_name=handler_name,
                    create_time=create_time,
                    accept_time=accept_time,
                    complete_time=complete_time,
                    deadline=deadline,
                    area_name=area_name,
                    description=description[:500] if description else None,
                    sync_batch_id=batch_id,
                    source="detail",
                    ticket_type=ticket_type,
                    brand=brand,
                ))
                imported += 1

                # 每1000条批量提交
                if len(batch) >= 1000:
                    db.bulk_save_objects(batch)
                    db.commit()
                    batch.clear()
                    # 更新进度
                    if progress_cb and total_rows > 0:
                        progress_cb(0.05 + 0.9 * (imported + skipped) / total_rows)
                    print(f"  ...已导入 {imported} 条")

            except Exception as e:
                skipped += 1
                if skipped <= 10:
                    print(f"  行{row_idx}异常: {e}")
                continue

        # 提交剩余数据
        if batch:
            db.bulk_save_objects(batch)
            db.commit()

        wb.close()

        if progress_cb:
            progress_cb(1.0)

        print(f"[同步] 工单导入完成: 导入{imported}, 跳过{skipped}")
        return {"imported": imported, "skipped": skipped}

    @staticmethod
    def _import_snapshots_from_excel(file_path: str, batch_id: int, db: Session,
                                      progress_cb=None) -> dict:
        """从下载的Excel文件导入随手拍数据（暴力覆盖：先删后插）

        数据源规则：
          - 内部员工发起统计从 snapshots 表查询（按initiator_id匹配人力清单）
          - 外包统计从 work_tickets 表查询（按brand字段）
          - 所以随手拍只写 snapshots 表，不双写 work_tickets
        """
        import openpyxl
        import json

        print(f"[同步] 读取随手拍: {Path(file_path).name}")
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active

        mappings = db.query(ProjectNameMapping).all()
        name_map = {m.bi_name: m.standard_name for m in mappings}
        projects = db.query(Project).all()
        projects_by_name = {p.name: p.id for p in projects}
        # 同时用BI名映射
        for p in projects:
            if p.bi_names:
                bi_list = json.loads(p.bi_names) if isinstance(p.bi_names, str) else p.bi_names
                for bn in bi_list:
                    if bn not in projects_by_name:
                        projects_by_name[bn] = p.id

        # === 暴力覆盖：先删除所有随手拍数据（仅snapshots表） ===
        snap_deleted = db.query(Snapshot).delete()
        db.commit()
        print(f"[同步] 已清除旧随手拍: snapshots={snap_deleted}")
        if progress_cb:
            progress_cb(0.05)

        # 先数总行数
        total_rows = 0
        for _ in ws.iter_rows(min_row=2, values_only=True):
            total_rows += 1
        wb.close()
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active

        imported = 0
        skipped = 0
        snap_batch = []      # snapshots 表

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            try:
                if not row or len(row) < 6:
                    skipped += 1
                    continue

                ticket_no = f"S{row_idx:08d}"

                initiator_id = _clean_id(row[0])
                initiator_name = str(row[1] or "").strip()
                # 处理人（第13/14列）
                handler_id = _clean_id(row[13]) if len(row) > 13 and row[13] else None
                handler_name = str(row[14] or "").strip() if len(row) > 14 else ""
                create_time = _parse_datetime(row[5])
                problem_type = str(row[6] or "").strip()

                raw_status = str(row[11] or "").strip()
                if raw_status == "已解决":
                    order_status = "已完成"
                elif raw_status in ("待处理", "未处理"):
                    order_status = "待处理"
                else:
                    order_status = raw_status or "处理中"

                complete_time = _parse_datetime(row[12])

                # 项目匹配
                raw_project = ""
                standard_name = ""
                project_id = None

                dept = str(row[2] or "").strip()
                if dept and '/' in dept:
                    possible_name = dept.split('/')[0].strip()
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

                description = str(row[7] or "").strip()

                # 写入 snapshots 表
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
                    create_time=create_time,
                    complete_time=complete_time,
                    area_name=dept[:50] if dept else None,
                    description=description[:500] if description else None,
                    sync_batch_id=batch_id,
                ))

                imported += 1

                # 每1000条批量提交
                if len(snap_batch) >= 1000:
                    db.bulk_save_objects(snap_batch)
                    db.commit()
                    snap_batch.clear()
                    if progress_cb and total_rows > 0:
                        progress_cb(0.05 + 0.9 * (imported + skipped) / total_rows)
                    print(f"  ...已导入 {imported} 条")

            except Exception as e:
                skipped += 1
                if skipped <= 10:
                    print(f"  行{row_idx}异常: {e}")
                continue

        # 提交剩余数据
        if snap_batch:
            db.bulk_save_objects(snap_batch)
            db.commit()

        wb.close()

        if progress_cb:
            progress_cb(1.0)

        print(f"[同步] 随手拍导入完成: 导入{imported}, 跳过{skipped}")
        return {"imported": imported, "skipped": skipped}

    @staticmethod
    def _refresh_name_mappings(db: Session):
        """刷新项目名称映射（基于已有数据）"""
        raw_names = db.execute(text(
            "SELECT DISTINCT project_name FROM work_tickets WHERE project_name IS NOT NULL"
        )).fetchall()

        for (raw_name,) in raw_names:
            existing = db.query(ProjectNameMapping).filter(
                ProjectNameMapping.bi_name == raw_name
            ).first()
            if not existing:
                mapping = ProjectNameMapping(bi_name=raw_name, standard_name=raw_name, source="bi")
                db.add(mapping)

        db.commit()

    @staticmethod
    def get_sync_logs(page: int = 1, page_size: int = 10, db: Session = None) -> dict:
        """获取同步日志"""
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


def _update_progress(start_pct: int, end_pct: int, internal_pct: float):
    """将导入内部进度(0~1)映射到全局进度(start_pct~end_pct)"""
    global _sync_status
    p = start_pct + (end_pct - start_pct) * internal_pct
    _sync_status["progress"] = int(min(p, end_pct))


def _parse_datetime(val):
    """解析各种日期时间格式"""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    if not s or s in ('None', 'NaT', ''):
        return None

    # 纯数字格式：20260101001421
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


def _reset_sync_progress():
    """延迟重置同步进度（让前端有机会读取最终状态）"""
    _sync_status["progress"] = 0
