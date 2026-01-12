# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for ETTEM - Easy Table Tennis Event Manager
"""

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Base path
base_path = os.path.dirname(os.path.abspath(SPEC))

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
]

a = Analysis(
    ['launcher.py'],
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
        'PIL',
        'cv2',
    ],
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
    name='ETTEM',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Set to False for no console window (use True for debugging)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one: icon='assets/icon.ico'
)
