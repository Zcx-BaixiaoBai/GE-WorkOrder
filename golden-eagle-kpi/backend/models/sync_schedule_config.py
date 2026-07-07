"""金鹰工单KPI管理 - 定时同步配置模型"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from backend.database import Base
import datetime


class SyncScheduleConfig(Base):
    """定时同步任务配置（每通道一行）"""
    __tablename__ = "sync_schedule_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel = Column(String(20), nullable=False, unique=True, comment="通道: bi/wy/ipms")
    enabled = Column(Boolean, default=True, comment="是否启用")
    cron_times = Column(Text, default='["08:00","13:30","17:00"]', comment="执行时间点JSON数组")
    last_run_time = Column(DateTime, nullable=True, comment="上次执行时间")
    last_run_result = Column(String(50), nullable=True, comment="上次执行结果")
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "channel": self.channel,
            "enabled": self.enabled,
            "cron_times": json.loads(self.cron_times) if self.cron_times else [],
            "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
            "last_run_result": self.last_run_result,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
