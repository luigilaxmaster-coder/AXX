# Tarea para Claude: comandos fiables, Computer Use con visión y conexiones elegidas por el usuario

## Encargo

Trabaja en este repositorio para que Axx entienda y ejecute de forma fiable comandos escritos y hablados, pueda usar Computer Use con visión a través de un modelo seleccionado que realmente admita las capacidades requeridas, y permita al propietario elegir qué aplicaciones, servidores MCP y herramientas conecta, activa, desactiva o desconecta.

El objetivo principal es que el usuario pueda pedir en español acciones sobre aplicaciones autorizadas —por ejemplo abrir una aplicación, buscar en YouTube, controlar Spotify o completar una tarea visible en una ventana— y que Axx use la ruta disponible más fiable, compruebe el resultado y explique claramente cualquier limitación. El usuario decide las conexiones. No conectes, habilites ni autorices todas las aplicaciones automáticamente.

No te limites a “adaptarte” con más instrucciones de prompt o una lista grande de sinónimos. Audita el recorrido real, identifica dónde se pierde la intención o la capacidad y corrige la causa compartida. Implementa la solución completa y verificable en el código, interfaz, configuración y pruebas que correspondan. Una especificación o un mock no cuenta como implementación.

## Hechos de arquitectura que debes respetar y verificar

El repositorio ya contiene estos sistemas; estúdialos antes de crear otro:

1. **Comandos e intención:** `backend/actions/command_language.py` normaliza una gramática acotada; `backend/commands.py` expone `CommandService`, catálogo, resolución y preparación; `backend/actions/desktop.py` resuelve varias acciones de Windows, navegador y música; `1.AXX/scripts/command-library.js` enruta la entrada de la interfaz. Las frases pueden entrar por chat, barra rápida y voz. Mantén una única autoridad semántica en el backend y evita que una segunda gramática del frontend decida una acción distinta.
2. **Ejecución y comprobación:** `backend/actions/executor.py`, `backend/actions/tools.py` y `backend/commands.py` conectan los comandos con herramientas tipadas, aprobaciones, cancelación y recibos. `docs/UNIFIED-EXECUTION.md` describe estados `succeeded`, `failed` y `unknown`, postcondiciones y no repetición automática. No declares éxito por haber entregado un clic, una tecla o una llamada a una herramienta.
3. **Voz:** `backend/speech/offline_asr.py`, `backend/speech/speech_text.py`, `1.AXX/scripts/native-speech-stream.js`, `1.AXX/scripts/native-voice.js` y `1.AXX/scripts/voice-conversation.js` implementan partes diferentes de captura, transcripción, comandos y respuesta hablada. Conserva sus límites de tamaño, cancelación, privacidad y estados; inspecciona el flujo real para encontrar cualquier ruta duplicada.
4. **Computer Use:** `backend/computer_use.py`, `backend/computer_vision.py`, `backend/actions/computer_tools.py`, `backend/actions/desktop_input.py`, `backend/connect/registry.py`, `backend/connect/provider.py` y `1.AXX/scripts/computer-use.js` gestionan sesión, captura, herramientas, entrada, identidad de ventana y permisos. `docs/COMPUTER-USE.md` es el contrato que debes contrastar con el código.
5. **Visión de imagen:** `backend/magic_pen.py` y `1.AXX/scripts/magic-pen.js` tienen una ruta de análisis visual independiente. `1.AXX/scripts/model-profile.js` advierte que las capacidades declaradas no equivalen a una prueba real y que la conexión normal de chat puede ser solo de texto. Magic Pen no demuestra por sí solo que el agente general de Computer Use reciba capturas.
6. **Modelos:** `backend/inference/` contiene adaptadores, router, selección de modelos y configuración. `backend/connect/` implementa la ruta de Connect/Codex y sus herramientas dinámicas. No supongas que todo modelo compatible con chat acepta imágenes, llamadas a herramientas, respuestas estructuradas o captura de Axx.
7. **MCP:** `backend/mcp_host/` y `1.AXX/scripts/` del panel de conexiones ofrecen servidores MCP HTTP/stdio y catálogo de herramientas. `docs/MCP-LOCAL.md` indica que el usuario puede comprobar el catálogo y activar herramientas individualmente; las nuevas herramientas comienzan desactivadas y los secretos usan DPAPI. Integra este control existente antes de proponer una interfaz paralela.
8. **Aplicaciones:** `backend/application_catalog.py`, `backend/actions/application_tools.py`, `backend/actions/windows_apps.py` y `backend/actions/desktop.py` ya cubren inventario, perfiles y algunas acciones de aplicación. La existencia de un perfil, skill o ejecutable no implica un adaptador completo ni una operación verificada.

Consulta también `docs/COMANDOS-DESDE-CHAT.md`, `docs/VOICE-COMMAND-LANGUAGE.md`, `docs/PROVEEDORES-API-LOCAL.md`, `docs/PROMPT-CONTRACTS.md`, `docs/COMMAND-EXTENSIONS.md`, `docs/COMPUTER-USE-EXPANSION.md`, `docs/mobile/COMPATIBILITY-PROTOCOL.md` y los `AGENTS.md` aplicables. Trata documentación de estado como evidencia histórica: confirma el estado actual en el código, pruebas, configuración y runtime antes de afirmar que una capacidad está operativa.

## Condición inicial obligatoria

Antes de editar:

1. Revisa `git status`, ramas, resumen del diff y lista de archivos modificados. Este checkout puede incluir trabajo local previo en voz y resolución de comandos. **No restaures, sobrescribas, reordenes ni descartes cambios que no hayas creado.** Abre diffs detallados pertinentes por separado; no cargues binarios, adjuntos ni evidencia no relacionada al contexto.
2. Traza con referencias de archivo y función al menos un ejemplo real por cada entrada: texto en chat, barra rápida, voz transcrita, plan de varios pasos y llamada MCP. Sigue cada caso desde el evento frontend hasta `resolve`/`prepare`, ejecutor, adaptador, verificador y resultado mostrado.
3. Compara una petición equivalente escrita y hablada y registra dónde difieren origen, normalización, resolución, parámetros, permisos y respuesta. Clasifica fallos actuales con evidencia; no inventes defectos ni des por válida una prueba de fixture como aceptación física.
4. Comprueba el estado real de proveedores, capacidades de imagen/herramientas, servidor MCP, modelos locales y recursos de hardware disponibles. El nombre “Gemma 4 31B” es un modelo candidato solicitado por el usuario, no una garantía de compatibilidad ni de rendimiento. Verifica el ID exacto y el runtime; no descargues pesos ni cambies credenciales sin instrucción explícita.

## Resultado funcional requerido

### A. Un recorrido coherente para texto y voz

- Texto escrito y transcripción final de voz deben llegar al mismo resolvedor y al mismo catálogo tipado. La voz puede aportar una corrección fonética cuando la procedencia sea `voice`, pero debe conservar el texto original y no cambiar una búsqueda, cita, negación, pregunta o contenido literal por una orden.
- No ejecutar resultados parciales de ASR. Ante baja confianza, aplicación inexistente, dos destinos similares, verbo ambiguo o parámetros esenciales faltantes, preguntar o proponer opciones; no elegir a ciegas.
- Separar de forma determinista: abrir aplicación, navegar, buscar, leer, reproducir, pausar, escribir/dictar, seleccionar controles y ejecutar un comando explícito. “Busca una canción en Spotify” no significa reproducirla; abrir YouTube no significa haber encontrado o reproducido un vídeo.
- Las secuencias conservan orden, referencia a observaciones frescas, parámetros tipados, límite de pasos actual y revisión existente. Una corrección del usuario debe actualizar o cancelar un plan pendiente de manera visible y sin repetir efectos previos.
- Si la petición no tiene una implementación, indicar qué falta y presentar una alternativa o propuesta de capacidad. No afirmar que “aprendió”, “se adaptó” o ejecutó algo cuando solo generó un plan.

### B. Computer Use con un modelo de visión que el usuario elija

- Desacoplar el acceso a Computer Use de un único proveedor cuando el proveedor y modelo seleccionados soporten de verdad la entrada de imágenes y las llamadas de herramientas que Axx necesita. Reutilizar el contrato y las herramientas actuales de Computer Use; no crear un segundo inyector de mouse/teclado, un segundo ejecutor ni un agente paralelo con permisos más amplios.
- Mostrar compatibilidad por conexión y modelo usando metadatos comprobables y una prueba de capacidad. Distinguir **declarado**, **probado por solicitud de imagen**, **probado con herramientas**, **no admitido** y **fallido**. No inferir visión por el nombre del modelo. No seleccionar otro proveedor silenciosamente si el modelo falla.
- Permitir seleccionar explícitamente un modelo local como Gemma 4 31B u otro más pequeño **solo si** el ID instalado, runtime, tamaño disponible, recepción de imagen y formato de tool calling pasan pruebas reales. Si el modelo local solo puede describir imágenes o no puede llamar herramientas con el contrato actual, no lo presentes como Computer Use completo; permite usarlo para percepción/propuesta con ejecución revisada por la ruta compatible.
- Pasar la captura autorizada al modelo por un canal efímero asociado al chat y a la ejecución correctos. No guardar imágenes del escritorio en historial de operaciones, logs, métricas ni artefactos de publicación. Mostrar qué se comparte y con qué conexión; separar modelo local de proveedor remoto.
- Conservar los permisos explícitos existentes para captura e interacción, alcance de escritorio o ventana, vigencia, identidad HWND/PID/instancia, observación renovada antes de cada acción, coordenadas con `image_bounds`/DPI/topología, cancelación y revocación. Cambio de chat o proveedor debe seguir invalidando la concesión según el contrato existente.
- Tras una acción, observar y verificar la condición concreta. Si el resultado es parcial o incierto, mostrar `unknown` y detener secuencias dependientes; jamás repetir clics o escrituras automáticamente. No eludir UAC, UIPI, pantalla bloqueada, permisos del sistema ni restricciones de una aplicación.

### C. Selector explícito de conexiones por aplicación y herramienta

- Reutilizar **Ajustes → Conexiones MCP** para descubrir/registrar servidores, revisar esquemas y habilitar o deshabilitar cada herramienta; mantener apagadas las nuevas herramientas por defecto.
- Añadir o completar una selección clara por aplicación/servicio y capacidad para que el usuario conecte, desconecte o desactive, por ejemplo, Spotify, navegador/Browser Use, YouTube y otras aplicaciones que elija. Mostrar método (MCP oficial/verificado, API, navegador aislado, UIA o Computer Use), cuenta/perfil, herramientas habilitadas, permisos concedidos, requisitos y estado probado. No uses el rótulo “conectado” para una configuración que no pasó una operación de prueba.
- Mantener por separado la conexión MCP, la activación de una herramienta, el permiso de captura/Computer Use y la aprobación de una mutación. Desconectar una integración debe revocar o invalidar su autorización activa sin borrar otras credenciales, pairing, historial o permisos no relacionados.
- Priorizar, en orden: adaptador MCP oficial de la aplicación si está verificado; API oficial apropiada; adaptador existente; navegación en perfil aislado; Computer Use visual con alcance autorizado. Crear un MCP propio solo si no hay una ruta adecuada y verificable. No crear un conector de muestra que no opere contra la aplicación real.
- Conservar los servidores HTTP/stdio existentes, aislamiento de credenciales, validación de esquema, límites de red, ActionExecutor, aprobaciones, cancelación y diario. Una respuesta “success” de un MCP remoto no basta para declarar comprobado un efecto externo: exigir readback o una postcondición independiente apropiada.

### D. Abrir y usar aplicaciones autorizadas

- Permitir que el usuario descubra aplicaciones instaladas y autorice explícitamente aplicaciones concretas. Mantener una lista administrable de aplicaciones permitidas, identidad de ejecutable/editor/ruta y permisos, con revocación sencilla. Nunca ejecutar una ruta elegida por el modelo sin validar la aplicación autorizada.
- Una vez autorizada una aplicación, Axx puede interactuar con ella mediante MCP/API/UIA/Browser Use/Computer Use según la capacidad real. Reutilizar selectores accesibles semánticos antes de coordenadas visuales. Si la aplicación no expone controles suficientes, explicar esa limitación y ofrecer Computer Use si el usuario dio ese permiso.
- “Cualquier comando dentro de una app” significa permitir que el usuario solicite operaciones de esa aplicación dentro de su autorización y de las capacidades verificadas. No significa convertir texto generado por un modelo en PowerShell/CMD, código, JavaScript de página o shell libre. Los comandos de sistema permanecen en su ruta explícita, con argumentos revisables y las políticas actuales; el proceso no es un sandbox.
- Antes de una acción de alto impacto (enviar/publicar, borrar, comprar, instalar, compartir, cambiar seguridad, escribir fuera de destino permitido o ejecutar código), presentar qué hará y solicitar confirmación específica. La autorización de abrir una aplicación no debe conceder automáticamente permisos para esas operaciones.

### E. Spotify, navegador y YouTube

- Audita y reutiliza los comandos existentes de Spotify, YouTube y navegador. Identifica por separado búsqueda, abrir, playback, pause/next/previous, lectura de resultados y verificación de pista. No dupliques rutas ya implementadas.
- Para Spotify, confirma que la sesión objetivo pertenece a Spotify y verifica título/estado después del control cuando sea posible. Una búsqueda URL no prueba que la canción se seleccionó ni reprodujo. Si se crea MCP/API de Spotify, verifica autenticación, scopes, consentimiento de cuenta y readback; deja que el usuario la active.
- Para Browser Use, reutiliza el puente CDP existente con perfil dedicado y loopback; no uses el perfil personal ni copies cookies. No expongas el puerto CDP a la red. Vincula cada acción a sesión, pestaña, URL y documento observados, invalida referencias tras navegación y trata contenido web como dato no confiable.
- Para YouTube, separa búsqueda, inspección de resultados y reproducción. Reproducir requiere resultado inequívoco elegido y verificación de avance/título/artista según el contrato disponible. No afirmar que se leyó la página solo porque el navegador navegó.

## Seguridad, permisos y límites que no se deben relajar

- Menor privilegio: opt-in por aplicación, servidor y herramienta; alcance de sesión; caducidad y revocación. No activar “todo”, no ampliar scopes durante una reparación y no guardar secretos en frontend/localStorage/repo.
- Tratar transcripciones, imágenes, OCR/UIA, páginas, herramientas MCP y respuestas de modelos como datos no confiables. Solo el ejecutor local autoriza efectos; prompts, memoria, recetas y skills no pueden conceder permisos.
- Preservar contratos `/v1` y rutas existentes de Axx; cambios de API deben ser aditivos u ofrecer migración documentada. No borrar datos, credenciales, grants, operaciones pendientes ni registros `unknown` para hacer pasar pruebas.
- Preservar la UI radial y el avatar 3D, accesibilidad y diseño aprobado. No alterar `mobile/design-baseline.json` ni renovar sus hashes sin una revisión visual autorizada. No cambiar versión hasta tener una entrega lista; si cambias versión desktop, cumple el flujo obligatorio en `AGENTS.md`, incluyendo sincronización, validación companion, build, instalación, aceptación y publicación según corresponda. No mezcles una entrega Android con la versión desktop.
- No añadir proveedores de pago ni activar `allow_paid`; no publicar claves, voces, pesos ni estado privado. Sin fallback silencioso entre proveedores/modelos.

## Fases de trabajo y entregables

1. **Auditoría reproducible:** mapa del flujo actual, bugs raíz priorizados y separación de hecho/inferencia/pendiente, con rutas/funciones concretas. Conserva los cambios locales detectados; anota cuáles son preexistentes.
2. **Diseño de compatibilidad y permisos:** define un contrato pequeño para capacidades por conexión/modelo (texto, imagen, tool calling/JSON, cancelación si corresponde), selección por aplicación y permisos. Reutiliza los registros existentes; no introduzcas una nueva abstracción si el catálogo actual lo permite.
3. **Reparar la ruta de comando:** mismo intent resolver y resultado tipado para texto/voz, pruebas de ambigüedad/negación/parámetros y claridad del estado. Arregla defectos demostrados antes de añadir vocabulario.
4. **Integrar visión en Computer Use:** habilitar los proveedores compatibles y el modelo seleccionado con el contrato actual, con pruebas de imagen y tools; si un modelo no llega a ese nivel, documentar exactamente su nivel y no degradar silenciosamente.
5. **Conexiones seleccionables:** completar la UI/API de elegir por aplicación y por herramienta, estado de prueba, permisos visibles, desconexión y revocación. Prueba al menos un ciclo real de conectar → inspeccionar → autorizar herramienta → operación de lectura → desactivar/desconectar.
6. **Integraciones de usuario:** completar primero Spotify, navegador y YouTube usando el adaptador más verificable disponible. Añadir conectores nuevos solo cuando la auditoría demuestre que faltan y dejar su activación a elección del usuario.
7. **Verificación y reporte:** ejecutar pruebas offline pertinentes, pruebas de API/UI y, si hay hardware/runtime disponible, aceptación nativa. Reporta por separado `ESPECIFICADO`, `IMPLEMENTADO_LOCAL`, `INTEGRADO_DEV` y `VALIDADO_WINDOWS`. Adjunta comandos ejecutados, resultados y límites. No declares soporte para equipos, modelos, aplicaciones o efectos no probados.

## Matriz mínima de aceptación

Incluye pruebas de regresión y evidencia para todos los casos aplicables:

1. Misma orden escrita y hablada produce el mismo `command_id` y parámetros; errores fonéticos se corrigen solo cuando la entrada es voz.
2. Negaciones, preguntas, citas y texto literal no generan una operación; fragmentos de voz tampoco.
3. Una petición ambigua pregunta; aplicación no instalada no se inventa; aplicación no autorizada no se abre.
4. Una orden compuesta conserva el orden, revisión, cancelación y parada ante fallo/resultado incierto.
5. Modelo local elegido recibe una imagen real autorizada y devuelve observación útil; tool calling se verifica separadamente. Registrar versión/runtime/model ID y tamaño de imagen, sin conservar captura privada.
6. Con un control visual, Axx obtiene observación fresca, actúa sobre el HWND/PID/instancia exactos, verifica postcondición y se detiene al fallar. No repetir entrada al simular timeout tras el despacho.
7. Modelo sin visión, sin tools, desconectado o no soportado se identifica correctamente; no hace fallback sin permiso ni afirma que vio la pantalla.
8. Usuario habilita/deshabilita una sola herramienta MCP y confirma que otras conexiones/herramientas y credenciales se mantienen intactas. Herramienta nueva empieza apagada.
9. Spotify diferencia búsqueda de playback y verifica el estado/título; YouTube diferencia búsqueda, resultado elegido y reproducción; navegador usa perfil aislado y referencias actuales.
10. Envío, borrado, compra/cambio externo y ejecución de código requieren la confirmación específica definida por política.
11. Compatibilidad anterior de comandos, API móvil y rutas MCP permanece; resultados inciertos no se borran ni repiten.

Empieza con las pruebas ya existentes relevantes, incluyendo `backend.tests.test_command_language`, `backend.tests.test_command_sequences`, `backend.tests.test_commands_http`, `backend.tests.test_computer_use`, `backend.tests.test_computer_desktop`, `backend.tests.test_desktop_observation`, `backend.connect.tests.test_provider`, `backend.connect.tests.test_provider_capability`, MCP host tests, speech tests, `node 1.AXX/scripts/test-command-library.cjs` y `node scripts/test-computer-use.cjs`. Revisa `docs/COMPUTER-USE.md` para sus comandos exactos y no ejecutes pruebas físicas destructivas sin aprobación del usuario.

## Qué debe devolver Claude

- Cambios completos en el checkout, respetando todos los cambios locales previos.
- Diagnóstico de las causas raíz con evidencia de código.
- Lista de capacidades soportadas por cada modelo/proveedor/app y su nivel de validación.
- Tabla de pruebas ejecutadas, aprobadas/fallidas/no disponibles.
- Riesgos, limitaciones de modelos locales y pasos de aceptación física que queden pendientes.
- Lista explícita de lo que requiere que el propietario elija o autorice en UI (conexiones, cuentas, permisos de pantalla y entrada). Nunca actives esas conexiones por él.

**No aceptes como resultado** cambios solo de prompt, un nuevo catálogo de frases sin corrección del flujo, un MCP ficticio, tool calling simulado, visión inferida por el nombre del modelo, abrir una aplicación como prueba de que funcionó dentro de ella, ni un reporte que mezcle pruebas unitarias con aceptación nativa.

## Prompt para iniciar Claude Code

La configuración del proyecto queda en `CLAUDE.md`, `.claude/skills/ponytail/SKILL.md` y `.claude/skills/axx-command-computer-use/SKILL.md`. En PowerShell, abre una sesión desde la raíz:

```powershell
Set-Location 'C:\Users\luigi\Desktop\axx2'
claude
```

El Claude Code detectado en este equipo es `2.1.111`. Actualízalo con `claude update` para tener la versión actual; `CLAUDE.md` importa `@AGENTS.md` para cubrir versiones anteriores. En la sesión, comprueba `/context` para que aparezca `CLAUDE.md`; invoca `/ponytail` y `/axx-command-computer-use`. Después pega este mensaje:

```text
Quiero que completes esta tarea en el repositorio, no que me des solo recomendaciones. Comprueba que cargaste CLAUDE.md y los skills /ponytail y /axx-command-computer-use; si un skill no aparece, lee directamente su archivo bajo .claude/skills/. Lee CLAUDE-TAREA-COMANDOS-COMPUTER-USE-VISION.md como especificación de aceptación y sigue AGENTS.md, importado por CLAUDE.md.

Primero inspecciona git status, ramas, resumen del diff y lista de archivos cambiados. Hay cambios locales míos: consérvalos, no los restaures ni los mezcles con cambios ajenos, y distingue lo preexistente. Lee diffs pertinentes uno por uno; no cargues binarios, adjuntos o cambios no relacionados. Después audita el código y tests reales, traza las causas raíz de comandos escritos y hablados, Computer Use/visión, modelos locales y conexiones MCP. Usa evidencia de archivos y funciones; no des por operativa una capacidad porque aparezca en documentación.

Implementa la solución necesaria de punta a punta usando las capas existentes. Quiero elegir yo qué aplicaciones, servidores y herramientas MCP conectar, habilitar, deshabilitar y desconectar. En particular, resuelve Spotify, Browser Use, YouTube, apertura de aplicaciones autorizadas y Computer Use con visión en un modelo local compatible. Gemma 4 31B es candidato, no asumas que funciona: comprueba el modelo/runtime y que Axx envíe imágenes y soporte tool calling. No conectes nada ni descargues modelos por mí.

No conviertas texto del modelo en shell/código libre, no amplíes permisos silenciosamente, no ejecutes efectos ambiguos, no repitas resultados inciertos y no llames éxito a un clic o despacho sin postcondición. Conserva privacidad de capturas, cancelación, permisos explícitos, `/v1`, diseño actual, credenciales y cambios locales. No añadas `Co-authored-by` de IA.

Avanza por las fases del documento: diagnóstico, corrección de comandos, compatibilidad real de visión/tools, selector explícito de conexiones, integraciones prioritarias y validación. Gestiona tokens con `/context`, `/usage` y `/compact` cuando corresponda: lecturas selectivas y evidencia resumida una sola vez. Usa el modelo/esfuerzo normal para exploración e implementación; reserva razonamiento profundo para causas raíz, arquitectura y límites de seguridad. Evita agentes paralelos salvo que una parte independiente reduzca el trabajo total. No ahorres tokens saltándote pruebas o validaciones necesarias.

Ejecuta pruebas pertinentes y reporta exactamente cuáles pasaron. Separa ESPECIFICADO, IMPLEMENTADO_LOCAL, INTEGRADO_DEV y VALIDADO_WINDOWS; si no tienes runtime/hardware, deja esa aceptación como pendiente. No cambies la versión ni publiques salvo que puedas completar las reglas de entrega de AGENTS.md.

Empieza ahora por el inventario y diagnóstico; sigue trabajando hasta implementar y verificar lo que sea posible en este checkout. Antes de finalizar, entrega archivos modificados, causa raíz, pruebas y resultados, límites/modelos no compatibles y pasos que requieren que yo seleccione o autorice una conexión.
```
