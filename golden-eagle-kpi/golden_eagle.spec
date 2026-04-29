# -*- mode: python ; coding: utf-8 -*-
"""金鹰工单KPI管理系统 v1.0.0 - PyInstaller打包配置

用法:
    cd golden-eagle-kpi
    pyinstaller golden_eagle.spec

产出:
    dist/金鹰工单KPI/金鹰工单KPI.exe
    dist/金鹰工单KPI/frontend/index.html
    dist/金鹰工单KPI/data/  (空目录，运行时创建)
"""
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_all

PROJECT_ROOT = Path(SPECPATH)

# 收集 requests 及其所有依赖
_requests_datas, _requests_binaries, _requests_hidden = collect_all('requests')

a = Analysis(
    [str(PROJECT_ROOT / 'launcher.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # 前端HTML（PyInstaller会打包到dist/frontend/）
        (str(PROJECT_ROOT / 'frontend' / 'index.html'), 'frontend'),
        # main.py（uvicorn "main:app" 动态导入需要它在可发现路径）
        (str(PROJECT_ROOT / 'main.py'), '.'),
        # backend目录（自定义项目代码，hiddenimports无法自动包含）
        (str(PROJECT_ROOT / 'backend'), 'backend'),
    ] + _requests_datas,
    hiddenimports=[
        # uvicorn 必须的隐藏导入
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # SQLAlchemy
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.sql.default_comparator',
        # backend 全部子模块
        'backend',
        'backend.api',
        'backend.api.auth',
        'backend.api.stats',
        'backend.api.tickets',
        'backend.api.personnel',
        'backend.api.sync',
        'backend.api.sync_all',
        'backend.api.sync_wy',
        'backend.api.sync_ipms',
        'backend.api.wy',
        'backend.api.ipms',
        'backend.api.export',
        'backend.api.config',
        'backend.api.websocket',
        'backend.api.search_api',
        'backend.api.ai_chat',
        'backend.api.update',
    ] + _requests_hidden + [
        'backend.models',
        'backend.models.work_ticket',
        'backend.models.snapshot',
        'backend.models.personnel',
        'backend.models.project',
        'backend.models.sync_log',
        'backend.models.user_session',
        'backend.models.role_mapping',
        'backend.models.project_name_mapping',
        'backend.models.project_manager',
        'backend.models.special_plan',
        'backend.models.ipms_task',
        'backend.services',
        'backend.services.auth_service',
        'backend.services.config_service',
        'backend.services.export_service',
        'backend.services.personnel_service',
        'backend.services.stats_service',
        'backend.services.sync_service',
        'backend.services.ticket_service',
        'backend.scraper',
        'backend.scraper.bi_client',
        'backend.scraper.final_v17_headles',
        'backend.scraper.wy_crawler',
        'backend.scraper.ipms_crawler',
        'backend.config',
        'backend.database',
        'backend.seed_data',
        'backend.import_real_data',
        # anyio/httpx
        'anyio._backends._asyncio',
        'httpcore',
        'httpx',
        'sniffio',
        'h11',
        # JWT
        'jwt',
        'jwt.algorithms',
        # openpyxl
        'openpyxl',
        'openpyxl.cell',
        'openpyxl.workbook',
        # APScheduler
        'apscheduler',
        'apscheduler.schedulers',
        'apscheduler.schedulers.asyncio',
        # Playwright（使用系统Chrome，不需要下载浏览器）
        'playwright',
        'playwright.async_api',
        'playwright._impl',
        'playwright._impl._browser',
        'playwright._impl._page',
        'playwright._impl._playwright',
    ],
    hookspath=[str(PROJECT_ROOT / 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大模块
        'pystray',
        'PIL',
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'pytest',
        'setuptools',
        'pip',
        'pandas',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='金鹰工单KPI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 隐藏终端窗口，双击即用
    icon=None,
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='金鹰工单KPI',
)
