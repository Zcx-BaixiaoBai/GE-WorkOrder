"""金鹰工单KPI管理 - 筹建专项计划模型"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, Float
from sqlalchemy.orm import relationship
from backend.database import Base


class SpecialPlan(Base):
    """筹建专项计划数据"""
    __tablename__ = "special_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 项目信息
    project_code = Column(String(50), comment="项目编码")
    project_name = Column(String(100), comment="项目名称")
    # 专项信息
    special_id = Column(String(50), comment="专项ID")
    special_name = Column(String(200), comment="专项计划名称")
    special_detail_id = Column(String(50), comment="明细ID")
    # 计划级别
    plan_level = Column(String(20), comment="计划级别")
    # 任务事项
    plan_content = Column(Text, comment="任务事项")
    # 责任信息
    plan_dept = Column(String(100), comment="责任部门")
    plan_person = Column(String(50), comment="责任人ID")
    person_name = Column(String(50), comment="责任人")
    # 计划时间
    plan_start_date = Column(DateTime, comment="计划开始日期")
    plan_end_date = Column(DateTime, comment="计划完成日期")
    plan_cycle = Column(Integer, comment="计划周期(天)")
    # 实际时间
    real_start_date = Column(DateTime, comment="实际开始日期")
    real_end_date = Column(DateTime, comment="实际完成日期")
    real_cycle = Column(Integer, comment="实际周期(天)")
    # 状态
    plan_state = Column(String(20), comment="计划状态")
    plan_remark = Column(Text, comment="计划备注")
    finish_flag = Column(Integer, comment="完成标识: 0=进行中, 1=已完成")
    danger_flag = Column(Integer, comment="逾期标识: 0=否, 1=是")
    warning_flag = Column(Integer, comment="预警标识: 0=否, 1=是")
    pause_flag = Column(Integer, comment="暂停标识: 0=执行中, 1=已暂停")
    # 评分
    score = Column(Float, comment="评分")
    # 标准
    operate_demand = Column(Text, comment="操作标准及要求")
    check_standard = Column(Text, comment="完成及考核标准")
    remark = Column(Text, comment="备注")
    attach_count = Column(Integer, default=0, comment="附件数量")
    # 同步批次
    sync_batch_id = Column(Integer, ForeignKey("sync_logs.id"), comment="同步批次")
    created_at = Column(DateTime, default=lambda: __import__("datetime").datetime.now())
    updated_at = Column(DateTime, default=lambda: __import__("datetime").datetime.now(),
                       onupdate=lambda: __import__("datetime").datetime.now())

    __table_args__ = (
        Index("idx_sp_project", "project_code"),
        Index("idx_sp_plan_end_date", "plan_end_date"),
        Index("idx_sp_finish", "finish_flag"),
        Index("idx_sp_danger", "danger_flag"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "project_code": self.project_code,
            "project_name": self.project_name,
            "special_name": self.special_name,
            "plan_content": self.plan_content,
            "plan_dept": self.plan_dept,
            "person_name": self.person_name,
            "plan_start_date": self.plan_start_date.isoformat() if self.plan_start_date else None,
            "plan_end_date": self.plan_end_date.isoformat() if self.plan_end_date else None,
            "real_end_date": self.real_end_date.isoformat() if self.real_end_date else None,
            "plan_state": self.plan_state,
            "finish_flag": self.finish_flag,
            "danger_flag": self.danger_flag,
            "warning_flag": self.warning_flag,
            "pause_flag": self.pause_flag,
            "score": self.score,
        }
