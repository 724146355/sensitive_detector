# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller 构建配置 - macOS x86_64 版本
# 输出: dist/SensitiveDetector
#
# 构建方式:
#   python3 -m PyInstaller --clean --noconfirm --target-arch x86_64 sensitive_detector_macos.spec
#

block_cipher = None

# ---------------------------------------------------------------------------
# 数据文件：随应用打包，运行时解压到临时目录
# ---------------------------------------------------------------------------
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
# 排除不必要的模块以减小体积
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
# 单文件可执行
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
    version=None,
)
