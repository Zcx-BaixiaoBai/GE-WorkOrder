"""PyInstaller hook: 排除Playwright自带浏览器（我们用channel="chrome"调用系统Chrome）"""
from PyInstaller.utils.hooks import collect_data_files

# 只收集playwright的Python数据文件，排除浏览器二进制
datas = []
for item in collect_data_files('playwright'):
    # 排除浏览器二进制文件（.local-browsers目录下的chromium/firefox/webkit）
    if '.local-browsers' not in item[0] and 'driver' not in item[0]:
        datas.append(item)

# 如果datas为空，至少收集最小必要文件
if not datas:
    datas = collect_data_files('playwright', include_py_files=False)

# 过滤掉大文件
filtered = []
for src, dst in datas:
    # 排除浏览器和驱动目录
    skip_keywords = ['.local-browsers', 'chromium-', 'firefox-', 'webkit-', 'ffmpeg-']
    if any(kw in src for kw in skip_keywords):
        continue
    filtered.append((src, dst))

datas = filtered
