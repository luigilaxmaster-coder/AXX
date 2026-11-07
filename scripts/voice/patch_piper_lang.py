from pathlib import Path
import re

path = Path('C:/Users/luigi/Desktop/axx2/backend/speech/piper_tts.py')
content = path.read_text(encoding='utf-8')

# Add _detect_language function before PiperSpeechService
detector_code = '''
_ES_MARKERS = re.compile(
    r'[¿¡ñáéíóúü]|\\b(el|la|los|las|un|una|unos|unas|y|o|de|del|en|con|por|para|que|no|me|te|se|mi|tu|su|nos|es|son|'
    r'fue|era|va|vamos|bien|muy|como|todo|todos|esto|esta|este|amor|cielo|vida|quiero|puedo|hola|gracias|bueno|buenas|'
    r'noches|dias|estoy|estas|estan|siento|perfecto|ahora|aqui|ya|si|tiempo|persona|hacer|estar|decir|ir|ver|dar|saber|'
    r'querer|llegar|pasar|deber|poner|parecer|quedar|creer|hablar|llevar|dejar|seguir|encontrar|llamar|venir|pensar|'
    r'salir|volver|tomar|conocer|vivir|sentir|tratar|mirar|contar|empezar|esperar|buscar|existir|entrar|trabajar|'
    r'escribir|perder|producir|ocurrir|entender|pedir|recibir|recordar|terminar|permitir|aparecer|conseguir|comenzar|'
    r'servir|sacar|necesitar|mantener|resultar|leer|caer|cambiar|presentar|crear|abrir|considerar|oir|acabar|ganar|'
    r'formar|traer|partir|morir|aceptar|realizar|suponer|comprender|lograr|explicar|preguntar|tocar|reconocer|estudiar|'
    r'alcanzar|nacer|dirigir|correr|utilizar|pagar|ayudar|gustar|jugar|escuchar|cumplir|ofrecer|descubrir|levantar|intentar)\\b',
    re.I
)

_EN_MARKERS = re.compile(
    r'\\b(the|is|are|was|were|you|your|he|she|it|they|we|my|him|her|them|that|this|these|those|and|but|if|of|at|by|for|'
    r'with|about|into|through|during|before|after|above|below|to|from|up|down|in|out|on|off|over|under|again|further|'
    r'then|once|here|there|when|where|why|how|all|any|both|each|few|more|most|other|some|such|no|nor|not|only|own|same|'
    r'so|than|too|very|can|will|just|should|now|hello|darling|honey|please|thank|thanks|welcome|good|morning|afternoon|'
    r'evening|night|yes|yeah|sure|okay|cool|awesome|great|nice|love|baby|sweetheart)\\b',
    re.I
)

def _detect_piper_language(text: str) -> str:
    es_score = len(_ES_MARKERS.findall(text))
    en_score = len(_EN_MARKERS.findall(text))
    if es_score > en_score:
        return 'es'
    if en_score > es_score:
        return 'en'
    if re.search(r'[¿¡ñáéíóúü]', text):
        return 'es'
    return 'es'
'''

if '_detect_piper_language' not in content:
    idx = content.find('def _private_meta')
    content = content[:idx] + detector_code + '\n\n' + content[idx:]

# Update synthesize in piper_tts.py
old_prep = """        # Clean spoken text and resolve language
        cleaned_text, lang = prepare_spoken_text(text, body.get('language', 'auto'))
        spoken_text = cleaned_text.strip() or text.strip()"""

new_prep = """        # Robust language resolution
        lang = body.get('language')
        if not lang or lang == 'auto':
            lang = _detect_piper_language(text)
        cleaned_text, _ = prepare_spoken_text(text, lang)
        spoken_text = cleaned_text.strip() or text.strip()"""

if old_prep in content:
    content = content.replace(old_prep, new_prep)

path.write_text(content, encoding='utf-8')
print("Successfully patched piper_tts.py with robust language detector!")
