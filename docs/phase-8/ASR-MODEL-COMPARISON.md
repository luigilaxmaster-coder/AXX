# Motores: comparación y límites

Selección por solicitud/tarea, sin imponer Parakeet. El dictado global y archivos
usan model opcional; chat/comandos/conversación conservan el motor anterior.
El endpoint compartido permite que esas superficies elijan un ID en el futuro
sin cambiar su proveedor ni sus permisos. Modelos disponibles no se descargan.

| Modelo | Integración | Ejecución real de pesos en esta fase |
| --- | --- | --- |
| faster-whisper base existente | Supervisor actual CPU int8 y respaldo por defecto | Sí, 3 clips SAPI ingleses sintéticos |
| faster-whisper tiny/small/medium | Selección local por ID | No, pesos seleccionables no presentes en raíz local |
| Parakeet V3 Q8_0 | Sidecar CPU compilado, catálogo con hash | BLOQUEADO: pesos no instalados |
| Whisper Small/Medium GGUF | Mismo sidecar y validación | BLOQUEADO: pesos no instalados |
| Canary 180M Q8_0 | Catálogo, traducción explícita a inglés | BLOQUEADO: pesos no instalados |

Parakeet declara ES/EN/FR en la fuente de Handy. Su soporte de idioma no demuestra
que respete una lengua forzada ni que maneje mejor cifras. Las observaciones del
usuario sobre números son una hipótesis de comparación; no un benchmark local.
No hay ganador de calidad en esta fase.

Smoke real disponible, no aceptación: 3 clips SAPI Zira en inglés, referencia
con puntuación y números en palabras, normalización NFC/casefold/espacios.
WER 0.39394, CER 0.41398 para base. No extrapolar a personas, acento dominicano,
Spanglish ni cifras digitadas. Parakeet reportó NOT_SUPPORTED, no PASS simulado.
Recibo privado: build/phase8/asr-synthetic-smoke.json.

Comparación reproducible de los mismos archivos:
python scripts/benchmark_dictation.py --corpus corpus.json --models default parakeet-tdt-0.6b-v3 whisper-small --output build/phase8/asr.json
El script no descarga ni conserva referencias/hipótesis en su informe. Requiere
50+ frases reales autorizadas para marcar acceptance_corpus=true (eso por sí
solo no certifica los resultados). Incluir ES dominicano, EN, Spanglish, nombres,
terminología médica, código, números/medidas y puntuación; revisar errores de
cifras por separado de WER. Se mantienen separados transcribir y traducir.

Canary exige idioma de origen explícito: auto se rechaza antes de cargarlo, porque su catálogo no anuncia detección. Preparar el modelo no exige aún audio/idioma. No se fuerza un idioma en Parakeet por el mero hecho de dar un hint.
