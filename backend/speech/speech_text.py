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
    text = re.sub(r'[\u200b-\u200f\ufeff\ufe00-\ufe0f]', '', text)
    text = re.sub(r'[\U0001f000-\U0001faff\u2600-\u27bf]', ' ', text)
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
        # Email arroba and domains
        text = re.sub(r'(?<=\w)@(?=\w)', ' arroba ', text)
        text = re.sub(r'\.com\b', ' punto com', text, flags=re.I)
        # File extensions with leading dot
        exts = {'pdf': 'punto pe-de-efe', 'png': 'punto pe-ene-ge', 'jpg': 'punto jota-pe-ge',
                'jpeg': 'punto jota-pe-ge', 'wav': 'punto uav', 'mp3': 'punto eme-pe-tres',
                'mp4': 'punto eme-pe-cuatro', 'txt': 'punto te-equis-te', 'csv': 'punto ce-ese-uve',
                'json': 'punto yeison', 'zip': 'punto sip', 'html': 'punto hache-te-eme-ele',
                'css': 'punto ce-ese-ese', 'js': 'punto jota-ese'}
        for ext, spoken in exts.items():
            text = re.sub(r'\.' + ext + r'\b', ' ' + spoken, text, flags=re.I)
        # Technical acronyms and natural Spanish loanword phonetics:
        text = re.sub(r'\bPDF\b', 'pe-de-efe', text)
        text = re.sub(r'\bPNG\b', 'pe-ene-ge', text)
        text = re.sub(r'\bJPG\b|\bJPEG\b', 'jota-pe-ge', text)
        text = re.sub(r'\bWAV\b', 'uav', text)
        text = re.sub(r'\bMP3\b', 'eme-pe-tres', text)
        text = re.sub(r'\bMP4\b', 'eme-pe-cuatro', text)
        text = re.sub(r'\bTXT\b', 'te-equis-te', text)
        text = re.sub(r'\bURL\b', 'u-erre-ele', text)
        text = re.sub(r'\bWi[-]?Fi\b', 'uay-fay', text, flags=re.I)
        text = re.sub(r'\b(?:okay|ok)\b', 'okey', text, flags=re.I)
        # Units of measurement (when preceded by a cardinal)
        units = [
            (r'\b(\d+)\s*cm\b', lambda m: m.group(1) + (' centímetro' if m.group(1) == '1' else ' centímetros')),
            (r'\b(\d+)\s*mm\b', lambda m: m.group(1) + (' milímetro' if m.group(1) == '1' else ' milímetros')),
            (r'\b(\d+)\s*km\b', lambda m: m.group(1) + (' kilómetro' if m.group(1) == '1' else ' kilómetros')),
            (r'\b(\d+)\s*kg\b', lambda m: m.group(1) + (' kilo' if m.group(1) == '1' else ' kilos')),
            (r'\b(\d+)\s*ms\b', lambda m: m.group(1) + (' milisegundo' if m.group(1) == '1' else ' milisegundos')),
            (r'\b(\d+)\s*(?:seg|s)\b', lambda m: m.group(1) + (' segundo' if m.group(1) == '1' else ' segundos')),
            (r'\b(\d+)\s*min\b', lambda m: m.group(1) + (' minuto' if m.group(1) == '1' else ' minutos')),
            (r'\b(\d+)\s*(?:hrs|h)\b', lambda m: m.group(1) + (' hora' if m.group(1) == '1' else ' horas')),
            (r'\b(\d+)\s*°C\b', lambda m: m.group(1) + (' grado Celsius' if m.group(1) == '1' else ' grados Celsius')),
            (r'\b(\d+)\s*GB\b', lambda m: m.group(1) + ' gigabytes'),
            (r'\b(\d+)\s*MB\b', lambda m: m.group(1) + ' megabytes'),
            (r'\b(\d+)\s*KB\b', lambda m: m.group(1) + ' kilobytes'),
        ]
        for pattern, repl in units:
            text = re.sub(pattern, repl, text, flags=re.I)
        # Missing accents restoration on common conversational words
        common_accents = {
            'codigo': 'código', 'codigos': 'códigos',
            'digito': 'dígito', 'digitos': 'dígitos',
            'musica': 'música',
            'microfono': 'micrófono', 'microfonos': 'micrófonos',
            'cancion': 'canción', 'canciones': 'canciones',
            'numero': 'número', 'numeros': 'números',
            'telefono': 'teléfono', 'telefonos': 'teléfonos',
            'tambien': 'también', 'despues': 'después', 'aqui': 'aquí',
            'ultimo': 'último', 'ultima': 'última', 'facil': 'fácil', 'dificil': 'difícil',
            'pagina': 'página', 'paginas': 'páginas', 'rapido': 'rápido', 'rapida': 'rápida',
        }
        for unacc, acc in common_accents.items():
            text = re.sub(r'\b' + unacc + r'\b',
                          lambda m, r=acc: r.capitalize() if m.group()[0].isupper() else r,
                          text, flags=re.I)
        # Conversational discourse breathing pauses for natural pacing
        starters = r'Hola(?:\s+principal)?|Por\s+supuesto|Entendido|De\s+acuerdo|Sin\s+embargo|Por\s+ejemplo|Claro(?:\s+que\s+sí)?|Además|Con\s+gusto|En\s+efecto|Perfecto|Excelente'
        text = re.sub(r'(?i)(^|[.!?]\s+)(' + starters + r')(?!\s*[,;:.!?])\s+',
                      lambda m: (m.group(1) or '') + m.group(2) + ', ', text)
        # Do not reinterpret versions, URLs, dates, IDs or decimal/grouped forms.
        # Isolated cardinal numbers, percentages, and comma-separated lists have a clear reading.
        text = re.sub(r'(?<![\w./:\-])(?<!\d,)(?:0|[1-9][0-9]{0,3})\s*%(?!\w)',
                      lambda m: spanish_integer(int(m.group()[:-1].strip())) + ' por ciento', text)
        text = re.sub(r'(?<![\w./:\-])(?<!\d,)(?:0|[1-9][0-9]{0,3})(?![\w/:\-]|\.\d|,\d)',
                      lambda m: spanish_integer(int(m.group())), text)
    text = re.sub(r'(?<=\D),\s*|\s*,(?=\D)', ', ', text)
    text = re.sub(r'(?:,\s*)+,', ', ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\s+([,.;:!?])', r'\1', text)
    if text and text[-1] not in '.!?;:':
        text += '.'
    return text, lang
