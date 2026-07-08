"""金鹰工单KPI管理 - API路由：驾驶舱/统计"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, distinct
from backend.database import get_db
from backend.services.stats_service import StatsService

router = APIRouter(prefix="/api/stats", tags=["统计"])


@router.get("/months")
def get_available_months(
    projectId: int = Query(None),
    db: Session = Depends(get_db),
):
    """获取有数据的所有月份 YYYY-MM 列表"""
    if projectId:
        sql = """
            SELECT DISTINCT strftime('%Y-%m', create_time) as month
            FROM work_tickets
            WHERE project_id = :pid AND create_time IS NOT NULL
            UNION ALL
            SELECT DISTINCT strftime('%Y-%m', complete_time) as month
            FROM work_tickets
            WHERE project_id = :pid AND complete_time IS NOT NULL
            ORDER BY month DESC
        """
        rows = db.execute(text(sql), {"pid": projectId}).fetchall()
    else:
        # 无项目过滤时，合并 work_tickets 和 snapshots 的所有月份
        sql = """
            SELECT DISTINCT strftime('%Y-%m', create_time) as month
            FROM work_tickets WHERE create_time IS NOT NULL
            UNION
            SELECT DISTINCT strftime('%Y-%m', complete_time) as month
            FROM work_tickets WHERE complete_time IS NOT NULL
            UNION
            SELECT DISTINCT strftime('%Y-%m', create_time) as month
            FROM snapshots WHERE create_time IS NOT NULL
            UNION
            SELECT DISTINCT strftime('%Y-%m', complete_time) as month
            FROM snapshots WHERE complete_time IS NOT NULL
            ORDER BY month DESC
        """
        rows = db.execute(text(sql)).fetchall()
    months = sorted(set(r[0] for r in rows if r[0]), reverse=True)
    
    # 补充当前月份及前5个月（即使无数据也显示，方便用户选择）
    from datetime import datetime
    now = datetime.now()
    for i in range(6):
        y = now.year
        m = now.month - i
        while m <= 0:
            m += 12
            y -= 1
        month_str = f"{y}-{m:02d}"
        if month_str not in months:
            months.append(month_str)
    months = sorted(months, reverse=True)
    
    return {"months": months}


@router.get("/dashboard")
def get_dashboard_stats(
    projectId: int = Query(None),
    month: str = Query(None),
    db: Session = Depends(get_db),
):
    """驾驶舱统计卡片"""
    return StatsService.get_dashboard_stats(projectId, month, db)


@router.get("/initiation")
def get_initiation(
    projectId: int = Query(...),
    month: str = Query(None),
    db: Session = Depends(get_db),
):
    """四层级发起统计"""
    return StatsService.get_initiation_by_level(projectId, month, db)


@router.get("/warnings")
def get_warnings(
    projectId: int = Query(None),
    level: str = Query(None),
    threshold: float = Query(100),
    month: str = Query(None),
    db: Session = Depends(get_db),
):
    """预警清单

    - projectId 有值：只返回该项目的人（带该项目在全部项目中的排名）
    - projectId 无值：返回全部项目中排名最差的前5个项目的人
    """
    return StatsService.get_warnings(projectId, level, threshold, month, db)


@router.get("/completion")
def get_completion(
    projectId: int = Query(...),
    month: str = Query(None),
    db: Session = Depends(get_db),
):
    """完成情况统计"""
    return StatsService.get_completion(projectId, month, db)


@router.get("/score")
def get_score(
    projectId: int = Query(...),
    month: str = Query(None),
    db: Session = Depends(get_db),
):
    """综合评分"""
    return StatsService.get_score(projectId, month, db)
