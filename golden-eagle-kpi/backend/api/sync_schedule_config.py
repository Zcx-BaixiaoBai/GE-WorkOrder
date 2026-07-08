"""金鹰工单KPI管理 - API路由：定时同步任务配置（任务制）

仅系统管理员可访问。
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List
from backend.database import get_db
from backend.models.sync_schedule_config import SyncScheduleConfig
from backend.api.auth_deps import require_super_admin

router = APIRouter(prefix="/api/config/sync-schedule", tags=["定时同步配置"])


@router.get("")
def get_sync_schedule(db: Session = Depends(get_db), user: dict = Depends(require_super_admin)):
    """获取所有定时任务"""
    configs = db.query(SyncScheduleConfig).order_by(SyncScheduleConfig.id).all()
    if not configs:
        # 首次使用，创建一个默认任务
        default = SyncScheduleConfig(name="每日全量同步", channels='["wy","ipms"]', cron_times='["08:00","13:30","17:00"]', enabled=True)
        db.add(default)
        db.commit()
        db.refresh(default)
        configs = [default]
    return {"items": [c.to_dict() for c in configs]}


class TaskCreate(BaseModel):
    name: str = ""
    channels: List[str] = []
    cron_times: List[str] = []
    enabled: bool = True


@router.post("")
def create_task(req: TaskCreate, db: Session = Depends(get_db), user: dict = Depends(require_super_admin)):
    """新建定时任务"""
    if not req.channels:
        raise HTTPException(status_code=400, detail="请至少选择一个同步通道")
    if not req.cron_times:
        raise HTTPException(status_code=400, detail="请至少选择一个执行时间")
    task = SyncScheduleConfig(
        name=req.name or f"任务{db.query(SyncScheduleConfig).count() + 1}",
        channels=json.dumps(req.channels),
        cron_times=json.dumps(req.cron_times),
        enabled=req.enabled,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    # 触发调度器重载
    _trigger_reschedule()
    return task.to_dict()


class TaskUpdate(BaseModel):
    name: str | None = None
    channels: List[str] | None = None
    cron_times: List[str] | None = None
    enabled: bool | None = None


@router.put("/{task_id}")
def update_task(task_id: int, req: TaskUpdate, db: Session = Depends(get_db), user: dict = Depends(require_super_admin)):
    """更新定时任务"""
    task = db.query(SyncScheduleConfig).filter(SyncScheduleConfig.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if req.name is not None:
        task.name = req.name
    if req.channels is not None:
        if not req.channels:
            raise HTTPException(status_code=400, detail="请至少选择一个同步通道")
        task.channels = json.dumps(req.channels)
    if req.cron_times is not None:
        if not req.cron_times:
            raise HTTPException(status_code=400, detail="请至少选择一个执行时间")
        task.cron_times = json.dumps(req.cron_times)
    if req.enabled is not None:
        task.enabled = req.enabled
    db.commit()
    db.refresh(task)
    _trigger_reschedule()
    return task.to_dict()


@router.delete("/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db), user: dict = Depends(require_super_admin)):
    """删除定时任务"""
    task = db.query(SyncScheduleConfig).filter(SyncScheduleConfig.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    db.delete(task)
    db.commit()
    _trigger_reschedule()
    return {"success": True}


def _trigger_reschedule():
    """触发调度器重新加载"""
    try:
        import main as _main
        if hasattr(_main, '_reschedule_sync_jobs'):
            _main._reschedule_sync_jobs()
    except Exception:
        pass
