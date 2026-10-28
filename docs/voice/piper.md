# Voces Piper en Axx

El apartado **Voces de Axx** reúne el selector compartido de chat, lector,
dictado y Voz en vivo. El chat conserva un selector y un botón de prueba
compactos. Elegir Piper no cambia **Xxx default** ni ninguna preferencia
guardada hasta que el usuario selecciona otra voz.

## Instalación local

En Windows con Python 3.12 instalado, desde este repositorio:

```powershell
python scripts/setup-piper-voices.py all
```

También se puede pasar `es_ES-carlfm-x_low` o `es_MX-ald-medium` para instalar
solo una voz. El script instala Piper 1.4.1 en un entorno privado, descarga
el modelo ONNX y su configuración desde `rhasspy/piper-voices`, y comprueba el
SHA256 del modelo. Los archivos quedan en `%LOCALAPPDATA%\Axx\speech\piper`.
Reinicia Axx y pulsa **Actualizar voces** en **Voces de Axx**. Una voz ausente
permanece visible pero deshabilitada; la voz elegida no se sustituye en silencio.

Piper usa un proceso local persistente que carga cada modelo una vez. El audio
sale por el lector existente, con pausa, cancelación y preferencia compartida.
Las dos voces de las capturas son CarlFM (España, 16 kHz, modelo ligero) y Ald
(México, 22,05 kHz, calidad media). La preparación inicial puede tardar varios
segundos. La calidad percibida y la latencia de micrófono a altavoz requieren
escucha y medición en la aplicación instalada.

Mediciones de síntesis aislada en este equipo, frase “Hola, soy Axx. ¿En qué
puedo ayudarte hoy?”, dos ejecuciones por voz después de preparar el modelo:

| Voz | Preparación inicial | Primera síntesis | Segunda síntesis |
| --- | ---: | ---: | ---: |
| CarlFM | 9,6 s | 813 ms | 390 ms |
| Ald | 7,7 s | 281 ms | 375 ms |

Son ejecuciones individuales del servicio local, no percentiles ni tiempos de
respuesta de Voz en vivo. La reproducción física no se verificó con esta prueba.

El runtime Piper actual tiene licencia GPL-3.0-or-later; los modelos tienen sus
propias fichas. El entorno Piper y los pesos se mantienen fuera del instalador
y del repositorio. Revisar licencias antes de redistribuirlos. Fuentes:
[API de Piper](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md),
[licencia del runtime](https://github.com/OHF-Voice/piper1-gpl/blob/main/setup.py),
[CarlFM](https://huggingface.co/rhasspy/piper-voices/blob/main/es/es_ES/carlfm/x_low/MODEL_CARD),
[Ald](https://huggingface.co/rhasspy/piper-voices/blob/main/es/es_MX/ald/medium/MODEL_CARD).
