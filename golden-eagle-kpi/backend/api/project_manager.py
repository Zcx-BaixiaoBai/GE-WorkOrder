"""金鹰工单KPI管理 - API路由：项目负责人维护"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.project_manager import ProjectManager
from backend.models.project import Project

router = APIRouter(prefix="/api/project-managers", tags=["项目负责人"])


@router.get("")
def get_project_managers(
    project_id: int = Query(None, description="项目ID筛选"),
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """获取项目负责人列表"""
    query = db.query(ProjectManager)
    
    if project_id:
        query = query.filter(ProjectManager.project_id == project_id)
    
    query = query.order_by(ProjectManager.project_id)
    
    total = query.count()
    items = query.offset((page - 1) * pageSize).limit(pageSize).all()
    
    # 补充项目名称
    result = []
    for item in items:
        project = db.query(Project).filter(Project.id == item.project_id).first()
        result.append({
            "id": item.id,
            "project_id": item.project_id,
            "project_name": project.name if project else f"项目{item.project_id}",
            "manager_name": item.manager_name,
        })
    
    return {"items": result, "total": total, "page": page, "pageSize": pageSize}


@router.post("")
def create_project_manager(
    data: dict,
    db: Session = Depends(get_db),
):
    """新增项目负责人"""
    project_id = data.get("project_id")
    manager_name = data.get("manager_name", "").strip()
    
    if not project_id or not manager_name:
        raise HTTPException(status_code=400, detail="项目ID和负责人姓名不能为空")
    
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 检查是否已存在该项目的负责人
    existing = db.query(ProjectManager).filter(
        ProjectManager.project_id == project_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"项目【{project.name}】已存在负责人【{existing.manager_name}】，请先删除再添加")
    
    pm = ProjectManager(project_id=project_id, manager_name=manager_name)
    db.add(pm)
    db.commit()
    db.refresh(pm)
    
    return {"id": pm.id, "project_id": pm.project_id, "manager_name": pm.manager_name}


@router.put("/{pm_id}")
def update_project_manager(
    pm_id: int,
    data: dict,
    db: Session = Depends(get_db),
):
    """更新项目负责人"""
    pm = db.query(ProjectManager).filter(ProjectManager.id == pm_id).first()
    if not pm:
        raise HTTPException(status_code=404, detail="项目负责人不存在")
    
    manager_name = data.get("manager_name", "").strip()
    if not manager_name:
        raise HTTPException(status_code=400, detail="负责人姓名不能为空")
    
    pm.manager_name = manager_name
    db.commit()
    
    return {"id": pm.id, "project_id": pm.project_id, "manager_name": pm.manager_name}


@router.delete("/{pm_id}")
def delete_project_manager(
    pm_id: int,
    db: Session = Depends(get_db),
):
    """删除项目负责人"""
    pm = db.query(ProjectManager).filter(ProjectManager.id == pm_id).first()
    if not pm:
        raise HTTPException(status_code=404, detail="项目负责人不存在")
    
    db.delete(pm)
    db.commit()
    
    return {"success": True}
