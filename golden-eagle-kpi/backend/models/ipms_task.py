"""金鹰工单KPI管理 - IPMS设备管理任务模型"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Index
from backend.database import Base


class IPMSTask(Base):
    """IPMS设备管理任务（巡检/维保）"""
    __tablename__ = "ipms_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 任务标识
    task_id = Column(String(50), unique=True, comment="任务ID")
    task_type = Column(String(10), comment="任务类型: patrol=巡检, maintain=维保")
    # 项目信息
    project_id = Column(String(50), comment="项目ID")
    project_name = Column(String(100), comment="所属项目")
    # 任务基本信息
    task_name = Column(String(200), comment="计划名称/规则名称")
    address_name = Column(String(100), comment="机房/位置")
    sys_name = Column(String(100), comment="所属系统")
    # 人员信息
    user_id = Column(String(50), comment="巡检人员ID")
    user_name = Column(String(50), comment="巡检人员")
    executor_name = Column(String(50), comment="执行人")
    # 时间信息
    start_time = Column(DateTime, comment="开始时间")
    end_time = Column(DateTime, comment="结束时间")
    submit_time = Column(DateTime, comment="提交时间")
    working_time = Column(Integer, comment="工时(分钟)")
    # 状态
    task_state = Column(Integer, comment="状态码")
    task_state_name = Column(String(20), comment="巡检状态")
    # 同步批次
    sync_batch_id = Column(Integer, comment="同步批次")
    created_at = Column(DateTime, default=lambda: __import__("datetime").datetime.now())
    updated_at = Column(DateTime, default=lambda: __import__("datetime").datetime.now(),
                       onupdate=lambda: __import__("datetime").datetime.now())

    __table_args__ = (
        Index("idx_ipms_task_id", "task_id"),
        Index("idx_ipms_project", "project_id"),
        Index("idx_ipms_task_type", "task_type"),
        Index("idx_ipms_end_time", "end_time"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "project_name": self.project_name,
            "task_name": self.task_name,
            "address_name": self.address_name,
            "sys_name": self.sys_name,
            "user_name": self.user_name,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "task_state_name": self.task_state_name,
        }
