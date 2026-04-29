"""金鹰工单KPI管理 - API路由：聚合同步（一次触发三个系统）

设计原则：
- 三个系统并发同步（daemon线程）
- BI 是 async（Playwright），在新事件循环中运行
- WY/IPMS 是 sync（requests），直接在线程中运行
- 状态动态聚合，不维护额外的全局状态
"""

import os
import threading
from fastapi import APIRouter
from backend.services.sync_service import SyncService, _sync_status
from backend.api.sync_wy import get_wy_sync_status, _wy_sync_status
from backend.api.sync_ipms import get_ipms_status, _ipms_sync_status

router = APIRouter(prefix="/api/sync_all", tags=["聚合同步"])

# 爬虫账号
SCRAPER_ACCOUNT = os.environ.get("SCRAPER_ACCOUNT", "zhangchenxi")
SCRAPER_PASSWORD = os.environ.get("SCRAPER_PASSWORD", "Zcx020618")


def _trigger_bi():
    """在子线程中运行 BI 异步同步任务

    关键：BI 使用 Playwright（async），必须创建独立事件循环
    不能用 asyncio.run()（Python 3.12 中会检测到已有线程的事件循环策略冲突）
    """
    import asyncio
    import traceback

    def _run():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    SyncService._run_sync_task(SCRAPER_ACCOUNT, SCRAPER_PASSWORD, 1)
                )
            finally:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()
            print("[BI同步] 线程正常结束")
        except Exception as e:
            traceback.print_exc()
            _sync_status["is_syncing"] = False
            _sync_status["progress"] = 0
            _sync_status["message"] = f"BI同步异常: {e}"
            _sync_status["last_sync_result"] = "failed"
            print(f"[BI同步] 线程异常退出: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _trigger_wy():
    """触发 WY 筹建专项同步（复用 sync_wy.py 的实际同步逻辑）"""
    from datetime import datetime
    from backend.scraper.wy_crawler import Crawler
    from backend.models.special_plan import SpecialPlan
    from backend.database import get_session_local

    def _run():
        _wy_sync_status["is_syncing"] = True
        _wy_sync_status["progress"] = 0
        _wy_sync_status["message"] = "开始同步..."
        try:
            crawler = Crawler()
            _wy_sync_status["progress"] = 20
            _wy_sync_status["message"] = "登录系统..."
            crawler.login()
            _wy_sync_status["progress"] = 40
            _wy_sync_status["message"] = "爬取数据..."
            year = datetime.now().year
            data = crawler.crawl_all(year=year)
            _wy_sync_status["progress"] = 70
            _wy_sync_status["message"] = f"获取 {len(data)} 条，写入数据库..."

            session = get_session_local()()
            try:
                session.query(SpecialPlan).delete()
                session.commit()

                # 分批写入
                batch = []
                for i, item in enumerate(data):
                    batch.append(SpecialPlan(
                        project_code=str(item.get("项目编码", "")),
                        project_name=str(item.get("项目名称", "")),
                        special_id=str(item.get("special_id", "")),
                        special_name=str(item.get("special_name", "")),
                        special_detail_id=str(item.get("special_detail_id", "")),
                        plan_level=str(item.get("plan_level", "")),
                        plan_content=str(item.get("plan_content", "")),
                        plan_dept=str(item.get("plan_dept", "")),
                        plan_person=str(item.get("plan_person", "")),
                        person_name=str(item.get("person_name", "")),
                        plan_start_date=_parse_wy_date(item.get("plan_start_date")),
                        plan_end_date=_parse_wy_date(item.get("plan_end_date")),
                        plan_cycle=int(item.get("plan_cycle") or 0),
                        real_start_date=_parse_wy_date(item.get("real_start_date")),
                        real_end_date=_parse_wy_date(item.get("real_end_date")),
                        real_cycle=int(item.get("real_cycle") or 0),
                        plan_state=str(item.get("plan_state", "")),
                        plan_remark=str(item.get("plan_remark", "")),
                        finish_flag=int(item.get("finish_flag") or 0),
                        danger_flag=int(item.get("danger_flag") or 0),
                        warning_flag=int(item.get("warning_flag") or 0),
                        pause_flag=int(item.get("pause_flag") or 0),
                        score=float(item.get("score") or 0),
                        operate_demand=str(item.get("operate_demand", "")),
                        check_standard=str(item.get("check_standard", "")),
                        remark=str(item.get("remark", "")),
                        attach_count=int(item.get("attach_count") or 0),
                    ))
                    if len(batch) >= 200:
                        session.bulk_save_objects(batch)
                        session.commit()
                        batch.clear()
                if batch:
                    session.bulk_save_objects(batch)
                    session.commit()

                _wy_sync_status["progress"] = 100
                _wy_sync_status["message"] = f"完成，共 {len(data)} 条"
                _wy_sync_status["last_result"] = f"success: {len(data)} 条"
            except Exception as e:
                session.rollback()
                _wy_sync_status["message"] = f"数据库写入失败: {e}"
                _wy_sync_status["last_result"] = f"error: {e}"
            finally:
                session.close()

        except Exception as e:
            import traceback
            traceback.print_exc()
            _wy_sync_status["message"] = f"同步失败: {e}"
            _wy_sync_status["last_result"] = f"error: {e}"
        finally:
            _wy_sync_status["is_syncing"] = False
            _wy_sync_status["last_sync_time"] = datetime.now().isoformat()

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _trigger_ipms():
    """触发 IPMS 维保巡检同步（复用 sync_ipms.py 的实际同步逻辑）"""
    from datetime import datetime
    from backend.scraper.ipms_crawler import IPMSCrawler
    from backend.models.ipms_task import IPMSTask
    from backend.database import get_session_local

    def _run():
        _ipms_sync_status["is_syncing"] = True
        _ipms_sync_status["progress"] = 0
        _ipms_sync_status["message"] = "开始同步..."

        try:
            session = get_session_local()()

            _ipms_sync_status["progress"] = 10
            _ipms_sync_status["message"] = "登录IPMS..."

            crawler = IPMSCrawler()
            if not crawler.login("njjyadmin", "123654"):
                _ipms_sync_status["message"] = "登录失败，请检查账号密码"
                _ipms_sync_status["last_result"] = "error: login failed"
                session.close()
                return

            start_date = f"{datetime.now().year}-01-01"
            end_date = datetime.now().strftime("%Y-%m-%d")

            _ipms_sync_status["progress"] = 30
            _ipms_sync_status["message"] = "爬取巡检任务..."
            patrol_data = crawler.crawl_patrol(start_date, end_date)
            total_patrol = len(patrol_data)
            _ipms_sync_status["progress"] = 60
            _ipms_sync_status["message"] = f"巡检 {total_patrol} 条，爬取维保任务..."

            maintain_data = crawler.crawl_maintain(start_date, end_date)
            total_maintain = len(maintain_data)
            _ipms_sync_status["progress"] = 75
            _ipms_sync_status["message"] = "写入数据库..."

            try:
                session.query(IPMSTask).delete()
                session.commit()

                # 分批写入（巡检和维保分开标记 task_type）
                def _add_ipms_batch(data_list, task_type):
                    batch = []
                    for item in data_list:
                        batch.append(IPMSTask(
                            task_id=str(item.get("taskId", "")),
                            task_type=task_type,
                            project_id=str(item.get("projectId", "")),
                            project_name=str(item.get("projectName", "")),
                            task_name=str(item.get("patrolRuleName", "")),
                            address_name=str(item.get("addressName", "")),
                            sys_name=str(item.get("sysName", "")),
                            user_id=str(item.get("userId", "")),
                            user_name=str(item.get("userName", "")),
                            executor_name=str(item.get("xUserName", "")),
                            start_time=_parse_ipms_datetime(item.get("fullStartDate")),
                            end_time=_parse_ipms_datetime(item.get("fullEndDate")),
                            submit_time=_parse_ipms_datetime(item.get("submitDate")),
                            working_time=int(item.get("workingTime") or 0),
                            task_state=int(item.get("taskState") or 0),
                            task_state_name=str(item.get("taskStateName", "")),
                        ))
                        if len(batch) >= 500:
                            session.bulk_save_objects(batch)
                            session.commit()
                            batch.clear()
                    if batch:
                        session.bulk_save_objects(batch)
                        session.commit()

                _add_ipms_batch(patrol_data, "patrol")
                _add_ipms_batch(maintain_data, "maintain")

                _ipms_sync_status["progress"] = 100
                _ipms_sync_status["message"] = f"完成，巡检{total_patrol}条，维保{total_maintain}条"
                _ipms_sync_status["last_result"] = f"patrol={total_patrol}, maintain={total_maintain}"
            except Exception as e:
                session.rollback()
                _ipms_sync_status["message"] = f"写入失败: {e}"
                _ipms_sync_status["last_result"] = f"error: {e}"
            finally:
                session.close()

        except Exception as e:
            import traceback
            traceback.print_exc()
            _ipms_sync_status["message"] = f"同步失败: {e}"
            _ipms_sync_status["last_result"] = f"error: {e}"
        finally:
            _ipms_sync_status["is_syncing"] = False
            _ipms_sync_status["last_sync_time"] = datetime.now().isoformat()

    t = threading.Thread(target=_run, daemon=True)
    t.start()


@router.get("/status")
def get_sync_all_status():
    """聚合三个系统的同步状态"""
    bi = SyncService.get_sync_status()
    wy = get_wy_sync_status()
    ipms = get_ipms_status()

    # 任意一个在同步中
    any_syncing = bi.get("isSyncing") or wy.get("is_syncing") or ipms.get("is_syncing")

    # 汇总消息
    parts = []
    if bi.get("isSyncing"):
        parts.append(f"BI:{bi.get('message','')}")
    if wy.get("is_syncing"):
        parts.append(f"WY:{wy.get('message','')}")
    if ipms.get("is_syncing"):
        parts.append(f"IPMS:{ipms.get('message','')}")

    if not any_syncing:
        # 全部完成，显示各系统最后结果
        results = []
        if bi.get("lastSyncResult"):
            results.append(f"BI:{bi['lastSyncResult']}")
        if wy.get("last_result"):
            results.append(f"WY:{wy['last_result']}")
        if ipms.get("last_result"):
            results.append(f"IPMS:{ipms['last_result']}")
        msg = "; ".join(results) if results else "就绪"
    else:
        msg = "; ".join(parts) if parts else "同步中"

    return {
        "isSyncing": any_syncing,
        "message": msg,
        "bi": bi,
        "wy": wy,
        "ipms": ipms,
    }


@router.post("/start")
def start_sync_all():
    """同时触发三个系统同步"""
    # 检查是否已有任意系统在同步
    bi = SyncService.get_sync_status()
    wy = get_wy_sync_status()
    ipms = get_ipms_status()

    if bi.get("isSyncing") or wy.get("is_syncing") or ipms.get("is_syncing"):
        return {"success": False, "error": "有系统正在同步中，请稍后"}

    # 同时触发三个系统
    _trigger_bi()
    _trigger_wy()
    _trigger_ipms()

    return {"success": True, "message": "三个系统同步已同时启动"}


# ============================================================
# 辅助函数
# ============================================================

def _parse_wy_date(val):
    if not val:
        return None
    from datetime import datetime
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    if not s or s in ("None", ""):
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _parse_ipms_datetime(val):
    if not val:
        return None
    from datetime import datetime
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    if not s or s in ("None", ""):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None
