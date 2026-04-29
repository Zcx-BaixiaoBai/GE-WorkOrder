"""金鹰工单KPI管理 - API路由：IPMS设备管理同步"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.database import get_db

router = APIRouter(prefix="/api/sync_ipms", tags=["IPMS同步"])


class SyncIPMSRequest(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    username: str | None = None
    password: str | None = None


_ipms_sync_status = {
    "is_syncing": False,
    "progress": 0,
    "message": "",
    "last_sync_time": None,
    "last_result": None,
}


@router.get("/status")
def get_ipms_status():
    """获取同步状态"""
    return _ipms_sync_status


@router.post("/sync")
def sync_ipms(request: SyncIPMSRequest = None, db: Session = Depends(get_db)):
    """同步IPMS数据"""
    global _ipms_sync_status

    if _ipms_sync_status["is_syncing"]:
        return {"error": "同步进行中，请稍后"}

    from datetime import datetime
    import threading

    if request and request.start_date:
        start_date = request.start_date
    else:
        start_date = f"{datetime.now().year}-01-01"

    if request and request.end_date:
        end_date = request.end_date
    else:
        end_date = datetime.now().strftime("%Y-%m-%d")

    username = (request.username or "njjyadmin").strip()
    password = (request.password or "123654").strip()

    def _run():
        global _ipms_sync_status
        _ipms_sync_status["is_syncing"] = True
        _ipms_sync_status["progress"] = 0
        _ipms_sync_status["message"] = "开始同步..."

        try:
            from backend.scraper.ipms_crawler import IPMSCrawler
            from backend.database import get_session_local
            from backend.models.ipms_task import IPMSTask

            session = get_session_local()()

            _ipms_sync_status["progress"] = 10
            _ipms_sync_status["message"] = f"登录IPMS ({username})..."

            crawler = IPMSCrawler()
            if not crawler.login(username, password):
                _ipms_sync_status["message"] = "登录失败，请检查账号密码"
                _ipms_sync_status["is_syncing"] = False
                _ipms_sync_status["last_result"] = "error: login failed"
                session.close()
                return

            total_patrol = 0
            total_maintain = 0

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

                # 分批写入（bulk_save_objects 性能更好）
                def _add_batch(data_list, task_type):
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
                            start_time=_parse_datetime(item.get("fullStartDate")),
                            end_time=_parse_datetime(item.get("fullEndDate")),
                            submit_time=_parse_datetime(item.get("submitDate")),
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

                _add_batch(patrol_data, "patrol")
                _add_batch(maintain_data, "maintain")

                session.commit()
                total = total_patrol + total_maintain
                _ipms_sync_status["message"] = f"完成，巡检{total_patrol}条，维保{total_maintain}条"
                _ipms_sync_status["last_result"] = f"patrol={total_patrol}, maintain={total_maintain}"
            except Exception as e:
                session.rollback()
                _ipms_sync_status["message"] = f"写入失败: {e}"
                _ipms_sync_status["last_result"] = f"error: {e}"
            finally:
                session.close()

            _ipms_sync_status["progress"] = 100
            _ipms_sync_status["is_syncing"] = False
            _ipms_sync_status["last_sync_time"] = datetime.now().isoformat()

        except Exception as e:
            _ipms_sync_status["is_syncing"] = False
            _ipms_sync_status["progress"] = 0
            _ipms_sync_status["message"] = f"同步失败: {e}"
            _ipms_sync_status["last_result"] = f"error: {e}"

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return {
        "message": "同步已启动",
        "start_date": start_date,
        "end_date": end_date,
    }


def _parse_datetime(val):
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
