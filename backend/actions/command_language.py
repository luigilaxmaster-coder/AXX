"""Spanish command carriers and slot aliases; never rewrite arbitrary payloads."""
import re
import unicodedata
from difflib import SequenceMatcher


def plain(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c))


VERBS = {
    'abre': ('abre', 'abrir', 'abrirme', 'abreme', 'abras', 'abrirnos', 'lanza', 'lanzar', 'arranca', 'inicia', 'iniciar'),
    'cierra': ('cierra', 'cerrar', 'cerrarme', 'cierrame', 'cierres'),
    'busca': ('busca', 'buscar', 'buscarme', 'buscame', 'busques'),
    'reproduce': ('reproduce', 'reproducir', 'reproduceme', 'reproduzcas', 'escucha', 'escuchar'),
    'mueve': ('mueve', 'mover', 'moverme', 'mueveme', 'muevas', 'coloca', 'colocar', 'colocame'),
    'enfoca': ('enfoca', 'enfocar', 'enfoques'),
    'lee': ('lee', 'leer', 'leeme', 'leas'),
    'pulsa': ('pulsa', 'pulsar', 'pulses'),
}
FORM = {word: verb for verb, words in VERBS.items() for word in words}
VOICE_VERBS = {'habre': 'abre', 'avre': 'abre', 'bosca': 'busca', 'vusca': 'busca',
               'reprogoce': 'reproduce', 'reprodose': 'reproduce'}
TARGETS = {'you tube': 'youtube', 'yotube': 'youtube', 'yotune': 'youtube', 'google chrome': 'chrome', 'chat gpt': 'chatgpt'}
VOICE_TARGETS = {'yotube': 'youtube', 'yutube': 'youtube', 'yu tube': 'youtube',
                 'crom': 'chrome', 'gugle': 'google', 'espotifai': 'spotify',
                 'espotify': 'spotify', 'spatifi': 'spotify', 'obsedia': 'obsidian'}
CARRIER = re.compile(
    r'^(?:(?:(?:oye|hola|hey|ok|ey|escucha)[,\s]+)?axx\b[\s,.:!-]*|(?:oye|hola|hey)[,\s]+|'
    r'por\s+favor[,\s]+|(?:(?:me|nos)\s+)?(?:puedes|podr[ií]as|pod[ií]as)[,:\s]+|'
    r'(?:quiero|necesito|quisiera|me\s+gustar[ií]a)\s+que\s+(?:me\s+)?|primero[,\s]+|pero\s+)', re.I)
SEARCH_TARGETS = {'chrome', 'youtube', 'google', 'bing', 'duckduckgo', 'internet', 'spotify'}
SEARCH_NAMES = '|'.join(re.escape(name) for name in sorted(SEARCH_TARGETS | TARGETS.keys() | VOICE_TARGETS.keys(), key=len, reverse=True))


def command_sequence(text, source):
    raw = command_carrier(text)
    if raw.startswith('/'):
        return None
    forms = set(FORM) | {'encuentra','encontrar','localiza','lista','muestra','consulta','pausa','reanuda','inspecciona','crea','crear','copia','renombra','calcula','guarda','borra','elimina','envia','organiza','convierte','descarga','instala'}
    head = re.match(r'\w+', raw)
    leading_search = re.match(r'^(?:en|and)\s+(?:'+SEARCH_NAMES+r')[.,:]?\s+(?:busca|buscar|buscame|búscame|encuentra|encontrar|localiza)\b',raw,re.I)
    if not head or not leading_search and plain(head[0]) not in forms | (set(VOICE_VERBS) if source == 'voice' else set()): return None
    # Mask quoted payloads before finding separators; preserve original offsets and text.
    masked = list(raw); quote = None; escaped = False
    for index, char in enumerate(raw):
        if quote:
            masked[index] = ' '
            if char == quote and not escaped: quote = None
            escaped = char == '\\' and not escaped
        elif char in ('"', '«', '“') or char == "'" and (index == 0 or not raw[index-1].isalnum()):
            quote = {'«':'»','“':'”'}.get(char,char); masked[index] = ' '; escaped = False
    verbs = r'(?:' + '|'.join(sorted(forms | {'envía','escribe','pega','teclea'}, key=len, reverse=True)) + r')\b'
    separator = r'\s*(?:;|\n+|\s+(?:y\s+)?(?:luego|despu[eé]s)\s*,?\s+|,\s*(?:y\s+)?(?='+verbs+r')|\s+y\s+(?='+verbs+r'))\s*'
    cuts = list(re.finditer(separator, ''.join(masked), re.I))
    if not cuts: return None
    starts = [0] + [cut.end() for cut in cuts]
    ends = [cut.start() for cut in cuts] + [len(raw)]
    for index, start in enumerate(starts):
        if re.match(r'(?:escribe|pega|teclea)\b',raw[start:],re.I):
            # Free-form typing owns its entire remaining payload, including command-like words.
            return [raw[a:b].strip() for a,b in zip(starts[:index],ends[:index])] + [raw[start:].strip()]
    return [raw[start:end].strip() for start,end in zip(starts,ends)]


def target_name(value, source):
    key = ' '.join(plain(value).strip(' .!?').split())
    return (VOICE_TARGETS.get(key) if source == 'voice' else None) or TARGETS.get(key) or value


def command_carrier(text):
    """Strip only the request prefix, before interpreting any argument slots."""
    raw = text.strip()
    if raw.startswith('/') or re.match(r'^ejecuta\s+en\s+(?:cmd|powershell):', raw, re.I):
        return raw
    raw = re.sub(r'^[¡¿\s]+', '', raw)
    for _ in range(6):
        stripped = CARRIER.sub('', raw, count=1).lstrip('¿¡ ,')
        if stripped == raw: break
        raw = stripped
    if re.match(r'^(?:escribe|pega|teclea)\b', raw, re.I):
        return raw
    raw = re.sub(r',\s*por favor[?.!]*$', '', raw, flags=re.I)
    desire = re.match(r'^(?:quiero|necesito|quisiera|me gustar[ií]a)\s+(\w+)\b', raw, re.I)
    if desire and plain(desire[1]) in FORM:
        raw = raw[desire.start(1):]
    return raw


def command_text(text, source):
    """Return canonical command syntax while keeping every argument literal."""
    raw = command_carrier(text)
    if raw.startswith('/') or re.match(r'^(?:escribe|pega|teclea|ejecuta\s+en\s+(?:cmd|powershell):)\b', raw, re.I):
        return raw
    # Only an explicit imperative carrier is removed. Negation, quotes and
    # informational requests keep their leading words and cannot match a verb.
    def verb(word):
        key = plain(word)
        return FORM.get(key) or (VOICE_VERBS.get(key) if source == 'voice' else None)
    leading_target = re.fullmatch(r'(?:en|and)\s+('+SEARCH_NAMES+r')[.,:]?\s+(\w+)\b(?:\s+([\s\S]+))?', raw, re.I)
    if leading_target and (source == 'voice' or not raw.lower().startswith('and ')):
        target = plain(target_name(leading_target[1], source))
        if target in SEARCH_TARGETS and (verb(leading_target[2]) == 'busca' or plain(leading_target[2]) in {'encuentra','encontrar','localiza'}):
            query = leading_target[3] or ''
            return ('en Chrome busca ' if target == 'chrome' else 'busca en '+target+' ')+query
    head = re.match(r'^(\w+)\b', raw)
    if head and (canonical := verb(head[1])):
        tail = raw[head.end():]
        if source == 'voice':tail = re.sub(r'^[.,:]\s+', ' ', tail)
        if canonical in {'abre','cierra','enfoca','lee','mueve','pulsa'}:
            tail = re.sub(r'\s+por favor[?.!]*$', '', tail, flags=re.I)
        raw = canonical+tail
    explicit_search = re.fullmatch(r'(?:encuentra|encontrar|localiza)\s+([\s\S]+?)\s+(?:en|usando|con)\s+('+SEARCH_NAMES+r')[.!?]*', raw, re.I)
    if explicit_search and plain(target_name(explicit_search[2],source)) in SEARCH_TARGETS:
        raw = 'busca '+explicit_search[1]+' en '+plain(target_name(explicit_search[2],source))
    leading_slot = re.fullmatch(r'(busca|reproduce|ponme|pon)\s+en\s+('+SEARCH_NAMES+r')(\s+[\s\S]+)?', raw, re.I)
    if leading_slot:
        target = plain(target_name(leading_slot[2], source))
        if target in SEARCH_TARGETS:
            raw = leading_slot[1]+' en '+target+(leading_slot[3] or '')
    trailing_slot = re.fullmatch(r'(busca|reproduce|ponme|pon)\s+([\s\S]+?)\s+en\s+('+SEARCH_NAMES+r')[.!?]*', raw, re.I)
    if trailing_slot:
        target = plain(target_name(trailing_slot[3], source))
        if target in SEARCH_TARGETS:
            raw = trailing_slot[1]+' '+trailing_slot[2]+' en '+target
    media = re.fullmatch(r'(reproduce|reanuda|pausa)\s+([\w ]{2,30})[.!?]*', raw, re.I)
    if media and plain(target_name(media[2], source)) == 'spotify':
        raw = media[1]+' Spotify'
    search = re.fullmatch(r'busca\s+([\s\S]+?)\s+(?:usando|con|en)\s+([\w ]{2,30})[.!?]*', raw, re.I)
    if search:
        target = plain(target_name(search[2], source)).strip(' .!?')
        if target in SEARCH_TARGETS:
            return ('en Chrome busca '+search[1] if target == 'chrome' else 'busca '+search[1]+' en '+target)
    return raw


def voice_suggestion(text):
    """A close unknown verb is a question, never execution authorization."""
    head = re.match(r'^(\w{5,14})\s+(.{2,200})$', text)
    if not head or plain(head[1]) in FORM or plain(head[1]) in {'nunca','explica','explicame','quisiera','quiero','necesito'}:
        return None
    scores = {}
    for form, canonical in FORM.items():
        score = SequenceMatcher(None, plain(head[1]), form).ratio()
        scores[canonical] = max(scores.get(canonical,0),score)
    ranked = sorted(scores.items(),key=lambda item:item[1],reverse=True)
    if ranked[0][1] < .85 or ranked[0][1]-ranked[1][1] < .12:return None
    return ranked[0][0]+' '+head[2]
