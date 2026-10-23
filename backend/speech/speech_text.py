"""Small, deterministic spoken-text preparation; never changes displayed text.

No phoneme API is assumed. Spanish keeps its accents and sentence punctuation;
unambiguous numbers/abbreviations are expanded before the multilingual model.
Unknown languages retain the upstream normalizer. No audio or text is logged.
"""
from __future__ import annotations

import re
import unicodedata

_SMALL = ('cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece '
          'catorce quince dieciséis diecisiete dieciocho diecinueve veinte veintiuno '
          'veintidós veintitrés veinticuatro veinticinco veintiséis veintisiete '
          'veintiocho veintinueve').split()
_TENS = ('', '', '', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa')
_HUNDREDS = ('', 'ciento', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos',
             'seiscientos', 'setecientos', 'ochocientos', 'novecientos')


def spanish_integer(value: int) -> str:
    if not 0 <= value <= 9999:
        raise ValueError('Number outside spoken cardinal range')
    if value < 30:
        return _SMALL[value]
    if value < 100:
        return _TENS[value // 10] + (' y ' + _SMALL[value % 10] if value % 10 else '')
    if value == 100:
        return 'cien'
    if value < 1000:
        return _HUNDREDS[value // 100] + (' ' + spanish_integer(value % 100) if value % 100 else '')
    return ('mil' if value < 2000 else _SMALL[value // 1000] + ' mil') + (
        ' ' + spanish_integer(value % 1000) if value % 1000 else '')


def resolve_language(text: str, language: str = 'auto') -> str:
    base = language.lower().split('-')[0]
    if base != 'auto':
        return base
    # Only infer Spanish with positive evidence; short ambiguous fragments stay
    # automatic. Native callers send their selected language explicitly.
    if re.search(r'[¿¡ñáéíóúü]|\b(hola|soy|estoy|puedes|señor|gracias|para|tienes)\b', text, re.I):
        return 'es'
    return 'en' if re.search(r'[a-z]', text, re.I) else 'auto'


def prepare_spoken_text(text: str, language: str = 'auto') -> tuple[str, str]:
    text = unicodedata.normalize('NFC', text)
    lang = resolve_language(text, language)
    if lang not in ('es', 'en'):
        return text, lang
    text = re.sub(r'[\u200b-\u200f\ufeff]', '', text)
    text = re.sub(r'\[([^\]]+)\]\(https?://[^)]+\)', r'\1', text)
    text = re.sub(r'(?m)^\s*(?:#{1,6}\s+|[-*•]\s+)', '', text)
    text = text.replace('**', '').replace('`', '').replace('*', '')
    text = re.sub(r'\s*[—–]\s*', ', ', text)
    text = re.sub(r'(?:\.{3,}|…+)', ', ', text)
    text = re.sub(r'([!?.,])\1+', r'\1', text)
    if lang == 'es':
        # Spoken text only; visible responses and command payloads are intact.
        initials = {'PC': 'computadora', 'CPU': 'procesador', 'GPU': 'tarjeta gráfica',
                    'USB': 'u ese be', 'RAM': 'ram', 'QR': 'cu erre', 'CMD': 'ce eme de'}
        text = re.sub(r'\b(?:PC|CPU|GPU|USB|RAM|QR|CMD)\b', lambda m: initials[m.group()], text)
        text = re.sub(r'\bwi[ -]?fi\b', 'wifi', text, flags=re.I)
        abbreviations = {'Sr': 'señor', 'Sra': 'señora', 'Dr': 'doctor', 'Dra': 'doctora',
                         'Ud': 'usted', 'Uds': 'ustedes', 'aprox': 'aproximadamente', 'etc': 'etcétera'}
        for short, full in abbreviations.items():
            text = re.sub(r'\b' + short + r'\.(?=\s|$)', full, text, flags=re.I)
        # Do not reinterpret versions, URLs, dates, IDs or decimal/grouped forms.
        # Only isolated cardinal numbers and percentages have a clear reading.
        text = re.sub(r'(?<![\w./:,\-])(?:0|[1-9][0-9]{0,3})\s*%(?!\w)',
                      lambda m: spanish_integer(int(m.group()[:-1].strip())) + ' por ciento', text)
        text = re.sub(r'(?<![\w./:,\-])(?:0|[1-9][0-9]{0,3})(?![\w/,:\-]|\.\d)',
                      lambda m: spanish_integer(int(m.group())), text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\s+([,.;:!?])', r'\1', text)
    if text and text[-1] not in '.!?;:':
        text += '.'
    return text, lang
