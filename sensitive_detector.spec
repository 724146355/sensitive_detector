# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller 构建配置 - Windows 便携版单文件 EXE
# 输出: dist/SensitiveDetector.exe
# 特点: 无需安装 Python，双击即用，不写入注册表
#
# 构建方式（二选一）:
#   1. GitHub Actions（推荐）: 推送代码到 GitHub 自动构建
#   2. Windows 本地构建:
#      pip install -r requirements.txt
#      pyinstaller --clean --noconfirm sensitive_detector.spec
#

import sys
from pathlib import Path

block_cipher = None

# ---------------------------------------------------------------------------
# 数据文件：随 EXE 打包，运行时解压到临时目录
# ---------------------------------------------------------------------------
# config.json 为内置默认配置；用户如需自定义，可将 config.json 放于 EXE 同目录
added_files = [
    ('config.json', '.'),
]

# ---------------------------------------------------------------------------
# 隐藏导入：确保 PyInstaller 能正确打包动态/延迟加载的模块
# ---------------------------------------------------------------------------
hidden_imports = [
    'docx',
    'olefile',
    'openpyxl',
    'xlrd',
    'pptx',
    'pdfplumber',
    'pyzipper',
    'csv',
    'zipfile',
    'everything_scanner',
]

# ---------------------------------------------------------------------------
# 排除不必要的模块以减小 EXE 体积
# ---------------------------------------------------------------------------
excludes = [
    'tkinter',
    'unittest',
    'test',
    'setuptools',
    'pydoc',
    'lib2to3',
    'asyncio',
    'email',
    'http',
    'xml',
    'pdb',
    'profile',
    'pstats',
    'tabnanny',
    'trace',
    'pickletools',
    'difflib',
]

# ---------------------------------------------------------------------------
# Windows 版本信息（右键 EXE → 属性 → 详细信息可见）
# ---------------------------------------------------------------------------
version_info = {
    'FileDescription': '敏感文件扫描与加密备份工具',
    'ProductName': 'SensitiveDetector',
    'CompanyName': '',
    'FileVersion': '1.0.0',
    'ProductVersion': '1.0.0',
    'InternalName': 'SensitiveDetector',
    'LegalCopyright': '',
    'OriginalFilename': 'SensitiveDetector.exe',
}

# ---------------------------------------------------------------------------
# 构建分析
# ---------------------------------------------------------------------------
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    module_collection_mode={},
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ---------------------------------------------------------------------------
# 单文件 EXE（非目录模式，便携无毒）
# ---------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SensitiveDetector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    version=version_info,
)
