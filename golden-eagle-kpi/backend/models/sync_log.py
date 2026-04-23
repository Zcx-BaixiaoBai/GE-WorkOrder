"""金鹰工单KPI管理 - 同步日志模型"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from backend.database import Base


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_type = Column(String(30), nullable=False, comment="full / tickets / snapshots")
    project_id = Column(Integer, nullable=True, comment="项目ID")
    status = Column(String(20), nullable=False, comment="running / completed / failed")
    records_fetched = Column(Integer, default=0)
    records_inserted = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    file_size_kb = Column(Float, comment="下载文件大小")
    duration_sec = Column(Float, comment="耗时(秒)")
    error_message = Column(Text)
    started_at = Column(DateTime, default=lambda: __import__("datetime").datetime.now())
    finished_at = Column(DateTime)
    tickets_synced = Column(Integer, default=0, comment="工单导入数")
    snapshots_synced = Column(Integer, default=0, comment="随手拍导入数")

    def to_dict(self):
        return {
            "syncId": f"sync-{self.id}",
            "syncType": self.sync_type,
            "status": self.status,
            "recordsFetched": self.records_fetched,
            "recordsInserted": self.records_inserted,
            "recordsUpdated": self.records_updated,
            "fileSizeKb": self.file_size_kb,
            "durationSec": self.duration_sec,
            "errorMessage": self.error_message,
            "startTime": self.started_at.isoformat() if self.started_at else None,
            "endTime": self.finished_at.isoformat() if self.finished_at else None,
        }
