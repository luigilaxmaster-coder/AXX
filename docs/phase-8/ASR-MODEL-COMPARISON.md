# Motores: comparación y límites

Selección por solicitud/tarea, sin imponer Parakeet. El dictado global y archivos
usan model opcional; chat/comandos/conversación conservan el motor anterior.
El endpoint compartido permite que esas superficies elijan un ID en el futuro
sin cambiar su proveedor ni sus permisos. Modelos disponibles no se descargan.

| Modelo | Integración | Ejecución real de pesos en esta fase |
| --- | --- | --- |
| faster-whisper base existente | Supervisor actual CPU int8 y respaldo por defecto | Sí, 3 clips SAPI ingleses sintéticos |
| faster-whisper tiny/small/medium | Selección local por ID | No, pesos seleccionables no presentes en raíz local |
| Parakeet V3 Q8_0 | Sidecar CPU y SHA256 comprobados | Sí, mismos 3 clips; backend empaquetado también |
| Whisper Small GGUF | Mismo sidecar y validación | Sí, mismos 3 clips; backend empaquetado también |
| Whisper Medium GGUF | Catálogo y selección | No, no descargado |
| Canary 180M Q8_0 | Catálogo, traducción explícita a inglés | BLOQUEADO: pesos no instalados |

Parakeet declara ES/EN/FR en la fuente de Handy. Su soporte de idioma no demuestra
que respete una lengua forzada ni que maneje mejor cifras. Las observaciones del
usuario sobre números son una hipótesis de comparación; no un benchmark local.
No hay ganador de calidad en esta fase.

Smoke real disponible, no aceptación: 3 clips SAPI Zira en inglés, referencia
con puntuación y números en palabras, normalización NFC/casefold/espacios.
WER/CER: base 0.39394/0.41398, Parakeet 0.42424/0.44086, Whisper Small
0.45455/0.48387. Referencias con números en palabras: convertirlos a dígitos
también cuenta como error con esta normalización. No usarlo como ranking de
comprensión ni extrapolar a personas, español dominicano o Spanglish.
Recibo: build/phase8/asr-approved-models-comparison.json, acceptance_corpus=false.

Observación concreta del mismo clip: Parakeet produjo «12.5 milligrams every 8
hours»; Whisper Small «12.5 mg every 8 hours». Ambos dieron cifras en ese caso;
Whisper abrevió la unidad. No demuestra que uno siempre numere mejor ni autoriza
reescrituras médicas. Se conserva selección explícita, perfil literal y ningún
postproceso semántico automático. Detalle sintético: numeric-observation.log.

Descargas autorizadas en este chat: 739508576 y 269751136 bytes, respectivamente;
revisiones/tamaños/SHA256 exactos del catálogo, solo perfil privado de candidata.
Sin pesos nuevos en instalador/Git. La primera carga detectó wrapper 0.4.0/sys
0.4.1 incompatibles; ambos están fijados a 0.4.0 y tienen test de ABI enlazada.
Preparar/transcribir/liberar ambos mediante el backend empaquetado pasó sin
llamadas externas ni acciones automáticas: build/phase8/packaged-models.json.

Comparación reproducible de los mismos archivos:
python scripts/benchmark_dictation.py --corpus corpus.json --models default parakeet-tdt-0.6b-v3 whisper-small --output build/phase8/asr.json
El script no descarga ni conserva referencias/hipótesis en su informe. Requiere
50+ frases reales autorizadas para marcar acceptance_corpus=true (eso por sí
solo no certifica los resultados). Incluir ES dominicano, EN, Spanglish, nombres,
terminología médica, código, números/medidas y puntuación; revisar errores de
cifras por separado de WER. Se mantienen separados transcribir y traducir.

Canary exige idioma de origen explícito: auto se rechaza antes de cargarlo, porque su catálogo no anuncia detección. Preparar el modelo no exige aún audio/idioma. No se fuerza un idioma en Parakeet por el mero hecho de dar un hint.
