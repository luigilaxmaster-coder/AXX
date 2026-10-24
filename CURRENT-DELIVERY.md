# Entrega Windows: Axx 0.21.4

- Fecha: 24 de octubre de 2026.
- Instalación: `%LOCALAPPDATA%\Programs\Axx\Axx.exe`.
- Compilación final: 04:58:26–05:07:01, hora de Santo Domingo.
- Instalador: `Axx_0.21.4_x64-setup.exe`, **213.101.568 bytes**.
- SHA-256 del instalador: `4d534e98fdc4524a50e5c0d71e2660bc298d0a78b673252a00aafb858d73e6d0`.
- SHA-256 del backend: `72fcce11f74e4a7ed21ac21e92e074db5870556a58dd1b4ba3e7339eb0bff2a0`.
- SHA-256 del EXE instalado: `da137928f8cc58bca0aa29bafc093afb0fe97753a125173840bc93e7a15cdde9`.
- La diferencia respecto al EXE de compilación corresponde exactamente a los tres bytes del marcador NSIS de Tauri.
- Recibos privados: `build/chat-0.21.4/build-result.json`, `installed-files.json`, `installed-runtime.json` y los recibos de aceptación del mismo directorio. No se publican datos del usuario ni muestras de voz.

## Chat, contexto y personalización

- SQLite conserva conversaciones, borradores e identidades de integración separados. Los grupos comparten solamente contexto añadido explícitamente. Los hilos vinculados contienen extractos revisables, sin borradores ni notas privadas de otros grupos.
- La retención máxima es de 90 días; archivar no amplía ese límite. Las exportaciones y los datos ya enviados a proveedores externos quedan fuera de esta limpieza local.
- Perfil persistente de identidad, trabajo, instrucciones y comandos preferidos. Temas claro/oscuro, colores de fondo/texto/iconos y tipografía; tamaños independientes por herramienta y una sola vista activa por panel.
- Preguntar y Auto seguro respetan la política del backend. El comando pendiente conserva el chat de origen, la aprobación y el resultado; cambiar de chat no repite sus efectos.
- Reinicio real: borrador recuperado, preparación anterior caducada y nueva aprobación explícita. Cancelación persistida.
- Foco: eliminado el autofocus duplicado de 50/70 ms. La apertura inicial respeta la interacción posterior. Ocho casos nativos escriben inmediatamente en búsqueda, tanto al volver al chat como al cambiar de apartado, sin redirigir letras al borrador.
- Historial largo: la lista conserva la altura de sus filas y desplaza la barra lateral; no invade los controles de grupos. Comprobación nativa con 18 conversaciones guardadas en ambos temas.

## Voz en vivo y dictado

**Chat → Voz en vivo**, junto al cuadro de mensaje. Un clic inicia y otro termina. La configuración permite elegir micrófono, voz y pausa entre turnos. El medidor muestra el nivel recibido y el dispositivo activo. «Preparando micrófono» permanece visible hasta terminar la calibración; después aparece «Te escucho». El micrófono del compositor dicta un borrador sin enviarlo.

La detección usa un umbral adaptado al ruido, con calibración por mediana y un mínimo de seis frames. La voz baja, el ruido continuo, una pausa del hilo de interfaz y la cancelación concurrente tienen regresiones específicas. Cambiar el foco a otra aplicación conserva la conversación visible; ocultar/cerrar el panel o cambiar de chat la detiene. Un dispositivo seleccionado que desaparece muestra el error sin cambiar silenciosamente a otro.

Corregido el fallo `options is not defined` al enviar una pregunta al modelo. El origen de voz atraviesa los adaptadores del chat. El selector de modelo de voz muestra el catálogo detectado de la misma conexión, conserva la elección al reiniciar y no cambia el modelo principal; modelos o conexiones no verificados se rechazan antes del envío. Catálogo detectado e inferencia comprobada siguen siendo estados distintos.

La aceptación instalada comprueba transcripción completa de un WAV, Whisper local, captura real de un track de micrófono, contexto de un hilo vinculado, respuesta del proveedor seleccionado, reproducción una sola vez, interrupción y liberación del micrófono. La frase de entrada es sintetizada; no acredita reconocimiento de una persona hablando en ese ambiente.

Las cuatro voces locales Valeria, Elena, Mateo y Dante completaron reproducción por frases con eventos de inicio/final y cero vaciados del búfer PCM. Las muestras personales y los modelos MOSS se conservan en el equipo y no se distribuyen en el instalador.

La conversación funciona por turnos: pausa la escucha mientras responde. Las medidas de la ejecución final quedan en `installed-live.json` y las [notas de versión](docs/releases/0.21.4.md). La identidad del modelo es la configurada en el proveedor; la ruta de ese perfil no certifica independientemente qué modelo upstream respondió.

## Taller de capacidades y ECC

- **Comandos → Taller de Axx**, también accesible mediante `/capacidad`: objetivo → propuesta versionada → revisión → prueba aprobada → activación con evidencia del ejecutor.
- Generación real con el proveedor configurado, ejecución de telemetría, activación, acceso al formulario de parámetros existente y revocación comprobados desde la app instalada.
- Editar o restaurar genera otra revisión. La aprobación está ligada a revisión y digest. La activación requiere recibos persistidos de `CommandService` y `ActionExecutor`; un resultado incierto no sirve como prueba de éxito.
- Propuestas de código exportables como texto. Axx no importa ni ejecuta ese código, no se concede permisos y no modifica autónomamente su propio ejecutable.
- ECC **2.2.3** instalado en Codex; verificación de rutas del plugin completada. Sus guías se aplicaron con agentes de voz, capacidades y revisión independiente. Las nuevas skills se descubren en una nueva sesión de Codex; ECC no se incorpora al runtime de Axx.

## Magic Pen

- Barra sobre el escritorio con **En directo**, pausa y cancelación accesibles. La tinta se repinta por frame; una selección terminada o una pausa de 650 ms inicia el análisis.
- Captura y consulta separadas. Una selección nueva cancela la anterior; las respuestas conservan captura, revisión y proveedor. El modo manual usa la conexión elegida y no cambia de ruta silenciosamente.
- Historial con previsualización propia, fecha de captura y modelo visibles. Los controles recortados del historial no interceptan el escritorio fuera del widget.
- Detener durante una recaptura conserva selección/tinta. Deshacer o borrar todas las marcas elimina la región derivada; una apertura vieja no sustituye una sesión nueva. Las capturas se serializan también al cerrar y reabrir.
- Movimiento, tamaño y DPI invalidan las coordenadas. Un lease nativo serializa la afinidad de captura y grabación; el cierre del halo sigue disponible. Un cambio de halo fallido se recupera mediante la consulta siguiente.
- Corregido el bloqueo de todas las herramientas al abrir en una segunda pantalla con otra escala: Python enumeraba coordenadas virtualizadas y Tauri físicas. La captura y grabación usan ahora el mismo contexto DPI por hilo, con restauración garantizada. La comprobación instalada anterior observó dos pantallas de 1920 × 1080 y grabó sobre la segunda. En la última ronda Windows anuncia solo una pantalla; la repetición multimonitor queda pendiente de que vuelva a estar disponible.
- La ruta configurada `axxx3` / `gemma4:31b` superó una prueba visual real con imagen de números y formas; se habilitó su capacidad `vision` conservando credenciales, cuota y modelo. Esto no certifica identidad independiente del upstream.
- Ocho bloques de pruebas de puntero con captura/inferencia simuladas: PASS, cero errores JavaScript y un repintado para una ráfaga de 100 movimientos. La aceptación instalada se registra aparte en `magic-pen/installed-magic-pen.json`.
- Aceptación final instalada: **10 comprobaciones PASS**. Captura física y selección reconocieron el número y color de un estímulo conocido mediante el proveedor configurado en 4,768 s; cancelación persistida en 238 ms. Punto, lazo, pantalla completa, tinta, marcador, borrador, deshacer/rehacer, historial, temas y reapertura respondieron. La grabación de área produjo 7 frames decodificables y un archivo verificado; estas medidas corresponden a esta ejecución con un monitor disponible.

## Control de Windows y tentáculos

- **P1:** propietario único de entrada y cancelación observables. Un evento Windows sin etiqueta de Axx revoca la concesión y libera la entrada; es una prueba sintetizada, no concurrencia física de una persona.
- **Explorador:** carpeta y foreground comprobados; ventana minimizada restaurada; identidad de ventana cerrada rechazada.
- **P2:** escritura aprobada sobre un documento de prueba de Notepad, comprobación SHA-256/longitud, pérdida de foco bloqueada y operation_id repetido sin duplicar el efecto.
- **P3:** procedimiento parametrizado guardado y reutilizado sobre otro documento/control observado, con aprobación y cero llamadas de modelo en la repetición.
- **UIA lento:** proveedor WPF real demora SetValue 12 segundos; timeout conserva `unknown`, bloquea duplicación y reconcilia por lectura el efecto tardío. El proveedor recibe una sola escritura.
- Tentáculos: conexión a la silueta real, material del avatar, normales continuas, cobertura subpíxel y raster con presupuesto limitado. Capturas nativas de tres formas en ambos temas, arrastre de panel cerca/lejos, detalle y retracción. La prueba calcula distancias desde la posición observada del avatar.
- Sesenta combinaciones de longitud, ángulo y escala de píxel comprueban cobertura sin columnas vacías interiores, bordes sin recortar y límite de memoria. No es un benchmark general de todas las GPU/CPU.

## Regresión y reproducción

- Backend: **386 PASS** en 220,401 s en la regresión posterior a la corrección DPI. La cobertura incluye cancelación interna del adaptador, restauración DPI, revisión, recuperación, comandos, persistencia y reglas del router. La pasada específica de Magic Pen/HTTP/adaptador/router contiene **101 PASS** y se solapa con la general; no se suman como casos únicos.
- Rust: **31 PASS**, un helper interno ignorado. Se corrigió una interferencia entre pruebas que compartían flags globales del modelo de residente; cada caso aísla ese estado y el caso de concurrencia conserva sus hilos internos.
- Frontend controlado: **26/26 PASS**, sin excepciones no capturadas; incluye envío real de texto/voz mediante IPC controlado, selección de modelos y persistencia del modelo y la pausa, y ausencia del botón flotante sobre los apartados. Contratos de comandos: **23 PASS**.
- Dictado/voz, audio completo, chat SQLite/HTTP y ciclo del taller: PASS. Los dobles de modelo de las pruebas controladas se distinguen de la generación real instalada.
- Auditoría instalada: **62 vistas** en claro/oscuro; foco, navegación, tamaños independientes y controles 3D. La revisión visual no certifica salida física de lector de pantalla.

```powershell
node scripts/test-installed-restart.cjs prepare
# Reiniciar mediante scripts/install-verified-windows.ps1 con CDP temporal.
node scripts/test-installed-restart.cjs verify
node scripts/test-installed-chat-focus.cjs
node scripts/test-installed-chat-layout.cjs
node scripts/test-installed-chat.cjs
node scripts/test-installed-capabilities.cjs
node scripts/test-installed-live.cjs
node scripts/test-installed-appearance.cjs
node scripts/test-installed-surfaces.cjs
node scripts/test-installed-tendril-quality.cjs
node scripts/test-installed-tentacles.cjs
node scripts/test-installed-application-control.cjs build/chat-0.21.4/application-control
node scripts/test-installed-uia-timeout.cjs build/chat-0.21.4/application-control
node scripts/test-installed-speech.cjs
node scripts/test-installed-magic-pen.cjs
```

Los scripts usan el EXE instalado, IPC autenticado y CDP temporal en loopback 9224; deben ejecutarse secuencialmente. La entrega termina con arranque normal y sin ese puerto de depuración.

## Límites y publicación

Quedan fuera de la aceptación automatizada: calidad acústica subjetiva, frase hablada físicamente, lector de pantalla audible, concurrencia de mouse/teclado físicos y cobertura universal de aplicaciones. Wake word y dispositivos externos no se habilitan en esta entrega. Android mantiene su versión; no se declara una nueva validación física Android.

El instalador se publica únicamente cuando `scripts/release.py publish` comprueba fuente, instalación y digest del asset en GitHub. El estado confirmado de la descarga se mantiene en `release.json` y README.

Guías: [chat y voz](docs/CHAT-WORKSPACE.md), [Magic Pen](docs/MAGIC-PEN-DESKTOP.md), [capacidades](docs/SELF-IMPROVEMENT.md), [extensiones](docs/COMMAND-EXTENSIONS.md), [ECC](docs/ECC-WORKFLOW.md), [tentáculos](docs/TENTACLE-RENDERING.md).
