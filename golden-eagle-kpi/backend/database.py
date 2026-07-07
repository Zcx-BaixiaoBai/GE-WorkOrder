"""金鹰工单KPI管理 - 数据库连接与初始化"""
import sqlite3
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.config import AppConfig

Base = declarative_base()
engine = None
_SessionLocal = None  # 内部变量，init_engine时设置


def get_session_local():
    """获取SessionLocal（延迟解析，避免模块级导入时为None）"""
    global _SessionLocal
    if _SessionLocal is None:
        raise RuntimeError("数据库未初始化，请先调用 init_database()")
    return _SessionLocal


def init_engine():
    """初始化数据库引擎"""
    global engine, _SessionLocal
    AppConfig.ensure_dirs()
    engine = create_engine(
        AppConfig.get_db_url(),
        connect_args={"check_same_thread": False},
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,
    )

    # 启用WAL模式和外键约束（多用户并发安全）
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=10000")  # 10秒防锁表
        cursor.execute("PRAGMA synchronous=NORMAL")   # WAL模式下NORMAL足够安全且更快
        cursor.close()

    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """获取数据库会话（依赖注入用）"""
    SessionCls = get_session_local()
    db = SessionCls()
    try:
        yield db
    finally:
        db.close()


def init_database():
    """初始化数据库：创建所有表和视图，首次运行自动导入初始数据"""
    from backend.models import (  # noqa: F401 - 需要导入以注册模型
        work_ticket, snapshot, personnel, project,
        sync_log, user_session, role_mapping, project_name_mapping,
        project_manager, sync_schedule_config
    )

    init_engine()

    # 创建所有表（如果不存在）
    Base.metadata.create_all(bind=engine)

    # 补充生成列（SQLite GENERATED ALWAYS AS ... STORED）
    _add_generated_columns(engine)

    # 创建视图
    _create_views(engine)

    # 首次运行自动导入初始数据（projects表为空时触发）
    _auto_seed_if_empty(engine)

    return engine


def _auto_seed_if_empty(eng):
    """首次运行时自动导入初始数据"""
    with eng.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM projects"))
        count = result.scalar()

    if count == 0:
        print("[DB] 检测到空数据库，自动导入初始数据...")
        try:
            from backend.seed_data import seed_database
            seed_database()
        except Exception as e:
            print(f"[DB] 自动导入失败（可手动运行 python -m backend.seed_data）: {e}")
    else:
        print(f"[DB] 数据库已有 {count} 个项目，跳过自动导入")


def _add_generated_columns(eng):
    """为工单表和随手拍表添加生成列（如果不存在）"""
    generated_columns = [
        # work_tickets 表生成列
        """ALTER TABLE work_tickets ADD COLUMN is_completed INTEGER 
           GENERATED ALWAYS AS (CASE WHEN order_status IN ('已完成', '已关闭') THEN 1 ELSE 0 END) STORED""",
        """ALTER TABLE work_tickets ADD COLUMN is_timely INTEGER 
           GENERATED ALWAYS AS (
               CASE WHEN complete_time IS NOT NULL AND deadline IS NOT NULL 
                    AND complete_time <= deadline THEN 1 ELSE 0 END
           ) STORED""",
        """ALTER TABLE work_tickets ADD COLUMN process_days REAL 
           GENERATED ALWAYS AS (
               CASE WHEN create_time IS NOT NULL AND complete_time IS NOT NULL 
                    THEN ROUND((julianday(complete_time) - julianday(create_time)), 2) 
                    ELSE NULL END
           ) STORED""",
        # snapshots 表生成列
        """ALTER TABLE snapshots ADD COLUMN is_completed INTEGER 
           GENERATED ALWAYS AS (CASE WHEN order_status IN ('已完成', '已关闭') THEN 1 ELSE 0 END) STORED""",
        """ALTER TABLE snapshots ADD COLUMN is_timely INTEGER 
           GENERATED ALWAYS AS (
               CASE WHEN complete_time IS NOT NULL AND deadline IS NOT NULL 
                    AND complete_time <= deadline THEN 1 ELSE 0 END
           ) STORED""",
    ]
    
    with eng.connect() as conn:
        for ddl in generated_columns:
            try:
                conn.execute(text(ddl))
                conn.commit()
            except Exception:
                pass  # 列已存在则跳过


def _create_views(eng):
    """创建统计视图"""
    views = {
        "v_monthly_stats": """
            CREATE VIEW IF NOT EXISTS v_monthly_stats AS
            SELECT
                p.id AS project_id,
                p.name AS project_name,
                strftime('%Y-%m', wt.create_time) AS month,
                COUNT(*) AS total_count,
                SUM(wt.is_completed) AS completed_count,
                SUM(wt.is_timely) AS timely_count,
                ROUND(AVG(wt.process_days), 2) AS avg_process_days,
                ROUND(SUM(wt.is_completed) * 100.0 / COUNT(*), 2) AS completion_rate,
                ROUND(SUM(wt.is_timely) * 100.0 / NULLIF(SUM(wt.is_completed), 0), 2) AS timely_rate
            FROM work_tickets wt
            JOIN projects p ON wt.project_id = p.id
            WHERE wt.create_time IS NOT NULL
            GROUP BY p.id, strftime('%Y-%m', wt.create_time)
        """,
        "v_snapshot_monthly_stats": """
            CREATE VIEW IF NOT EXISTS v_snapshot_monthly_stats AS
            SELECT
                p.id AS project_id,
                p.name AS project_name,
                strftime('%Y-%m', s.create_time) AS month,
                COUNT(*) AS total_count,
                SUM(s.is_completed) AS completed_count,
                SUM(s.is_timely) AS timely_count,
                ROUND(SUM(s.is_completed) * 100.0 / COUNT(*), 2) AS completion_rate,
                ROUND(SUM(s.is_timely) * 100.0 / NULLIF(SUM(s.is_completed), 0), 2) AS timely_rate
            FROM snapshots s
            JOIN projects p ON s.project_id = p.id
            WHERE s.create_time IS NOT NULL
            GROUP BY p.id, strftime('%Y-%m', s.create_time)
        """,
        "v_project_personnel": """
            CREATE VIEW IF NOT EXISTS v_project_personnel AS
            SELECT
                p.id AS project_id,
                p.name AS project_name,
                p.area,
                p.outsourcing_target,
                COUNT(pm.id) AS headcount,
                SUM(CASE WHEN pm.is_outsourcing = 1 THEN 1 ELSE 0 END) AS outsourcing_count,
                SUM(CASE WHEN pm.is_outsourcing = 0 THEN 1 ELSE 0 END) AS self_count
            FROM projects p
            LEFT JOIN personnel pm ON p.id = pm.project_id AND pm.status = '在职'
            GROUP BY p.id
        """,
    }

    with eng.connect() as conn:
        for name, ddl in views.items():
            try:
                conn.execute(text(ddl))
                conn.commit()
            except Exception as e:
                print(f"[DB] 创建视图 {name} 失败（可能已存在）: {e}")
