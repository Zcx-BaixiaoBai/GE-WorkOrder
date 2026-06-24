#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
示例脚本：如何调用爬虫
"""
import asyncio
import os
from bi_client import BiClient
from wy_crawler import Crawler as WYCrawler

# ============== 配置说明 ==============
# BI系统账密（工单和随手拍）
BI_ACCOUNT = os.environ.get('BI_ACCOUNT', '你的OA账号')
BI_PASSWORD = os.environ.get('BI_PASSWORD', '你的OA密码')

# 物业系统账密（筹建专项）
WY_CONFIG = {
    'base_url': os.environ.get('WY_BASE_URL', 'http://58.213.109.123:8181'),
    'token': os.environ.get('WY_TOKEN', '你的token'),
    'username': os.environ.get('WY_USERNAME', '你的用户名'),
    'password': os.environ.get('WY_PASSWORD', '你的密码'),
}


async def fetch_bi_data():
    """
    示例1：爬取BI系统的工单和随手拍数据
    
    返回:
        list[str]: 下载的Excel文件路径列表
    """
    print("\n========== 爬取BI系统数据 ==========")
    
    # 创建客户端
    client = BiClient(
        account=BI_ACCOUNT,
        password=BI_PASSWORD,
        download_dir='./downloads'  # 指定下载目录
    )
    
    # 爬取所有报表
    files = await client.fetch_all()
    
    print(f"\n下载完成，共 {len(files)} 个文件:")
    for f in files:
        print(f"  - {f}")
    
    return files


def fetch_wy_data(year=2026):
    """
    示例2：爬取物业系统的筹建专项数据
    
    参数:
        year (int): 要爬取的年份
    
    返回:
        list[dict]: 专项明细数据
    """
    print(f"\n========== 爬取物业系统数据 ({year}年) ==========")
    
    # 创建爬虫
    crawler = WYCrawler(config=WY_CONFIG)
    
    # 登录
    if not crawler.login():
        print("登录失败！")
        return None
    
    # 爬取数据
    data = crawler.crawl(year=year)
    
    print(f"\n爬取完成，共 {len(data)} 条记录")
    
    return data


async def main():
    """主函数：演示如何调用所有爬虫"""
    
    # 1. 爬取BI系统（工单+随手拍）
    try:
        bi_files = await fetch_bi_data()
    except Exception as e:
        print(f"BI系统爬取失败: {e}")
        bi_files = []
    
    # 2. 爬取物业系统（筹建专项）
    try:
        wy_data = fetch_wy_data(year=2026)
    except Exception as e:
        print(f"物业系统爬取失败: {e}")
        wy_data = None
    
    print("\n========== 爬取任务完成 ==========")
    print(f"BI系统: {len(bi_files)} 个文件")
    print(f"物业系统: {len(wy_data) if wy_data else 0} 条记录")


if __name__ == '__main__':
    asyncio.run(main())
