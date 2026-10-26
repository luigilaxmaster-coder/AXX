import os
from pathlib import Path
import tempfile
import unittest
from PIL import Image, ImageDraw, ImageFont
from backend.actions.artifact_verification import run_inspector
from backend.actions.local_ocr import models


@unittest.skipUnless(os.environ.get('AXX_TEST_OCR_NATIVE') == '1', 'requires private verified OCR models')
class LocalOcrTests(unittest.TestCase):
    def test_latin_model_preserves_spanish_numbers_units_and_negation(self):
        models()
        with tempfile.TemporaryDirectory() as folder:
            image = Image.new('RGB', (1100,240), 'white')
            draw = ImageDraw.Draw(image)
            font = ImageFont.truetype(str(Path(os.environ['WINDIR'])/'Fonts/arial.ttf'), 36)
            expected = ['Año 2026 - revisión técnica', 'Área 12,50 m² - longitud 3,25 m', 'NO borrar plano_ñ.ifc']
            for i, text in enumerate(expected): draw.text((35,20+i*65), text, font=font, fill='black')
            target = Path(folder)/'spanish.png'; image.save(target)
            result = run_inspector('ocr', str(target))
            text = ' '.join(result['text'].split())
            self.assertEqual(text, ' '.join(expected))
            self.assertFalse(result['confidence_calibrated'])
            self.assertTrue(result['local_only'])
            self.assertEqual(result['semantic_verification'], 'unverified')
            report = Path(__file__).resolve().parents[2]/'evidence/mcp-expansion-20261026/ocr-spanish.json'
            import json
            report.parent.mkdir(exist_ok=True, parents=True)
            report.write_text(json.dumps({'source_only':True,'expected':expected,'recognized':result['text'],
                'elapsed_seconds':result['elapsed_seconds'],'model':'Latin PP-OCRv5','fixture_passed':True},ensure_ascii=False,indent=2),encoding='utf-8')
