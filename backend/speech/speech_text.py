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
    text = re.sub(r'["“”«»]', '', text)
    text = re.sub(r'\s*\(([^)]+)\)\s*', r', \1, ', text)
    text = re.sub(r'\s*[—–]\s*', ', ', text)
    text = re.sub(r'(?:\.{3,}|…+)', ', ', text)
    text = re.sub(r'([!?.,])\1+', r'\1', text)
    if lang == 'es':
        text = text.replace(';', ',')
        text = re.sub(r'(?<=[a-zA-ZáéíóúÁÉÍÓÚñÑ]):(?=\s+[a-zA-ZáéíóúÁÉÍÓÚñÑ])', ',', text)
        abbreviations = {'Sr': 'señor', 'Sra': 'señora', 'Dr': 'doctor', 'Dra': 'doctora',
                         'Ud': 'usted', 'Uds': 'ustedes', 'aprox': 'aproximadamente', 'etc': 'etcétera',
                         'pág': 'página', 'págs': 'páginas', 'ej': 'ejemplo', 'atte': 'atentamente',
                         'depto': 'departamento', 'ing': 'ingeniero', 'lic': 'licenciado'}
        for short, full in abbreviations.items():
            text = re.sub(r'\b' + short + r'\.(?=\s|$)', full, text, flags=re.I)
        # Ordinal numbers: 1º, 1ª, 2º, etc.
        text = re.sub(r'\b1(?:º|er)\b', 'primer', text, flags=re.I)
        text = re.sub(r'\b1ª\b', 'primera', text, flags=re.I)
        text = re.sub(r'\b2(?:º|do)\b', 'segundo', text, flags=re.I)
        text = re.sub(r'\b2ª\b', 'segunda', text, flags=re.I)
        text = re.sub(r'\b3(?:º|er)\b', 'tercer', text, flags=re.I)
        text = re.sub(r'\b3ª\b', 'tercera', text, flags=re.I)
        # Technical acronyms:
        text = re.sub(r'\bPDF\b', 'pe-de-efe', text)
        text = re.sub(r'\bURL\b', 'u-erre-ele', text)
        text = re.sub(r'\bWi[-]?Fi\b', 'uay-fay', text, flags=re.I)
        # Conversational discourse breathing pauses for natural pacing
        starters = r'Hola(?:\s+principal)?|Por\s+supuesto|Entendido|De\s+acuerdo|Sin\s+embargo|Por\s+ejemplo|Claro(?:\s+que\s+sí)?|Además|Con\s+gusto|En\s+efecto|Perfecto|Excelente'
        text = re.sub(r'(?i)(^|[.!?]\s+)(' + starters + r')(?!\s*[,;:.!?])\s+',
                      lambda m: (m.group(1) or '') + m.group(2) + ', ', text)
        # Do not reinterpret versions, URLs, dates, IDs or decimal/grouped forms.
        # Only isolated cardinal numbers and percentages have a clear reading.
        text = re.sub(r'(?<![\w./:,\-])(?:0|[1-9][0-9]{0,3})\s*%(?!\w)',
                      lambda m: spanish_integer(int(m.group()[:-1].strip())) + ' por ciento', text)
        text = re.sub(r'(?<![\w./:,\-])(?:0|[1-9][0-9]{0,3})(?![\w/,:\-]|\.\d)',
                      lambda m: spanish_integer(int(m.group())), text)
    text = re.sub(r'(?<=\D),\s*|\s*,(?=\D)', ', ', text)
    text = re.sub(r'(?:,\s*)+,', ', ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\s+([,.;:!?])', r'\1', text)
    if text and text[-1] not in '.!?;:':
        text += '.'
    return text, lang
