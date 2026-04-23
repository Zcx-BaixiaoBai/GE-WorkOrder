"""金鹰工单KPI管理 - API路由：配置管理"""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.services.config_service import ConfigService

router = APIRouter(prefix="/api/config", tags=["配置管理"])


# === 项目 ===

class ProjectCreate(BaseModel):
    name: str
    area: float | None = None
    outsourcingTarget: float | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    area: float | None = None
    outsourcingTarget: float | None = None
    kpiCompletionRate: float | None = None
    kpiTimelyRate: float | None = None


@router.get("/projects")
def get_projects(db: Session = Depends(get_db)):
    """获取项目列表"""
    return ConfigService.get_projects(db)


@router.post("/projects")
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    """创建项目"""
    return ConfigService.create_project(data.dict(), db)


@router.put("/projects/{project_id}")
def update_project(project_id: int, data: ProjectUpdate, db: Session = Depends(get_db)):
    """更新项目"""
    result = ConfigService.update_project(project_id, data.dict(exclude_unset=True), db)
    if not result:
        raise HTTPException(status_code=404, detail="项目不存在")
    return result


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    """删除项目"""
    success = ConfigService.delete_project(project_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"success": True}


# === 角色映射 ===

class RoleMappingCreate(BaseModel):
    sourceRole: str
    targetRole: str


class RoleMappingUpdate(BaseModel):
    sourceRole: str | None = None
    targetRole: str | None = None


@router.get("/role-mappings")
def get_role_mappings(db: Session = Depends(get_db)):
    """获取角色映射列表"""
    return ConfigService.get_role_mappings(db)


@router.post("/role-mappings")
def create_role_mapping(data: RoleMappingCreate, db: Session = Depends(get_db)):
    """创建角色映射"""
    return ConfigService.create_role_mapping(data.dict(), db)


@router.put("/role-mappings/{mapping_id}")
def update_role_mapping(mapping_id: int, data: RoleMappingUpdate, db: Session = Depends(get_db)):
    """更新角色映射"""
    result = ConfigService.update_role_mapping(mapping_id, data.dict(exclude_unset=True), db)
    if not result:
        raise HTTPException(status_code=404, detail="映射不存在")
    return result


@router.delete("/role-mappings/{mapping_id}")
def delete_role_mapping(mapping_id: int, db: Session = Depends(get_db)):
    """删除角色映射"""
    success = ConfigService.delete_role_mapping(mapping_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="映射不存在")
    return {"success": True}


# === 项目名称映射 ===

class NameMappingCreate(BaseModel):
    biName: str
    standardName: str


class NameMappingUpdate(BaseModel):
    biName: str | None = None
    standardName: str | None = None


@router.get("/name-mappings")
def get_name_mappings(db: Session = Depends(get_db)):
    """获取项目名称映射列表"""
    return ConfigService.get_name_mappings(db)


@router.post("/name-mappings")
def create_name_mapping(data: NameMappingCreate, db: Session = Depends(get_db)):
    """创建项目名称映射"""
    return ConfigService.create_name_mapping(data.dict(), db)


@router.put("/name-mappings/{mapping_id}")
def update_name_mapping(mapping_id: int, data: NameMappingUpdate, db: Session = Depends(get_db)):
    """更新项目名称映射"""
    result = ConfigService.update_name_mapping(mapping_id, data.dict(exclude_unset=True), db)
    if not result:
        raise HTTPException(status_code=404, detail="映射不存在")
    return result


@router.delete("/name-mappings/{mapping_id}")
def delete_name_mapping(mapping_id: int, db: Session = Depends(get_db)):
    """删除项目名称映射"""
    success = ConfigService.delete_name_mapping(mapping_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="映射不存在")
    return {"success": True}


# === 项目负责人清单 ===

@router.get("/projects-manager-list")
def get_projects_manager_list(db: Session = Depends(get_db)):
    """获取项目负责人清单"""
    return ConfigService.get_projects_manager_list(db)


# === KPI全局阈值 ===

class KpiThresholdUpdate(BaseModel):
    leader_target: float = None
    manager_target: float = None
    staff_target: float = None
    vendor_target: float = None
    completion_rate: float = None
    timely_rate: float = None


@router.get("/kpi-thresholds")
def get_kpi_thresholds(db: Session = Depends(get_db)):
    """获取全局KPI阈值配置"""
    return ConfigService.get_kpi_thresholds(db)


@router.put("/kpi-thresholds")
def update_kpi_thresholds(data: KpiThresholdUpdate, db: Session = Depends(get_db)):
    """更新全局KPI阈值配置"""
    return ConfigService.update_kpi_thresholds(data.model_dump(exclude_none=True), db)


# === KPI目标 ===

@router.get("/kpi-targets/{project_id}")
def get_kpi_targets(project_id: int, db: Session = Depends(get_db)):
    """获取KPI目标配置"""
    return ConfigService.get_kpi_targets(project_id, db)


@router.put("/kpi-targets/{project_id}")
def update_kpi_targets(project_id: int, data: dict, db: Session = Depends(get_db)):
    """更新KPI目标"""
    result = ConfigService.update_kpi_targets(project_id, data, db)
    if not result:
        raise HTTPException(status_code=404, detail="项目不存在")
    return result
