# AXX Notch Integration — Project Singularity Production Directive

La corrección central de esta iteración es definitiva: **AXX tiene dos anatomías visuales distintas pero un único runtime**. Cuando está libre en el escritorio, conserva el avatar 3D personalizado y puede usar sus tentáculos como parte de la interacción espacial. Cuando está acoplado arriba, **deja de comportarse como avatar extendido y pasa a comportarse como un notch convencional de alta calidad: compacto, claramente visible, internamente interactivo y sin un solo tentáculo**. El paso de un modo al otro debe conservar actividad, sesión, permisos, progreso y estado; únicamente cambia la representación.

Esto mejora sustancialmente la dirección anterior porque elimina una contradicción de producto: intentar que toda función del notch naciera físicamente del avatar estaba convirtiendo una interfaz compacta en una demostración visual excesivamente compleja. La especificación original de Project Singularity ya defendía que actividad y presentación fueran entidades separadas y que Orbit, Portal, Stage, Parallel y Continuum fueran manifestaciones de un runtime compartido; esa parte debe conservarse, pero la manifestación acoplada ahora queda estrictamente separada de la anatomía orgánica libre. fileciteturn2file0

La implementación debe ser **Windows 11 primero**, acorde con el AXX real y con Dynamic, no macOS primero como planteaban documentos conceptuales anteriores. El repositorio actual de AXX describe explícitamente un asistente residente para Windows, y su host nativo usa Tauri/Win32; la auditoría anterior de integración también localizó la autoridad de ejecución en `backend/commands.py`, `backend/actions/executor.py`, `backend/connect/*` y los adaptadores de UI existentes, recomendando precisamente no crear una segunda capa de automatización que compita con ellos. citeturn202026view3 fileciteturn2file2

## Base técnica verificada y corrección arquitectónica

La primera decisión de implementación debe ser **no reconstruir AXX alrededor del notch**. El repositorio actual ya contiene las tres piezas críticas: un renderer de avatar, un sistema de conexiones orgánicas y una autoridad nativa de ventana. La documentación vigente de tentáculos identifica `OrganicTendrils`, `fitTendrilLink`, `organicCurve` y `flowArmRadius` en `1.AXX/Axx.html`; los tentáculos reutilizan la tabla de iluminación y la paleta del avatar, consultan la silueta rasterizada del mismo cuadro para enterrar correctamente la raíz y se renderizan antes de componer la pantalla. Eso significa que existe una base gráfica real que merece conservarse **para el modo libre**, no reciclarse artificialmente dentro del notch. citeturn992270view1

El contrato visual aprobado del proyecto también exige cuidado. `AGENTS.md` ordena preservar la interfaz 3D existente, mantener compatibilidad escritorio/móvil y respetar `mobile/design-baseline.json`; los hashes protegidos no pueden regenerarse únicamente para hacer pasar un test y un cambio visual requiere autorización explícita y revisión de regresión. La misma guía separa la versión Android de la de escritorio y exige validación específica antes de publicar. citeturn992270view0

Por tanto, la arquitectura recomendada es esta:

```text
                     AXX RUNTIME ÚNICO
        ┌─────────────────────────────────────┐
        │ Activities · Sessions · Actions     │
        │ Commands · Agents · Media · Voice   │
        │ Transfers · Magic Pen · Companion   │
        └──────────────────┬──────────────────┘
                           │
                    Presentation State
                           │
              ┌────────────┴────────────┐
              │                         │
       FREE PRESENTATION          DOCKED PRESENTATION
              │                         │
      Avatar 3D completo          AXX Notch Surface
      forma/paleta/material       shell + contenido interno
      escala personalizada        estados compactos
      OrganicTendrils ✓           OrganicTendrils ✗
      Orbit orgánico opcional     controles internos
      OrganicDesk opcional        Stage desacoplable
```

**Invariante no negociable:** `physicalMode === "docked"` implica `tendrilsEnabled === false`. No “casi cero”, no tentáculos decorativos de 8 px, no líneas simuladas, no conexiones laterales. La prueba automatizada debe tratar cualquier geometría de tentáculo visible o interactiva durante un estado acoplado como fallo.

El segundo invariante es la restauración de identidad. Antes de iniciar el docking se toma un snapshot de la presentación libre —forma, paleta, finish/material, escala, orientación, parámetros de movimiento aplicables, posición, monitor y cualquier dato requerido para reconstruir exactamente el estado—. Se retraen primero las extensiones libres; después comienza el acoplamiento. Al desacoplar, el notch desaparece mediante la transición inversa y se restaura el snapshot, sin escribir una nueva personalización como efecto secundario.

El tercer invariante es **una sola autoridad de negocio**. La documentación técnica histórica de AXX ya describe un amplio catálogo de comandos y continuidad, pero distingue claramente especificación de implementación: una edición documental catalogó 619 acciones en 57 dominios, muchas marcadas explícitamente como `SPECIFIED_NOT_IMPLEMENTED`. Esto refuerza que el notch no debe inventar progreso, disponibilidad ni resultados: sólo puede proyectar capacidades y estados realmente expuestos por el runtime vigente. fileciteturn2file1

Dynamic es útil como referencia de problemas resueltos, no como arquitectura copiable. Su repositorio público actual documenta Companion, personalización, Command Palette, docking/floating, multimonitor y una política de ocultación cuando una aplicación fullscreen ocupa el mismo monitor; también dice que no inyecta overlays ni captura el contenido de pantalla para esa función. El repositorio público inspeccionado es esencialmente un repositorio de releases/documentación, por lo que no hay base para atribuirle una implementación interna privada. citeturn992270view4

Hay una limitación de evidencia importante: GitHub expone hoy `1.AXX/Axx.html` como un archivo de unas veinte mil líneas, pero su vista HTML no entrega el cuerpo completo en este canal. Por eso las rutas documentadas y archivos independientes sí se han vuelto a comprobar sobre `main`, mientras que el agente implementador debe **fijar el SHA exacto de HEAD y recuperar el blob completo de `Axx.html` antes de editarlo**, volver a localizar `SoftwareRenderer`, `ShapeTransition`, `Spring`, `LivingMotion`, `OrganicTendrils`, `OrganicDesk`, `ReachHub`, `ResidentDesktop`, `DesktopRuntime`, `updateHitMap` y el bridge de hit-testing, y no confiar ciegamente en posiciones de línea de auditorías anteriores. citeturn202026view0

## Dirección visual del notch y sistema de composición

La meta estética no debería ser “hacerlo parecer Apple”. Debe alcanzar **el mismo nivel de disciplina**: jerarquía clara, movimiento con propósito, control de materiales, excelente tipografía, estados consistentes, accesibilidad y atención meticulosa al detalle, pero manteniendo la identidad de AXX.

Evaluaría tres direcciones antes de bloquear el arte final.

| Dirección | Descripción | Ventaja | Riesgo | Dictamen |
|---|---|---|---|---|
| **Neutral Monolith** | Shell oscuro/neutro constante, muy compacto. | Máxima lectura y reconocimiento del notch. | Puede sentirse desconectado de la personalización AXX. | Excelente baseline. |
| **Theme Adaptive** | Shell derivado de los tokens claro/oscuro y personalización UI de AXX. | Coherencia con la aplicación. | Contraste variable sobre wallpapers y contenido. | Útil, pero requiere solver de contraste. |
| **AXX Identity Accent** | Shell neutro estable + identidad de AXX usada sólo como acento controlado: tono, brillo, línea, pequeño glyph/material cue. | Conserva reconocimiento y conecta notch/avatar sin meter el muñeco entero ni tentáculos. | Necesita disciplina para no transformarse en “glassmorphism”. | **Recomendada.** |

La recomendación es **AXX Identity Accent**. El notch necesita una base visual estable para que siempre se reconozca, mientras la identidad personal del avatar se expresa en elementos secundarios. Apple separa precisamente los materiales funcionales de controles/navegación del contenido y recomienda usar efectos de material con moderación porque el exceso debilita la jerarquía y la legibilidad; ese principio es trasladable al diseño de AXX aunque la implementación sea Windows/WebView2 y no Liquid Glass. citeturn900839view0

La anatomía propuesta tiene cinco regiones. **Top seam**: unión exacta con el borde superior. **Shell**: silueta negra/neutra o temática, siempre visible. **Status spine**: región central persistente para identidad de estado. **Leading lane** y **trailing lane**: información contextual y actividades. **Expansion body**: zona inferior que aparece sólo en `peek`, `expanded` o `stage-trigger`, sin sustituir el shell superior. Así, cuando la superficie crece, el usuario siempre conserva un punto de referencia espacial.

Una geometría inicial debe definirse mediante **tokens y fórmulas**, no una colección de `width: 320px` dispersa. Los números siguientes son parámetros de prototipo y deben ajustarse tras capturas reales:

```text
N = notch shell
D = escala UI/DPI lógica
Wv = ancho útil del monitor en DIP
C = complejidad semántica del contenido
A = actividades visibles

N.compact.height     = clamp(30, round(32 * Dui), 40) DIP
N.compact.width      = clamp(168, resolveContentWidth(C,A), min(360, 0.24*Wv))
N.peek.height        = clamp(52, contentPeekHeight, 92) DIP
N.expanded.width     = clamp(320, semanticWidth, min(680, 0.58*Wv))
N.expanded.height    = clamp(180, semanticHeight, min(520, 0.48*Hv))

shellRadius          = function(height, state)
innerGap             = 6–8 DIP candidate
contentInsetX        = 10–14 DIP candidate
contentInsetY        = 6–10 DIP candidate
```

Esos valores **no son requisitos de Windows ni de Apple**. Son puntos iniciales que el equipo debe comparar mediante capturas a 100%, 125%, 150%, 175% y 200% y validar con contenido localizado.

La silueta nunca debe quedar escondida enteramente fuera del monitor. “Compact” no equivale a invisible. Incluso en reposo debe existir una presencia visual reconocible de baja densidad: por ejemplo, shell + glyph AXX + estado real mínimo. **Hover mejora información; no descubre la existencia del producto.**

La jerarquía tipográfica debe usar la familia ya coherente con AXX/Windows antes de introducir una fuente nueva. Apple recomienda tipografía con jerarquía clara, legibilidad en tamaños pequeños y pruebas en distintos contextos; su cifra de 13 pt predeterminada y 10 pt mínima corresponde a macOS, por lo que no debe copiarse como regla Windows, pero sí sirve como evidencia de que “microtexto” excesivo no es una solución premium. citeturn900839view2

Propongo cuatro roles, derivados del tamaño de interfaz del usuario: `status`, `body`, `label`, `micro`. `micro` sólo para metadatos no críticos. Estado, error, aprobación o acción nunca deben depender de 9 px de texto.

El shell necesita comportarse bien sobre fondos negros, blancos, HDR, wallpapers texturados y ventanas brillantes. No debe fingir un blur real mediante una captura estática del escritorio. Tauri permite configurar fondo y ventanas, pero la documentación advierte restricciones concretas del canal alfa en Windows; por eso cualquier transparencia efectiva tiene que probarse en la combinación Tauri/WebView2 real y disponer de fallback opaco. citeturn992270view7

La personalidad visual de AXX puede entrar en el notch mediante **tres canales seguros**: un acento cromático derivado de la paleta activa, una respuesta luminosa muy contenida derivada del material, y un pequeño “identity mark” abstracto derivado de la forma. No renderizaría el avatar 3D completo dentro del notch compacto por defecto: reducirlo a 20–28 DIP desperdicia el renderer y perjudica legibilidad. Una miniatura 3D puede estudiarse como opción de `peek` o configuración, pero no debe ser la base del sistema.

La matriz visual mínima debería ser:

| Estado | Siempre visible | Bajo interacción | Nunca |
|---|---|---|---|
| Idle | shell + AXX identity mark | home compacto | tentáculos |
| Active | estado/actividad principal | detalle de actividad | tentáculos |
| Progress | progreso real + identificador | acciones válidas | progreso falso |
| Completed | resultado/confirmación breve | abrir/continuar | animación infinita |
| Approval | acción pendiente claramente distinguible | aprobar/rechazar | autoaprobar |
| Error | error compacto inequívoco | diagnóstico/recuperación | ocultarlo por timeout |
| Offline | conectividad/status | acciones offline válidas | spinner perpetuo |
| Media | título/estado mínimo | controles | sobresaturar shell |
| Multiple | primaria + contador/secondary cue | Parallel | 5 miniwidgets simultáneos |

Apple Live Activities demuestra un principio útil: la misma actividad puede tener representaciones compactas, mínimas y expandidas según el espacio, conservando su identidad. Es una referencia conceptual de composición, **no un requisito de Windows ni una API que AXX vaya a usar**. citeturn992270view5

## Modelo de estados, Orbit, Portal, Parallel, Intent y Stage

El error que debe evitarse es una mega-enumeración como `DOCKED_EXPANDED_MEDIA_RUNNING_HOVERED_FULLSCREEN`. El estado tiene que estar dividido en ejes ortogonales y el compositor resolver su representación.

```ts
// PSEUDOCÓDIGO DE DISEÑO — no API real del repositorio

type PhysicalMode =
  | "free"
  | "approach"
  | "retracting"
  | "docking"
  | "docked"
  | "undocking";

type SurfaceSize =
  | "compact"
  | "ambient"
  | "peek"
  | "expanded"
  | "stage";

type ContentMode =
  | "home"
  | "media"
  | "orbit"
  | "portal"
  | "parallel"
  | "intent"
  | "chat"
  | "voice"
  | "agents"
  | "transfer"
  | "settings";

type Attention =
  | "idle"
  | "active"
  | "progress"
  | "completed"
  | "approval"
  | "error"
  | "offline";

type Interaction =
  | "none"
  | "pointer"
  | "hoverIntent"
  | "keyboard"
  | "dragEnter"
  | "dragActive"
  | "focused";

type VisibilityPolicy =
  | "normal"
  | "presentation"
  | "fullscreenSuppressed"
  | "privacySuppressed"
  | "userHidden";
```

El estado renderizado es una función:

\[
P = Resolve(Physical,\ Surface,\ Content,\ Attention,\ Interaction,\ Visibility,\ Activities,\ Geometry,\ Preferences)
\]

No es una tabla con todas las combinaciones posibles. Los invariantes podan el espacio de estados: en `free`, el notch no existe; en `docked`, tentáculos son imposibles; `stage` conserva el shell como origen visual pero la superficie de trabajo puede ser otra región/ventana; `fullscreenSuppressed` puede reducir u ocultar el notch según política sin terminar la actividad.

**Docking.** La transición válida es `free → approach → retracting → docking → docked`. Si existen tentáculos, `retracting` es obligatorio. El motor no debe iniciar morph de notch hasta que cada tentáculo esté `retracted`, `cancelledSafe` o haya alcanzado un timeout que desemboque en rollback. Una operación empresarial que el tentáculo representaba no se cancela por retraer su representación.

**Undocking.** `docked → undocking → free`. Primero se contrae cualquier superficie expandida hasta un shell estable, se libera correctamente foco/hit regions, se reconstruye el avatar desde el snapshot y sólo después se habilitan tentáculos libres cuando la geometría del cuerpo ya es válida. El usuario puede interrumpir la transición; el controlador debe retargetear desde la posición y velocidad actuales, no reiniciar una animación desde cero.

**Compact.** Debe soportar una actividad real sin hover: icono/glyph, estado y al menos la información de mayor valor. Si sólo existe una operación, no mostrar navegación superflua.

**Ambient.** Señales de muy baja atención: temporizador, música, agente en ejecución o transferencia. No crece automáticamente por eventos ordinarios.

**Peek.** Es una ampliación breve por click, hover intencional configurado o atajo. Hover nunca es la única ruta. El sistema debe ignorar cruces rápidos del cursor.

**Expanded.** Aquí viven los controles internos. Un expanded de música no debe cargar una dashboard con chat, archivos y agentes. La superficie cambia semánticamente según contenido.

**Orbit en notch.** Ya no significa satélites conectados por tentáculos. Debe ser un **activity strip/rail adaptativo interno**: 1–3 actividades visibles según ancho, prioridad y densidad. Una actividad seleccionada puede abrir detalle de forma independiente. El nombre Orbit describe organización, no geometría circular obligatoria.

**Portal en notch.** Al entrar un drag externo, el shell cambia a modo de recepción. Los destinos compatibles reemplazan temporalmente el contenido normal. No se expande a diez acciones; se muestran 2–4 destinos principales y “más” si es necesario. Al salir el drag sin drop, se restaura exactamente el estado anterior.

**Parallel.** Dos actividades relevantes pueden ocupar lanes distintas; más actividades se agrupan. El usuario expande una sin matar ni reiniciar las demás. El notch es una vista del activity runtime, no su scheduler.

**Intent.** Se abre como campo/compositor compacto. El usuario expresa un objetivo y la UI lista capacidades reales resueltas por el sistema existente. No debe ofrecer una opción que no tenga handler/permiso/availability válidos.

**Stage.** No necesita tentáculo. Desde expanded, una tarea que necesita más espacio puede pasar a un workspace temporal centrado o cercano; el notch conserva una representación resumida que actúa como retorno y estado. Stage y notch consumen la **misma session ID**. Cerrar Stage vuelve a compact/expanded sin terminar la sesión.

La prioridad temporal debe seguir esta regla: `explicit user interaction > safety/approval > error requiring action > selected activity > ongoing high-value work > passive status`. No usaría una sola puntuación fija como fuente de verdad; los pesos pueden existir como heurística dentro de una política que respete guards y contexto.

Una matriz de transición mínima:

| Evento | Estado de origen | Guard | Resultado | Si se interrumpe |
|---|---|---|---|---|
| Drag avatar to top | free | dock enabled | approach | retorna free |
| Capture threshold | approach | stable target | retracting | vuelve desde posición actual |
| Tentacles gone | retracting | identity snapshot valid | docking | rollback snapshot |
| Dock settle | docking | native geometry ack | docked/compact | retry bounded o rollback |
| Pointer intentional | compact | policy allows | peek | reverse desde estado actual |
| Click/shortcut | compact/peek | interactive | expanded | preserva actividad |
| Drag content enter | docked | MIME/type accepted | portal | restore previous presentation |
| Activity completes | any docked | receipt valid | completed cue | no cambia sesión |
| Open Stage | expanded | task supports stage | stage | return expanded |
| Pull down | docked | not approval-locked | undocking | redock desde estado actual |
| Fullscreen detected | docked | same monitor + policy | suppress/reduce | restore previous dock state |
| Monitor removed | any | current display gone | migrate/recover | safe primary fallback |

## Motion, fluidez y comportamiento nativo de Windows

El movimiento tiene que comunicar estructura, no exhibir animaciones. Apple formula tres principios particularmente útiles como referencia de calidad: movimiento con propósito, feedback breve/preciso y posibilidad de cancelar una transición sin esperar a que concluya. Esos principios son directamente compatibles con una interfaz notch de Windows y deberían convertirse en criterios de aceptación. citeturn900839view1

El sistema de motion debe operar sobre **valores continuos**, no sobre clases CSS que se encienden y apagan:

```ts
// PSEUDOCÓDIGO
interface MotionChannel {
  value: number;
  velocity: number;
  target: number;
  stiffness: number;
  damping: number;
  maxOvershoot: number;
}

interface NotchMotionState {
  x: MotionChannel;
  y: MotionChannel;
  width: MotionChannel;
  height: MotionChannel;
  radius: MotionChannel;
  opacity: MotionChannel;
  contentReveal: MotionChannel;
}
```

Al retargetear, se conserva `value` **y** `velocity`. Eso elimina uno de los defectos típicos de interfaces “bonitas” pero poco fluidas: cambiar de objetivo provoca un salto en derivada porque la nueva animación asume velocidad cero. El requisito visual debe ser continuidad C0 de posición y, salvo casos deliberados de impacto, continuidad C1 perceptual de velocidad.

El docking debería sentirse aproximadamente así, con tiempos iniciales sujetos a ensayo:

```text
t=0        Usuario entra en capture band.
t=0–60     El avatar responde a la atracción; ninguna UI de notch todavía.
t=40–180   Tentáculos libres se retraen si existen.
t=150–260  El cuerpo converge hacia el punto de docking.
t=220–360  La silueta del notch empieza a aparecer/componer.
t=300–440  Avatar deja de ser representación dominante.
t=380–520  Shell queda estable; contenido compacto entra.
t>=520     Estado interactivo, sin movimiento residual importante.
```

No debe ocurrir `avatar → frame negro instantáneo`. Durante una parte corta de la transición puede existir una composición cruzada entre avatar y shell, pero el estado final acoplado es una superficie notch limpia. Si una deformación 3D real no añade valor durante esos 200–300 ms, **no hay razón para deformar la malla**: una transición de posición, escala, máscara y crossfade coordinada puede ser más robusta y conservar mejor la identidad. Esa es una mejora importante respecto a propuestas anteriores que suponían que “morphing” debía significar siempre manipular vértices.

Para `compact → peek → expanded`, animaría primero el **contenedor**, después revelaría contenido jerárquicamente. Anchura y altura no deben terminar con 100 ms de diferencia generando sensación de goma. El contenido no debería hacer reflow cada frame; su layout destino se calcula primero y se interpola el clipping/transform de una estructura estable. Texto nuevo entra cuando existe espacio legible suficiente.

El notch necesita además una ruta `Reduce Motion`: cambio de geometría de menor amplitud, duración corta, crossfade o cambio prácticamente directo, sin rebotes. En WebView2 se puede respetar `prefers-reduced-motion`, que refleja la preferencia del sistema en plataformas compatibles; además, las funciones esenciales nunca deben depender de animación. citeturn202026view21

**Rendimiento.** A 60 Hz el presupuesto matemático total es 16,67 ms; a 120 Hz son 8,33 ms. Eso no significa que AXX tenga derecho a consumir todo el frame. Propongo medir `p50/p95/p99` de tiempo de presentación y dropped frames y establecer un gate basado en baseline real del hardware. Un objetivo inicial razonable de ingeniería es mantener el trabajo propio de composición/motion claramente por debajo del frame budget y evitar regresión significativa del renderer; el número definitivo debe fijarse después de medir la versión base, no antes.

Se deben registrar, como mínimo: `frame_time_ms`, `layout_time_ms`, `paint_time_ms`, `native_geometry_ack_ms`, `hit_map_revision_lag`, `input_to_visual_ms`, `activity_event_to_visual_ms`, `dropped_frame_count`, idle CPU, active CPU, working set y crecimiento de memoria después de cientos de ciclos de expand/contract. Ningún porcentaje puede declararse aprobado sin hardware y escenario documentados.

**Ventana nativa.** `resident.rs` ya contiene lógica de residente, recuperación y multimonitor, y sus tests incluyen un monitor con coordenadas negativas y escala 1.5; esto es exactamente el tipo de infraestructura que el notch debe extender en lugar de montar un controlador nativo paralelo. citeturn992270view2turn992270view3

Windows recomienda probar distintas dimensiones, DPI y escalas y advierte que Win32 no obtiene automáticamente toda la gestión per-monitor DPI que proporcionan frameworks más modernos. PMv2 entrega eventos de cambio DPI y requiere que la aplicación reajuste correctamente la UI. AXX debe probar desplazamiento entre monitores 100–200%, monitor principal/secundario, coordenadas negativas y cambio de escala mientras está abierto. citeturn202026view12turn992270view9

La autoridad nativa debe manejar un único **geometry revision**:

```text
JS compositor resolves desired notch rect + hit regions
        ↓ revision=1842
Tauri command / native bridge
        ↓
Win32 applies window geometry without activation
        ↓ nativeAck revision=1842
WebView2 surface applies/validates same revision
        ↓
Hit-test mask publishes revision=1842
```

Nunca aceptar una máscara de hit-test vieja sobre una geometría nueva. Si `hitRevision < geometryRevision`, la política segura es restringir temporalmente interacción al shell conocido, no dejar regiones fantasma que intercepten clics fuera del notch.

WebView2 integra render, input, foco y accesibilidad con el host; la documentación oficial señala que esas responsabilidades forman parte explícita del controlador. Eso significa que un notch “bonito” pero con WebView2 mal sincronizado puede fallar en foco, input o accessibility aunque la UI HTML parezca correcta. citeturn992270view8

Para mover/redimensionar la ventana sin robar foco, Win32 permite cambios de posición/Z-order mediante `SetWindowPos`; `SWP_NOACTIVATE` evita activar la ventana. El código de AXX ya utiliza esa familia de mecanismos, por lo que el notch debe preservar el comportamiento no activante en reposo/peek y sólo solicitar foco cuando el usuario inicia explícitamente una interacción de teclado. citeturn202026view17

**Política de visibilidad propuesta, no requisito absoluto del usuario:** `normal` = visible; `fullscreen` en el mismo monitor = ocultar o reducir según preferencia; juego = preferencia equivalente; screen sharing/privacy = permitir suppression manual/automática sólo cuando la señal sea fiable; `always-on-top` = configurable y dinámico, no permanentemente obligatorio. Tauri permite consultar/cambiar always-on-top, por lo que no hace falta convertirlo en una propiedad irreversible del proceso. citeturn202026view16

El notch no debe bloquear controles de otras aplicaciones. Fuera de su silueta y regiones interactivas actuales, el input debe atravesar la superficie. Los controles internos necesitan ruta de teclado y foco visible. Microsoft exige que controles accesibles por teclado sean alcanzables mediante navegación de foco y que los custom controls mantengan una indicación clara de foco; UI Automation permite representar controles personalizados con semántica apropiada. citeturn202026view18turn202026view19

Para drag-and-drop, además del gesto debe existir alternativa sin arrastre cuando la misma función pueda hacerse por selección/acción. WCAG 2.2 AA exige alternativa de puntero único para funcionalidades basadas en dragging y un mínimo de 24×24 CSS px para targets salvo excepciones; 44×44 pertenece al criterio mejorado AAA, por lo que no debe presentarse incorrectamente como requisito AA. citeturn202026view20

## Arquitectura de implementación sobre AXX

No introduciría un “Notch OS” paralelo. Añadiría una **Notch Presentation Layer** pequeña y explícita entre runtime y vista, con adaptadores hacia `resident.rs` y la superficie WebView existente.

Arquitectura objetivo:

```text
Existing AXX business/runtime authorities
 ├─ CommandService / ActionExecutor
 ├─ Connect registry/service
 ├─ Agent/task services
 ├─ Chat / voice
 ├─ Media
 ├─ Transfers
 ├─ Magic Pen
 └─ Companion/mobile
             │
             ▼
      Activity Projection Adapter
             │
       one canonical model
             │
   ┌─────────┴─────────────┐
   │                       │
Free Avatar            Notch Surface
Presentation           Presentation
   │                       │
OrganicTendrils         NotchCoordinator
OrganicDesk             NotchLayoutResolver
ReachHub                NotchMotionController
                        VisibilityPolicy
                        HitRegionProjector
                        StagePresenter
   └──────────────┬────────┘
                  │
           ResidentDesktop
                  │
             resident.rs
                  │
          Win32 / WebView2
```

Los nombres nuevos son **propuestos**, no símbolos existentes. El agente debe comprobar si alguna responsabilidad ya vive en `ResidentDesktop`, `DesktopRuntime`, `OrganicDesk` o módulos recientes antes de crear archivos.

Yo separaría los datos así:

```ts
// PSEUDOCÓDIGO DE CONTRATO

interface PresentationSnapshot {
  identityRevision: number;
  formId: number;
  paletteId: number;
  finishId: string;
  avatarScale: number;

  freePosition: { displayId: string; x: number; y: number };
  orientation?: [number, number, number];

  // Sólo atributos realmente persistidos por AXX tras la auditoría.
}

interface ActivityProjection {
  activityId: string;
  sessionId?: string;
  source: string;
  status:
    | "pending"
    | "running"
    | "awaiting_user"
    | "completed"
    | "failed"
    | "cancelled"
    | "unknown";

  progress?: {
    kind: "determinate" | "indeterminate";
    value?: number; // sólo si fuente real
  };

  title: string;
  subtitle?: string;
  availableActions: string[];
  updatedAt: number;
  revision: number;
}

interface NotchPresentationState {
  physicalMode: PhysicalMode;
  size: SurfaceSize;
  content: ContentMode;
  attention: Attention;
  interaction: Interaction;
  visibility: VisibilityPolicy;

  activeActivityIds: string[];
  selectedActivityId?: string;

  geometryRevision: number;
  activityRevision: number;
}
```

La regla de progreso es estricta: si el servicio no expone una métrica determinista, la UI usa `indeterminate`, una fase textual real o ninguna barra. **Nunca derivar 68% del tiempo transcurrido** para que la interfaz parezca viva.

Los eventos deberían incluir revisión/cursor para evitar regresiones de estado:

```ts
interface ProjectionEvent<T> {
  eventId: string;
  sourceRevision: number;
  occurredAt: number;
  activityId?: string;
  payload: T;
}
```

El reducer/compositor descarta cualquier evento cuyo revision/cursor sea anterior al aplicado para la misma entidad. Los comandos con efectos externos mantienen idempotency/operation IDs del runtime existente; la capa notch no vuelve a enviar automáticamente una operación incierta después de reconectar.

**Portal** consume el catálogo real de capacidades compatibles con la entrada. **Intent** usa los resolvers existentes. **Parallel** observa actividades. **Stage** presenta la sesión. **Orbit** compone indicadores. Ninguno se convierte en un segundo executor.

Para Companion, la continuidad debe sincronizar **estado semántico**, no geometría de notch. El teléfono no necesita saber que la UI de PC mide 384×72 DIP; necesita activity/session IDs, estados, acciones autorizadas y resultados apropiados a sus permisos. `AGENTS.md` exige mantener el protocolo de compatibilidad y validarlo por separado. citeturn992270view0

El renderer y los tentáculos se mantienen completamente fuera de la ruta de composición del notch salvo durante el corto handoff visual de docking/undocking. Esto también reduce el coste de idle docked: si el avatar 3D no está visible, el agente debe evaluar si puede suspender o bajar la frecuencia del renderer sin romper dependencias, en lugar de gastar CPU pintando algo cubierto por el notch.

## Plan de implementación, gates y validación

La implementación debería avanzar en incrementos que produzcan evidencia concreta. No empezar por Orbit, Portal y Agent UI a la vez.

**Baseline y arqueología.** Fijar SHA de HEAD, guardar `git status`, leer `AGENTS.md`, `docs/mobile/COMPATIBILITY-PROTOCOL.md`, `mobile/design-baseline.json` y procedimientos de tests/releases. Extraer el blob completo de `Axx.html`, regenerar un mapa de símbolos y propietarios, localizar `SoftwareRenderer`, `ShapeTransition`, `Spring`, `LivingMotion`, `OrganicTendrils`, `OrganicDesk`, `ReachHub`, `ResidentDesktop`, `DesktopRuntime`, hit-map, bridge nativo y servicios reales. Capturar antes de cambiar: avatar libre, tentáculos, menús, tema claro/oscuro, escalas, varios monitores. No tocar baseline hashes. Las restricciones de preservación y release están explicitadas por el propio repositorio. citeturn992270view0

**Exploración de diseño.** Implementar tres composiciones visuales aisladas usando datos reales o fixtures claramente marcados: Neutral Monolith, Theme Adaptive e Identity Accent. Comparar legibilidad, contraste, densidad, reconocimiento, compatibilidad con temas y coste de implementación. No seleccionar por gusto; documentar decisión en ADR. La salida debe incluir capturas a escala 100/150/200%, fondos luminosos/oscuros y Reduce Motion.

**Vertical slice.** Es el gate de producto más importante:

```text
Avatar real personalizado
    ↓ drag to top
Tentáculos actuales se retraen
    ↓
Preview de docking
    ↓
Notch compacto completamente visible
    ↓
Una actividad/función REAL de AXX
    ↓
compact → expanded
    ↓
acción real + estado real
    ↓
contracción sin terminar actividad
    ↓
undock
    ↓
avatar exacto restaurado
    ↓
tentáculos disponibles otra vez
```

No avanzar si este recorrido tiene flicker, roba foco, deja hit regions fantasma, pierde estado o altera la personalización.

**Hardening nativo.** Sólo después: multimonitor, DPI, coordenadas negativas, taskbar en distintos bordes, monitor desconectado, sleep/resume, fullscreen, cambio de desktop virtual, alt-tab, focus restore y crash recovery. El código actual ya contempla virtual desktops y recuperación en `resident.rs`, por lo que deben extenderse esos mecanismos y sus tests, no duplicarlos. citeturn992270view2

**Experiencias.** En orden: Orbit interno → Parallel → Portal → Intent → Stage. Es una secuencia deliberada: Orbit/Parallel validan composición sin introducir drag/drop; Portal añade input externo; Intent añade capability resolution; Stage añade una segunda superficie y por tanto mayor complejidad de foco/windowing.

**Integración restante.** Media, voz/chat, agentes, transferencias, Magic Pen y settings se proyectan mediante los mismos contratos. Una función sólo entra al notch cuando haya handler real y representación compacta coherente.

**QA final.** Matriz visual y funcional de las 24 formas × 9 paletas × 4 acabados **sólo si el inventario actual vuelve a confirmar que esas cardinalidades siguen vigentes**. No congelar números de una auditoría anterior si HEAD ha cambiado. Para cada combinación no hace falta probar manualmente cada función, pero sí verificar identidad snapshot/restore, paleta/material readback y screenshots seleccionados por familias de formas.

Los gates deben ser:

| Gate | Condición de salida |
|---|---|
| **Identity** | Dock/undock devuelve exactamente el estado persistente y visual válido. |
| **Zero Tendrils Docked** | 0 draw calls/links/hit regions de OrganicTendrils durante todos los estados docked. |
| **Visibility** | Compact siempre reconocible cuando la política permite visibilidad. |
| **State Integrity** | Transiciones canceladas/reentrantes no producen estados imposibles. |
| **Activity Integrity** | Cambiar de superficie no reinicia ni duplica una actividad. |
| **Input** | Sin ghost hits; keyboard/focus/drag tienen rutas correctas. |
| **Native Geometry** | DPI, multimonitor y coordenadas negativas pasan pruebas. |
| **Motion** | Sin saltos detectables por retarget; Reduce Motion funcional. |
| **Performance** | Sin regresión fuera del umbral fijado tras baseline, p95/p99 documentados. |
| **Accessibility** | teclado, focus visible, UIA, contraste y motion alternativo verificados. |
| **Companion** | protocolo y validación móvil sin regresión. |
| **Baseline** | hashes no manipulados para aprobar; cambios autorizados con evidencia. |
| **Release Safety** | build/test/install/publish siguen procedimiento del repo; esta investigación no publica. |

Pruebas mínimas nuevas:

```text
notch_state_machine:
  free -> approach -> retract -> dock -> undock
  interrupt each transition at 10%, 50%, 90%
  repeated dock/undock x500
  stale event rejection
  duplicate event idempotency
  monitor loss mid-transition
  fullscreen policy change mid-expanded

tendril_invariant:
  assert docked => links.length == 0
  assert docked => tendril draw path not invoked
  assert docked => no tendril interactive region
  assert undockComplete => free policy may re-enable

geometry:
  DPI 100/125/150/175/200
  negative monitor coordinates
  portrait/landscape
  top/bottom/left taskbar
  display disconnect/reconnect
  resolution/scale change while expanded

visual:
  compact/ambient/peek/expanded
  light/dark/high contrast
  bright/dark/textured wallpaper
  single/dual/overflow activities
  approval/error/offline/empty
  localized long strings
  125%/150% text scale where applicable

input:
  pointer
  keyboard only
  drag alternative
  focus restore
  click-through outside active region
  rapid enter/leave
  external drag cancel/drop

runtime:
  determinate progress from real source
  unknown progress stays indeterminate
  approval
  cancellation
  backend disconnect/reconnect
  stale cursor
  no automatic replay of uncertain effect
```

No hay resultados de estos tests en esta investigación. Son criterios y casos que el implementador debe ejecutar.

La revisión artística debe puntuar cada build de 0–5 en **silhouette, hierarchy, optical balance, contrast, rhythm, density, motion continuity, spatial stability, input clarity, AXX identity y restraint**. Cualquier dimensión <4 bloquea la aceptación visual, aunque compile. “Funciona” no equivale a “producto terminado”.

## Directiva maestra autónoma para Codex o agente implementador

El siguiente bloque está diseñado para ser entregado directamente al agente. Está deliberadamente escrito para **obligarlo a investigar y mejorar la propuesta**, no para convertirlo en ejecutor literal.

```text
AXX NOTCH INTEGRATION / PROJECT SINGULARITY
PRODUCTION IMPLEMENTATION DIRECTIVE

Repositorio principal:
https://github.com/luigilaxmaster-coder/AXX

Referencia pública secundaria:
https://github.com/JustKoal/Dynamic-releases

OBJETIVO

Evoluciona AXX con una modalidad de notch residente para Windows 11 que tenga
calidad de producto premium, una dirección artística propia y una integración
nativa, fluida, reversible y técnicamente verificable.

No copies Apple, Dynamic, Dynamic Island ni otras aplicaciones. Estúdialas sólo
como referencias de problemas, principios de interacción y nivel de ejecución.

Tu responsabilidad no consiste en implementar literalmente este documento.
Actúa como un equipo sénior compuesto por product design, motion design,
graphics engineering, frontend, Windows/Win32, Tauri/WebView2, arquitectura,
accesibilidad, performance y QA.

Antes y durante cada fase:

1. inspecciona el código real;
2. fija hechos y evidencia;
3. detecta errores o contradicciones de esta directiva;
4. compara alternativas;
5. selecciona una solución superior cuando puedas demostrarla;
6. implementa incrementalmente;
7. mide;
8. revisa críticamente;
9. corrige;
10. documenta evidencia.

No suavices un problema para poder declarar éxito.

======================================================================
INVARIANTES NO NEGOCIABLES
======================================================================

A. DOS PRESENTACIONES, UN RUNTIME

AXX dispone de una presentación LIBRE y una presentación DOCKED/NOTCH.

FREE:
- avatar 3D real;
- forma seleccionada;
- paleta seleccionada;
- material/finish seleccionado;
- escala seleccionada;
- movimiento configurado;
- tentáculos permitidos según comportamiento actual;
- superficies orgánicas permitidas cuando correspondan.

DOCKED:
- notch convencional de alta calidad;
- completamente visible cuando la política de visibilidad lo permite;
- reconocible sin depender de hover;
- controles internos;
- estados compactos y expandidos;
- CERO tentáculos.

El notch NO es el avatar estirado horizontalmente.
El notch NO necesita mostrar el avatar 3D completo.
El notch NO necesita extensiones orgánicas para cada función.

B. CERO TENTÁCULOS ACOPLADO

physicalMode == docked
=> OrganicTendrils no dibuja conexiones
=> no existen raíces
=> no existen segmentos
=> no existen hit regions de tentáculos
=> no existen líneas visuales que los simulen.

Esta regla aplica a compact, ambient, peek, expanded, Portal, Orbit,
Parallel, Intent, Stage-trigger, media, chat, agentes, transferencias,
settings y cualquier estado futuro mientras la presentación continúe docked.

Los tentáculos sólo pueden existir en FREE.

C. TRANSICIÓN REVERSIBLE

free
→ approach
→ retracting
→ docking
→ docked

Si existen tentáculos, RETRAERLOS antes de completar docking.

docked
→ undocking
→ free

Al volver a free, restaurar exactamente identidad y presentación válidas.
No guardar una nueva forma, escala, paleta o material como efecto secundario.

Tomar un snapshot explícito de lo necesario para restauración.
No asumir nombres/campos: audita primero el modelo real.

D. UNA AUTORIDAD DE EJECUCIÓN

El notch es una proyección.
No implementa un segundo CommandService, ActionExecutor, Agent Runtime,
Transfer Runtime, Media Runtime, Voice Runtime ni Activity Scheduler.

Reutiliza los servicios reales.
No dupliques acciones según superficie.
No generes porcentajes ficticios.
No simules resultados.
No auto-reintentes efectos inciertos.

E. LÍNEA GRÁFICA AXX

Reutiliza el sistema visual, preferencias y tokens existentes cuando sean
compatibles.

No impongas:
- cápsula negra genérica como única identidad;
- gradients arbitrarios;
- neon;
- glassmorphism indiscriminado;
- dashboard de tarjetas;
- páginas web comprimidas dentro del notch.

El resultado debe reconocerse como AXX incluso sin logotipo.

F. WINDOWS PRIMERO

Plataforma de aceptación inicial:
Windows 11 + Tauri + WebView2 + Win32.

Android Companion debe permanecer compatible.

macOS es una adaptación futura separada.
No introduzcas Swift/AppKit en la rama Windows para “seguir el concepto”.

======================================================================
FASE DE ARQUEOLOGÍA OBLIGATORIA
======================================================================

ANTES DE EDITAR:

1. git status
2. registrar branch y HEAD SHA completo
3. leer AGENTS.md completo
4. leer docs/RELEASING.md
5. leer docs/mobile/COMPATIBILITY-PROTOCOL.md
6. leer mobile/design-baseline.json
7. localizar todos los AGENTS.md adicionales aplicables
8. revisar cambios locales y no sobrescribirlos
9. capturar baseline visual y funcional
10. registrar tests existentes y comandos exactos

Recupera COMPLETO 1.AXX/Axx.html mediante blob/raw si la interfaz de GitHub lo
trunca.

Vuelve a localizar por símbolo, no por número histórico de línea:

- SoftwareRenderer
- CpuRaster
- ShapeTransition
- Spring
- LivingMotion
- OrganicTendrils
- fitTendrilLink
- organicCurve
- flowArmRadius
- OrganicDesk
- ReachHub
- ResidentDesktop
- DesktopRuntime
- hit-map/updateHitMap o equivalente actual
- bridge nativo de hit-testing
- renderer/material/palette/shape ownership
- avatar customization/persistence

Inspecciona además:

- 1.AXX/scripts/interface-theme.js
- 1.AXX/scripts/optical-glass.js
- 1.AXX/scripts/avatar-remote.js
- mobile avatar customization/runtime relevante
- src-tauri/src/resident.rs
- src-tauri/src/lib.rs
- backend/commands.py
- backend/actions/executor.py
- backend/connect/registry.py
- backend/connect/service.py
- command-library.js
- chat
- voice
- agents
- Acts/Code Studio
- Magic Pen
- media
- transfers
- Companion/mobile
- tests relacionados.

Produce docs/notch/AXX-NOTCH-CODE-AUDIT.md con:

- SHA inspeccionado;
- ruta;
- símbolo;
- responsabilidad;
- propietario de estado;
- inputs/outputs;
- dependencia;
- riesgo;
- punto de extensión recomendado;
- evidencia.

CLASIFICA cada afirmación:
VERIFIED
OBSERVED
INFERRED
ASSUMPTION
UNKNOWN
CONTRADICTED

No programes sobre una ASSUMPTION crítica.

======================================================================
INVESTIGACIÓN DE DISEÑO
======================================================================

Antes del diseño definitivo, crea al menos tres exploraciones REALES:

A. NEUTRAL MONOLITH
Base oscura/neutra altamente legible.

B. THEME ADAPTIVE
Superficie que usa el sistema light/dark/customization de AXX.

C. AXX IDENTITY ACCENT
Base neutral estable + acentos sutiles derivados de identidad del avatar.

Compara:

- reconocimiento;
- legibilidad;
- contraste;
- integración AXX;
- compatibilidad con wallpapers;
- light/dark;
- high contrast;
- costo de render;
- complejidad;
- accesibilidad;
- mantenimiento.

No selecciones una opción sólo por preferencia estética.

Por defecto, investiga C como candidata principal, pero cámbiala si la evidencia
del prototipo demuestra una alternativa superior.

Crea ADR con comparación y decisión.

======================================================================
ANATOMÍA DEL NOTCH
======================================================================

Diseña:

- top seam;
- shell;
- identity/status spine;
- leading lane;
- trailing lane;
- expansion body;
- overflow;
- focus indicator;
- drag affordance cuando corresponda.

El shell compacto debe permanecer visible sin hover.

No debe quedar cortado por límites de monitor.
No debe tapar más aplicación de la necesaria.
No debe bloquear input fuera de su silueta.

Usa DIP/lógica de escala, no px rígidos.

Define tokens:
- compact width min/preferred/max;
- compact height;
- peek min/max;
- expanded min/max;
- inset;
- gap;
- corner geometry;
- optical alignment;
- type roles;
- control density;
- hit area;
- motion;
- material;
- status/attention.

Los valores iniciales son hipótesis.
Valídalos a 100/125/150/175/200% DPI y en diferentes resoluciones.

No presentes valores de Apple/iOS/macOS como requisitos Windows.

======================================================================
MATERIALES Y VISUAL
======================================================================

No simules blur nativo inexistente mediante una captura falsa del fondo.

Prueba en la combinación Tauri/WebView2/Windows real:
- background transparency;
- window transparency;
- clipping;
- border artifacts;
- text antialiasing;
- high contrast;
- wallpaper claro;
- wallpaper oscuro;
- HDR si hay hardware;
- reduce transparency/equivalente aplicable.

Si un efecto no es robusto, utiliza fallback opaco/refinado.

La identidad del avatar puede influir sutilmente en:
- accent color;
- highlight;
- small identity glyph;
- progress treatment.

No conviertas el material 3D del avatar en fondo de todo el notch.

======================================================================
MODELO DE ESTADOS
======================================================================

NO construyas un enum combinatorio gigante.

Separa dimensiones:

PhysicalMode:
free / approach / retracting / docking / docked / undocking

SurfaceSize:
compact / ambient / peek / expanded / stage

ContentMode:
home / media / orbit / portal / parallel / intent /
chat / voice / agents / transfer / settings

Attention:
idle / active / progress / completed / approval / error / offline

Interaction:
none / pointer / hoverIntent / keyboard / dragEnter /
dragActive / focused

Visibility:
normal / presentation / fullscreenSuppressed /
privacySuppressed / userHidden

Ajusta nombres a arquitectura real.

Define eventos, guards, efectos, cancelación, timeout, reentrada,
persistencia, recovery e invariantes.

Crea tests de transición.

======================================================================
EXPERIENCIAS
======================================================================

ORBIT:
En notch, es composición interna de actividades.
No usa tentáculos.
No requiere geometría circular.
Una actividad puede expandirse sin expandir todas.

PORTAL:
Drag enter cambia temporalmente la superficie a destinos compatibles reales.
Resolver compatibilidad desde capacidades reales.
Drag leave restaura exactamente presentación previa.
Drop inicia una acción por la autoridad existente.
No ejecutar por hover.

PARALLEL:
Representa actividades concurrentes.
No crea ejecutores.
No reinicia tareas.
Agrupa overflow.
Conserva activity/session IDs.

INTENT:
Campo de objetivo + capacidades compatibles reales.
No ofrecer acciones no disponibles.
Permisos y approvals continúan siendo responsabilidad del runtime.

STAGE:
Workspace temporal para una tarea que necesita más espacio.
NO requiere tentáculo.
La sesión continúa siendo la misma.
El notch conserva una representación compacta de la tarea.
Cerrar/desacoplar Stage no termina la actividad.

MEDIA / CHAT / VOICE / AGENTS / TRANSFERS / MAGIC PEN:
Crear representaciones específicas, compactas y semánticas.
No meter todas las funciones en una dashboard.

======================================================================
MOTION SYSTEM
======================================================================

Las transiciones deben ser:
- interruptibles;
- retargeteables;
- continuity-preserving;
- input responsive;
- accesibles.

Mantén para cada canal:
value
velocity
target
spring/easing params.

Al cambiar objetivo:
NO reiniciar velocity a cero salvo que esté deliberadamente justificado.

Investiga y mide:
- C0 continuity;
- C1 perceptual continuity;
- overshoot;
- settle time;
- input latency;
- layout stability.

Dock storyboard mínimo:

free
→ approach response
→ retract tentacles
→ native positioning
→ notch shell formation
→ compact content reveal

Undock:
expanded if needed
→ compact
→ detach shell
→ restore avatar snapshot
→ validate body geometry
→ enable free tentacles

No usar tentáculos como puente visual durante docking final.

Decide por evidencia entre:
1. deformación real del avatar;
2. compositing/masking/crossfade;
3. híbrido.

No deformes malla sólo porque “morphing” suene más sofisticado.

REDUCE MOTION:
- disminuir desplazamiento;
- eliminar rebote;
- usar crossfade/cambio breve;
- conservar significado y control.

======================================================================
NATIVE WINDOWS INTEGRATION
======================================================================

Extiende la autoridad residente existente si es viable.
No crees otra autoridad de ventana sin demostrar necesidad.

Diseña revisioned geometry:

desired geometry revision
→ native apply
→ native ack
→ webview layout
→ hit regions same revision

No aceptar hit maps obsoletos.

Resolver:
- PMv2/per-monitor DPI;
- 100–200%;
- coordenadas negativas;
- múltiples monitores;
- taskbar en distintos bordes;
- cambios de resolución;
- cambio de escala en ejecución;
- monitor hot unplug;
- sleep/resume;
- virtual desktops;
- fullscreen;
- alt-tab;
- no-activate;
- keyboard focus;
- z-order;
- click-through;
- external drag/drop;
- recovery.

VISIBILITY POLICY:
Requisito del usuario:
el notch es visible/legible en operación normal.

Decisión a investigar:
no imponer always-on-top sobre fullscreen, juegos o privacidad.

Implementa una policy configurable:
normal
fullscreen suppression
gaming suppression
privacy/user hide.

No ocultes automáticamente basándote en señales poco fiables sin explicar
y permitir configuración.

======================================================================
RUNTIME / ACTIVITY PROJECTION
======================================================================

Crea un adaptador mínimo de proyección, no otro runtime.

Cada proyección debe incluir sólo datos reales:
- activity ID;
- session ID si existe;
- status;
- progress real o indeterminate;
- title/subtitle;
- available actions;
- revision/cursor;
- timestamps necesarios.

No inventes progreso.

Si un efecto externo queda en estado incierto:
NO retry automático desde la UI.
Consulta/reconcilia mediante contratos existentes.

Mantén idempotencia/operation IDs del backend.

Una actividad continúa aunque:
- notch se contraiga;
- cambie content mode;
- Stage se abra/cierre;
- usuario cambie monitor;
- notch se oculte temporalmente;
- avatar vuelva a free.

======================================================================
VERTICAL SLICE OBLIGATORIO
======================================================================

Antes de ampliar funcionalidades, demuestra en Windows real:

1. iniciar AXX con personalización real;
2. avatar visible en free;
3. tentáculos libres si corresponden;
4. arrastrar hacia top edge;
5. intención/capture de docking;
6. retraer tentáculos;
7. formar notch;
8. notch compact totalmente visible;
9. cero tentáculos;
10. mostrar UNA capacidad real;
11. expandir;
12. ejecutar/interactuar con la capacidad real;
13. mostrar estado/progreso real;
14. contraer sin reiniciar actividad;
15. undock;
16. recuperar avatar;
17. verificar forma/paleta/material/escala;
18. reactivar tentáculos sólo en free;
19. confirmar continuidad de actividad;
20. confirmar foco e input correctos.

Si falla cualquiera de los invariantes P0:
NO ampliar a Orbit/Portal/Parallel/Intent/Stage.

======================================================================
ORDEN DE IMPLEMENTACIÓN
======================================================================

PHASE A — baseline + audit
PHASE B — design explorations + ADR
PHASE C — state coordinator
PHASE D — native geometry + hit-test synchronization
PHASE E — dock/undock vertical slice
PHASE F — compact/peek/expanded with one real capability
PHASE G — hardening native
PHASE H — Orbit
PHASE I — Parallel
PHASE J — Portal
PHASE K — Intent
PHASE L — Stage
PHASE M — media/chat/voice/agents/transfers/Magic Pen integrations
PHASE N — accessibility/performance/long-run validation
PHASE O — release readiness only when authorized

Para CADA fase entrega:
- archivos modificados;
- símbolos modificados;
- razón;
- tests ejecutados;
- resultados;
- capturas;
- mediciones;
- problemas;
- riesgos;
- rollback;
- estado:
  VERIFIED / PARTIAL / BLOCKED.

======================================================================
TESTS
======================================================================

Añade unit/integration/native/UI/visual/performance tests.

OBLIGATORIOS:

- zero tentacles for every docked state;
- tentacles return only after free is valid;
- exact identity restore;
- transition interruption at multiple points;
- stale event rejection;
- no duplicate action execution;
- no fake determinate progress;
- geometry revision == hit revision;
- no ghost hit region;
- keyboard-only operation;
- visible focus;
- drag alternative where applicable;
- fullscreen policy;
- DPI 100/125/150/175/200;
- negative monitor coordinates;
- monitor disconnect;
- sleep/resume;
- backend disconnect/reconnect;
- localization overflow;
- high contrast;
- reduced motion;
- light/dark;
- Companion regression.

Si HEAD confirma 24 formas × 9 paletas × 4 materiales, genera una matriz
automatizada de identidad/restore para esas combinaciones.
No hardcodees esas cantidades si el inventario actual difiere.

Ejecuta los tests de tentáculos y apariencia existentes localizados en HEAD.
No afirmes resultados de pruebas que no hayas ejecutado.

======================================================================
PERFORMANCE
======================================================================

Antes de optimizar:
medir baseline.

Registrar:
- idle CPU;
- active CPU;
- working set;
- memory growth;
- frame p50/p95/p99;
- input-to-visual latency;
- activity-event-to-visual latency;
- native geometry ack;
- dropped frames;
- long-session behavior.

60 Hz = 16.67 ms/frame.
120 Hz = 8.33 ms/frame.

No utilices esos números como permiso para consumir el frame completo.
Fija el gate después de medir baseline y hardware.

Documenta:
CPU/GPU
Windows build
display refresh
DPI
monitor count
power state
WebView2 runtime
AXX commit.

======================================================================
ACCESSIBILITY
======================================================================

Proveer:
- keyboard traversal;
- visible focus;
- UI Automation semantics;
- non-color state cues;
- reduced motion;
- high contrast;
- adequate hit areas;
- alternative to hover;
- alternative to dragging where viable;
- localization;
- announcements for important state changes.

No sacrifiques accesibilidad para conseguir una cápsula visual más pequeña.

======================================================================
QUALITY GATES
======================================================================

G0 Repository integrity
G1 Identity preservation
G2 Zero tentacles docked
G3 State-machine correctness
G4 Native geometry and hit testing
G5 Visual visibility/legibility
G6 Motion continuity
G7 Activity/runtime integrity
G8 Accessibility
G9 Performance
G10 Companion compatibility
G11 Regression
G12 Long-run/native acceptance
G13 Release readiness

Un gate sólo pasa con evidencia.

======================================================================
VISUAL REVIEW RUBRIC
======================================================================

Puntúa 0–5:

- silhouette;
- hierarchy;
- optical alignment;
- typography;
- contrast;
- spacing/rhythm;
- density;
- material restraint;
- AXX identity;
- state clarity;
- motion continuity;
- spatial stability;
- focus/input clarity;
- accessibility;
- visual regression.

Cualquier criterio <4 requiere revisión antes de cerrar la fase visual.

Haz review a:
100%
125%
150%
175%
200%
DPI/scale,
fondos claros/oscuros/texturados,
light/dark/high contrast,
strings largas,
una/dos/múltiples actividades,
idle/progress/completed/approval/error/offline.

======================================================================
SELF-REVIEW LOOP
======================================================================

Después de cada incremento:

ARCHITECTURE REVIEW
¿Duplicamos una autoridad?
¿Hay nuevo estado sin propietario?

PRODUCT REVIEW
¿La función reduce fricción?
¿Es necesaria en notch?

DESIGN REVIEW
¿Parece AXX o una dashboard genérica?

MOTION REVIEW
¿Puede interrumpirse?
¿Conserva posición y velocidad?

WINDOWING REVIEW
¿Hay focus theft, flicker o ghost input?

PERFORMANCE REVIEW
¿Hay regresión medida?

ACCESSIBILITY REVIEW
¿Puede operarse sin hover/drag/motion?

RUNTIME REVIEW
¿La UI muestra sólo estados reales?

REGRESSION REVIEW
¿Avatar, tentáculos libres, voz, chat, Magic Pen, agentes,
transferencias y Companion siguen funcionando?

Si una respuesta es negativa:
CORREGIR antes de ampliar alcance.

======================================================================
REPO / RELEASE SAFETY
======================================================================

Trabaja en rama aislada.

No:
- sobrescribas cambios del usuario;
- regenere hashes de design-baseline para hacer pasar gates;
- publiques;
- crees release;
- instales sobre la copia de producción;
- cambies versiones;
sin seguir las instrucciones actuales del repo y autorización aplicable.

Si se autoriza una versión futura:
seguir AGENTS.md y docs/RELEASING.md exactamente.

Esta tarea de implementación termina con una candidata y evidencia,
NO con publicación automática.

======================================================================
DEFINITION OF DONE
======================================================================

El notch sólo está listo cuando:

- se ve intencionalmente diseñado;
- es visible en operación normal;
- no depende de hover para existir;
- cero tentáculos aparecen acoplado;
- el avatar vuelve exacto;
- las actividades no reinician por cambiar superficie;
- no existe runtime duplicado;
- el input fuera de la forma no queda bloqueado;
- foco/teclado/drag son correctos;
- DPI/multimonitor están aceptados;
- Reduce Motion y high contrast funcionan;
- performance está medida;
- no hay regresión crítica;
- Companion continúa compatible;
- los tests están registrados;
- limitaciones están declaradas.

No declarar DONE porque “compila”.

======================================================================
ENTREGABLES
======================================================================

1. AXX-NOTCH-CODE-AUDIT.md
2. AXX-NOTCH-PRODUCT-DECISION.md
3. AXX-NOTCH-DESIGN-SYSTEM.md
4. AXX-NOTCH-STATE-MODEL.md
5. AXX-NOTCH-MOTION-SPEC.md
6. AXX-NOTCH-NATIVE-WINDOWING.md
7. AXX-NOTCH-ACTIVITY-PROJECTION.md
8. AXX-NOTCH-ACCESSIBILITY.md
9. AXX-NOTCH-PERFORMANCE-BASELINE.md
10. AXX-NOTCH-TEST-PLAN.md
11. ADRs de decisiones relevantes
12. vertical slice funcional
13. capturas reales before/after
14. resultados de tests
15. métricas
16. inventario de archivos modificados
17. rollback documentado
18. final acceptance report

Diferencia siempre:
DESIGNED
IMPLEMENTED
TESTED
NATIVE-VALIDATED
RELEASED

Nunca mezcles esas categorías.

======================================================================
MANDATO FINAL
======================================================================

No trates este documento como una orden estática.

Tu tarea es mejorar AXX.

Si encuentras:
- una decisión visual superior;
- un algoritmo más estable;
- una forma más simple de reutilizar infraestructura;
- un conflicto con el código real;
- un requisito técnicamente incorrecto;
- una mejora de accesibilidad;
- una forma de reducir latencia o complejidad,

propón la alternativa, demuestra por qué es mejor y úsala si conserva los
invariantes no negociables.

No cambies los invariantes del usuario:
NOTCH LIMPIO ACOPLADO.
CERO TENTÁCULOS ACOPLADO.
TENTÁCULOS SÓLO FUERA.
IDENTIDAD DEL AVATAR PRESERVADA.
TRANSICIÓN REVERSIBLE.
UNA AUTORIDAD DE ACTIVIDADES/SESIONES/ACCIONES.
WINDOWS PRIMERO.
LÍNEA GRÁFICA AXX.

El estándar de revisión es el rigor de un equipo sénior de diseño e ingeniería
de producto de primer nivel, comparable en atención al detalle con Apple,
sin copiar su marca, sus activos ni afirmar aprobación o certificación Apple.
```

Esta iteración corrige el punto más débil de las propuestas anteriores: **la diferenciación de AXX ya no depende de llenar el notch de tentáculos ni de transformar cada herramienta en una extensión orgánica**. La diferenciación pasa a residir en la continuidad entre dos expresiones coherentes del mismo producto: un avatar libre, tridimensional y orgánico cuando hay espacio para jugar con él; y un notch disciplinado, compacto, legible y extremadamente pulido cuando AXX está acoplado.

La referencia de Apple aporta principios de jerarquía, moderación material, precisión tipográfica y motion cancelable, pero no dicta la implementación Windows. Microsoft y WebView2 son las autoridades técnicas para DPI, foco, accesibilidad y superficie nativa de la plataforma inicial. Dynamic demuestra públicamente que un asistente Windows puede combinar estados compactos, personalización, Companion, fullscreen awareness y herramientas contextuales, pero no ofrece código público suficiente para justificar copiar su arquitectura interna. citeturn900839view0turn900839view1turn202026view12turn992270view8turn992270view4

**Estado de evidencia:** esta investigación ha inspeccionado documentación y archivos públicos actuales de AXX, Dynamic, Apple, Microsoft, Tauri y W3C, además de las especificaciones y auditorías aportadas. No se modificó el repositorio, no se compiló AXX, no se ejecutó el notch propuesto y no se realizó aceptación física en Windows. La primera obligación del agente implementador es fijar el HEAD exacto que vaya a modificar, recuperar `Axx.html` completo, actualizar el mapa de símbolos y medir el baseline antes de convertir cualquier propuesta de este informe en hecho implementado.