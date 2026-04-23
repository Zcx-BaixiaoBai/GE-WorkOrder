"""金鹰工单KPI管理 - API路由：导出"""
import os
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.services.export_service import ExportService
from backend.config import AppConfig

router = APIRouter(prefix="/api/export", tags=["导出"])


@router.get("/personnel")
def export_personnel(
    projectId: int = Query(None),
    month: str = Query(None),
    db: Session = Depends(get_db),
):
    """导出人力清单Excel"""
    filepath = ExportService.export_personnel(projectId, month, db)
    filename = os.path.basename(filepath)
    return FileResponse(filepath, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=filename)


@router.get("/tickets")
def export_tickets(
    project: str = Query(None),
    status: str = Query(None),
    month: str = Query(None),
    ticketType: str = Query(None),
    keyword: str = Query(None),
    kpiStatus: str = Query(None),
    db: Session = Depends(get_db),
):
    """导出工单明细Excel（按当前筛选条件）"""
    # 支持逗号分隔的多个项目ID
    project_ids = None
    if project:
        project_list = project.split(",")
        if len(project_list) == 1:
            project_ids = int(project_list[0])
        else:
            project_ids = [int(p) for p in project_list]
    
    filters = {
        "project_id": project_ids,
        "status": status.split(",") if status else None,
        "month": month,
        "ticket_type": ticketType.split(",") if ticketType else None,
        "keyword": keyword,
        "kpi_status": kpiStatus.split(",") if kpiStatus else None,
    }
    filepath = ExportService.export_tickets(filters, db)
    filename = os.path.basename(filepath)
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/kpi")
def export_kpi_report(
    projectId: int = Query(...),
    month: str = Query(None),
    db: Session = Depends(get_db),
):
    """导出KPI报表Excel"""
    filepath = ExportService.export_kpi_report(projectId, month, db)
    filename = os.path.basename(filepath)
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/download/{filename}")
def download_export(filename: str):
    """下载导出文件"""
    filepath = os.path.join(str(AppConfig.EXPORTS_DIR), filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
