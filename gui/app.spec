# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

spec_dir = Path('.').resolve()

a = Analysis(
    ['main.py'],
    pathex=[str(spec_dir)],
    binaries=[],
    datas=[
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
        'playwright',
        'playwright.sync_api',
        'douban_fucker',
        'douban_fucker.scrapers',
        'douban_fucker.scrapers.apple_music',
        'douban_fucker.scrapers.musicbrainz',
        'douban_fucker.uploader',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='豆瓣专辑上传工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='豆瓣专辑上传工具',
)
app = BUNDLE(
    coll,
    name='豆瓣专辑上传工具.app',
    icon=None,
    bundle_identifier=None,
)
