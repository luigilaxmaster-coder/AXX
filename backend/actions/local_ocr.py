"""Local Latin OCR over bounded images; recognizer scores never authorize input."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading

from .file_inspection import hash_file, validate_path


def models():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    manifest = json.loads((root/'resources/ocr-model-manifest.json').read_text())
    private = Path(os.environ.get('LOCALAPPDATA', Path.home()))/'Axx/models/ocr'
    paths = {}
    for kind, record in manifest['models'].items():
        path = private/record['file']
        if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('OCR_UNAVAILABLE: ejecuta scripts/prepare-ocr.py para instalar los modelos latinos verificados')
        if hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError('OCR_UNAVAILABLE: el hash del modelo no coincide')
        paths[kind + '_model_path'] = str(path)
    return paths


def inspect_ocr(raw):
    from PIL import Image
    from rapidocr_onnxruntime import RapidOCR
    import numpy as np
    path = validate_path(raw)
    if path.stat().st_size > 20 * 1024 * 1024: raise ValueError('El recorte supera 20 MiB')
    before = hash_file(str(path), threading.Event())
    with Image.open(path) as image:
        if image.format not in ('PNG', 'JPEG') or image.width * image.height > 4_000_000:
            raise ValueError('OCR requiere un recorte PNG/JPEG de hasta 4 megapíxeles')
        image = image.convert('RGB')
        engine = RapidOCR(**models(), intra_op_num_threads=2, inter_op_num_threads=1)
        result, elapsed = engine(np.array(image), use_cls=False)
        lines = []
        for box, text, score in result or []:
            points = [[float(x), float(y)] for x,y in box]
            if (len(points) != 4 or any(not math.isfinite(v) for point in points for v in point)
                    or not 0 <= float(score) <= 1 or len(text) > 2000):
                raise ValueError('OCR devolvió una caja o texto fuera de límites')
            if any(not 0 <= x <= image.width or not 0 <= y <= image.height for x,y in points):
                raise ValueError('OCR devolvió coordenadas fuera del recorte')
            lines.append({'text': text, 'box': points, 'recognizer_score': float(score)})
        if len(lines) > 500 or sum(len(row['text']) for row in lines) > 12000: raise ValueError('El OCR excedió el límite de texto')
        width, height = image.size
    if hash_file(str(path), threading.Event()) != before: raise ValueError('La imagen cambió durante el OCR')
    return {**before, 'text': '\n'.join(row['text'] for row in lines), 'lines': lines, 'width': width, 'height': height,
            'engine': 'RapidOCR 1.4.4 / Latin PP-OCRv5 / CPU', 'elapsed_seconds': elapsed,
            'verification': 'local_ocr_response', 'confidence_calibrated': False, 'semantic_verification': 'unverified', 'local_only': True}


class DesktopOcrTool:
    name, version = 'computer_ocr', '1.0.0'
    description = 'Read a fresh observed window crop locally, without sending the image or dispatching input'

    def verify_preconditions(self, inputs):
        from .computer_tools import ComputerTool
        return ComputerTool('ocr').verify_preconditions(inputs)

    def execute_with_runtime(self, inputs, workspace_root, cancelled, runtime):
        from .tools import ToolResult
        from .artifact_verification import run_inspector
        from .visual_grounding import captured_window, _current
        from . import windows_automation as uia
        try:
            valid, reason = self.verify_preconditions(inputs)
            if not valid: raise ValueError(reason)
            observed = uia.get_observation(inputs['observation_id'], inputs['window_id'], inputs['pid'])
            capture = getattr(runtime, 'capture_service', None)
            _current(observed)
            frame, crop, source, shot = captured_window(observed, capture)
            digest = hashlib.sha256(frame.tobytes()).hexdigest()
            with tempfile.TemporaryDirectory(prefix='axx-ocr-') as folder:
                path = Path(folder)/'crop.png'; frame.save(path)
                output = run_inspector('ocr', str(path), cancelled)
            _current(observed)
            refreshed = capture.capture({'monitor': source['id']})
            fresh = capture.original(refreshed).crop(crop)
            _current(observed)
            if cancelled.is_set() or fresh.size != frame.size or hashlib.sha256(fresh.tobytes()).hexdigest() != digest:
                raise ValueError('STALE_OBSERVATION: el recorte cambió; observa de nuevo')
            output.pop('path', None)
            output.update(observation_id=inputs['observation_id'], source_sha256=shot['sha256'],
                          transform={'scale_x':1,'scale_y':1,'offset_x':source['x']+crop[0],'offset_y':source['y']+crop[1]})
            return ToolResult(True, output=output, evidence={'verification':'unchanged_window_crop_ocr', 'effect_executed':False})
        except Exception as exc:
            return ToolResult(False, error=str(exc)[:600], evidence={'cancelled':cancelled.is_set()})

    def verify_postconditions(self, inputs, result):
        return bool(result.success and result.evidence.get('verification') == 'unchanged_window_crop_ocr'), 'OCR local de recorte sin cambios'
