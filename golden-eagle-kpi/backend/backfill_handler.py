"""用原始Excel数据回填work_tickets表的handler_id字段"""
import openpyxl
import warnings
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 先init数据库
from backend.database import init_database
init_database()

from backend.database import get_session_local
from backend.models.work_ticket import WorkTicket

warnings.filterwarnings('ignore')

def _clean_id(raw_id):
    if raw_id is None:
        return None
    if isinstance(raw_id, float):
        raw_id = str(int(raw_id))
    raw_id = str(raw_id).strip()
    if not raw_id or raw_id == 'None':
        return None
    result = raw_id.zfill(10)
    return result if result != '0000000000' else None

EXCEL_PATH = r"C:\Users\Administrator\记忆\数据样本\工单明细表 2026-04-09 17_54_49.xlsx"

def main():
    print("读取Excel...")
    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
    ws = wb.active

    # 建立 ticket_no -> handler_id 映射
    handler_map = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or len(row) < 20:
            continue
        ticket_no = str(row[2] or "").strip()
        if not ticket_no:
            continue
        handler_id = _clean_id(row[18]) if row[18] else None
        if handler_id:
            handler_map[ticket_no] = handler_id

    wb.close()
    print(f"从Excel读取到 {len(handler_map)} 条有handler_id的记录")

    # UPDATE数据库
    db = get_session_local()()
    updated = 0
    for ticket_no, handler_id in handler_map.items():
        result = db.query(WorkTicket).filter(WorkTicket.ticket_no == ticket_no).update({"handler_id": handler_id})
        if result > 0:
            updated += 1

    db.commit()

    # 验证
    total = db.query(WorkTicket).filter(WorkTicket.handler_id.isnot(None)).count()
    print(f"已更新 {updated} 条记录的 handler_id")
    print(f"当前数据库有 handler_id 的记录数: {total}")

    db.close()

if __name__ == "__main__":
    main()
