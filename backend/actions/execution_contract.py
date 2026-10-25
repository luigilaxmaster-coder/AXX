"""Delivery policy for registered local tools; no inferred external capabilities."""
from __future__ import annotations

import os
from pathlib import Path
import time

MODES = ('background', 'foreground', 'isolated')
# Only implementations with no global input, launch or clipboard path belong here.
BACKGROUND_TOOLS = frozenset({
    'file_artifact_writer', 'file_inspection', 'system_telemetry', 'process_state_inspector',
    'architecture_status', 'desktop_list_apps', 'desktop_list_windows',
    'desktop_inspect_window', 'desktop_read_window', 'desktop_cli_anything_scan',
    'desktop_find_control',
})


def delivery_policy(tool_name):
    background = tool_name in BACKGROUND_TOOLS
    return {'default_mode': 'background' if background else 'foreground',
            'supported_modes': ['background', 'foreground'] if background else ['foreground'],
            'may_use_global_input': not background,
            'isolation_verified': False}


def resolve_mode(tool_name, requested=None):
    policy = delivery_policy(tool_name)
    mode = policy['default_mode'] if requested is None else requested
    if not isinstance(mode, str) or mode not in MODES:
        raise ValueError('Modo de entrega inválido: usa background, foreground o isolated.')
    if mode not in policy['supported_modes']:
        raise ValueError(f'{mode}_unavailable: la operación no dispone de esa ruta; no se cambió de modo.')
    return mode


def architecture_status():
    worker = Path(__file__).with_name('uia_worker.ps1')
    powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    uia_ready = os.name == 'nt' and worker.is_file() and powershell.is_file()
    return {'schema_version': 1, 'observed_at': time.time(), 'context_id': 'host',
            'components': [
                {'id': 'command_executor', 'state': 'available', 'backend': 'axx_native',
                 'reason': 'Registro cerrado, aprobación, cancelación y diario SQLite.'},
                {'id': 'windows_uia', 'state': 'available' if uia_ready else 'unavailable',
                 'backend': 'axx_native', 'reason': 'Worker local presente; compatibilidad por control se verifica al observar.' if uia_ready else 'Falta Windows o el worker de UIA.'},
                {'id': 'model_router', 'state': 'unknown',
                 'reason': 'Router existente; credenciales y ejecución se comprueban por solicitud en Proveedores.'},
                *[{'id': name, 'state': 'unavailable', 'reason': reason} for name, reason in (
                    ('cua_driver', 'No hay adaptador Cua registrado. UIA nativa no equivale a Cua.'),
                    ('visual_grounding', 'No hay modelo visual calibrado ni pesos verificados registrados.'),
                    ('rea', 'No hay proveedor REA registrado y validado para este runtime.'),
                    ('isolated_desktop', 'No hay contexto VM con aislamiento verificado registrado.'),
                    ('telegram', 'No hay canal Telegram autenticado registrado.'),
                )]],
            'limitation': 'Un skill o un ejecutable instalado no habilita una capacidad. Sin fallback de modo.'}
