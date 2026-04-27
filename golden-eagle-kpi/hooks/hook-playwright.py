"""PyInstaller hook: 排除Playwright自带浏览器（我们用channel="chrome"调用系统Chrome）"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# 收集playwright数据文件，但排除浏览器二进制（.local-browsers）
datas = []
for item in collect_data_files('playwright'):
    src, dst = item
    # 彻底排除 .local-browsers 浏览器二进制目录
    if '.local-browsers' in src:
        continue
    datas.append((src, dst))

# 确保必要的Python模块被识别
hiddenimports = collect_submodules('playwright')

# 禁止PyInstaller将playwright/driver下的浏览器二进制打入包（通过排除该模块）
# 注意： playwright 顶层模块仍会被收集，只是 driver 子目录被排除
excludedimports = []
