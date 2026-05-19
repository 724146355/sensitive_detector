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

try:
    from PyInstaller.utils.win32.versioninfo import (
        VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct,
        VarFileInfo, VarStruct
    )
    _has_versioninfo = True
except ImportError:
    _has_versioninfo = False

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
    'openpyxl.cell',
    'openpyxl.reader',
    'openpyxl.reader.excel',
    'openpyxl.workbook',
    'openpyxl.writer',
    'openpyxl.writer.excel',
    'et_xmlfile',
    'xlrd',
    'pptx',
    'pdfplumber',
    'pdfminer',
    'pdfminer.high_level',
    'pdfminer.pdfinterp',
    'pdfminer.converter',
    'pdfminer.layout',
    'pdfminer.pdftypes',
    'pdfminer.utils',
    'pdfminer.pdfpage',
    'pdfminer.pdfdocument',
    'pdfminer.pdfparser',
    'pdfminer.psparser',
    'pdfminer.arcfour',
    'pdfminer.pdffont',
    'pdfminer.pdfcolor',
    'pdfminer.image',
    'pdfminer.settings',
    'PIL',
    'PIL._imaging',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'lxml',
    'lxml.etree',
    'lxml._elementpath',
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
if _has_versioninfo:
    version_info = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=(1, 0, 0, 0),
            prodvers=(1, 0, 0, 0),
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0)
        ),
        kids=[
            StringFileInfo([
                StringTable(
                    '040904B0',
                    [StringStruct('FileDescription', '敏感文件扫描与加密备份工具'),
                     StringStruct('ProductName', 'SensitiveDetector'),
                     StringStruct('CompanyName', ''),
                     StringStruct('FileVersion', '1.0.0'),
                     StringStruct('ProductVersion', '1.0.0'),
                     StringStruct('InternalName', 'SensitiveDetector'),
                     StringStruct('LegalCopyright', ''),
                     StringStruct('OriginalFilename', 'SensitiveDetector.exe')]
                )
            ]),
            VarFileInfo([VarStruct('Translation', [1033, 1200])])
        ]
    )
else:
    version_info = None

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
    module_collection_mode={
        'openpyxl': 'pyz+py',
        'pdfplumber': 'pyz+py',
        'pdfminer': 'pyz+py',
        'xlrd': 'pyz+py',
        'docx': 'pyz+py',
        'pptx': 'pyz+py',
        'PIL': 'pyz+py',
        'lxml': 'pyz+py',
        'olefile': 'pyz+py',
    },
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
    target_arch='32bit',
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    version=version_info,
)
