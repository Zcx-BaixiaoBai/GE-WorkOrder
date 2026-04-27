"""金鹰工单KPI管理 - API路由：筹建专项同步"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.database import get_db

router = APIRouter(prefix="/api/sync_wy", tags=["筹建专项同步"])


class SyncWYRequest(BaseModel):
    year: int | None = None


_wy_sync_status = {
    "is_syncing": False,
    "progress": 0,
    "message": "",
    "last_sync_time": None,
    "last_result": None,
}


def get_wy_sync_status():
    return _wy_sync_status


@router.get("/status")
def get_wy_status():
    """获取同步状态"""
    return get_wy_sync_status()


@router.post("/sync")
def sync_wy(request: SyncWYRequest = None, db: Session = Depends(get_db)):
    """同步筹建专项数据"""
    global _wy_sync_status

    if _wy_sync_status["is_syncing"]:
        return {"error": "同步进行中，请稍后"}

    from datetime import datetime
    import threading

    year = request.year if request and request.year else datetime.now().year

    def _run():
        global _wy_sync_status
        _wy_sync_status["is_syncing"] = True
        _wy_sync_status["progress"] = 0
        _wy_sync_status["message"] = "开始同步..."
        try:
            from backend.scraper.wy_crawler import Crawler

            crawler = Crawler()
            _wy_sync_status["progress"] = 20
            _wy_sync_status["message"] = "登录系统..."

            crawler.login()

            _wy_sync_status["progress"] = 40
            _wy_sync_status["message"] = "爬取数据..."
            data = crawler.crawl_all(year=year)

            _wy_sync_status["progress"] = 70
            _wy_sync_status["message"] = f"获取 {len(data)} 条，写入数据库..."

            from backend.database import get_session_local
            from backend.models.special_plan import SpecialPlan

            session = get_session_local()()

            try:
                session.query(SpecialPlan).delete()
                session.commit()

                for item in data:
                    sp = SpecialPlan(
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
                        plan_start_date=_parse_date(item.get("plan_start_date")),
                        plan_end_date=_parse_date(item.get("plan_end_date")),
                        plan_cycle=int(item.get("plan_cycle") or 0),
                        real_start_date=_parse_date(item.get("real_start_date")),
                        real_end_date=_parse_date(item.get("real_end_date")),
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
                    )
                    session.add(sp)
                session.commit()
                _wy_sync_status["message"] = f"完成，共 {len(data)} 条"
                _wy_sync_status["last_result"] = f"success: {len(data)} 条"
            except Exception as e:
                session.rollback()
                _wy_sync_status["message"] = f"数据库写入失败: {e}"
                _wy_sync_status["last_result"] = f"error: {e}"
            finally:
                session.close()

            _wy_sync_status["progress"] = 100
            _wy_sync_status["is_syncing"] = False
            from datetime import datetime as dt
            _wy_sync_status["last_sync_time"] = dt.now().isoformat()

        except Exception as e:
            _wy_sync_status["is_syncing"] = False
            _wy_sync_status["progress"] = 0
            _wy_sync_status["message"] = f"同步失败: {e}"
            _wy_sync_status["last_result"] = f"error: {e}"

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return {"message": "同步已启动", "year": year}


def _parse_date(val):
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
