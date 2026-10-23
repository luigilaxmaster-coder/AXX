# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs, collect_data_files
from pathlib import Path

a = Analysis(
    ['backend/server.py'],
    pathex=[SPECPATH, str(Path(SPECPATH) / 'vendor' / 'cli_anything_blender')],
    binaries=collect_dynamic_libs('ctranslate2') + collect_dynamic_libs('av') + collect_dynamic_libs('tokenizers'),
    datas=[('resources/providers.default.json', 'resources'),
           ('backend/speech/moss_worker.py', 'speech'),
           ('resources/command-library.json', 'resources'),
           ('resources/procedure-library.zip', 'resources'),
           ('master_icon.png', '.'),
           ('vendor/cli_anything_blender/LICENSE', 'licenses/cli-anything'),
           ('vendor/cli_anything_blender/UPSTREAM.json', 'licenses/cli-anything'),
           ('resources/models/faster-whisper-tiny', 'models/faster-whisper-tiny')]
           + collect_data_files('faster_whisper'),
    hiddenimports=collect_submodules('backend', filter=lambda name: '.tests' not in name and '.test_' not in name) + [
        'cli_anything.blender.core.scene', 'cli_anything.blender.core.objects',
        'cli_anything.blender.core.lighting', 'cli_anything.blender.core.render',
        'cli_anything.blender.utils.bpy_gen', 'faster_whisper', 'ctranslate2',
        'av', 'numpy', 'tokenizers', 'huggingface_hub', 'pypdf'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchaudio', 'transformers', 'tensorflow', 'fairseq', 'onnxruntime', 'pandas', 'scipy', 'matplotlib', 'pytest', 'IPython'],
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
