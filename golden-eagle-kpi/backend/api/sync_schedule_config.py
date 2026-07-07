"""金鹰工单KPI管理 - API路由：定时同步配置

仅系统管理员可访问。
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List
from backend.database import get_db
from backend.models.sync_schedule_config import SyncScheduleConfig
from backend.services.auth_service import AuthService
from backend.config import AppConfig

router = APIRouter(prefix="/api/config/sync-schedule", tags=["定时同步配置"])


def _require_super_admin(authorization: str = Header(None), db: Session = Depends(get_db)):
    """验证系统管理员权限"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未授权")
    token = authorization[7:]
    user = AuthService.get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Token无效或已过期")
    if user.get("role") not in ("系统管理员", "super_admin"):
        raise HTTPException(status_code=403, detail="需要系统管理员权限")
    return user


def _ensure_default_configs(db: Session):
    """确保三个通道都有默认配置"""
    defaults = [
        {"channel": "bi", "enabled": False, "cron_times": ["08:00", "13:30", "17:00"]},
        {"channel": "wy", "enabled": True, "cron_times": ["08:00", "13:30", "17:00"]},
        {"channel": "ipms", "enabled": True, "cron_times": ["08:00", "13:30", "17:00"]},
    ]
    for d in defaults:
        existing = db.query(SyncScheduleConfig).filter(SyncScheduleConfig.channel == d["channel"]).first()
        if not existing:
            db.add(SyncScheduleConfig(
                channel=d["channel"],
                enabled=d["enabled"],
                cron_times=json.dumps(d["cron_times"]),
            ))
    db.commit()


@router.get("")
def get_sync_schedule(db: Session = Depends(get_db), user=Depends(_require_super_admin)):
    """获取定时同步配置列表"""
    _ensure_default_configs(db)
    configs = db.query(SyncScheduleConfig).order_by(SyncScheduleConfig.channel).all()
    return {"items": [c.to_dict() for c in configs]}


class UpdateScheduleRequest(BaseModel):
    enabled: bool | None = None
    cron_times: List[str] | None = None


@router.put("/{channel}")
def update_sync_schedule(
    channel: str,
    req: UpdateScheduleRequest,
    db: Session = Depends(get_db),
    user=Depends(_require_super_admin),
):
    """更新某个通道的定时配置"""
    if channel not in ("bi", "wy", "ipms"):
        raise HTTPException(status_code=400, detail="通道必须是 bi/wy/ipms")

    _ensure_default_configs(db)
    config = db.query(SyncScheduleConfig).filter(SyncScheduleConfig.channel == channel).first()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    if req.enabled is not None:
        config.enabled = req.enabled
    if req.cron_times is not None:
        # 验证时间格式 HH:MM
        for t in req.cron_times:
            if not isinstance(t, str) or len(t) != 5 or t[2] != ":":
                raise HTTPException(status_code=400, detail=f"时间格式错误: {t}，需要 HH:MM")
        config.cron_times = json.dumps(req.cron_times)

    db.commit()
    db.refresh(config)

    # 触发调度器重新加载（如果APScheduler已启动）
    try:
        from main import _reschedule_sync_jobs
        _reschedule_sync_jobs()
    except Exception:
        pass  # APScheduler可能还未启动

    return config.to_dict()
