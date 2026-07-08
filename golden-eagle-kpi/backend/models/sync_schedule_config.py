"""金鹰工单KPI管理 - 定时同步任务配置模型

任务制设计：每个任务可选择多个通道，设定执行时间
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from backend.database import Base
import datetime


class SyncScheduleConfig(Base):
    """定时同步任务配置（任务制，每行一个任务）"""
    __tablename__ = "sync_schedule_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), default='', comment="任务名称")
    channels = Column(Text, default='["wy","ipms"]', comment="通道列表JSON: bi/wy/ipms")
    cron_times = Column(Text, default='["08:00"]', comment="执行时间点JSON数组")
    enabled = Column(Boolean, default=True, comment="是否启用")
    last_run_time = Column(DateTime, nullable=True, comment="上次执行时间")
    last_run_result = Column(String(100), nullable=True, comment="上次执行结果")
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "name": self.name or f"任务{self.id}",
            "channels": json.loads(self.channels) if self.channels else [],
            "cron_times": json.loads(self.cron_times) if self.cron_times else [],
            "enabled": self.enabled,
            "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
            "last_run_result": self.last_run_result,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
