# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs, collect_data_files
from pathlib import Path

a = Analysis(
    ['backend/server.py'],
    pathex=[SPECPATH, str(Path(SPECPATH) / 'vendor' / 'cli_anything_blender')],
    binaries=collect_dynamic_libs('ctranslate2') + collect_dynamic_libs('av') + collect_dynamic_libs('tokenizers')
        + collect_dynamic_libs('ifcopenshell', search_patterns=['ifcopenshell_parse_schema_*.dll']),
    datas=[('resources/providers.default.json', 'resources'),
           ('resources/application-profiles.json', 'resources'),
           ('resources/model-candidates.json', 'resources'),
           ('resources/ocr-model-manifest.json', 'resources'),
           ('scripts/setup-freellmapi.ps1', 'scripts'),
           ('scripts/configure-native-gateway.py', 'scripts'),
           ('scripts/anythingmcp-local.py', 'scripts'),
           ('backend/speech/moss_worker.py', 'speech'),
           ('resources/piper_worker.py', 'speech'),
           ('backend/speech/speech_text.py', 'speech'),
           ('backend/actions/uia_worker.ps1', 'backend/actions'),
           ('backend/actions/uia_observer.ps1', 'backend/actions'),
           ('resources/command-library.json', 'resources'),
           ('resources/procedure-library.zip', 'resources'),
           ('master_icon.png', '.'),
           ('vendor/cli_anything_blender/LICENSE', 'licenses/cli-anything'),
           ('vendor/cli_anything_blender/UPSTREAM.json', 'licenses/cli-anything'),
           ('resources/models/faster-whisper-tiny', 'models/faster-whisper-tiny')]
           + collect_data_files('faster_whisper') + collect_data_files('mcp') + collect_data_files('jsonschema_specifications')
           + collect_data_files('rapidocr_onnxruntime', excludes=['models/*']),
    hiddenimports=collect_submodules('backend', filter=lambda name: '.tests' not in name and '.test_' not in name)
        + collect_submodules('mcp', filter=lambda name: not name.startswith('mcp.cli')) + collect_submodules('uvicorn') + [
        'cli_anything.blender.core.scene', 'cli_anything.blender.core.objects',
        'cli_anything.blender.core.lighting', 'cli_anything.blender.core.render',
        'cli_anything.blender.utils.bpy_gen', 'faster_whisper', 'ctranslate2',
        'av', 'numpy', 'tokenizers', 'huggingface_hub', 'pypdf', 'qrcode', 'qrcode.image.svg', 'websocket',
        'win32com.client', 'win32api', 'win32security', 'pythoncom', 'pywintypes', 'playwright.async_api', 'psutil', 'jsonschema', 'httpx', 'anyio',
        'ifcopenshell', 'ifcopenshell.util.unit', 'rapidocr_onnxruntime', 'onnxruntime'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchaudio', 'transformers', 'tensorflow', 'fairseq', 'pandas', 'scipy', 'matplotlib', 'pytest', 'IPython'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='axx-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
