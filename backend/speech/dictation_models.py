"""Pinned, local-only model selection; never downloads or executes user paths."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from .windows_tts import SpeechError

CATALOG = json.loads(Path(__file__).with_name('dictation-models.json').read_text(encoding='utf-8'))


def model_root():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Axx' / 'models'


def cpp_binary():
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2] / 'workers' / 'dictation-asr' / 'target' / 'release'
    return base / 'axx-dictation-asr.exe'


def models(default_path):
    rows = []
    installed = bool(importlib.util.find_spec('faster_whisper'))
    for name in ('tiny', 'base', 'small', 'medium'):
        path = model_root() / ('faster-whisper-' + name)
        if default_path is not None and default_path.name == path.name: path = default_path
        available = installed and all((path / f).is_file() for f in ('model.bin', 'tokenizer.json', 'config.json', 'vocabulary.txt'))
        rows.append({'id': 'faster-whisper-' + name, 'engine': 'faster-whisper', 'available': available, 'translation_target': 'en', 'forced_language': True, 'local_only': True})
    for item in CATALOG['models']:
        path = model_root() / 'dictation' / item['filename']
        rows.append({**item, 'available': cpp_binary().is_file() and path.is_file() and path.stat().st_size == item['size'],
                     'verification': 'sha256_before_load', 'forced_language': item['family'] != 'parakeet', 'local_only': True})
    return {'api_version': 1, 'models': rows, 'downloads': False, 'default': 'existing-asr', 'engine_version': CATALOG['engine_version']}


def resolve(model_id, default_path, language, task):
    if not isinstance(model_id, str): raise SpeechError('INVALID_REQUEST', 'Invalid model ID')
    if model_id in {'faster-whisper-' + n for n in ('tiny', 'base', 'small', 'medium')}:
        path = model_root() / model_id
        if default_path is not None and default_path.name == model_id: path = default_path
        if not all((path / f).is_file() for f in ('model.bin', 'tokenizer.json', 'config.json', 'vocabulary.txt')):
            raise SpeechError('NOT_SUPPORTED', 'Selected local Whisper model is not installed')
        return 'faster-whisper', path
    item = next((m for m in CATALOG['models'] if m['id'] == model_id), None)
    if item is None: raise SpeechError('INVALID_REQUEST', 'Unknown local model ID')
    if task != 'prepare' and language is None and not item['capabilities']['languageDetection']:
        raise SpeechError('NOT_SUPPORTED', 'Selected model requires an explicit source language')
    if language is not None and language not in item['languages']: raise SpeechError('NOT_SUPPORTED', 'Language unavailable in selected model')
    if task == 'translate' and not item['capabilities']['translate']: raise SpeechError('NOT_SUPPORTED', 'Selected model cannot translate')
    path = model_root() / 'dictation' / item['filename']
    if not cpp_binary().is_file() or not path.is_file(): raise SpeechError('NOT_SUPPORTED', 'Native ASR worker/model is not installed')
    if path.stat().st_size != item['size']: raise SpeechError('INVALID_REQUEST', 'Model size mismatch')
    return 'transcribe-cpp', path


def verify_cpp_model(path):
    item = next((m for m in CATALOG['models'] if m['filename'] == Path(path).name), None)
    if item is None: raise SpeechError('INVALID_REQUEST', 'Uncatalogued native model')
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''): digest.update(block)
    if digest.hexdigest() != item['sha256']: raise SpeechError('INVALID_REQUEST', 'Native model SHA256 mismatch')
