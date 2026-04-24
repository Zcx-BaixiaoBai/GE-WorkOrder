"""金鹰工单KPI管理 - API路由：人力清单"""
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.services.personnel_service import PersonnelService

router = APIRouter(prefix="/api/personnel", tags=["人力清单"])


@router.post("/create")
def create_personnel(
    data: dict,
    db: Session = Depends(get_db),
):
    """新增人员"""
    result = PersonnelService.create_personnel(data, db)
    if not result:
        raise HTTPException(status_code=400, detail="创建失败，可能工号已存在")
    return result


@router.get("")
def get_personnel_list(
    projectId: int = Query(None),
    role: str = Query(None),
    keyword: str = Query(None),
    month: str = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    """获取人力清单"""
    return PersonnelService.get_personnel_list(
        project_id=projectId, role=role, keyword=keyword,
        month=month, page=page, page_size=pageSize, db=db,
    )


@router.get("/list")
def get_personnel_list_alias(
    projectId: int = Query(None),
    role: str = Query(None),
    keyword: str = Query(None),
    month: str = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    """获取人力清单（别名，兼容旧路径）"""
    return PersonnelService.get_personnel_list(
        project_id=projectId, role=role, keyword=keyword,
        month=month, page=page, page_size=pageSize, db=db,
    )


@router.post("/import")
async def import_personnel(
    file: UploadFile = File(...),
    mode: str = Query("append", pattern="^(append|replace)$"),
    db: Session = Depends(get_db),
):
    """导入人力清单Excel"""
    file_bytes = await file.read()
    result = PersonnelService.import_personnel(file_bytes, mode, db)
    return result


@router.put("/{personnel_id}")
def update_personnel(
    personnel_id: str,
    data: dict,
    db: Session = Depends(get_db),
):
    """更新人员信息"""
    result = PersonnelService.update_personnel(personnel_id, data, db)
    if not result:
        raise HTTPException(status_code=404, detail="人员不存在")
    return result


@router.delete("/{personnel_id}")
def delete_personnel(personnel_id: str, db: Session = Depends(get_db)):
    """删除人员"""
    success = PersonnelService.delete_personnel(personnel_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="人员不存在")
    return {"success": True}
