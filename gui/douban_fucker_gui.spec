# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置
将豆瓣专辑上传工具打包成可执行文件
"""

import sys
import os
from pathlib import Path

block_cipher = None

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent
GUI_DIR = Path(__file__).parent
DOUBAN_FUCKER_DIR = ROOT_DIR / "douban_fucker"

a = Analysis(
    ['main.py'],
    pathex=[str(GUI_DIR)],
    binaries=[],
    datas=[
        # 包含 HTML 前端
        ('index.html', '.'),
    ],
    hiddenimports=[
        'fastapi',
        'uvicorn',
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
        'python_multipart',
        # 原项目依赖
        'douban_fucker',
        'douban_fucker.cli',
        'douban_fucker.scrapers',
        'douban_fucker.scrapers.musicbrainz',
        'douban_fucker.scrapers.applemusic',
        'douban_fucker.scrapers.discogs',
        'douban_fucker.scrapers.spotify',
        'douban_fucker.scrapers.rym',
        'douban_fucker.browser',
        'douban_fucker.browser.douban',
        'douban_fucker.browser.session',
        'douban_fucker.storage',
        'douban_fucker.storage.file_storage',
        'douban_fucker.models',
        'douban_fucker.models.album',
        'douban_fucker.utils',
        'douban_fucker.utils.config',
        'douban_fucker.utils.downloader',
        'httpx',
        'bs4',
        'playwright',
        'click',
        'rich',
        'yaml',
        'pydantic',
    ],
    hookspath=[],
    hooksconfig={},
    keys=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='豆瓣专辑上传工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windows 下不显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可添加图标: icon='icon.ico'
)

# 收集 Playwright 浏览器
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='豆瓣专辑上传工具',
)
