# Cierre 0.22.48 — NOT_READY

Fecha: 13 de noviembre de 2026. Rama: `codex/axx-optical-glass-magicpen-recovery`.
Base solicitada: `c879d2a75623ee9d5857b5f049fa4f4895ba872c`.
Corrección del bloqueo CI: `5c11330a512a1ebf4f2852e5ca711559fd2a9b8d`.
Código de conexiones/voz: `d8575b4e44d27498975025fde423fa480ece4395`.

La publicación permanece bloqueada por Ollama local sin servidor, disponibilidad intermitente de Gemini, carga MOSS no fiable en este equipo y aceptación nativa final pendiente. No se construyó ni instaló un instalador productivo de este cierre. No hubo integración en main ni publicación. Los binarios debug previos no son entregables productivos.

## Bloqueo de memoria en Windows

El run [43379638538](https://github.com/luigilaxmaster-coder/AXX/actions/runs/43379638538) quedó esperando una promesa del proveedor sintético. El caso de solicitud antigua incrementaba la generación del chat sin enviar el token antiguo; el producto adoptaba correctamente la generación actual e invocaba al proveedor. El fixture guardaba esa solicitud y nunca resolvía su promesa.

Clasificación: **problema de fixture con promesa no resuelta**. No se observó carrera de inicialización, espera imposible del navegador ni error del producto en ese caso. Se reprodujo con Playwright 1.64.1 y Chromium headless shell 1248, versión 156.0.8078.4, como CI.

Se conserva cada aserción. El fixture captura y envía el token antes de invalidarlo; un caso adicional comprueba la solicitud nueva sin token y resuelve su respuesta. Evaluaciones con límite de 10 s, watchdog de suite de 120 s y step CI de 3 minutos producen FAIL explícito. El diagnóstico incluye etapa, browser, errores, estado de generaciones y nombres de IPC, sin datos de usuario.

Evidencia privada: `build/closure/ci-hang-before.log`, `ci-bounded-before.log`, y logs de memoria aislada. El FAIL acotado se reprodujo antes de corregir el fixture; después pasó la suite aislada. El [workflow completo 43439149261](https://github.com/luigilaxmaster-coder/AXX/actions/runs/43439149261) y [compatibilidad 43439149199](https://github.com/luigilaxmaster-coder/AXX/actions/runs/43439149199) pasaron sobre 5c11330. Los checks del nuevo código se consultan en [43447578913](https://github.com/luigilaxmaster-coder/AXX/actions/runs/43447578913) y [43447579022](https://github.com/luigilaxmaster-coder/AXX/actions/runs/43447579022); el estado autoritativo está en Actions.

Reproducción:

```powershell
npm install --no-save --package-lock=false --ignore-scripts playwright@1.64.1
npx --no-install playwright install chromium
node 1.AXX/scripts/test-task-memory.cjs
```

## Conexiones reales

No se modificaron claves, configuraciones ni proveedor seleccionado. Se usaron las autorizaciones existentes y una imagen sintética; no se enviaron imágenes personales. Los recibos privados guardan etapa, plazo, ruta/modelo solicitado y confirmado, respuesta sintética completa, uso, finish_reason y error saneado.

- Claude `axx1`: texto, visión y plan 3D/JSON correctos en dos sesiones nuevas del adaptador. Se conserva la ruta visual ya aceptada. Esto no sustituye un reinicio de la aplicación instalada con el nuevo código.
- Codex: 2 fallos `RPC_TIMEOUT` antes de `thread/ready`, seguidos de un PASS. Un arranque posterior midió `thread/start` en 17,453 s con límite de 20 s, frente a 1,187/0,547 s en caliente. Inferencia: margen insuficiente de arranque local bajo carga, no rechazo del esquema ni fallo de visión demostrado. La creación del hilo de planificación admite ahora hasta 45 s, siempre acotada por el plazo total. No se repite una solicitud incierta. El presupuesto interno respeta los 70/150 s solicitados, en lugar de recortar todos los planes a 70 s. Tres llamadas nuevas pasaron con `gpt-6.1-sol`, proveedor efectivo `openai`, JSON y visión comprobados; arranques 10,750/0,813/0,578 s. No prueba estabilidad universal bajo cualquier carga.
- Gemini `axx55`: texto 6,156 s y visión/JSON 20,390 s dentro de 70 s en el primer intento. El siguiente recibió HTTP 503 por alta demanda antes de validar salida. El timeout previo no se reprodujo como tal: se distinguen el plazo del cliente, transporte, rechazo del proveedor y validación del plan. No se ocultó el 503 con otro proveedor ni con un PASS histórico.
- Claude/Gemini: la selección y la ruta coinciden con el modelo configurado; el adaptador devuelve `identity=unverified_profile` y no un `responder_model` independiente. No se afirma una identidad upstream adicional que el recibo no confirme.
- Ollama local: rechazo 10061 en `127.0.0.1:11434`. No se intentó iniciar ni eludir el bloqueo previo. Inicio manual exacto: `& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" serve`; dejar esa ventana abierta y repetir las pruebas cuando `/api/tags` responda.
- Ollama Cloud: rechazo por facturación/402; no se activaron pagos.
- OpenRouter: endpoint público accesible; sin credencial, **no verificable**. No se declara conexión fallida.
- Los alias FreeLLMAPI usan el mismo gateway local detenido. No se atribuye su indisponibilidad local a los proveedores upstream ni se certifica su autenticación a partir de una clave guardada.

Matriz completa del catálogo existente y la cuenta Codex. «Sí» en Configurada sólo confirma el registro; no implica autenticación ni inferencia. Coste/cuota refleja autorización/evidencia declarada, no saldo confirmado. «JSON» significa salida validada; Gemini no recibió un schema obligatorio del proveedor.

| Ruta / modelo | Configurada | Endpoint accesible | Autenticada | Respuesta real | Visión | JSON | Coste/cuota | Último error / límite |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ollama-local / `qwen2.5:3b` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Local | 10061: servidor detenido |
| openrouter-free / `openrouter/free` | Sí | Sí | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | No verificable: falta credencial |
| gemini-free-tier / `gemini-2.0-flash` | Sí | Sí | No comprobada | No comprobada | No comprobada | No comprobada | No autorizado | Deshabilitada; no se llamó |
| axxx3 / `gemma4:31b` | Sí | Sí | No comprobada | No comprobada | No comprobada | No comprobada | Uso autorizado; importe no verificado | 402: requiere facturación |
| Candidate b2f0d08cd586048de0f5 / `auto:axx_e_w_ae1d53d40a1a` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Axx anonymous kilo 152 / `auto:axx_e_l_f58ba6d634fb` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Axx anonymous aihorde 529 / `auto:axx_e_l_ae1d53d40a1a` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Candidate a448a825d67db197f53b / `auto:axx_e_t_ae1d53d40a1a` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Axx anonymous aihorde 530 / `auto:axx_e_l_d7a16eb4074c` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| axx1 / `claude-sonnet-5-5` | Sí | Sí | Sí | Sí | Sí | Sí | Uso autorizado; importe no verificado | — |
| axx44 / `claude-sonnet-5-5` | Sí | Sí | No comprobada | No comprobada | No comprobada | No comprobada | Uso autorizado; importe no verificado | — |
| axx55 / `gemini-3.6-flash` | Sí | Sí | Sí | Sí | Sí previa; último 503 | Sí previa; último 503 | Uso autorizado; importe no verificado | 503: alta demanda |
| Candidate 9cd5b5e360983b116bf0 / `auto:axx_e_c_ae1d53d40a1a` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Candidate af01cc7b24de53744c82 / `auto:axx_e_l_f58ba6d634fb` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Candidate ec52cb038b453d464dd3 / `auto:axx_e_p_7e343544d957` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Candidate dbf41ba44b46f228a30e / `auto:axx_e_p_f58ba6d634fb` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Candidate 883dfea7c9cba8c65c5a / `auto:axx_e_r_7e343544d957` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Candidate 25cd491a634f1bff0121 / `auto:axx_e_r_ae1d53d40a1a` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Candidate 96de2ed3364bc9374b9b / `auto:axx_e_d_f58ba6d634fb` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Candidate ebb91efe4b227437e0dc / `auto:axx_e_d_ae1d53d40a1a` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Candidate c4889c0e7561e388a603 / `auto:axx_e_w_7e343544d957` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Candidate 525838cba2608b50dc0d / `auto:axx_e_w_f58ba6d634fb` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Candidate 8488b8930ca2be12244c / `auto:axx_e_t_f58ba6d634fb` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Candidate 9d5387136460d87b10cb / `auto:axx_e_t_7e343544d957` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Axx anonymous kilo 153 / `auto:axx_e_l_f58ba6d634fb` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Axx anonymous kilo 178 / `auto:axx_e_l_7e343544d957` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| Axx anonymous ovh 154 / `auto:axx_e_l_1587e0ef3883` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| FreeLLMAPI - Qwen2.5-VL-72B / `qwen2.5-vl-72b` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Declarada gratis | Gateway local detenido; upstream no probado |
| FreeLLMAPI / `axx-anonymous-kilo-coherenorth-mini-codefree` | Sí | No en la prueba | No comprobada | No comprobada | No comprobada | No comprobada | Uso autorizado; importe no verificado | Gateway local detenido; upstream no probado |
| @codex / `gpt-6.1-sol` | Sí | Sí | Sí | Sí | Sí | Sí | Suscripción existente | — |

Recibos privados: `build/closure/providers-live.json`, `providers-restart.json`, `codex-after.json` y `connection-matrix.json`. Contienen evidencias sintéticas y quedan excluidos de Git. Diagnóstico reproducible:

```powershell
python scripts/verify-recovery-providers.py --config "$env:LOCALAPPDATA\Axx\providers.json" --output build/closure/recheck.json --name axx1 --name axx55 --name ollama-local --name axxx3 --name openrouter-free --vision --codex
```

Estas llamadas consumen la cuota o uso ya autorizado de las rutas. No cambian el catálogo ni autorizan facturación nueva. `--codex` realiza tres intentos visuales explícitos, sin reintentar operaciones inciertas por debajo.

## Voz de Axxmorcito

La ampliación posterior del usuario autoriza corregir la salida TTS; micrófono y dictado siguen EN STANDBY.

1. Se comprobó que cada paquete PCM sufría fades y solape de 6 ms, recortando una onda continua. El reproductor conserva ahora la duración exacta de las muestras y la amplitud en los límites. Prueba OfflineAudioContext roja antes y verde después; se conservan pausa, reanudación, cancelación y buffering adaptativo.
2. Se recupera el descubrimiento de los modelos privados `axx-*.onnx` existentes y sus estilos, perdido frente al código anterior. No se copian pesos ni muestras al repositorio. Se excluyen backups y nombres con rutas; se conserva la identidad/idioma del JSON y se normaliza texto hablado con el helper existente.
3. Piper usa dos hilos sin spinning para dejar CPU al renderer. La primera carga observada superaba 30 s; mantiene un límite explícito de 90 s. Se respetan los parámetros calibrados del modelo y los overrides acotados de estilos. No se cambia automáticamente la voz elegida.

Medidas privadas: carga aislada con dos hilos 21,843 s; síntesis 3,563 s para 5,689 s de audio. Una llamada completa al servicio produjo 5,596 s de WAV, tardando 33,594 s incluida la carga. La carga fría no es síntesis más rápida que tiempo real. La muestra está en `build/closure/voice/piper-axx-morcito-es.wav`; es evidencia privada, no recurso de instalación.

MOSS falló dos veces al cargar en 90 s con carga alta del equipo (CPU 99,5 %, RAM disponible 1,5 GB). Otro worker terminó, pero el primer probe usó una ruta de salida relativa y no encontró su WAV desde el proceso padre: ese error concreto era del probe, no evidencia de fallo de síntesis del producto. El WAV recuperado contiene 7,68 s de audio y pausas largas; no se certifica naturalidad humana ni aceptación acústica. No se aplicaron humanizadores DSP sin comprobar, cambios de ASR ni reentrenamiento.

## Regresiones y estado de entrega

- Proveedores UI: PASS, incluido estado antiguo tras cambiar modelo. Se completa el fixture de memoria de su prueba; no se debilitan las guardas del producto.
- Reproducción PCM: PASS, con muestras continuas, buffering lento, inicio temprano, ES/EN, pausa y cancelación. Se limpió la evidencia sintética anterior antes de medir el caso siguiente.
- Codex: 77 pruebas, PASS; una prueba live optativa ignorada por su gate habitual.
- Backend focalizado: 149 ejecutadas; 148 PASS y una prueba sintética de concurrencia ASR falló bajo carga. Esa misma prueba aislada pasó en 0,879 s. No se modificó ASR para hacerla pasar.
- Rust: 27 PASS, dos ignoradas por sus gates existentes.
- Geometría de tentáculos y silueta: PASS. Sintaxis del renderer: 39 scripts válidos. Se ejecutan además las pruebas nuevas de diagnóstico y voces privadas.
- Gate PC/Android: contrato, reconstrucción del renderer y 113 pruebas backend pasaron (una ignorada); la fase browser local no había terminado al registrar este informe. No se presenta el recibo incompleto como PASS. La aceptación física Android es independiente.
- Magic Pen UI local: ejecutada; sin resultado final al registrar el informe. Un probe instrumentado mostró progreso por controles, captura y resumen, y alcanzó su watchdog diagnóstico de 90 s sin completar la suite. Esto no demuestra una regresión del producto. El contrato nativo anterior de Optical Glass/Magic Pen permanece documentado en `OPTICAL-GLASS-MAGICPEN-ACCEPTANCE.md`; no se repitió ni se sustituyó por estos fixtures.

Sin diferencias respecto a c879d2a en el renderer HTML, motor Magic Pen, worker MOSS, ASR, native-voice, ni baseline de diseño. Optical Glass, materiales, geometrías y apariencia aprobados conservan sus bytes. La corrección Phase 7 sólo liga estados IA a la firma de ruta vigente.

El ejecutable instalado conserva SHA-256 `fd1a784a7a4bbfcc952d339bd6c9fa59ae642aa3b1edd78aedab3c23c05a6761` en `%LOCALAPPDATA%\Programs\Axx\Axx.exe`, igual al inicio. No se instalaron estos cambios. La entrega 0.22.48 sigue siendo **rama de diagnóstico**, no release. No hay nuevo instalador productivo, hash/sidecars productivos, backup/restore nuevo, aceptación nativa final, merge ni publicación que declarar. Esos pasos siguen bloqueados y deben ejecutarse sobre el código final sólo cuando los gates requeridos pasen, conforme a `docs/RELEASING.md`.
