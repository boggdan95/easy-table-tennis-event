# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for ETTEM - Easy Table Tennis Event Manager
Cross-platform: generates .exe on Windows, .app on macOS
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
is_macos = sys.platform == 'darwin'

# Base path
base_path = os.path.dirname(os.path.abspath(SPEC))

# Icon paths
icon_file = None
if is_macos:
    _icns = os.path.join(base_path, 'assets', 'ettem.icns')
    if os.path.exists(_icns):
        icon_file = _icns
else:
    _ico = os.path.join(base_path, 'assets', 'ettem.ico')
    if os.path.exists(_ico):
        icon_file = _ico

# Collect all data files
datas = [
    # Templates
    (os.path.join(base_path, 'src', 'ettem', 'webapp', 'templates'), 'ettem/webapp/templates'),
    # Static files (CSS, JS)
    (os.path.join(base_path, 'src', 'ettem', 'webapp', 'static'), 'ettem/webapp/static'),
    # i18n files
    (os.path.join(base_path, 'i18n'), 'i18n'),
    # Config samples (optional)
    (os.path.join(base_path, 'config'), 'config'),
]

# Hidden imports that PyInstaller might miss
hiddenimports = [
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
    'uvicorn.lifespan.off',
    'email.mime.multipart',
    'email.mime.text',
    'email.mime.message',
    # FastAPI and Starlette
    'fastapi',
    'starlette',
    'starlette.middleware',
    'starlette.middleware.sessions',
    'starlette.routing',
    'starlette.templating',
    # Jinja2
    'jinja2',
    # SQLAlchemy
    'sqlalchemy',
    'sqlalchemy.ext.declarative',
    # Pydantic
    'pydantic',
    # YAML
    'yaml',
    # ETTEM modules
    'ettem',
    'ettem.webapp',
    'ettem.webapp.app',
    'ettem.models',
    'ettem.storage',
    'ettem.standings',
    'ettem.bracket',
    'ettem.group_builder',
    'ettem.validation',
    'ettem.i18n',
    'ettem.io_csv',
    'ettem.config_loader',
    'ettem.pdf_generator',
    'ettem.paths',
    'ettem.licensing',
    # xhtml2pdf and reportlab dependencies
    'xhtml2pdf',
    'reportlab',
    'reportlab.graphics.barcode',
    'reportlab.graphics.barcode.code128',
    'reportlab.graphics.barcode.code39',
    'reportlab.graphics.barcode.code93',
    'reportlab.graphics.barcode.usps',
    'reportlab.graphics.barcode.usps4s',
    'reportlab.graphics.barcode.ecc200datamatrix',
    'reportlab.graphics.barcode.eanbc',
    'reportlab.graphics.barcode.qr',
    'reportlab.graphics.barcode.fourstate',
    'reportlab.graphics.barcode.lto',
    'reportlab.graphics.barcode.widgets',
    'PIL',
    'PIL.Image',
]

# Analysis - platform-specific params
analysis_kwargs = dict(
    pathex=[os.path.join(base_path, 'src')],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'cv2',
    ],
    cipher=block_cipher,
    noarchive=False,
)

# Windows-only Analysis params
if not is_macos:
    analysis_kwargs['win_no_prefer_redirects'] = False
    analysis_kwargs['win_private_assemblies'] = False

a = Analysis(['launcher.py'], **analysis_kwargs)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ETTEM',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=not is_macos,  # Windows: console visible; macOS: no console
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

# macOS: create .app bundle
if is_macos:
    app = BUNDLE(
        exe,
        name='ETTEM.app',
        icon=icon_file,
        bundle_identifier='com.ettem.tournament-manager',
        info_plist={
            'CFBundleName': 'ETTEM',
            'CFBundleDisplayName': 'ETTEM - Tournament Manager',
            'CFBundleShortVersionString': '2.2.0',
            'CFBundleVersion': '2.2.0',
            'NSHighResolutionCapable': True,
        },
    )
