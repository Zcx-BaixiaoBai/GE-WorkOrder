"""
筹建专项计划管理系统爬虫
用于爬取"筹建专项完成情况维护"数据

系统: http://58.213.109.123:8181
账号: YOUR_WY_USERNAME_HERE / YOUR_WY_PASSWORD_HERE

调用方式:
    from spider import crawl
    data = crawl(year=2026)  # 自动生成可读Excel
"""

import json
import hashlib
import requests
from datetime import datetime
from typing import Optional, List, Dict


def _write_dicts_to_excel(data: List[Dict], filepath: str, columns: List[str] = None) -> None:
    """将字典列表写入Excel（不依赖pandas，使用openpyxl）"""
    if not data:
        # 创建一个空文件
        from openpyxl import Workbook
        wb = Workbook()
        wb.save(filepath)
        return

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active

    # 确定列顺序
    if columns:
        keys = columns
    else:
        keys = list(data[0].keys())

    # 写入表头
    ws.append(keys)

    # 写入数据行
    for row in data:
        ws.append([row.get(k, '') for k in keys])

    wb.save(filepath)


# ============== 配置 ==============
CONFIG = {
    'base_url': 'http://58.213.109.123:8181',
    'token': 'YOUR_WY_TOKEN_HERE',
    'username': 'YOUR_WY_USERNAME_HERE',
    'password': 'YOUR_WY_PASSWORD_HERE',
}

# ============== 字段映射 ==============
FIELD_MAP = {
    'special_detail_id': '明细ID',
    'special_id': '专项ID',
    'plan_level': '计划级别',
    'plan_content': '任务事项',
    'plan_dept': '责任部门',
    'plan_person': '责任人ID',
    'person_name': '责任人',
    'plan_start_date': '计划开始日期',
    'plan_end_date': '计划完成日期',
    'plan_cycle': '计划周期(天)',
    'real_start_date': '实际开始日期',
    'real_end_date': '实际完成日期',
    'real_cycle': '实际周期(天)',
    'plan_state': '计划状态',
    'plan_remark': '计划备注',
    'finish_flag': '完成标识',
    'danger_flag': '逾期标识',
    'warning_flag': '预警标识',
    'score': '评分',
    'special_name': '专项计划名称',
    'project_name': '项目名称',
    'pause_flag': '暂停标识',
    'operate_demand': '操作标准及要求',
    'check_standard': '完成及考核标准',
    'remark': '备注',
    'attach_count': '附件数量',
}


class Crawler:
    """爬虫类"""

    def __init__(self, config: dict = None):
        self.config = config or CONFIG
        self.session = requests.Session()
        self._logged_in = False

    def login(self) -> bool:
        """AJAX登录"""
        base = self.config['base_url']
        token = self.config['token']
        username = self.config['username']
        password = self.config['password']

        # 1. 访问登录页
        self.session.get(f"{base}/Login/doLogin?token={token}")

        # 2. AJAX登录(密码MD5)
        pwd_md5 = hashlib.md5(password.encode()).hexdigest()
        resp = self.session.post(
            f"{base}/Login/login",
            data=json.dumps({
                'login_name': username,
                'password': pwd_md5,
                'type': '1'
            }),
            headers={
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            }
        )

        result = resp.json()
        if result.get('result') == 0:
            self._logged_in = True
            return True
        raise Exception(f"登录失败: {result.get('msg')}")

    def get_projects(self) -> List[Dict]:
        """获取项目列表"""
        base = self.config['base_url']
        resp = self.session.post(
            f"{base}/WYProject/getPlanAllList",
            data={
                'pageNumber': 1,
                'pageSize': 1000,
                'paramList': json.dumps({
                    'project_name': '',
                    'plan_end_date_b': '',
                    'plan_end_date_e': ''
                })
            },
            headers={'X-Requested-With': 'XMLHttpRequest'}
        )
        return resp.json().get('rows', [])

    def get_data(self, project_id: str, year: int = None) -> List[Dict]:
        """
        获取指定项目的数据

        Args:
            project_id: 项目ID
            year: 年份(默认当年)

        Returns:
            数据列表
        """
        if year is None:
            year = datetime.now().year

        base = self.config['base_url']

        param = {
            "project_id": project_id,
            "plan_dept": "",
            "special_name": "",
            "plan_start_date_b": "",
            "plan_start_date_e": "",
            "plan_end_date_b": f"{year}-01-01",
            "plan_end_date_e": f"{year}-12-31",
            "plan_content": "",
            "plan_state": ""
        }

        resp = self.session.get(
            f"{base}/WYSpecialPlan/getSpecialPlanFinishList",
            params={
                "pageNumber": 1,
                "pageSize": 500,
                "param_list": json.dumps(param)  # 注意是 param_list
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{base}/WYSpecialPlan/Finish_WY"
            }
        )

        return resp.json().get('rows', [])

    def crawl_all(self, year: int = None) -> List[Dict]:
        """爬取所有项目数据"""
        if year is None:
            year = datetime.now().year

        print(f"[INFO] 获取项目列表...")
        projects = self.get_projects()
        print(f"[INFO] 共 {len(projects)} 个项目")

        all_data = []
        for proj in projects:
            pid = str(proj.get('project_id', ''))
            pname = proj.get('project_name', '')

            if not pid:
                continue

            rows = self.get_data(pid, year)

            for row in rows:
                row['项目名称'] = pname
                row['项目编码'] = pid

            all_data.extend(rows)
            print(f"[INFO] {pname} ({pid}): {len(rows)} 条")

        return all_data

    def save(self, data: List[Dict], year: int, output_dir: str = ".") -> None:
        """保存数据（使用openpyxl，不依赖pandas）"""
        if not data:
            print("[WARN] 无数据")
            return

        # 1. 原始数据（使用 _write_dicts_to_excel）
        raw_file = f"{output_dir}/data_{year}_raw.xlsx"
        _write_dicts_to_excel(data, raw_file)
        print(f"[OK] 原始数据: {raw_file}")

        # 2. 可读版本（手动构建列，避免pandas）
        readable_cols = [
            '项目名称', '项目编码', 'special_name', 'plan_content', 'plan_dept',
            'plan_start_date', 'plan_end_date', 'real_start_date', 'real_end_date',
            'plan_cycle', 'pause_flag', 'danger_flag', 'finish_flag',
            'operate_demand', 'check_standard', 'remark', 'attach_count',
        ]

        def _flag_transform(val, mapping):
            return mapping.get(val, str(val)) if val is not None else ''

        readable_data = []
        for row in data:
            rrow = {k: row.get(k, '') for k in readable_cols if k in row}
            # 状态转换
            pf = row.get('pause_flag')
            rrow['执行状态'] = _flag_transform(pf, {1: '已暂停', 0: '执行中'})
            df = row.get('danger_flag')
            rrow['逾期'] = '是' if df == 1 else '否'
            wf = row.get('warning_flag')
            rrow['预警'] = '是' if wf == 1 else '否'
            ff = row.get('finish_flag')
            rrow['完成状态'] = _flag_transform(ff, {1: '已完成', 0: '进行中'})
            readable_data.append(rrow)

        readable_file = f"{output_dir}/data_{year}_readable.xlsx"
        _write_dicts_to_excel(readable_data, readable_file)
        print(f"[OK] 可读数据: {readable_file}")

        # 3. 字段说明
        field_info = []
        for eng, chn in FIELD_MAP.items():
            if eng in data[0]:
                sample = str(data[0][eng])[:30] if data else ''
                field_info.append({
                    '英文字段': eng,
                    '中文表头': chn,
                    '示例': sample
                })

        field_file = f"{output_dir}/field_mapping.xlsx"
        _write_dicts_to_excel(field_info, field_file)
        print(f"[OK] 字段说明: {field_file}")


def crawl(
    year: int = None,
    output_dir: str = ".",
    config: dict = None
) -> List[Dict]:
    """
    便捷函数: 一步完成登录+爬取+保存

    Args:
        year: 年份(默认当年)
        output_dir: 输出目录
        config: 自定义配置

    Returns:
        原始数据列表

    Example:
        from spider import crawl

        # 爬取2026年数据
        data = crawl(year=2026)

        # 自定义配置
        data = crawl(
            year=2026,
            output_dir='./output',
            config={
                'base_url': 'http://xxx.com',
                'token': 'xxx',
                'username': 'user',
                'password': 'pass'
            }
        )
    """
    if year is None:
        year = datetime.now().year

    print("=" * 50)
    print("筹建专项计划管理系统爬虫")
    print("=" * 50)

    crawler = Crawler(config)
    crawler.login()

    print(f"\n爬取 {year} 年数据...")
    data = crawler.crawl_all(year=year)

    print(f"\n共获取 {len(data)} 条数据")

    if data:
        crawler.save(data, year, output_dir)

    return data


if __name__ == '__main__':
    # 直接运行
    crawl(year=2026)
