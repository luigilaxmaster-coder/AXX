# Axx Desktop · Manual completo de implementación

**Base: Axx 20. Estado: especificación y plan; no ejecutable nativo terminado.**

Consulta README y AGENTS para comenzar. Este documento reúne los 26 capítulos técnicos; contratos, herramientas y tareas detalladas se incluyen por separado.


---

# 00 · Decisión de producto y primer resultado útil

Axx deja de ser una pestaña de demostración y pasa a ser una aplicación de Windows 11 por usuario, residente en bandeja, con presencia transparente y herramientas reales. El HTML es la referencia visual y su TypeScript es código reutilizable; no debe tirarse ni confundirse con el producto nativo completo.

## Primer resultado verificable
El primer incremento debe permitir: instalar o ejecutar Axx Desktop en modo desarrollo; ver la figura sin marco; invocarla desde Bloc de notas; devolverla a la esquina; conservar forma, material, cámara, tamaño y ubicación después de cerrar; abrir un chat mínimo; iniciar un temporizador real; y pasar clics al escritorio fuera de las zonas interactivas. Ese recorrido se completa antes de añadir captura avanzada, activación de voz o múltiples proveedores.

## Restricciones que no se negocian durante la migración
La entidad sigue sin rostro, con materia oscura e iridiscente. Se conservan los 24 identificadores de forma y las nueve paletas, los movimientos y los estilos guardados. Los botones siguen alrededor. No se introduce una barra lateral permanente ni un panel de bienvenida lleno de tarjetas. Las preferencias elegidas no son sugerencias: tienen prioridad sobre los estados automáticos. No se exige GPU dedicada ni se cambia a PNG para solucionar rendimiento.

La acción y su representación continúan separadas. Pausar la grabación no significa cerrar su ventana; cerrar una ventana no cancela una tarea. Una animación no concede permisos, no inicia una compra y no confirma la entrega de un mensaje. El dictado nunca pulsa Enviar por inferencia.

## Alcance de este expediente
Windows 11 x64 es el destino inicial. El Acer Spin 3 con i7 de 11.ª generación, 16 GB e integrada es la referencia indicada en el proyecto, no una medición de esta entrega. Se diseña para esa clase de equipo y se mide allí. El despliegue móvil conserva contratos e identidad, pero no se usa para retrasar la primera versión de Windows.

## Tres productos distintos que hay que identificar
**Prototipo Axx 20:** UI y servicios web; pruebas históricas en entorno controlado.
**Axx Desktop Development:** shell nativo y adaptadores incorporados gradualmente; puede contener funciones desactivadas.
**Axx Desktop Release:** instalador firmado, datos durables, permisos auditados y matriz de pruebas físicas aprobada para las funciones que anuncia.

No se cambia la etiqueta a Release solo porque Tauri consiga abrir el HTML. Tampoco se elimina una función del plan porque no esté disponible en un WebView: se asigna al adaptador adecuado y se muestra su estado.

## Qué debe aportar el propietario
Una carpeta de trabajo y espacio libre; consentimiento para instalar herramientas de desarrollo cuando falten; elección explícita de proveedor de IA si se usa nube; autorización de micrófono/captura; pruebas de destinos de dictado; cuenta/aplicación de Spotify si esa integración se habilita; y certificado de firma cuando se distribuya públicamente. No se solicita ninguna contraseña en un chat ni se incrusta un secreto en un prompt.

## Resultado de cada sesión de desarrollo
Commit o parche identificable, comandos realmente ejecutados, archivos modificados, resultados de pruebas, captura del software cuando cambie la UI y una lista de pendientes. El informe debe distinguir prueba de protocolo, reproducción de medios reales y prueba física en Windows. Ver [18](docs/18-PRUEBAS.md) y [21](docs/21-ENTREGAS.md).


---

# 01 · Requisitos vinculantes y aceptación

Los códigos R01–R36 son el contrato de producto. Se utilizan en planes, pruebas y revisiones. La ruta de implementación puede cambiar; el requisito no desaparece sin decisión escrita del propietario.

| ID | Requisito | Aceptación observable |
|---|---|---|
| R01 | Identidad conservada | Guardar forma/material/cámara, cambiar herramientas, reiniciar: mismo conjunto. |
| R02 | Vista previa reversible | Probar otra forma no persiste; descartar restaura toda la revisión previa. |
| R03 | Calidad visual | Mantener malla, antialias y material de referencia; no disminuirlos silenciosamente. |
| R04 | Galería ampliable | 24 formas existentes con IDs estables; nuevas formas no renumeran las anteriores. |
| R05 | Órbita independiente | Cada acceso alrededor, legible, arrastrable y sin ejecutar al arrastrar. |
| R06 | Presencia mínima | Aparcado: figura sola; primer toque revela Herramientas, no controla la tarea anterior. |
| R07 | Atajo global | Alt+Mayús+A llama desde otra app; segunda A ≤450 ms devuelve; autorepeat no cuenta. |
| R08 | Detener seguimiento | Esc detiene seguimiento sin cancelar música, tiempo o captura. |
| R09 | Escritorio transparente | Fuera de regiones interactivas, los clics llegan a la app inferior. |
| R10 | Multimonitor/DPI | Posiciones correctas con escala 100/125/150/200 %, monitor desconectado y coordenadas negativas. |
| R11 | Paneles libres | Mover/redimensionar cada apartado sin alterar texto ni preferencias de otra superficie. |
| R12 | Chat mínimo | Un compositor y mensajes; ajustes/modelo/historial secundario en menú discreto. |
| R13 | IA real | Pregunta abierta usa proveedor conectado; error o desconexión no se reemplaza por respuesta ficticia. |
| R14 | Comandos locales | Tiempo/notas/pausa se resuelven sin LLM cuando la intención es inequívoca. |
| R15 | Control corporal | El cuerpo pausa/continúa la actividad seleccionada y conserva su identidad de tarea. |
| R16 | Números 9→1 | Cuenta real activa determina el dígito; pausa no sigue restando y cancelación restaura figura. |
| R17 | Dictado por destino | Campo seleccionado explícitamente; finales únicos; no destinos secretos/contraseñas. |
| R18 | Inserción protegida | Se conserva selección/sufijo, se detecta conflicto y nunca se envía automáticamente. |
| R19 | Voz traducida | Original y resultado separados, FIFO de finales, motor real preparado y cancelación. |
| R20 | Lector progresivo | Texto autorizado, avance visible, pausa/seguir y ausencia de lectura recursiva del micrófono. |
| R21 | Hey Axx | Opt-in; detector/ASR/permiso separados; funciona con la aplicación residente, no tras cerrarla. |
| R22 | Fuente musical | Control y estado pertenecen al reproductor seleccionado, no al último local. |
| R23 | Audio reactivo | Usa señal autorizada; silencio y pausa no generan ritmos inventados. |
| R24 | Captura real | Selección de fuente, pausa/seguir, finalización y tiempo activo correctos. |
| R25 | Halo nativo | Perímetro del monitor correcto, siempre no interactivo y estado inequívoco. |
| R26 | Grabación durable | Segmentos recuperables, memoria acotada, error de disco sin declarar guardado. |
| R27 | Destino de grabación | Carpeta autorizada, nombre seguro, no sobrescritura accidental, ubicación confirmada. |
| R28 | Tiempo avanzado | Duración actual, favoritos, ajustes, intervalos finitos, historial y suspensión/reanudación. |
| R29 | Morph Reach | Trayectoria coherente; no tapa controles; no se presenta como acción real antes de ejecutarla. |
| R30 | Archivos/apps | Catálogo autorizado y apertura por identificador, sin texto arbitrario pasado al shell. |
| R31 | Preferencias durables | Esquema versionado, migración y backup; no múltiples almacenes autoritarios. |
| R32 | Seguridad por capacidad | Validación en runtime, no solo botones ocultos; comandos y aprobaciones con IDs. |
| R33 | Rendimiento | Comparación reproducible con misma calidad; respuesta de UI desacoplada del raster. |
| R34 | Release verificable | Instalación, actualización, rollback, desinstalación y ausencia de secretos comprobados. |
| R35 | Accesibilidad | Teclado, foco, contraste, zoom, reducción de movimiento y avisos no dependientes solo del color. |
| R36 | Conservación de herramientas | Notas/tareas/archivos/texto/imágenes/cronómetro siguen accesibles y con sus datos. |

## Regla de prioridad
Permisos y contrato de una tarea > integridad del dato > preferencia explícita > legibilidad y controles de seguridad > coreografía > decoración. Una notificación puede cambiar el acento, no reescribir la forma guardada. Un mensaje de error no abre cuatro ventanas ni borra el borrador.

## Acciones sensibles
Enviar texto, reemplazar una selección externa, capturar audio, iniciar grabación, abrir un programa y escribir un archivo se clasifican por contexto. Una autorización persistida permite únicamente su alcance; no autoriza un destino nuevo, un archivo distinto o una orden propuesta por contenido de una web. Aprobar texto no equivale a aprobar envío.

## Límites de la primera entrega
No se promete control universal de toda app. El release indica destinos compatibles comprobados. Los límites de servicios y modelos siguen visibles como requisito, sin convertir una función ausente en botón aparentemente activo. Una advertencia breve con recuperación útil sustituye al bloqueo de toda la aplicación.


---

# 02 · Auditoría de base y migración sin perder el proyecto

## Fuente de verdad
El paquete original es `Axx-20-proyecto.zip`. El inventario automático incluye scripts reales de package.json, nombres de archivos, hashes y ubicación de símbolos: [auditoría](reference/AUDITORIA-DE-FUENTES.md), [JSON](reference/SOURCE-INVENTORY.json). La documentación histórica de Axx 20 se copia sin reinterpretarla en `reference/AXX20-*`.

El HTML canónico publicado en esa documentación tiene SHA-256 `c93c68ea9e9a63ee392487384941b5ee85c8d3e1f88e024ffd081cbe287458eb`. Comprobarlo contra los bytes recibidos: una diferencia significa otra revisión, no autoriza sobrescribirla. El ZIP tiene su hash propio registrado en el inventario.

La validación de la base reporta 268 pruebas de código y 252 comprobaciones de navegador/contratos. Son resultados históricos del prototipo; no se usan como prueba de Windows. La compilación y la suite se vuelven a ejecutar en M0. Un wrapper Tauri no valida por sí solo micrófono, sistema de archivos, interacción entre procesos o atajos globales.

## Qué se conserva
| Código de Axx 20 | Decisión de migración |
|---|---|
| src/core/model.ts y motion.ts | Conservar IDs, tipos y perfiles; resolver apariencia desde configuración nativa. |
| src/render/software-core.ts y software-renderer.ts | Mantener como implementación de referencia y fallback; extraer trabajo pesado a worker sin alterar fotograma. |
| src/ui/app.ts, experience.ts y stability20.ts | Conservar comportamiento; sustituir escritura localStorage por SettingsPort transaccional. |
| src/ui/flow.ts, orbit12.ts, organic.ts | Conservar navegación radial y Morph Reach; alimentar coordenadas desde WindowCoordinator. |
| src/ui/companion.ts y home18.ts | Conservar semántica de llamada/base; trasladar registro global y coordenadas al runtime. |
| src/ui/action11.ts y action-windows.ts | Conservar selección de acción y paneles; reemplazar autoridad de geometría y tareas de escritorio gradualmente. |
| src/ui/dictation13.ts y servicios de voz | Conservar UX y transacción; entrada nativa única mediante AudioRuntime/ASR. |
| src/ui/time19.ts y capture19.ts | Conservar controles; runtime posee reloj y grabación durable. |
| Música/MediaHub16/servidor/extensión | Reutilizar lógica validada; aislar tokens y control nativo, no duplicar reproductores. |

Antes de crear un archivo por su nombre, consultar el inventario. Las rutas nuevas en este expediente se marcan **NUEVA PROPUESTA** y no se afirman existentes. Localizar `NativeBridge` por símbolo; no asumir que ya hay un crate Rust porque exista una detección de Tauri en JavaScript.

## Migración por sustitución de adaptadores
1. Congelar una copia de Axx 20 con hash. Crear rama `desktop/bootstrap`. Capturar apariencias y exportación de preferencias del usuario.
2. Añadir shell Tauri, sin mover todavía todo el árbol. Generar `dist` con el build actual. No introducir React/Vue ni reescribir la UI por conveniencia.
3. Añadir puertos tipados `SettingsPort`, `WindowPort`, `CommandPort`, `AudioPort`, `CapturePort`. El adaptador web conserva la demostración; el nativo implementa producción. Cada capacidad se selecciona una vez al iniciar, no según excepciones silenciosas.
4. Migrar ajustes: importar snapshot aprobado a SQLite, verificar equivalencia y marcar revisión importada. No sincronizar dos almacenes en ambos sentidos.
5. Migrar tareas una por una. Cuando NativeTimer sea autoridad, App deja de ejecutar su reloj autoritario y solo presenta eventos. Igual para ScreenSession y micrófono.
6. Mantener el monolito compilado como referencia temporal; convertir a módulos ES solo cuando la compatibilidad visual esté cubierta. No exigir ese refactor para el primer shell funcional.

## Antirregresiones obligatorias
Probar forma fija durante Success/Focus; preview cancelado; size/camera tras reinicio; regreso con paso 0; primer toque tras jitter de 2 px; apertura de menús que no inicia drag; elección de tiempo nuevo tras cuenta terminada; pausa de captura que no cambia archivo; traducción tardía que no escribe en destino nuevo; música que no se reinicia al abrir chat.

## Evidencia que falta
Doble clic/navegación real en Windows, persistencia nativa entre procesos, instalación de extensión, captura/micrófono/disco físicos, sesiones autorizadas de proveedores y 30 minutos de carga representativa. Cada ausencia tiene un gate; no se disimula con mocks.


---

# 03 · Arquitectura objetivo

**Decisión:** Tauri 2 + Rust para host Windows y el TypeScript existente para la interfaz. SQLite por usuario; procesos auxiliares solo para trabajos pesados o aislables. Node sigue siendo herramienta de desarrollo y puente provisional del prototipo, no requisito del usuario final. Las API de Tauri/Windows se fijan y verifican en M0/M1 [S01–S08, S20].

## Componentes y límites de confianza
```text
Ventanas de Axx / UI existente
  → IPC Tauri con comandos tipados y capacidad de la ventana
  → RuntimeCoordinator
       ├── SettingsStore / SQLite / SecretStore DPAPI
       ├── TaskRegistry + CommandDispatcher + PermissionBroker
       ├── WindowCoordinator + GlobalInput + NativeTargetBroker
       ├── AudioRuntime → Wake/VAD/ASR worker → transcript
       ├── LLMGateway → proveedor autorizado
       ├── MediaSessionBroker → GSMTC / adaptador web / proveedor
       └── CaptureService → EncoderWorker → segmentos durables
Extensión autorizada → Native Messaging host → named pipe por usuario → Broker
```

El renderer y la animación no conocen secretos, rutas arbitrarias ni endpoints de pago. Un contenido de web, nombre de archivo o respuesta de modelo no tiene autoridad para invocar una operación. El runtime comprueba cada petición.

## Árbol de trabajo propuesto
Se añade al repositorio actual, sin mover `src` en el primer incremento:
```text
src/                         TypeScript y CSS actuales
src/ports/                   NUEVO: interfaces de integración
src/adapters/native/         NUEVO: cliente IPC / snapshots
src-tauri/                   NUEVO: proyecto Rust Tauri
  src/runtime/               coordinador, comandos, permisos, eventos
  src/platform/windows/      ventanas, DPI, hotkeys, UIA, GSMTC, WGC, WASAPI
  src/storage/               migraciones, settings, backup, secretos
  src/media/                 reloj, captura, segmentos, sesiones
  capabilities/              permisos por ventana
  migrations/                migraciones SQL revisadas
workers/asr/                 NUEVO: adaptador/manifest del binario ASR
native-messaging/            NUEVO: host acotado de extensión
extension/                   existente, evolucionada
contracts/                   copia sincronizada de contratos aceptados
```

## Estado autoritario
El runtime es propietario de la configuración guardada, tareas, grants y recursos de captura. La UI posee borradores visuales no confirmados, foco y transiciones. Un snapshot de arranque incluye `revision`, preferencias, tareas activas y capacidades disponibles. Cada cambio produce un evento con secuencia. Al reconectar una ventana, recibe snapshot y solo eventos posteriores; no reproduce animaciones históricas en lote.

Un único proceso es instancia principal. Una segunda ejecución envía `show` al principal y sale. El worker ASR puede reiniciarse sin cerrar la UI. Un fallo de codificador termina la sesión con error conservando segmentos; no reinicia automáticamente una captura. Los procesos auxiliares no exponen puertos en la LAN.

## Flujos principales
**Pregunta:** compositor → mensaje de conversación → comandos deterministas seguros o LLM → respuesta progresiva → opcional propuesta de herramienta → validación/confirmación → tarea → resultado. No se confunde texto recibido con autorización.
**Dictado:** destino capturado → sesión de audio autorizada → resultados finales ordenados → traducción opcional → revisión/inserción autorizada → feedback Morph Reach. Las palabras provisionales no modifican campos externos.
**Captura:** gesto → selector → fuente verificada → cuenta previa → encoder → archivo temporal/segmentos → finalizar → comprobar escritura → resultado. El halo recibe estado; no dirige el encoder.
**Tamaño:** gesto manual → `settings.patch(expected_revision)` → commit SQLite → snapshot a todas las ventanas. Un encaje automático es solo `presentationBounds`, nunca un patch de preferencia.

## Fronteras de transporte
UI↔runtime por IPC Tauri con payload máximo y listas cerradas. Worker local por stdio o pipe con framing y cancelación. Extensión↔host por framing Native Messaging; host↔runtime por pipe con ACL del SID actual. Proveedores HTTPS desde runtime. Autorización OAuth usa callback explícito y correlación de sesión; no permite cargar una URL remota dentro del WebView privilegiado.

## Compatibilidad degradada, no apariencia falsa
Una función puede quedar `unavailable(reason)` manteniendo las demás. Si falta ASR, existen teclado y comandos escritos; si falta captura, notas y tiempo siguen funcionando; si falla renderer, se muestra un control accesible temporal sin presentarlo como el acabado final. No se inventa una respuesta ni se oculta una degradación.


---

# 04 · Registro de decisiones técnicas

| ADR | Decisión | Razón / coste |
|---|---|---|
| 001 | Tauri 2, Windows primero | Mantiene TS y añade Rust/Win32. Exige trabajo real de integración; WebView2 no resuelve por sí solo overlay ni ASR. |
| 002 | No reescribir UI en otro framework | Reduce riesgo de perder interacciones, IDs y estilos; deuda del namespace se elimina después con pruebas. |
| 003 | Runtime autoritario y UI proyectada | Evita doble reloj, micrófonos duplicados y preferencias sobrescritas; requiere snapshots/revisiones. |
| 004 | SQLite por usuario + DPAPI para secretos | Datos transaccionales separados de credenciales; recuperación/backup explícitos [S19,S27,S28]. |
| 005 | Software renderer como referencia | Preserva compatibilidad y calidad; optimizar worker/caché antes de migrar motor [S26]. |
| 006 | Paneles nativos separados cuando salgan del área del avatar | Permite escritorio real; aumenta coordinación, DPI y memoria de WebViews. |
| 007 | Captura nativa durable en una fase propia | El recorder web es útil para comparar, no para recuperación tras fallo ni halo global. |
| 008 | AudioRuntime único | Un dueño del micrófono, varias suscripciones; desacoplar captura de reconocimiento y medición. |
| 009 | ASR local pequeño primero, proveedor opcional | Medir sobre 16 GB sin prometer grandes modelos. La selección de modelo/licencia es explícita. |
| 010 | Wake word opt-in, no autenticación | Evita activación accidental como permiso; requiere pruebas de falsas alarmas. |
| 011 | UIA + adaptador DOM, no escritura universal ficticia | Ninguna técnica funciona igual en todos los editores. Fallback de pegado solo autorizado [S11–S13,S23]. |
| 012 | Media control y señal de audio separados | GSMTC/API pueden controlar sin audio crudo; loopback mide sin controlar [S16,S18]. |
| 013 | Firma de instalador y firma de actualización separadas | La firma del actualizador no sustituye Authenticode ni garantiza reputación [S07,S08]. |
| 014 | Un release declara solo capacidades probadas | Integraciones beta identificadas; no promover mocks a evidencias físicas. |

## Alternativas descartadas como elección inicial
**Electron:** viable para una futura decisión, pero no se cambia a él solo para envolver el mismo HTML. Añade distribución de Chromium y no elimina permisos Windows, UIA, captura o firma.
**Aplicación web/PWA:** conserva los límites de otras ventanas y atajos globales. No satisface el destino principal de esta migración.
**Reescritura completa en motor de juego:** puede mejorar ciertas técnicas 3D, pero multiplica riesgo visual y de integración. No se aprueba antes de demostrar necesidad y compatibilidad funcional.
**Ejecutar todo por un LLM:** aumenta latencia/coste y permite errores en acciones deterministas. El modelo propone; capacidades verificadas ejecutan.

## Decisiones que se cierran mediante un ensayo acotado
La estrategia exacta de input selectivo entre ventanas, el motor de wake word, la latencia del ASR, el contenedor recuperable y la viabilidad de 60 FPS no se resuelven con un eslogan. Cada ensayo tiene un resultado observable, límite de alcance y una comparación. Si falla, registrar por qué y elegir la alternativa indicada; no acumular hacks sin actualizar el ADR.

## Política de cambios
Un cambio que afecte forma/material, permisos, coste externo, algoritmo de inserción, persistencia o contratos necesita ADR y prueba de migración. Un ajuste CSS local sin cambio semántico necesita captura comparativa y prueba de foco/tamaño. No se acepta reducir calidad como arreglo implícito de una caída de rendimiento.


---

# 05 · Preparación de Windows y comandos de desarrollo

## Herramientas de desarrollo
Windows 11 x64; Git; Node.js compatible con el lockfile de la base; Rust MSVC; Microsoft C++ Build Tools con el workload de escritorio C++ y un Windows SDK; WebView2 Runtime. Los requisitos oficiales de Tauri se consultan en S01. La base fue probada con Node 22.16.0 y TypeScript 5.8.3; eso es una referencia de reproducibilidad, no una afirmación de que sean las versiones actuales más recientes. Mantener Node 22 mantenido o validar otra rama LTS antes de cambiar el lock [S43,S44].

El usuario final no necesitará Git, Node, Rust, Visual Studio ni una clave de desarrollador. El instalador debe resolver WebView2 según el modo de distribución elegido y requisitos documentados [S07].

## Preparación sin cambios ocultos
En PowerShell abre la carpeta de este expediente y ejecuta:
```powershell
& .\tools\Preflight-Windows.ps1 -OutputDirectory .\evidence\mi-pc
```
El script es de lectura de entorno y creación de informe: no instala nada, no eleva permisos, no cambia política de ejecución ni activa escucha. Si PowerShell bloquea un script, revisa su contenido y la política con el administrador; no se proporciona un bypass automático.

Extrae las fuentes mediante la herramienta de preparación, utilizando la ruta real del ZIP:
```powershell
& .\tools\Preparar-Workspace.ps1 `
  -SourceZip "$HOME\Downloads\Axx-20-proyecto.zip" `
  -Destination "$HOME\Documents\Axx-Desktop"
```
El destino debe ser nuevo. El script comprueba rutas de archivo, limita extracción y no sobrescribe proyectos. Después abre la subcarpeta que contenga `package.json`, identificada en el informe.

## Primero: reproducir la base
Desde la raíz real de las fuentes:
```powershell
node --version
npm --version
npm ci
npm run build
npm test
```
Usar `npm ci` únicamente si existe un lockfile válido y concordante; si falla, conservar el error y corregir la causa antes de recrear el lock. No ejecutar `npm audit fix --force` como parte del arranque. La lista real de scripts aparece en `reference/package.original.json`.

Para inspeccionar el prototipo: ejecutar el script `start` si está declarado en package.json, o el comando de servidor que declare su LEEME. No se denomina a ese paso "arrancar la aplicación nativa". `scripts/server20.mjs`, cuando exista, es prueba de servidor; verificar su contenido antes de tratarlo como daemon.

## Después: crear el shell nativo, solo en la rama de migración
Los siguientes son pasos de implementación M1. **No se ejecutaron ni crean por sí solos las capacidades descritas en los demás documentos.**
```powershell
git switch -c desktop/bootstrap
npm install --save-dev --save-exact @tauri-apps/cli@2
npx tauri init
```
La instalación `--save-exact` registra la versión 2.x resuelta; guardar package-lock y registrar CLI/crates/toolchain. En el asistente de init utilizar las fuentes existentes: `frontendDist` debe resolver a `../dist` respecto de src-tauri. `beforeBuildCommand` invoca `npm run build`. Para dev puede usarse el servidor local actual, pero no dejarlo como dependencia Node de la release.

Si la UI mantiene namespace/outFile inicialmente, el adaptador puede usar `withGlobalTauri: true` y la API global verificada de Tauri. No insertar imports ES sin ajustar el build. Para una migración a módulos, plan y prueba aparte. Configurar capabilities para las ventanas reales y denegar contenido remoto privilegiado [S02,S04].

## Compilar cuando M1 esté implementado
Desde la raíz que contiene src-tauri:
```powershell
npx tauri info
npx tauri dev
cargo test --manifest-path src-tauri/Cargo.toml
npx tauri build --bundles nsis
```
Estos comandos **requieren el proyecto Rust todavía por desarrollar**. `tauri init` genera un esqueleto; el contrato del producto requiere ventana/bandeja/instancia/datos/IPC y las puertas de M1. Registrar las rutas de artefactos producidas por el build real, no asumir nombre/versionado de un .exe que aún no existe.

## Fijar versiones
Crear `rust-toolchain.toml` con la versión exacta validada, Cargo.lock, package-lock y un manifiesto de modelos con hash/licencia. No actualizar toolchain, WebView2 policy ni motores de voz en mitad de una corrección de UI. Antes de publicar, ejecutar análisis de dependencias y revisar vulnerabilidades vigentes; no certificar seguridad solo por usar versiones fijadas.

## Carpeta del usuario
Datos: `%LOCALAPPDATA%\Axx\` para base, logs y manifiestos; vídeos en una carpeta elegida. Binarios: instalación por usuario separada. No escribir bases o tokens junto al exe ni en Program Files. No usar la carpeta de desarrollo como almacén del usuario.

## Incorporar el expediente a las fuentes
Desde la carpeta de este expediente, después de extraer el ZIP base, ejecuta `tools/Instalar-Expediente.ps1 -SourceDirectory` indicando la raíz real que contiene package.json. Copia la documentación a `docs/axx-desktop` y crea `AXX-LEER-PRIMERO.md`, sin sobrescribir AGENTS.md existentes ni código. El agente comienza leyendo ese archivo.


---

# 06 · Presencia de escritorio, paneles, DPI y atajos

## Objetivo
Axx debe existir sobre aplicaciones de Windows sin convertirse en un rectángulo invisible que impida trabajar. Transparencia visual y transparencia de entrada son problemas distintos. Tauri permite configurar ventanas, pero la política de interacción selectiva se implementa y valida en el adaptador Windows [S04,S09,S10,S41,S42].

## Composición propuesta
**Ventana visual de presencia:** sin marco ni tarea en barra; always-on-top configurable; no roba foco; ignora entrada. Contiene avatar, brillo y efectos locales. Una ventana de halo por monitor es decorativa y siempre ignora entrada.
**Superficie de entrada del avatar:** proxy Win32 acotado cuya región corresponde al cuerpo/controles utilizables. Recibe clic/arrastre y los comunica al coordinador. La región no debe ser todo el canvas transparente. El brillo continúa dibujándose en la ventana visual, no queda recortado por la máscara de input.
**Paneles de herramientas:** ventanas WebView normales, acotadas, activables al pulsar sus campos. Comparten datos mediante runtime; no crean un segundo reproductor o tarea. Pueden fijarse, recogerse y restaurarse sin perder borradores.

Esta separación es la estrategia inicial del ensayo M1. Una alternativa de ventana única que alterne `set_ignore_cursor_events` por posición de cursor solo se admite si las pruebas muestran que no pierde el primer clic. `WM_NCHITTEST/HTTRANSPARENT` no debe anunciarse como solución universal entre procesos: la documentación limita su búsqueda de ventanas del mismo hilo. Una máscara visual por sí sola tampoco demuestra click-through [S41].

## Regiones de interacción
El renderer software ya conoce geometría y alfa. Generar una máscara dilatada de 3–4 píxeles CSS y convertirla a región nativa o rectángulos fusionados, junto a los controles activos. Actualizar como máximo al ritmo necesario; no leer todo el escritorio ni hacer readPixels de pantalla. Una región solo se publica con su `frameId`, caja y escala; si queda obsoleta durante un cambio importante, utilizar una región conservadora pequeña, no la pantalla completa.

Aceptación: pulsar 100 puntos fuera de cuerpo/botones sobre Bloc de notas y Explorador; 100 dentro de cada objetivo; mover mientras se pulsa; cerrar panel con captura de puntero; abrir menú sin drag; comprobar que Ctrl+C en otra app no se pierde. El cuerpo no toma foco al aparecer. Enviar texto sí requiere un destino y confirmación de foco apropiados.

## Coordenadas y monitores
Persistir posición deseada en unidades lógicas relativas al área de trabajo y al monitor; mantener también escala original e ID estable con fallback. Convertir a píxeles físicos una única vez en la capa Win32. La posición de un monitor puede ser negativa. No aplicar DPI dos veces ni asumir que la esquina inferior derecha del monitor primario es la de la ventana actual.

Ante `WM_DPICHANGED`, cambio de resolución o retirada de pantalla: recomputar caja visible, mantener la preferencia original y trasladar temporalmente al área de trabajo accesible. La barra de tareas, teclado virtual y márgenes seguros se excluyen. Una corrección automática no se guarda como un gesto manual.

Paneles: ancho mínimo orientativo 320 px CSS, texto principal 14–16 y objetivos prioritarios ≥44 px CSS; no escalar la UI completa para que quepa. Pantallas pequeñas usan scroll interno con cabecera/controles de cierre visibles. Zoom 200 % debe seguir permitiendo cerrar, detener captura y recuperar ajustes.

## Atajo de ida/vuelta
Usar registro nativo global y una sola máquina `RecallGesture`. Alt+Mayús+A de pulsación física llama inmediatamente. Segunda A liberada y pulsada dentro de 450 ms retorna; no contar autorepeat. Al retornar, Flow pasa a 0, los símbolos temporales se limpian y la base recupera la forma guardada. Un retraso visual no duplica acciones.

`Esc` se registra globalmente solo mientras Axx está siguiendo o tiene una operación de interacción que lo requiera; se desregistra al salir. No secuestrar Escape permanentemente para todo Windows. Si existe conflicto al registrar, mostrarlo y ofrecer reasignación. No mantener simultáneamente el listener DOM y el nativo ejecutando la misma acción: el evento nativo lleva un ID que se deduplica.

## Semántica de foco y tarea
Llamar no enfoca el chat automáticamente. Tocar la figura aparcada solo revela Herramientas. Tocar la figura en modo acción sí opera la tarea elegida. Un drag comienza después de >7 px de desplazamiento; cancel/lostcapture/blur cancelan el gesto y no ejecutan clic diferido. Retornar detiene micrófono y traducciones pendientes por política del usuario, pero no cancela música local, cronómetro, timer ni captura.

## Estado restaurable
Persistir base, tamaño deseado, posición y tamaño por panel, opacidad y tipografía. No persistir captura de ratón, hover, micrófono encendido, menú abierto por accidente ni permisos temporales. El arranque visual puede ser aparcado; la restauración de tareas sigue las reglas de cada servicio.


---

# 07 · Identidad, formas, materiales, brazos y rendimiento

## Contrato visual
La referencia es Axx 20: 24 formas, 9 paletas, 6 perfiles de movimiento y estilos guardados. Los IDs originales no cambian. Una ampliación agrega IDs al final y mantiene importaciones. El personaje no se sustituye por PNG/GIF/vídeo. Los gráficos del selector sí pueden ser miniaturas precalculadas; no se confunden con el avatar vivo.

La configuración autoritaria contiene forma, paleta, material, cámara, tamaño, keepForm, actionMorph y estilo de movimiento. Una operación de preview crea una revisión temporal, independiente. Guardar confirma el conjunto atómicamente; descartar elimina el preview entero. Una notificación no escribe en configuración. Una limitación temporal de tamaño no cambia la preferencia.

## Resolución de apariencia
1. Preview explícito mientras su editor esté activo.
2. Si existe actionMorph permitido y actividad seleccionada: símbolo volumétrico o dígito durante la ventana de tiempo real.
3. Si keepForm: figura guardada.
4. Solo si el usuario autorizó adaptación: forma contextual.
5. Aparcado: quitar símbolos transitorios y recuperar identidad guardada.

Los eventos de tarea aportan intensidad/movimiento, no config nueva. El proceso de geometría recibe un snapshot inmutable. El control sigue operando si actionMorph está desactivado.

## Calidad que se conserva
La documentación de referencia declara malla 112×72, 16.128 triángulos estándar, LUT bilineal 512×512 y raster al doble de la dimensión de salida. Esas son las condiciones del benchmark existente, no requisitos universales de cada tubo. Mantenerlas en la ruta equivalente y no activar resolución adaptativa sin decisión visible. No confundir aumentar el límite del scheduler a 60 con obtener 60 FPS.

## Optimización en orden
**Medir:** frame CPU, raster, composición, IPC, gc, tareas largas y respuesta al clic. Separar captura/media/ASR de la UI.
**Eliminar trabajo repetido:** reutilizar buffers, matrices, geometría invariante y LUT cuando el material efectivo no cambia. No recrear nodos ni textos cada tick.
**Aislar:** OffscreenCanvas/Worker cuando el WebView2 real lo soporte; transferir datos acotados y mantener DOM/input en main. Si no está disponible, fallback a la implementación actual sin perder funciones [S26].
**WASM/SIMD opcional:** solo tras medir y demostrar equivalencia del contorno/material y precisión necesaria. No hacer de una optimización experimental una nueva dependencia obligatoria.
**Ocultación:** detener decoración invisible sin detener tareas, reloj o audio; al reaparecer reconstruir el estado actual, no todas las transiciones omitidas.

La referencia debe compararse con misma pose, estado, viewport, DPI, calidad y audio. Para una optimización exacta se comparan todos los RGBA; para una mejora artística aprobada, las diferencias esperadas se registran y se revisan, no se exige una igualdad incompatible con el cambio visual.

## Presupuestos de aceptación, no resultados ya obtenidos
Objetivo de respuesta de input p95 <100 ms, ausencia de tareas de UI >100 ms repetidas, y 30 FPS sostenidos como puerta inicial a calidad fijada; 60 FPS es objetivo posterior. Medir CPU/RAM de 30 min con avatar, música y dos paneles. Si no se cumple, optimizar y registrar; no bajar calidad silenciosamente ni falsear los números parando el renderer en el test.

## Morph Reach
Una extensión nace de la misma materia y sigue una curva con tangentes continuas, radio de hombro/centro/punta, volumen y normales. La raíz se oculta correctamente detrás de la superficie; el trayecto evita editores y controles. No dibujar cinco cables permanentes en la órbita. Una sola conexión breve de anticipación puede asistir el acceso seleccionado.

El plan de mejora artística posterior une topológicamente raíz y cuerpo o usa una superficie implícita consistente; esta unión no está demostrada en el prototipo. Medir su coste antes de sustituir tubos. Un contacto transporta una tarjeta semántica real; no mover el archivo físico al mover su representación.

## Inserción y animación
Validar/comprometer la inserción primero. El brazo y la membrana representan esa transacción; al retirarse queda visible el texto que ya se colocó. Cancelar una animación no debe repetir o deshacer la escritura. Movimiento reducido ofrece transición corta/opacidad conservando resultado, foco y confirmación.

## Más formas sin perder coherencia
Cada forma nueva requiere: ID estable; función o malla editable; normales válidas; vista frontal/lateral/posterior; transición desde y hacia cada familia; hit-mask usable; prueba sin NaN/Inf; paletas verificadas; costo de dibujo; aprobación visual. Aumentar el conteo sin estas pruebas no cumple la solicitud de calidad.


---

# 08 · Persistencia, migración y recuperación

## Almacén autoritario
Producción usa SQLite por usuario en `%LOCALAPPDATA%\Axx\data\axx.db`. La UI no conserva una segunda configuración autoritaria en localStorage. Una interfaz `SettingsPort` recibe snapshot y envía patch con `expectedRevision`. El runtime escribe una transacción y publica nueva revisión; un conflicto no se resuelve pisando a ciegas.

`config/app.defaults.json` declara defaults propuestos. No es una configuración ya instalada. `contracts/storage-v1.sql` es esquema inicial de referencia, ejecutable sobre una base vacía para validación. El desarrollador lo adapta a sus tipos reales y lo versiona en migraciones; nunca lo aplica directamente sobre datos existentes sin backup.

## Dominios separados
**Identity:** figura/material/cámara/presets; versión y límites.
**Layout:** tamaño deseado y base por monitor; geometría por panel; no hover.
**Tasks:** tipo, identidad, estado, tiempo monotónico/wall y resultado; cancelado no completado.
**Content:** notas, pendientes y conversaciones que el usuario haya elegido guardar.
**Permissions:** grants de capacidades y destinos, expiración/revocación; no tokens OAuth en JSON.
**Media:** referencias autorizadas, manifiestos de capturas; la base no duplica un vídeo entero.

Tokens/secretos: DPAPI bajo el usuario actual o almacén de credenciales, con referencia en SQLite, no valor plano. DPAPI no hace que un equipo comprometido sea seguro y no se usa con alcance de máquina para eludir aislamiento de usuarios [S19].

## Importación del prototipo
Leer el backup exportado por Axx20 como datos no confiables. Validar enums, tipos, límites, rutas y longitud. Mapear `axx-studio-v2`, `identity20`, `axx.body15`, `axx.windows11`, preferencias de voz/música/base y demás campos reconocidos. Conservar desconocidos solo en copia de importación, no ejecutarlos. No importar consentimientos de micrófono como autorización activa.

Flujo: copia original → parse → informe de diferencias → preview del conjunto → aprobación → transacción de migración → verificación de snapshot → marca `importedHash`. Una segunda importación del mismo hash no duplica notas. Si el usuario aprueba fusionar, IDs estables y reglas documentadas evitan pérdidas.

## Consistencia de ajustes
Al redimensionar, guardar el valor deseado, no el resultado temporal de encajarlo en móvil. Vista pequeña reduce `presentationBounds` sin modificar `desiredBounds`. Cada patch identifica panel/herramienta. Aplicar un estilo de apariencia no modifica permisos, destino de dictado ni proveedor.

Los cambios frecuentes pueden agruparse por 150–250 ms, pero al finalizar gesto/cerrar se confirman. Escribir una revisión completa y `commit` evita mezclar forma nueva con cámara vieja. El renderer solo pinta snapshots confirmados o preview explícito.

## Tareas y reloj
Timer persistido con wall deadline, tiempo restante al pausar, estado y timestamp de reconciliación. Al reiniciar no simular tareas que nunca se ejecutaron. Registrar que un plazo venció mientras Axx no corría, distinguirlo de una sesión activa completada y evitar reproducir docenas de alarmas atrasadas. La captura no se reanuda automáticamente desde datos persistidos.

## Backup
Usar la API de backup de SQLite o snapshot coherente; no copiar solo `axx.db` mientras WAL está activo [S27,S28]. Backup exportado contiene versión, hashes y manifiesto. Secretos excluidos por defecto. Audio/transcripciones no se incluyen salvo opción explícita; un archivo de preferencias no debe convertirse en un registro accidental de conversaciones.

## Fallo y recuperación
Disco lleno: falla la transacción, conservar snapshot previo y mostrar recuperación; nunca indicar Guardado. Corrupción: apartar la base de forma no destructiva, ofrecer restaurar copia y exportar lo legible, sin borrar silenciosamente. Downgrade: si versión antigua no entiende esquema, no abrirlo en modo escritura; restaurar copia compatible o negarse de forma explicada.

## Pruebas físicas
Guardar y reabrir desde proceso nuevo con SQLite real; cortar proceso antes/después de commit; dos ventanas con expectedRevision antiguo; importar valores NaN/string enormes; escritorio 150 % → monitor 100 % → desconectar monitor → recuperar; fallar escritura sin perder preferencias; restaurar backup y verificar hashes.


---

# 09 · Contratos, comandos, eventos e idempotencia

Las interfaces de `contracts/` son **propuestas del runtime nuevo**, no endpoints que el HTML ya implemente. Se validan sintácticamente y se convierten en tipos TS/Rust y validación de entrada antes de conectarlas a una capacidad física.

## Solicitud
Cada comando contiene `contractVersion`, `id`, `sessionId`, `issuedAt`, `expiresAt`, `origin`, `capability`, `operation`, `payload` y una `approvalId` opcional. El origen lo fija/verifica el transporte, no se acepta una cadena que diga "usuario" enviada por el modelo. UUID e idempotency key se usan para no ejecutar dos veces tras un retry.

`CommandDispatcher` hace, en orden: límite de tamaño → parse/contrato → origen/ventana/sesión → plazo → capacidad → parámetros → destino vigente → aprobación si corresponde → deduplicación → ejecución → evento. El registro de una petición no implica que empezara ni terminara.

## Resultado y evento
Respuesta: `accepted`, `rejected` o `completed` con ID. Operaciones largas devuelven accepted y luego eventos secuenciados. Cada evento tiene `seq`, `timestamp`, `taskId`, `revision`, `type` y `payload` mínimo. La UI ignora secuencias antiguas y solicita snapshot si hay un salto. No utiliza un callback de fin de animación para cambiar la fase de una tarea.

## Catálogo de capacidades propuesto
| Capacidad | Operaciones | Riesgo/frontera |
|---|---|---|
| presence | summon, return_home, stop_follow | UI global pero no acceso a datos externos. |
| settings | snapshot, patch, export, import_preview, import_apply | Revisión y validación, permisos no heredados. |
| timer | start, pause, resume, extend, cancel | Duración/estado estrictos, un taskId. |
| dictation | prepare, start, pause, stop | Micrófono opt-in y destino explícito. |
| insertion | inspect_target, preview, commit, undo | Aprobación según política, conflicto/foco. |
| media | list_sessions, select, play, pause, next, previous, seek | Solo métodos soportados por destino. |
| capture | choose, start, pause, resume, stop, save | Selector y permisos; rutas acotadas. |
| files | list_authorized, search_authorized, open | Solo raíces autorizadas y referencias opacas. |
| apps | list_catalog, open | AppId permitido; no shell arbitrario. |
| reader | prepare, play, pause, resume, stop | Texto procedente de fuente autorizada. |

No existe `execute_shell(any_text)`, `eval`, PowerShell libre ni URL de API arbitraria como herramienta del LLM. Un conector o skill no amplía los permisos por aparecer en catálogo.

## Aprobación verificable
Un `ApprovalRecord` vincula usuario/sesión, operación, destino, hash de parámetros, plazo de 30 s propuesto y uso único. Un cambio de texto, destino, ruta o acción invalida el registro. Mostrar "Aprobar y colocar" no genera permiso para "enviar". Un yes recibido del modelo no es una confirmación del usuario. La política permite configurar inserción directa previamente autorizada en destinos de bajo riesgo, con indicador visible y revocación.

## Cancelación y concurrencia
Cada trabajo tiene cancellation token y generation. Cancelar invalida resultados pendientes incluso si el proveedor no cancela su computación a tiempo. Cambiar campo/idioma corta la generación de dictado traducido. Cambiar ventana no cambia automáticamente la tarea seleccionada. Stop de captura es idempotente: varias pulsaciones producen una sola finalización.

## Códigos de error
`CAPABILITY_UNAVAILABLE`, `PERMISSION_REQUIRED`, `PERMISSION_DENIED`, `TARGET_STALE`, `FOCUS_CHANGED`, `REVISION_CONFLICT`, `PROVIDER_DISCONNECTED`, `RATE_LIMITED`, `TIMEOUT`, `CANCELLED`, `STORAGE_FULL`, `ENCODER_FAILED`, `UNSUPPORTED_MEDIA`, `MODEL_NOT_INSTALLED`.

Cada error incluye `retryable` y un mensaje claro. Logs incluyen códigos e IDs, no transcripciones o claves. El usuario ve la acción posible: seleccionar otra fuente, renovar destino, reintentar guardar, conectar motor. Nunca "terminado" después de un timeout.

## Transporte seguro
Tauri capabilities por etiqueta de ventana; renderer/main no equivalen a un grant universal. Extension ID y origin permitidos, mensajes máximos acotados, sin browser content dentro del WebView privilegiado. Un pipe acepta solo usuario actual. Gateway web de transición en loopback no significa que cualquier página de Internet pueda invocarlo: verificar Origin, token de sesión, método y content-type.


---

# 10 · Voz, dictado y escritura en otras aplicaciones

## AudioRuntime único
Un servicio posee el dispositivo de micrófono mediante WASAPI; distribuye frames a medidor, VAD y ASR. No iniciar simultáneamente getUserMedia, SpeechRecognition, wake detector y tres capturadores nativos. Separar audio de micrófono, loopback y TTS; el medidor de voz no se alimenta del espectro musical.

La captura puede tener frecuencia nativa de 48 kHz u otra: negociarla y registrar el valor. Resamplear para el motor ASR según su contrato —por ejemplo PCM mono 16 kHz— con conversión correcta; no etiquetar bytes de 48 kHz como 16 kHz. Frames numerados y timestamps monotónicos. Buffer acotado: una pausa o cancelación libera consumidores y recursos que ya no sean necesarios.

## ASR propuesto
Evaluar whisper.cpp con un modelo multilingüe pequeño en CPU, proceso auxiliar versionado, hashes y licencia por artefacto [S29]. Tiny/base son candidatos de benchmark, no una promesa de precisión o tiempo real. No instalar pesos automáticamente. El manifiesto indica tamaño, idiomas esperados, memoria medida, proveedor y opción remota explícita.

El wrapper de Axx define su propio protocolo JSONL/pipe de trabajo; no inventar opciones de `whisper-cli`. Fijar una versión real, capturar `--help` y probar el binario en Windows. El ASR puede usar segmentos VAD con contexto: esto no equivale a un modelo de streaming token a token ni garantiza latencia fija.

## Flujo de usuario
Elegir Dictar mantiene modo compacto: entidad y cápsula de amplitud. Tocar Axx inicia tras consentimiento/destino; tocarlo pausa; Ajustes abre original, preferencias y lectura. La selección del campo con ratón establece una referencia de destino, no un listener que reinterpreta toda la actividad del usuario como permiso.

Resultados `partial` solo se muestran; `final` lleva segmentId único y orden. Antes de colocar: validar destino, estado editable, revisión y longitud. Cada inserción conserva sufijo/rango y devuelve confirmación observable. Sin autorización de enviar, no Enter ni click en Send.

## Estrategia de destinos
**DOM de Axx:** conservar transacción existente, `beforeinput`, `setRangeText` y eventos compatibles.
**Páginas autorizadas:** extensión con adaptador DOM de input/textarea; contenteditable requiere prueba por editor, composición/selection/ranges y validación del contenido cambiado. Los frameworks pueden controlar su estado; disparar un evento no garantiza compatibilidad con todos.
**Aplicaciones Windows:** UI Automation identifica control, editable/contraseña, proceso, ventana y RuntimeId. TextPattern sirve para leer/navegar texto, no ofrece una API universal de inserción. ValuePattern puede fijar todo el valor; no equivale a sustituir una selección sin tocar lo demás [S11,S13].

Para destinos nativos sin adaptador seguro, ofrecer pegado explícito por SendInput/portapapeles y solo mientras la misma ventana/control conserve foco. UIPI puede impedir inyección hacia procesos de mayor integridad. No elevar Axx ni usar uiAccess como parche automático [S12].

## TargetLease
Crear lease con HWND, PID, controlRef, usuario, capabilities, selectionSnapshot y expiration. No guardar el texto completo externo en logs. Guardar una huella corta de contexto solo en memoria cuando sea necesario. Si cambia foco, PID, selección, valor esperado o control desaparece: invalidar y conservar el borrador. Capturar destino antes de enfocar Axx y restaurarlo solo con intención explícita; no robar foco durante animación.

Fallback portapapeles: el usuario opta por él. Guardar temporalmente formatos restaurables y sequence number; escribir solo el texto aprobado; inyectar pegar; verificar donde sea posible; restaurar solo si el portapapeles aún contiene la revisión propia. No destruir una copia nueva del usuario. Si no puede garantizarse preservación de formatos, avisar y ofrecer copiar manualmente. No automatizar envío tras el pegado.

## Voz traducida
ASR final → original retenido → cola FIFO limitada a 24 segmentos → traductor elegido → validación de resultado completo → revisión/inserción. Cada trabajo cancela a los 45 s configurados por defecto; tiempo configurable sin cola infinita. Cambiar idioma/destino cancela todo lo pendiente. La traducción por navegador es solo un adaptador condicionado; el proyecto nativo puede reutilizar proveedor de texto real [S24,S25].

## Leer lo transcrito
Detener captura antes de TTS salvo modo full-duplex con control de eco validado. Fragmentos y estado de lectura alimentan widget; no fingir amplitud de micrófono desde eventos de palabras. El texto original, traducido y corregido permanecen distinguibles. Copiar/guardar/leer no inicia otra traducción ni envío.

## Pruebas físicas mínimas
Bloc de notas, búsqueda Explorador, navegador input y textarea, chat web autorizado, Word o editor solicitado. Selección parcial, acentos/nombres/números, campo readonly/contraseña, cambio rápido de destino, micrófono desconectado, resultado duplicado/tardío, proceso elevado no autorizado, editar durante traducción, deshacer después de nueva edición. Registrar la lista concreta compatible; no escribir "cualquier chat" sin cobertura.


---

# 11 · Activación manos libres, lectura e interrupciones

## Hey Axx no es otro asistente
Es un método de invocación del mismo RuntimeCoordinator. Se implementa después del dictado por pulsación y las pruebas físicas. Desactivado por defecto; únicamente activo mientras Axx esté ejecutándose y el usuario lo habilite. Cerrar Axx detiene sus recursos, no deja un listener oculto instalado como servicio.

## Máquina de estados propuesta
`disabled → armed → wake_detected → listening_command → interpreting → approval_wait/executing → responding → cooldown → armed`.

El detector usa una ventana de audio acotada en RAM; no graba un historial continuo. Tras activación, hasta 8 s iniciales para iniciar una orden y 20 s máximos propuestos para una orden corta, con ajuste por accesibilidad. El VAD delimita el final. Tiempo agotado devuelve al reposo con señal discreta, no manda audio vacío al LLM.

openWakeWord es candidato a evaluar, no una implementación prometida de una frase española personalizada. Revisar idioma, entrenamiento, licencia del código y de cada modelo; no heredar una licencia de software para todos los pesos [S30]. Un motor comercial puede ser alternativa opcional con coste/licencia explícitos. "Hey Axx" debe entrenarse o configurarse y medirse realmente antes de habilitar el interruptor en release.

## Comandos iniciales
"Ven aquí", "vuelve a tu esquina", "pausa", "continúa", "temporizador de cinco minutos", "crea una nota", "léeme esto" y "cancela" con contexto de tarea inequívoco. Si dos tareas admiten pausa, preguntar cuál o usar la tarea seleccionada mostrando su nombre. Enviar mensajes o abrir una app usa los mismos grants que el método de ratón; la voz no desbloquea permisos.

## Seguridad funcional
La voz del usuario reconocida no autentica su identidad. El audio de un vídeo, un altavoz o la salida del propio Axx puede parecer una orden. Medir falsas activaciones, atenuar/pausar salida durante escucha si es necesario y respetar mute físico. No evaluar URLs o instrucciones leídas de un documento como órdenes del propietario.

## Interrupciones
Primera versión: half-duplex —PTT o wake, escuchar y luego responder— con cancelación inmediata. Después: barge-in con eco cancelado/VAD y prueba con altavoces físicos, no solo auriculares. Interrumpir cancela reproducción de respuesta y, según tipo, la generación textual; no revierte automáticamente una acción ya completada. Una tarea de grabación solo se detiene con orden válida que la identifique.

## Lector progresivo
Fuentes: texto del chat, nota, documento importado, selección externa capturada explícitamente o página autorizada por extensión. Conservar título/origen, separar texto de instrucciones y limitar longitud. HTML se extrae como texto sanitizado; no se ejecutan scripts del documento.

El widget muestra fragmento actual, progreso por fragmentos y controles de pausa/continuación/atrás/adelante. Boundary events pueden variar entre motores TTS; mostrar fragmento si no hay tiempos de palabra precisos, sin inventarlos. Al cambiar voz/velocidad conservar índice y permitir repetir el fragmento. Cerrar el widget recoge la vista, pero mantiene indicador de lectura y un Stop accesible.

## Medición de release
Registrar al menos frases de varios acentos, ruido, música, TV y silencio; tasa de activaciones falsas por hora, porcentaje de invocaciones reconocidas, latencia wake→escucha y escucha→primer resultado, CPU en reposo y recursos liberados tras mute/salir. Los objetivos se fijan antes de la evaluación y los resultados se reportan, no se remplazan por una demostración grabada.


---

# 12 · Inteligencia, herramientas y memoria

## Orquestación
Conservar el chat mínimo. Un router clasifica primero comandos locales de gramática acotada; los cálculos, timers y navegación no requieren LLM. Preguntas abiertas usan el proveedor conectado. Un comando ambiguo se confirma antes de tener efectos externos. El router nunca identifica "contiene 9" como instrucción de iniciar una cuenta.

El `LLMGateway` nativo mantiene configuración, contexto, rate limits, cancelación y estado del proveedor. Ningún token de acceso vive dentro de Axx.html. El renderer recibe estados/respuestas, no credenciales. Streaming textual se muestra como tal; si falla a mitad, el texto parcial se etiqueta y no se presenta como respuesta completa.

## Proveedores
**Local:** adaptador Ollama usando API oficial cuando el usuario ya tiene un servicio/modelo instalado. Detectar modelos del servidor autorizado, no inventar nombres ni garantizar que el portátil ejecute modelos grandes. En loopback por defecto; una IP de LAN exige configuración/seguridad explícitas [S39].
**Nube:** proveedor configurado con coste y envío de contenido visibles. OpenAI API y suscripción ChatGPT no son un presupuesto automáticamente intercambiable. Codex tiene su propia autenticación de producto: no copiar tokens de Codex/OpenCode para dar por autorizado a Axx ni inventar un OAuth genérico de ChatGPT [S36,S38].
**Voz en tiempo real:** adaptador opcional con credenciales en runtime o tokens efímeros conforme al proveedor. Evaluar coste, latencia y políticas de retención. No habilitarlo solo porque hay un botón de micrófono [S37].

## Routing y límites
Config por proveedor: capabilities, endpoint autorizado, modelo real, timeout, límite de contexto y presupuesto. Para reintento, backoff con jitter y Retry-After; no reenviar una herramienta con efecto externo como si fuera una pregunta idempotente. Failover solo entre proveedores aprobados y mostrando cambios de privacidad/coste. No rotar cuentas para evadir límites.

En un portátil 16 GB: limitar concurrencia de ASR/modelo/render; el LLM remoto puede ser preferible para tareas pesadas, pero no se activa sin permiso. Un modelo local pequeño para comandos no reemplaza el validador determinista.

## Herramientas
El modelo produce una propuesta tipada con capacidad y argumentos. PermissionBroker valida; puede requerir confirmación. Resultados incluyen hechos y errores concretos. Texto de un archivo, web o email se delimita como contenido no confiable; no puede autoemitir un permiso. El resultado del modelo no se concatena en PowerShell, cmd, SQL o rutas de ejecutables.

## Memoria útil
Preferencias explícitas en SettingsStore; notas y tareas en base; conversaciones guardadas solo según opción elegida. Memoria procedimental opcional almacena una receta tipada con precondiciones, versión del adaptador, pasos y evidencia de éxito. Reutilizarla exige revalidar permisos y destino; una receta no almacena coordenadas de pantalla como verdad universal ni secretos.

Una receta se promueve después de varias ejecuciones satisfactorias definidas y se desactiva tras fallos. Mejoras se prueban en sandbox/fixture; no autoedita el programa de producción ni elimina confirmaciones. El coste/latencia de cada ejecución se registra sin contenido sensible por defecto.

## Privacidad de contexto
No adjuntar notas, pantalla, audio o historial completo porque un proveedor se conectó. Mostrar archivos y fragmentos añadidos al mensaje. Límites por tamaño/tokens; rechazar rutas fuera de autorización. Retirar un adjunto antes de enviar realmente lo elimina de esa solicitud. Una respuesta de traducción o investigación no se da por verificada solo por ser plausible.

## Prueba de aceptación
Conectar proveedor real elegido, hacer una pregunta y una segunda que dependa de la primera, cancelar streaming, desconectar, recibir 429, sobrepasar límite, ejecutar timer local sin conexión, intentar una herramienta no permitida y comprobar rechazo. Registrar endpoint/modelo/versión sin secretos; mock verde no sustituye esta prueba.


---

# 13 · Música, YouTube, Spotify y lo que suena en Windows

## Mantener la experiencia aprobada
Fuentes como botones independientes alrededor: archivos, sesiones de Windows, YouTube, Spotify y pestañas autorizadas. El cuerpo opera la fuente seleccionada y los controles inferiores permiten anterior/siguiente cuando exista esa capacidad. Cambiar de panel no reinicia un archivo ni crea otro audio. Dimensiones/preferencias no dependen del proveedor.

## Dos canales distintos
**Canal de control:** reproducción, pausa, posición, pista, aplicación y métodos soportados. **Canal de señal:** muestras de audio autorizadas para amplitud/espectro. Una API puede controlar música sin entregar PCM. Oír algo por loopback no da autoridad para pausarlo. Nunca animar un espectro inventado porque llegó el título de una canción.

## Fuentes
| Fuente | Control | Señal/reactividad | Estado de implementación |
|---|---|---|---|
| Archivos | Reutilizar reproductor local o servicio único | Audio real, espectro actual | Base conservada; validar producción. |
| Windows | GSMTC sesiones compatibles | WASAPI loopback autorizado separado | Adaptador nuevo [S16,S18]. |
| Pestañas | Extensión autorizada, HTML media | Captura permitida separada | Evolucionar extensión existente. |
| YouTube integrado | IFrame API oficial visible | API no entrega PCM | Conservar límites del reproductor [S35]. |
| Spotify | Web API/OAuth y dispositivo soportado | No analizar contenido por esa integración | Revisar elegibilidad/política antes de activar [S31–S34]. |

## Windows MediaSessionBroker
Enumerar sesiones GSMTC y mostrar aplicación/título que realmente entregue Windows. Permitir seleccionar destino estable; una sesión desaparecida invalida los controles. `TryPlayAsync`/`TryPauseAsync` o capacidades equivalentes se comprueban por estado y resultado; no todas las apps publican sesiones o siguiente/seek. No enviar una tecla multimedia global esperando que llegue a una app concreta. Esa tecla puede ser fallback manual identificado, nunca equivalente silencioso a control dirigido.

Solicitudes con generation y timeout; una consulta antigua no debe reemplazar la selección nueva. Estado remoto stale se muestra y deshabilita acciones no confirmables. El cuerpo no muestra Pausado antes de confirmar el estado recibido o un resultado válido de la sesión.

## Reactividad
Captura de audio local de archivo y loopback usan rutas separadas. Seleccionar mezcla de sistema puede incluir varias apps; indicarlo. Captura por proceso es una mejora condicionada a las API/versión Windows comprobadas, no un aislamiento ficticio. No abrir micrófono como sustituto silencioso de loopback.

Graves, medios y agudos alimentan envolventes medidas; normalización y ataque/liberación acotados. Silencio permanece cero, mute y pausa detienen reacción. No se llama al LLM por fotograma. La posición del control no vibra: solo materia/aureola, preservando hit target y legibilidad. Reproducción local, análisis y control comparten una sola sesión de audio por fuente.

## Spotify
PKCE, Client ID público, redirect exacto, state/correlación de uso único, scopes mínimos. Tokens en SecretStore, no HTML/localStorage/logs. El API puede exigir tipo de cuenta, cuotas y acceso de desarrollador; verificar condiciones vigentes y aprobación antes de distribuir. La política de Spotify contiene restricciones sobre asistentes de voz, contenido y sincronización visual. No anunciar integración comercial aprobada ni audio-reactividad de Spotify por defecto [S31–S34].

Callback loopback existente puede mantenerse como adaptador de transición con puerto/origin permitidos. No aceptar callbacks sin correlación de sesión ni abrir el servidor en 0.0.0.0. Cerrar sesión invalida peticiones/estado y limpia secretos locales; revocar el consentimiento en Spotify es operación distinta.

## YouTube
Reproductor oficial visible, tamaño utilizable, controles permitidos y errores de embedding. No extraer audio/descargar contenido ni ocultar vídeo para convertirlo en música de fondo. La regla existente de pausar iframe al ocultarlo se mantiene hasta validar diseño/políticas. Controlar una pestaña autorizada es otro adaptador, no demuestra permiso para todas las páginas [S35].

## Pruebas
Dos reproductores simultáneos y selección explícita; siguiente no soportado; sesión desaparecida; Seek remoto; rate limit; dispositivo desconectado; vídeo que prohíbe embedding; permisos extensión retirados; reproducción local mientras cambia panel; señal cero al pausar; Spotify real solo con autorización del usuario. Probar fuentes físicas, no sólo respuestas controladas.


---

# 14 · Captura de pantalla, halo y grabaciones recuperables

## De recorder web a servicio nativo
El prototipo ya tiene MediaRecorder y UI útil. Producción necesita captura/encoding/guardado independientes del WebView y un halo fuera de la página. Windows Graphics Capture es una vía oficial para seleccionar ventana o monitor; su soporte y recursos D3D del sistema se comprueban. Esto no impone una GPU dedicada al avatar, pero tampoco significa que toda la captura de Windows opere sin infraestructura gráfica del sistema [S14].

## Máquina de sesión
`idle → selecting → preparing → countdown → recording ↔ paused → stopping → finalizing → saved/recoverable/error`.

Un único taskId y un único dueño de las pistas/encoder. Tocar Axx solicita inicio o pausa/reanuda; Finalizar tiene acción independiente siempre accesible. Cancelar selección invalida toda concesión tardía. Cambiar de herramienta no corta la captura. Cerrar app solicita finalizar si hay sesión; no borra silenciosamente lo grabado.

Pausar mantiene fuente compartida pero excluye el intervalo del contenido y reloj activo. Timestamps de video/audio se rebasan a la misma línea temporal. No contar chunks para estimar duración. Una pausa no genera otro archivo final ni reinicia contador.

## Fuente y opciones
Selector de monitor/ventana; pestañas vía navegador cuando corresponda. Preflight informa tamaño real, FPS negociados, capacidad de audio y permisos. Resolución/FPS son solicitudes, no garantías. Presets iniciales 1080p30 y otras opciones tras benchmark; no anunciar 4K60 como resultado del portátil sin medir. Cursor y exclusión del propio Axx solo si la API/estrategia real lo soporta.

Audio fuente y micrófono son opciones separadas; mezcla en servicio de audio con timestamps y nivel. No reproducir micrófono por altavoces. Opcional webcam es fase posterior con consentimiento, preview y sincronización, no un toggle vacío.

## Halo nativo
Una ventana transparente decorativa por monitor elegido; no activa foco ni recibe clics. Usa la tabla/paleta del material de Axx con cinta cromática alrededor del área física del monitor, convertida correctamente desde DPI. Estados: movimiento al grabar; atenuado/quieto en pausa; indicador estático de preparación; desaparece al terminar. Mantener indicador de captura textual y Stop, incluso si el halo está desactivado.

No usar rojo para estado "listo" como si ya grabara. El preview del halo se marca MUESTRA y no adquiere la pantalla. `WDA_EXCLUDEFROMCAPTURE` se solicita en ventanas propias cuando el sistema lo admita, pero Microsoft no lo presenta como protección de seguridad universal. Validar si el método concreto lo excluye; si falla, avisar que Axx/halo pueden aparecer en el vídeo [S15]. No afirmar exclusión de ventanas ajenas.

## Guardado durable: diseño propuesto
La mejora prioritaria es no mantener todo el vídeo en RAM. Implementar segmentos independientes de aproximadamente 10 segundos con keyframe inicial y contenedor finalizable, en una carpeta de sesión autorizada. Encoder y muxer se fijan tras prueba con Media Foundation; Sink Writer ofrece la ruta de escritura, pero un MP4 sin finalizar no se considera recuperable por existir bytes [S17].

Carpeta `.axxrec-<id>` contiene `manifest.json`, `segment-0001.mp4`, etc. Escribir segmento temporal, finalizarlo y confirmar tamaño/hash; renombrar a definitivo; actualizar manifiesto por archivo temporal + replace atómico. Guardar duraciones/timestamps reales, parámetros codec, muestras de audio y discontinuidades. Un crash puede perder el segmento abierto, no los ya finalizados. No prometer pérdida cero.

Finalización: verificar todos los segmentos, remultiplexar en un archivo temporal único con timestamps continuos y misma configuración; cerrar; reproducir/verificar metadatos mínimos; renombrar final. Conservar segmentos hasta comprobar resultado. Si el remux nativo no está implementado, entregar recuperación por segmentos y marcar exportación unificada pendiente, no concatenar MP4 con bytes.

FFmpeg puede ser un helper opcional de remux cuando se decide explícitamente, se fija el binario/hash/licencia y se valida distribución. No asumir que cualquier build descargado tiene igual licencia ni ejecutar shell concatenando la ruta del usuario [S40].

## Espacio, nombres y fallos
Destino elegido con diálogo nativo; grant de raíz verificado. No sobrescribir por defecto: nombre saneado + fecha + ID. Preflight comprueba escritura con temporal y espacio orientativo, y vigila espacio durante captura. Volumen extraíble perdido/disco lleno: finalizar lo posible, marcar sesión recuperable, conservar segmentos y mostrar ruta. No declarar guardado antes de cerrar/confirmar.

Colas de frames/audio acotadas. Ante encoder lento, mostrar diagnóstico y detener de forma recuperable si no se sostiene; no bajar calidad secretamente. Registro de frames omitidos/errores de audio; una demo sin sonido no valida mezcla.

## Utilidades que sí aportan
Cuenta previa 0/3/5/10 s; nombre/proyecto; marcas temporales exportables; fotograma PNG desde frame autorizado; pausa/seguir por cuerpo; límite de tiempo; biblioteca de sesiones locales con estado guardado/recuperable; abrir carpeta; reintentar exportación; limpieza explícita después de validar. El historial no contiene capturas de otras apps no autorizadas.

## Aceptación física
Grabar monitor y ventana reales, 15 minutos con pausas; confirmar duración excluyendo pausas y sincronización voz/video; abrir el archivo en dos reproductores; cambiar DPI/monitor; revocar fuente; simular espacio bajo; matar proceso durante segmento y recuperar anteriores; probar exclusión halo; reintentar guardado sin duplicar. Web Canvas de test se mantiene para unitarios, no sustituye esta puerta.


---

# 15 · Tiempo, notas, archivos y acciones cotidianas

## Temporizador nativo
Un servicio mantiene TimerTask, independiente de ventanas y animaciones. Usar reloj monotónico para duración activa y wall clock para restauración/horario. No restar uno por cada callback: el scheduler puede retrasarse. Al despertar/suspender o cambiar hora de Windows, reconciliar explícitamente la política, no fabricar minutos de actividad.

Configurar duración de 1 s a 24 h. Vacío, cero, NaN o infinito son errores claros. Iniciar después de una cuenta completada utiliza la configuración actual, no el objeto viejo. Ajustar +15 s/+1 min/+5 min conserva taskId y pausa; reducir no resucita una tarea vencida. Finalización se emite una vez por ID.

La geometría numérica se calcula desde `ceil(remainingMs/1000)` dentro de 1–9 s, no desde un contador de animación. Durante pausa se congela; cancelación/restauración recupera apariencia. Si actionMorph está desactivado, el texto de estado comunica el tiempo sin reemplazar la figura.

## Intervalos de trabajo
Secuencia finita validada de trabajo/descanso. Preferencia por avance manual; automático explícito. No agregar descanso después de última ronda. Si Axx está cerrado o suspendido, no registrar ciclos completos como trabajo real. Historial distingue completado, cancelado y vencido fuera de ejecución; etiquetas y favoritos persisten.

## Cronómetro
Tiempo activo monotónico acumulado, vueltas con número y timestamp, pausa/continuación y CSV. Reiniciar pide confirmación si hay vueltas no exportadas. Cronómetro y temporizador pueden coexistir; el cuerpo controla solo la actividad seleccionada y su etiqueta debe indicarlo.

## Notas, pendientes y texto
Conservar editores existentes y drafts. Autosave transaccional con estado visible, títulos editables, búsqueda y exportación. Cancelar un panel no elimina contenido. Taller de texto mantiene transformaciones locales deterministas y undo; no se presenta ordenación de líneas como redacción por IA. Herramientas de imágenes conservan dimensiones/formato y procesan solo archivos elegidos, sin subirlos automáticamente.

## Búsqueda local de archivos
El usuario autoriza raíces. Indexación de metadatos inicialmente, no todo el contenido del disco. Canonicalizar y comprobar raíz después de resolver enlaces/reparse points; proteger contra rutas fuera del grant. Búsqueda por nombre/extensión/fecha devuelve referencias opacas, no comandos. Cambios del sistema invalidan referencias antiguas.

Resultados homónimos requieren elección; no abrir arbitrariamente "el presupuesto" si hay varios. El icono transportado por Morph Reach representa esa referencia real. Abrir utiliza un backend permitido por asociación o destino, informa solicitud aceptada y solo declara ventana verificada si efectivamente se comprobó.

## Aplicaciones
Catálogo desde fuentes permitidas de Windows, acceso directo y appId; validar firma/ruta cuando sea relevante. El modelo no aporta una línea cmd. Parámetros admitidos son de esquemas acotados por app. No resolver un nombre a un ejecutable descargado de Internet automáticamente. Revocación inmediata y evidencia de acciones sin secretos.

## Notificaciones y sesiones
Una finalización produce como máximo un evento sonoro principal. Los avisos no roban foco ni cambian una nota en edición. Silencio global afecta voz/efectos según política explícita; silencio de efectos no apaga el micrófono. Agrupar avisos al volver, no lanzar 20 animaciones atrasadas.

## Reacciones útiles
Aparcar: recoger superficies y no mostrar herramientas. Campo seleccionado: breve indicación del destino, no tentáculo continuo. Conflicto de inserción: materia se detiene y mantiene borrador. Tarea completada: señal breve; permanece el resultado. Error de red: estado discreto y reintento, no deformación interminable fingiendo trabajo. Todas son proyecciones del mismo evento de tarea.


---

# 16 · Extensión de navegador y Native Messaging

## Por qué existe
Un HTML de Axx no puede inspeccionar ni editar arbitrariamente otras pestañas. La extensión añade acceso a destinos autorizados y control de medios compatibles; no es un navegador completo ni necesita leer cookies/historial para estas funciones. Se mantiene el alcance mínimo [S21–S23].

## Arquitectura propuesta
Extension MV3 → Native Messaging host instalado por usuario → named pipe con ACL de ese usuario → runtime Axx. El host solo traduce framing y valida origen/tamaño, no ejecuta herramientas por sí mismo. La UI web del prototipo usaba un puente loopback; esa ruta puede continuar en desarrollo, pero no se añade un servidor expuesto en LAN.

`allowed_origins` del manifiesto contiene los IDs reales de las extensiones Chrome/Edge aprobadas. Se registran rutas reales de host en las claves de NativeMessagingHosts que documenta cada navegador, mediante instalador/desinstalador. No fijar IDs ficticios en código ni usar comodín. Una build de desarrollo sin ID estable debe registrar el ID que realmente generó ese perfil, mediante acción explícita.

## Mensajes
Framing oficial: longitud y JSON, respetando límites del protocolo; no escribir logs en stdout, que está reservado a mensajes. Axx fija máximo conservador 256 KiB por mensaje, texto segmentado con correlación y timeout. Nada de transferir PCM/vídeo crudo masivo por Native Messaging. Host valida schema, sesiones y grants; un `origin` declarado en payload no se considera prueba de procedencia.

## Permisos
`activeTab` tras gesto, `scripting` cuando se requiera y nativeMessaging para host. Los permisos de sitio amplios son opcionales y solo cuando una función lo requiera. El usuario puede ver y revocar sitios/destinos. Navegar a otro origen, cerrar tab, recargar frame o cambiar editor invalida TargetLease. Incógnito desactivado inicialmente.

## Adaptador DOM
Input/textarea de texto, no passwords/tokens/autocomplete sensible. Contenteditable requiere resolver selección y contexto del editor, no reemplazar `innerHTML`. Utilizar setters/eventos compatibles y comprobar el valor final, sin enviar formulario. El capturador de destino no ejecuta texto de la página ni transfiere todo el DOM. Guardar IDs por sesión, no selectores CSS frágiles como permiso permanente.

## Medios
Enumerar HTMLAudioElement/HTMLVideoElement en documento autorizado y shadow roots abiertas; anunciar capacidades reales. Marcos de otro origen requieren permisos separados, no un error ignorado. No saltar anuncios ni restricciones DRM. Selección de un elemento permite operaciones admitidas, no scraping general.

## Lectura de página
El usuario selecciona pestaña/fragmento. Extraer texto legible y título/origen, con límite y filtro de controles de contraseña/edición sensibles. Presentar contenido como datos no confiables para el LLM. Páginas autenticadas no se leen automáticamente por estar abiertas.

## Pruebas de aceptación
Instalar extensión realmente, observar service worker y host; ping real; autorizar/revocar tab; navegar otro origen; escribir con selección parcial; sitio que cancela beforeinput; editor de framework; audio real play/pause; host caído; tamaño excesivo; ID no permitido; mensaje inválido. Ejecutar scripts de contenido en un documento artificial solo prueba lógica, no instalación o aislamiento real.


---

# 17 · Seguridad, consentimiento y límites operativos

## Modelo de amenazas práctico
Axx puede recibir texto, audio y archivos de fuentes externas y tiene capacidades de escritorio. El riesgo principal es convertir contenido no confiable en acciones, permitir que una página remota use el puente local o escribir en un destino distinto al que el usuario eligió. El objetivo no es bloquear herramientas útiles, sino que actúen con la autoridad correcta.

| Entrada | Riesgo | Control |
|---|---|---|
| Respuesta LLM/web/PDF | Instrucciones maliciosas | Datos delimitados; dispatcher/grants fuera del modelo. |
| RPC navegador | Página extraña invoca localhost | Origin real, token de sesión, allowlist, métodos acotados. |
| Extensión | ID/sitio no autorizado | allowed_origins real, Native Messaging, grants por destino. |
| Ruta de archivo | Traversal/reparse/otro volumen | Canonicalizar, raíz autorizada, validar tras resolución. |
| Destino de escritura | Foco cambia | TargetLease y revalidación inmediatamente antes de commit. |
| Audio externo | Wake/orden falsa | Wake no autentica; confirmación sensible y política de contexto. |
| Actualización | Binario manipulado | Firma updater y firma Windows; claves fuera del cliente. |

## Permisos de Tauri
Una capability se aplica a ventanas concretas; no conceder plugin de shell amplio al renderer. No configurar URLs remotas como contenido privilegiado. CSP controla scripts/connect/frame fuentes necesarias; no `unsafe-eval` para resolver bugs. Las APIs de IPC no aceptan funciones JavaScript ni rutas sin validar [S02].

La UI presenta capacidades, pero el runtime decide. Un botón oculto no es control de acceso. Interacciones de pruebas o simulaciones no generan grants. El usuario puede revocar micrófono/captura/sitio/carpeta sin perder sus notas.

## Secretos
DPAPI por usuario o almacén de credenciales. No archivos .env distribuidos con valores, no tokens en localStorage, no logs con Authorization, no audio en reportes de fallos por defecto. Las plantillas contienen referencias vacías a secretos, no credenciales de ejemplo plausibles. No copiar credenciales desde otras aplicaciones.

## Procesos y red
Sin administrador por defecto. Servicios solo mientras Axx vive, no un servicio Windows oculto. Workers limitados a directorios temporales y canales definidos. Binarios/modelos se verifican con hash y licencia antes de ejecutar. No descargar y ejecutar código sugerido por un LLM. Acceso remoto a homelab es módulo posterior con autenticación; loopback no debe cambiarse a `0.0.0.0` por comodidad.

## Información persistida
Preferencias y metadatos operativos mínimos. Texto de dictado/transcripciones permanece en sesión salvo guardado explícito. Historial de inserción persiste metadatos por defecto, no contenido de otras apps. Support bundle pide consentimiento, enseña qué incluye y permite redactar rutas/nombres. Nunca incluir capturas de pantalla silenciosas para generar reflejos.

## Estados que exigen aprobación
Instalar dependencias, descargar modelos, activar escucha, capturar pantalla, abrir destinos nuevos, autorizar raíces, enviar mensajes, reemplazar texto externo y ejecutar apps no autorizadas. Operaciones repetidas dentro del mismo grant pueden ser rápidas; el grant es limitado y revocable. "Hey Axx" o reconocer una voz no sustituyen aprobación.

## Errores seguros
Fallo de permisos deja teclado/local tools disponibles. Disco lleno conserva capturas recuperables. Revocación interrumpe solo la capacidad correspondiente. Un fallo del renderer no elimina datos ni cancela tareas legítimas; existe stop visible alternativo. No ocultar un micrófono encendido porque se cerró el panel.

## Auditoría
Eventos con commandId/taskId, tipo, capability, estado, latencia y error; sin contenido sensible. Rotación por tamaño/días con defaults editables. Una acción sensible se puede rastrear hasta aprobación y parámetros hash. Evidencia no equivale a telemetría enviada: envío remoto desactivado inicialmente.


---

# 18 · Estrategia de pruebas y puertas de calidad

## Cuatro clases de evidencia
**U:** pruebas puras de tipos/lógica, reloj, identidad, payloads y coordenadas.
**I:** integración real de componentes locales, SQLite/HTTP/archivo/encoder.
**P:** Windows físico: foco, monitor, permisos, micrófono, grabación y apps.
**E:** servicios externos autorizados: IA, Spotify, YouTube y extensión instalada.

Una prueba con fuente Canvas es I de codificación, no P de captura. ASR con resultados fijos prueba contrato, no calidad lingüística. `page.set_content` y Map localStorage no prueban navegación ni persistencia real. Todas las evidencias tienen clase, versión/commit, entorno y comandos.

## Baseline M0
Extraer ZIP original, comprobar hash, compilar y ejecutar suite. Guardar las salidas completas y el código de salida; no contar tests históricos como nuevos. Las 268 pruebas de Axx20 son referencia esperada, no resultado obligatorio de una versión posterior. No borrar pruebas que revelan fallos sin documentar cambio de requisito.

## Pruebas automáticas a añadir
- Identity: guardar/preview/descartar/revisión obsoleta/reiniciar; estado no cambia forma.
- Input: doble A450ms, autorepeat, jitter7px, Escape no secuestra otras apps.
- Windows: DPI/monitores negativos, bounds deseado vs visible, target mask frame.
- Command: expiry, rechazo de origen, doble idempotency key, aprobación hash distinto.
- Timer: duración nueva tras terminado, ajustes en pausa, suspensión, reloj del sistema alterado, rutinas finitas.
- Dictation: parciales, finales duplicados, FIFO traducción, destino cambiado, error motor, antes de Enviar, undo tras edición.
- Capture: audio/video timestamp, pause rebase, fuente revocada, storage full, crash por segmento, saved solo tras close.
- Music: fuente stale, estado remoto tarde, silencio, no duplicar reproductor, capacidades no admitidas.
- Extension: framing, grants revocados, input sensible, host caído.

## Prueba end-to-end física canónica
Arrancar Axx instalado; abrir Bloc de notas; guardar forma/cámara/tamaño; invocar desde allí, mover, desplegar órbita y aparcar; cerrar/reabrir y comprobar identidad; dictar a selección parcial sin envío; traducir con motor real; pausar música de sesión Windows; iniciar timer y cambiar herramienta; grabar ventana con voz, pausar, continuar, finalizar en carpeta; reproducir resultado; detener escucha; salir y comprobar procesos/recursos liberados.

No ejecutar todo por primera vez al final del proyecto. Cada módulo se prueba con los anteriores activados para encontrar interferencias de foco, audio y reloj.

## Rendimiento a calidad constante
Benchmark de 30 min y un caso adverso de 2 h antes de release. Escenarios: avatar solo, dos paneles, música, dictado, grabación, pantalla con alta escala y cambio entre apps. Registrar CPU por proceso, working set/commit, frame p50/p95/p99, tareas largas, ASR latency, captura dropped frames y crecimiento de memoria. Usar Windows Performance Recorder/Profiler o medición explícita propia; no prometer datos no medidos.

Comparaciones mantienen malla/LUT/resolución/pose. Las pruebas funcionales pueden aislar renderer, pero entonces no se anuncian como rendimiento. Incluir al menos una captura/lote con renderer real y efectos activos.

## Matriz de entorno
Windows11 x64, GPU integrada, 16 GB; un monitor y dos monitores; escalas100/125/150/200%; resolución1366×768 y1920×1080 cuando disponibles; auriculares y altavoces; Edge/Chrome reales para extensión; usuario estándar; app objetivo elevada como caso de rechazo; sin Internet; permisos denegados; disco casi lleno; suspensión/reanudación.

## Gate de entrega
M0: base reproducible.
M1: presencia/atajos/input/foco físicos.
M2: preferencias durables e identidad.
M3: comandos/voz externa en destinos anunciados.
M4: multimedia y captura física durable.
M5: 30min/2h sin bloqueos, rollback, instalador y privacidad.

Un fallo P0 no se compensa con cien tests U verdes. Se pueden distribuir funciones beta desactivadas, no anunciar como finalizadas. El soporte debe señalar qué gates no han pasado.

## Informe
Usar `config/evidence.template.json` y `tools/verify_packet.py`. Este verificador comprueba el expediente, no el runtime nativo. Para aplicación: logs, capturas propias consentidas, vídeo de prueba no sensible, test report, hashes y una descripción exacta de sustituciones/mocks.


---

# 19 · Compilación, instalador, actualización y rollback

## Release no es solo npx tauri build
La build release contiene frontend compilado, host Rust, binarios auxiliares permitidos y manifiestos de modelos; no node_modules, fixtures, .env con secretos ni pruebas que registren audio. Una build que abre una ventana no confirma los contratos de escritorio.

## Versionado
Separar versión de producto, contrato IPC, esquema de datos y artefactos de modelo. Registrar commit y toolchain. Cargo.lock/package-lock versionados, modelos/binarios con hashes; no descargar `latest` en el primer arranque. La base visual Axx20 queda como referencia, no como una nueva numeración del contrato cada vez que cambia CSS.

## Instalador por usuario
NSIS mediante Tauri como objetivo inicial. Verificar rutas reales emitidas por el build. Crear acceso Inicio y desinstalador, registro de Native Messaging solo si el componente se instala y con consentimiento correspondiente. Inicio con Windows es opción desactivada inicialmente. No requerir administrador sin razón. Instalar WebView2 según estrategia documentada y soportar instalador offline si se decide [S07].

## Firma
Firma Authenticode del ejecutable/instalador con certificado del propietario; firma del bundle de actualización de Tauri con clave independiente. El actualizador exige validar la firma; no desactivarla para evitar un error [S08]. Claves privadas en almacén de secretos del proceso de publicación, nunca repo/prompt/ZIP. La firma no garantiza automáticamente reputación inmediata ni elimina toda alerta de SmartScreen.

## Modelos de voz
No incluir pesos sin licencia/notice ni prometer una descarga de tamaño desconocido. Un descargador autorizado verifica checksum antes de activar, reanuda temporalmente de forma segura y permite borrar modelos. La cancelación no deja modelo corrupto anunciado como disponible. Versionar modelos separados del instalador cuando facilite actualizaciones y tamaño.

## Actualización
Comprobar versión y compatibilidad de esquema/contrato; no instalar mientras se graba ni se está escribiendo una transacción de inserción. Ofrecer posponer, finalizar/guardar y luego actualizar. Backup coherente antes de migración. Actualización puede pedir nueva autorización si amplía capacidades, no heredar permisos silenciosamente.

## Rollback
Conservar build anterior y backup compatible. Si el esquema cambió sin reversión segura, la versión anterior no abre la base nueva en escritura. Restaurar snapshot aprobado o usar migración inversa probada. Conservar grabaciones externas y no borrar archivos del usuario al volver de versión.

## Desinstalación
Detener procesos propios, desregistrar host/atajos/autostart, retirar binarios, ofrecer conservar o eliminar datos. No eliminar la carpeta general de vídeos del usuario ni otras apps. Revocar tokens locales; revocación de acceso en servicios externos queda explicada como acción separada.

## Checklist de publicación
Instalación en usuario nuevo; primer arranque offline; permisos de mic/captura; startup opt-in; actualización desde versión anterior con notas y estilos; captura activa pospone update; rollback con SQLite; desinstalar conserva vídeos; escaneo de secretos/licencias; verificación de firma; smoke físico. Cada check deja evidencia, no solo una casilla verde manual.


---

# 20 · Operación, soporte y diagnóstico

## Diagnóstico opcional
Panel oculto por defecto: versión/commit, backend visual, tiempos de frame, tareas activas, mic/captura, proveedor y estado, base de datos/revisión, monitor/DPI, grants activos y errores recientes. No mostrar llaves ni transcripciones en el diagnóstico.

## Runbooks
| Síntoma | Inspección primero | Recuperación permitida |
|---|---|---|
| Forma cambia sola | savedRevision, preview, actionMorph, keepForm | Descartar preview o corregir proyección; nunca reset general. |
| Tamaño no se conserva | desired vs presentation bounds, escritura DB | Reintentar commit; no guardar caja móvil sobre escritorio. |
| Atajo no responde | registro/colisión, instancia principal, teclas físicas | Reasignar y desregistrar duplicados; no reiniciar tareas. |
| Clics bloqueados | regiones activas, frameId, ventanas transparentes | Desactivar proxy conflictivo, control accesible; no overlay pantalla completa. |
| Dicta en sitio incorrecto | TargetLease/foreground/selection | Cancelar inserción, conservar borrador, pedir nuevo destino. |
| No transcribe | permiso, dispositivo, ASR/modelo, frames | Ver error específico; teclado disponible. |
| Escucha su propia voz | rutas mic/TTS/loopback | Half-duplex y revisar eco; no volumen inventado. |
| Captura sin sonido | audio real en stream/ruteo/dispositivo | Aviso y fuente correcta; no activar mic de respaldo oculto. |
| Vídeo no guarda | close/finalize, espacio, ruta/grant | Conservar segmentos, exportar a otra carpeta. |
| Se traba al animar | p95 raster/GC/IPC/audio concurrencia | Cache/worker/colas; no reducir calidad sin autorización. |

## Recuperación sin perder identidad
Primer nivel reinicia la vista desde snapshot. Segundo reinicia el worker afectado. Tercero propone reinicio de app cuando no hay operaciones pendientes, preservando datos. No usar "restablecer todo" como primer arreglo; backup y lista exacta de qué se borrará.

## Indicadores persistentes
Micrófono activo y captura activa mantienen stop accesible incluso al recoger paneles. Pantalla bloqueada debe seguir la política explícita: detener dictado/wake o pausar suscripciones según elección segura; captura no se anuncia detenida hasta evento confirmado. Salir libera handles; cerrar un panel no significa salir.

## Datos de soporte
Bundle opt-in: logs redactados, versiones, capacidades, contadores, configuración sin secretos, informes de fallo. No incluir audio, capturas o texto del usuario por defecto. Preview del contenido antes de exportar. Archivo con hash/fecha; no subida automática.

## Controles operativos recomendados
Pausar escucha; detener captura; recoger todo; volver a base; exportar datos; administrar permisos; reiniciar worker ASR; pruebas de sonido; diagnóstico. Ninguno debe llenar el chat principal de opciones permanentes. Integrarlos en menú contextual o ajustes.


---

# 21 · Entregas y definición de producto terminado

## M0 · Base y entorno
Inventario, hashes, build reproducible, exportación de preferencias, lockfiles, pruebas heredadas y mapa de interfaces. No cambia visuales. Evidencia: informe de máquina, logs y capturas canónicas.

## M1 · Axx Desktop utilizable
Shell Tauri real, instancia única, bandeja, ventanas, atajos globales, selección de input y paneles. Primer recorrido: abrir desde otra app, llamar/devolver, timer local y chat. No se considera completo con una ventana rectangular web que bloquea clics.

## M2 · Persistencia y fidelidad
SQLite canónico, importación, reinicio real, preset/size/camera y optimización a calidad constante. Axx no se vuelve otra figura ni aparece Herramientas al aparcar. Primer release interno para evaluar escritorio real.

## M3 · Trabajo por voz
AudioRuntime, ASR autorizado, dictado y traducción, lector y al menos destinos externos declarados/validados. Mic/ondas reales, conflictos y no envío. No prometer compatibilidad universal; publicar matriz.

## M4 · Multimedia y captura
Sesiones Windows y extensión instaladas, captura con halo físico, folder real, segmentos recuperables, timers durables. Conservar API proveedores como integraciones condicionadas y probar cada cuenta antes de anunciarla.

## M5 · Distribución controlada
Instalador firmado, update/rollback, 30min y 2h de carga, accesibilidad, privacidad y soporte. Las funciones no listas aparecen desactivadas con motivo. Medir latencias/consumo en el portátil indicado.

## M6 · Manos libres y expansión
Hey Axx con evaluación de detector y licencias, barge-in, mejoras artísticas de unión de brazos, nuevas formas, voz bidireccional y móvil en iniciativas separadas. El proyecto no se queda eternamente en M1 esperando completar todas las ideas futuras.

## No se aceptan como entrega final
Otra lámina de imagen; nuevos botones que solo muestran alert; un HTML renombrado exe; un resultado de ASR hardcoded; un permiso inventado; un contador de tests sin logs; FPS calculados con render detenido; un archivo de vídeo que no se reproduce; o "funciona en Windows" tras test Linux de protocolo.

## Qué recibe el propietario en cada milestone
Build identificada, instrucciones concretas, código, diff/commits, limitaciones actuales, pruebas, captura de interfaz y una lista de acciones que requieren su permiso. El propietario aprueba cambios de identidad, coste, permisos o distribución; el agente no debe pedir otra vez información ya documentada ni convertir cada archivo en una nueva consulta.


---

# 22 · Trabajo con Codex, Antigravity u otro agente con acceso al repositorio

## Un coordinador, contratos compartidos
El coordinador lee AGENTS y el plan, registra decisiones y asigna tareas con alcance concreto. La paralelización solo después de fijar contratos; renderer y persistencia no escriben simultáneamente el mismo archivo de preferencias. Cada agente trabaja en su rama o copia aislada. No delegar una tarea y afirmar que pasó sin inspeccionar diff y ejecutar pruebas.

## Especialidades
| Rol | Propiedad principal | No puede decidir por su cuenta |
|---|---|---|
| Integración | montaje, puertos y secuencia | Rediseñar identidad o ampliar permisos. |
| Windows | ventanas, input, UIA, atajos | Elevar app por defecto o desactivar UAC. |
| Voz | audio, ASR, traducción, wake | Descargar modelos o enviar audio sin autorización. |
| Multimedia | media/capture/encoder/halo | Prometer señal Spotify o grabar fuente no elegida. |
| Datos/seguridad | SQLite, IPC, grants, secrets | Borrar datos para pasar tests. |
| Arte/rendimiento | formas, material, worker | Bajar calidad silenciosamente. |
| QA/release | pruebas físicas, empaquetado | Convertir mocks en pruebas reales. |

## Paquete de tarea
Objetivo y requisito IDs; base commit; archivos autorizados; contratos de entrada/salida; pruebas esperadas; permisos que faltan; forma de devolver evidencia. Un informe debe nombrar archivos realmente modificados. Si el agente no tiene toolchain o dispositivo, produce trabajo independiente útil y deja la prueba pendiente; no simula el dispositivo en secreto.

## Orden de integración
Los cambios de contratos se revisan primero. Luego puertos con adaptador web, shell, datos, input, workers y herramientas. Integrar una capacidad detrás de feature flag real evita invalidar toda la app. Cuando ya es autoridad nativa, eliminar la segunda ruta autoritaria, no mantener dos servicios activos.

## Prevención de alucinaciones
APIs externas solo desde documentación primaria comprobada. Nombres internos propuestos se implementan antes de invocarlos. No crear bibliotecas con nombres plausibles. Comandos de build se ejecutan realmente y se registra exit code. El archivo de estado no marca completado si falta el gate físico. No se cambian requisitos para convertir un fallo en éxito.

## Revisión
Otro agente o desarrollador revisa cuando sea posible; si no, se declara revisión propia. Diferenciar revisión de código, ejecución de test y validación de UX. La aprobación visual exige ver el software, no un prompt de imagen. Las decisiones de UI del usuario tienen precedencia sobre preferencias estéticas del implementador.


---

# 23 · Riesgos, dependencias y costes

| Riesgo | Impacto | Mitigación / puerta |
|---|---|---|
| Varias autoridades de ajustes | Apariencia cambia sola | SQLite revision y un SettingsPort; prueba de reinicio. |
| Input transparente entre apps | Clics bloqueados/perdidos | Ensayo real proxy/región y foco en M1. |
| UIA no soporta un editor | Dictado falla/corrompe | Adaptadores por destino y fallback explícito; matriz. |
| ASR CPU lento | Latencia y competencia con render | Modelo pequeño medido, worker, cuotas de concurrencia. |
| Grabación solo en RAM | Pérdida ante cierre/disco | Segmentos finalizados y recuperación M4. |
| WebView/Windows cambia comportamiento | Regresión input/media | Versions/evidencia, feature detection, smoke tras update. |
| Cambios en APIs/políticas Spotify | Integración inaccesible/no distribuible | Validación actual y modo desactivado si no autorizado. |
| Bucle TTS→mic | Órdenes falsas/transcripción recursiva | AudioRuntime, half-duplex inicial, eco medido. |
| Grandes modelos/medios | RAM16GB insuficiente | Descarga/presupuesto claros, memoria acotada. |
| Optimización altera reflejos | Degradación rechazada | Referencia RGBA/visual, aprobación y no downgrade oculto. |
| Demasiadas fases simultáneas | Interferencia y entrega nunca útil | M0–M6 y gates por recorrido. |

## Costes que hay que decidir
Certificado de firma/distribución, servicios de IA/ASR/traducción remotos, aplicación/cuenta de proveedor musical, eventual wake engine comercial, almacenamiento para grabaciones y hosting de actualizaciones. Las cifras dependen del proveedor/fecha/región: este expediente no inventa precios. Servicios gratuitos no se consideran ilimitados ni garantizados.

Los modelos locales también cuestan almacenamiento/RAM/CPU. Antes de descargar, mostrar tamaño y licencia; antes de elegir modelo, medir tiempo y memoria en la máquina. No hacer una recomendación de compra de hardware sin benchmark del proyecto.

## Estimación de esfuerzo
No se ofrece un plazo de producción sin auditar la máquina y ejecutar M0/M1. El plan divide trabajo por resultados y dependencias; el agente registra duración real de cada tarea y recalcula. Una shell inicial puede compilar antes que el producto completo, pero su existencia no acredita voz/captura/seguridad terminadas.

## Decisiones abiertas con cierre definido
Input proxy: se decide por pruebas de clic/foco. ASR: por evaluación local y consentimiento de modelo. Wake: por falsa alarma/latencia/licencia. Encoder: por captura física y recuperación. GPU rendering: no sustituye compatibilidad sin decisión explícita. Todas tienen alternativa útil y gate, no un TODO sin dueño.


---

# Referencias oficiales y registro de consulta

Los identificadores S01–S44 utilizados en los documentos remiten a estas fuentes primarias. La disponibilidad HTTP es una verificación del enlace, no una prueba de compatibilidad del producto ni de toda interpretación técnica. Las versiones y condiciones deben fijarse de nuevo antes de distribuir. No se reproduce el contenido íntegro de estas páginas.

## S01 · Tauri: requisitos Windows

https://v2.tauri.app/start/prerequisites/

Consulta: 2026-10-19T16:58:02.865919+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S02 · Tauri: capacidades y permisos

https://v2.tauri.app/security/capabilities/

Consulta: 2026-10-19T16:58:02.866925+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S03 · Tauri: atajos globales

https://v2.tauri.app/plugin/global-shortcut/

Consulta: 2026-10-19T16:58:02.867479+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S04 · Tauri: ventanas

https://v2.tauri.app/reference/javascript/api/namespacewindow/

Consulta: 2026-10-19T16:58:02.867898+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S05 · Tauri: bandeja

https://v2.tauri.app/learn/system-tray/

Consulta: 2026-10-19T16:58:02.868397+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S06 · Tauri: instancia única

https://v2.tauri.app/plugin/single-instance/

Consulta: 2026-10-19T16:58:02.868850+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S07 · Tauri: instalador Windows

https://v2.tauri.app/distribute/windows-installer/

Consulta: 2026-10-19T16:58:02.869625+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S08 · Tauri: actualizaciones firmadas

https://v2.tauri.app/plugin/updater/

Consulta: 2026-10-19T16:58:02.870102+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S09 · Windows: RegisterHotKey

https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey

Consulta: 2026-10-19T16:58:02.871348+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S10 · Windows: pantalla y DPI

https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-desktop-application-development-on-windows

Consulta: 2026-10-19T16:58:02.877044+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S11 · Windows: UI Automation TextPattern

https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-usingtextpattern

Consulta: 2026-10-19T16:58:02.886898+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S12 · Windows: SendInput e integridad

https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput

Consulta: 2026-10-19T16:58:02.888084+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S13 · Windows: ValuePattern

https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-implementingvalue

Consulta: 2026-10-19T16:58:02.888348+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S14 · Windows: Graphics Capture

https://learn.microsoft.com/en-us/windows/uwp/audio-video-camera/screen-capture

Consulta: 2026-10-19T16:58:07.891967+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S15 · Windows: afinidad/exclusión de captura

https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity

Consulta: 2026-10-19T16:58:07.892873+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S16 · Windows: WASAPI loopback

https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording

Consulta: 2026-10-19T16:58:07.894014+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S17 · Windows: Media Foundation Sink Writer

https://learn.microsoft.com/en-us/windows/win32/medfound/using-the-sink-writer-to-encode-video

Consulta: 2026-10-19T16:58:12.897535+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S18 · Windows: sesiones multimedia

https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessionmanager

Consulta: 2026-10-19T16:58:12.897915+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S19 · Windows: DPAPI

https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata

Consulta: 2026-10-19T16:58:12.898076+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S20 · Microsoft: windows-rs

https://github.com/microsoft/windows-rs

Consulta: 2026-10-19T16:58:12.898195+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S21 · Chrome: Native Messaging

https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging

Consulta: 2026-10-19T16:58:12.898431+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S22 · Chrome: permisos activeTab

https://developer.chrome.com/docs/extensions/develop/concepts/activeTab

Consulta: 2026-10-19T16:58:12.898538+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S23 · Chrome: content scripts

https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts

Consulta: 2026-10-19T16:58:12.898703+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S24 · Chrome: Translator API

https://developer.chrome.com/docs/ai/translator-api

Consulta: 2026-10-19T16:58:12.898819+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S25 · MDN: SpeechRecognition

https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition

Consulta: 2026-10-19T16:58:12.898963+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S26 · MDN: OffscreenCanvas

https://developer.mozilla.org/en-US/docs/Web/API/OffscreenCanvas

Consulta: 2026-10-19T16:58:12.901039+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S27 · SQLite: WAL

https://www.sqlite.org/wal.html

Consulta: 2026-10-19T16:58:17.902141+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S28 · SQLite: backup API

https://www.sqlite.org/backup.html

Consulta: 2026-10-19T16:58:17.902574+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S29 · whisper.cpp: proyecto oficial

https://github.com/ggml-org/whisper.cpp

Consulta: 2026-10-19T16:58:17.902691+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S30 · openWakeWord: proyecto y licencias

https://github.com/dscripka/openWakeWord

Consulta: 2026-10-19T16:58:17.904123+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S31 · Spotify: Web API

https://developer.spotify.com/documentation/web-api

Consulta: 2026-10-19T16:58:17.904302+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S32 · Spotify: PKCE

https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow

Consulta: 2026-10-19T16:58:22.907980+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S33 · Spotify: política de desarrolladores

https://developer.spotify.com/policy

Consulta: 2026-10-19T16:58:22.908718+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S34 · Spotify: redirect URI

https://developer.spotify.com/documentation/web-api/concepts/redirect_uri

Consulta: 2026-10-19T16:58:22.908850+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S35 · YouTube: IFrame API

https://developers.google.com/youtube/iframe_api_reference

Consulta: 2026-10-19T16:58:22.909023+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S36 · OpenAI: facturación ChatGPT y API

https://help.openai.com/en/articles/8156019-how-can-i-move-my-chatgpt-subscription-to-the-api

Consulta: 2026-10-19T16:58:22.909142+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S37 · OpenAI: Realtime

https://platform.openai.com/docs/guides/realtime

Consulta: 2026-10-19T16:58:22.909296+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S38 · OpenAI: Codex autenticación

https://developers.openai.com/codex/auth

Consulta: 2026-10-19T16:58:22.909421+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S39 · Ollama: API

https://docs.ollama.com/api/introduction

Consulta: 2026-10-19T16:58:22.909583+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S40 · FFmpeg: licencia/distribución

https://ffmpeg.org/legal.html

Consulta: 2026-10-19T16:58:22.909672+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S41 · Windows: WM_NCHITTEST

https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-nchittest

Consulta: 2026-10-19T16:58:22.909777+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S42 · Windows: SetWindowRgn

https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowrgn

Consulta: 2026-10-19T16:58:22.909901+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S43 · Node.js: releases

https://nodejs.org/en/about/previous-releases

Consulta: 2026-10-19T16:58:27.914201+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>

## S44 · Rust: instalación

https://www.rust-lang.org/tools/install

Consulta: 2026-10-19T16:58:27.914463+00:00 · No recuperado por este comprobador; verificar manualmente. <urlopen error [Errno -3] Temporary failure in name resolution>


---

# 25 · Trazabilidad requisito → implementación → prueba

| Requisito | Tareas que lo cubren | Estado |
|---|---|---|
| R01 | T00, T05, T06, T26 | Planificado; no validación nativa implícita |
| R02 | T05, T06 | Planificado; no validación nativa implícita |
| R03 | T07 | Planificado; no validación nativa implícita |
| R04 | T06, T07 | Planificado; no validación nativa implícita |
| R05 | T06 | Planificado; no validación nativa implícita |
| R06 | T02, T04, T06 | Planificado; no validación nativa implícita |
| R07 | T04, T26 | Planificado; no validación nativa implícita |
| R08 | T04 | Planificado; no validación nativa implícita |
| R09 | T02, T03, T26 | Planificado; no validación nativa implícita |
| R10 | T03, T04 | Planificado; no validación nativa implícita |
| R11 | T03, T05, T06, T23 | Planificado; no validación nativa implícita |
| R12 | T06, T15, T23 | Planificado; no validación nativa implícita |
| R13 | T15 | Planificado; no validación nativa implícita |
| R14 | T08, T15 | Planificado; no validación nativa implícita |
| R15 | T08, T09, T16, T19 | Planificado; no validación nativa implícita |
| R16 | T09 | Planificado; no validación nativa implícita |
| R17 | T10, T11, T12, T17 | Planificado; no validación nativa implícita |
| R18 | T12, T13, T17, T26 | Planificado; no validación nativa implícita |
| R19 | T11, T14 | Planificado; no validación nativa implícita |
| R20 | T10, T14, T17 | Planificado; no validación nativa implícita |
| R21 | T24 | Planificado; no validación nativa implícita |
| R22 | T16, T17, T18 | Planificado; no validación nativa implícita |
| R23 | T10, T16, T18 | Planificado; no validación nativa implícita |
| R24 | T19, T26 | Planificado; no validación nativa implícita |
| R25 | T21 | Planificado; no validación nativa implícita |
| R26 | T20 | Planificado; no validación nativa implícita |
| R27 | T20 | Planificado; no validación nativa implícita |
| R28 | T09 | Planificado; no validación nativa implícita |
| R29 | T07, T13, T22 | Planificado; no validación nativa implícita |
| R30 | T12, T22 | Planificado; no validación nativa implícita |
| R31 | T01, T05, T25 | Planificado; no validación nativa implícita |
| R32 | T01, T08, T15, T17, T22, T24 | Planificado; no validación nativa implícita |
| R33 | T07, T21, T24, T26 | Planificado; no validación nativa implícita |
| R34 | T02, T25, T26 | Planificado; no validación nativa implícita |
| R35 | T03, T23, T26 | Planificado; no validación nativa implícita |
| R36 | T00, T23 | Planificado; no validación nativa implícita |

Para la descripción y aceptación de cada requisito, consultar [01](docs/01-REQUISITOS.md). Para dependencias y pruebas, consultar [el plan](plans/PLAN-MAESTRO.md). No se marca cumplido un requisito completo porque una parte del prototipo lo simule.