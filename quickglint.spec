# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Unused large external libraries excluded to reduce package size
excluded_modules = [
    'tkinter',
    'unittest',
    'matplotlib',
    'scipy',
    'pandas',
    'IPython',
    'curses',
]

hidden_imports = [
    'pynput.keyboard._win32',
    'pynput.mouse._win32',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtSvg',
    'PySide6.QtPrintSupport',
    'PySide6.QtNetwork',
    'certifi',
    'email',
    'email.message',
    'email.parser',
    'email.mime',
    'winocr',
    'winrt.windows.foundation',
    'winrt.windows.foundation.collections',
    'winrt.windows.globalization',
    'winrt.windows.graphics.imaging',
    'winrt.windows.media.ocr',
    'winrt.windows.storage.streams',
]
hidden_imports += collect_submodules('app')
hidden_imports += collect_submodules('PIL')
hidden_imports += collect_submodules('pynput')
hidden_imports += collect_submodules('cryptography')
hidden_imports += collect_submodules('numpy')
hidden_imports += collect_submodules('phonenumbers')

datas = [
    ('config', 'config'),
    ('assets', 'assets'),
]
datas += collect_data_files('certifi')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Single executable with custom Quickglint icon and version metadata
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Quickglint',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # Disabling UPX dramatically speeds up launch time
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icons/quickglint.ico',
    version='version_info.txt' if os.path.exists('version_info.txt') else None,
)

# Onedir distribution for instant 0.1-second launch without %TEMP% extraction
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Quickglint',
)


