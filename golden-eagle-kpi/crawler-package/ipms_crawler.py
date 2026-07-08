"""
IPMS设备管理系统爬虫模块
目标: 任务管理 -> 巡检任务、维保任务
筛选: 高级筛选 -> 结束时间 -> 当年1.1到当天
"""

import requests
import json
import urllib3
from datetime import datetime
from typing import List, Dict, Optional

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class IPMSCrawler:
    """IPMS设备管理系统爬虫"""

    def __init__(self):
        self.base_url = 'https://ipms.jinying.com'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
        })
        self.token = None
        self.user_info = None

    def login(self, username: str, password: str) -> bool:
        """登录系统"""
        print(f"[INFO] 登录: {username}")

        # 1. 先访问首页
        self.session.get(f'{self.base_url}/deviceFront/', verify=False, timeout=30)

        # 2. 调用登录API (form-urlencoded)
        login_url = f'{self.base_url}/landcrm/rest/userInfo/qpiUserLogin'
        payload = {
            'userAccount': username,
            'password': password,
            'isSecurity': '0'
        }

        resp = self.session.post(
            login_url,
            data=payload,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            verify=False,
            timeout=30
        )

        try:
            result = resp.json()
        except Exception:
            print(f"[ERROR] 登录响应不是JSON")
            return False

        # 该系统 result=1 表示成功, token在users[0]中
        users = result.get('users', [])
        if users:
            user = users[0]
            self.token = user.get('token')
            self.user_info = user
            if self.token:
                print(f"[OK] 登录成功, 用户: {user.get('userName')}")

                self.session.headers.update({
                    'Authorization': f'Bearer {self.token}',
                    'token': self.token,
                    'userid': str(user.get('userid', '')),
                })
                return True

        print(f"[ERROR] 登录失败")
        return False

    def get_tasks(self, task_type: str = 'patrol', start_date: str = None, end_date: str = None,
                  page: int = 1, page_size: int = 500) -> tuple:
        """
        获取任务列表 (巡检/维保共用同一个API)

        Args:
            task_type: 'patrol' 巡检任务 或 'maintain' 维保任务
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            page: 页码
            page_size: 每页数量

        Returns:
            (List[Dict], int): 任务列表, 总数
        """
        if not start_date:
            start_date = f"{datetime.now().year}-01-01"
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')

        lp_category = 1 if task_type == 'patrol' else 2
        task_name = '巡检任务' if task_type == 'patrol' else '维保任务'

        url = f'{self.base_url}/device/ruleTask/pageList/{page_size}/{page}'

        # 处理日期格式：纯日期自动补全时间，已含时间则保持原样
        if start_date and ' ' in start_date:
            start_time_full = start_date
        else:
            start_time_full = f"{start_date} 00:00:00"

        if end_date and ' ' in end_date:
            end_time_full = end_date
        else:
            end_time_full = f"{end_date} 23:59:59"

        payload = {
            'areaId': '',
            'devicePartrolId': '',
            'endTime': end_time_full,
            'handleState': '',
            'lpCategory': lp_category,
            'pageIndex': page,
            'pageSize': page_size,
            'patrolRuleId': '',
            'patrolRuleName': '',
            'projectId': '',
            'ruleState': 0,
            'startTime': start_time_full,
            'sysId': '',
            'taskState': '',
            'timeType': 1,          # 1=开始时间
            'userId': '',
        }

        resp = self.session.post(url, json=payload, verify=False, timeout=60)

        try:
            result = resp.json()
        except Exception as e:
            print(f"[ERROR] 响应解析失败: {e}")
            return [], 0

        if result.get('status') == 200 or result.get('code') == 200:
            data = result.get('data', {})
            rows = data.get('records', [])
            total = data.get('total', len(rows))
            return rows, total

        print(f"[ERROR] 获取失败: {result.get('message') or result}")
        return [], 0

    def crawl_all(self, task_type: str = 'patrol', start_date: str = None, end_date: str = None,
                  page_size: int = 500) -> List[Dict]:
        """爬取所有任务 (分页模式, 备用)"""
        if not start_date:
            start_date = f"{datetime.now().year}-01-01"
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')

        all_data = []
        page = 1
        total = 0
        max_pages = 200

        while page <= max_pages:
            rows, total = self.get_tasks(task_type, start_date, end_date, page, page_size)

            if not rows:
                break

            all_data.extend(rows)
            print(f"[INFO] 第{page}页: {len(rows)}条, 累计{len(all_data)}/{total}")

            if len(all_data) >= total:
                break

            page += 1

        return all_data

    def crawl_all_fast(self, task_type: str = 'patrol', start_date: str = None, end_date: str = None) -> List[Dict]:
        """
        快速模式: 2次请求获取全部数据
        第1次请求1条获取total, 第2次请求total条一次性拉取
        """
        if not start_date:
            start_date = f"{datetime.now().year}-01-01"
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')

        task_name = '巡检任务' if task_type == 'patrol' else '维保任务'
        print(f"[INFO] {task_name} 快速模式: 先获取总数, 再一次性拉取")

        # 第1步: 请求1条获取total
        rows, total = self.get_tasks(task_type, start_date, end_date, page=1, page_size=1)
        print(f"[INFO] 总数: {total} 条")

        if total == 0:
            return []

        # 第2步: 一次性拉取全部
        print(f"[INFO] 一次性拉取 {total} 条...")
        all_rows, _ = self.get_tasks(task_type, start_date, end_date, page=1, page_size=total)
        print(f"[OK] 实际获取 {len(all_rows)} 条")

        return all_rows

    def crawl_patrol(self, start_date: str = None, end_date: str = None) -> List[Dict]:
        """爬取所有巡检任务 (快速模式)"""
        return self.crawl_all_fast('patrol', start_date, end_date)

    def crawl_maintain(self, start_date: str = None, end_date: str = None) -> List[Dict]:
        """爬取所有维保任务 (快速模式)"""
        return self.crawl_all_fast('maintain', start_date, end_date)


def save_to_excel(data: List[Dict], filename: str) -> None:
    """保存到Excel"""
    if not data:
        print(f"[WARN] 没有数据: {filename}")
        return

    try:
        import pandas as pd
        df = pd.DataFrame(data)
        df.to_excel(filename, index=False)
        print(f"[OK] 保存到: {filename} ({len(data)} 条)")
    except ImportError:
        import csv
        csv_file = filename.replace('.xlsx', '.csv')
        with open(csv_file, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        print(f"[OK] 保存到: {csv_file} ({len(data)} 条)")


def create_readable_excel(raw_data: List[Dict], filename: str) -> None:
    """创建可读性更好的Excel"""
    if not raw_data:
        return

    field_mapping = {
        'taskId': '任务ID',
        'patrolRuleName': '计划名称',
        'projectName': '所属项目',
        'addressName': '机房/位置',
        'sysName': '所属系统',
        'userName': '巡检人员',
        'xUserName': '执行人',
        'fullStartDate': '开始时间',
        'fullEndDate': '结束时间',
        'submitDate': '提交时间',
        'taskStateName': '巡检状态',
        'taskState': '状态码',
        'workingTime': '工时(分钟)',
        'serverTime': '同步时间',
        'endDate': '结束时间(仅时分秒)',
        'startDate': '开始时间(仅时分秒)',
        'projectId': '项目ID',
        'userId': '人员ID',
    }

    readable_data = []
    for r in raw_data:
        row = {}
        for key, label in field_mapping.items():
            row[label] = r.get(key, '')
        for key, val in r.items():
            if key not in field_mapping:
                row[key] = val
        readable_data.append(row)

    save_to_excel(readable_data, filename)


def crawl(
    username: str = 'YOUR_IPMS_USERNAME_HERE',
    password: str = 'YOUR_IPMS_PASSWORD_HERE',
    start_date: str = None,
    end_date: str = None,
    output_dir: str = '.'
) -> Dict[str, List[Dict]]:
    """
    便捷函数: 爬取IPMS任务数据

    Returns:
        {'patrol': 巡检任务列表, 'maintain': 维保任务列表}
    """
    if not start_date:
        start_date = f"{datetime.now().year}-01-01"
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')

    print("=" * 50)
    print("IPMS设备管理系统爬虫")
    print("=" * 50)
    print(f"日期范围: {start_date} 00:00:00 ~ {end_date} 23:59:59")
    print(f"筛选条件: 结束时间")
    print("=" * 50)

    crawler = IPMSCrawler()

    if not crawler.login(username, password):
        return {}

    result = {}

    print("\n--- 巡检任务 ---")
    patrol_data = crawler.crawl_patrol(start_date, end_date)
    result['patrol'] = patrol_data
    if patrol_data:
        save_to_excel(patrol_data, f"{output_dir}/ipms_patrol_raw.xlsx")
        create_readable_excel(patrol_data, f"{output_dir}/ipms_patrol_readable.xlsx")

    print("\n--- 维保任务 ---")
    maintain_data = crawler.crawl_maintain(start_date, end_date)
    result['maintain'] = maintain_data
    if maintain_data:
        save_to_excel(maintain_data, f"{output_dir}/ipms_maintain_raw.xlsx")
        create_readable_excel(maintain_data, f"{output_dir}/ipms_maintain_readable.xlsx")

    print(f"\n完成!")
    print(f"  巡检任务: {len(patrol_data)} 条")
    print(f"  维保任务: {len(maintain_data)} 条")

    return result


if __name__ == '__main__':
    crawl()
