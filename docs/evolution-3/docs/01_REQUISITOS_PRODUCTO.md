# 01 — Requisitos funcionales, UX y no funcionales

## 1.1 Visión de producto

AXX sigue siendo una presencia residente mínima. La vista principal muestra chat y entrada de voz. Herramientas y paneles siguen saliendo del cuerpo (Morph Reach), se arrastran y recuerdan tamaño/posición. Se añade un **modo de agente** dentro del sistema de chats existente, no otra interfaz que compita con él. Cada agente es una combinación de identidad, contexto, capacidad, permisos, recursos y sesión de ejecución; cada tarea puede delegarse y producir evidencia.

### Historias de usuario esenciales

- **UR-001:** convertir una conversación histórica en chat con agente sin cambiar `conversation_id`, mensajes, adjuntos, drafts, identidades de Connect ni operaciones pendientes.
- **UR-002:** crear agente desde `Chats y grupos` mediante asistente de perfil o lenguaje natural; previsualizar exactamente una de 24 formas AXX y nueve paletas; no crear mascota externa.
- **UR-003:** agente programador modifica un *worktree* mientras el usuario edita `main`, sin capturar el foco de la PC.
- **UR-004:** agente visual genera diagrama/escena, permite seleccionar objeto, editar parámetros sin reconstruir todo y comparar revisiones.
- **UR-005:** agente CAD crea STEP paramétrico con dimensiones introducidas y vista GLB, identifica inferencias geométricas cuando solo posee foto.
- **UR-006:** agente de navegador consulta páginas en perfil aislado; cookies y secretos no fluyen entre perfiles.
- **UR-007:** usuario puede exigir aprobación antes de que cualquier agente mueva el ratón en host; el motor debe poder decir «no disponible en segundo plano».
- **UR-008:** conversación de equipo muestra quién trabaja, artefactos, aprobaciones, errores y costes en una sola línea temporal.
- **UR-009:** delegación transmite un scope igual o más limitado, nunca un permiso nuevo.
- **UR-010:** cierre inesperado permite recuperar artefactos y trabajos conocidos; efectos `unknown` quedan bloqueados hasta reconciliación.
- **UR-011:** usuario puede importar plantilla de equipo sin credenciales ni grants heredados; las rutinas importadas comienzan desactivadas.
- **UR-012:** todos los modelos, voces, tamaños, permisos, políticas de fondo, canales y recursos se pueden configurar por agente y sobreescribir por sesión con scopes autorizados.
- **UR-013:** sincronización móvil sigue sin escalada: observar progreso de agente no equivale a controlar el PC.
- **UR-014:** usuario puede borrar memoria de agente sin que sobrevivan índices o caches de contenido retirado; TTL de chats preservado.

## 1.2 Modos de operación del agente

**Conversation:** responde sin ejecutar herramientas salvo interacciones existentes autorizadas. **Agent:** una identidad persistente con capacidad de planificar tareas y sugerir herramientas. **Team:** varios agentes en un chat, con coordinador, miembros y política de intervención. **Autonomous routine:** tarea programada/evento autorizado con controles propios; no activa automáticamente micrófono ni control host. **Code workspace:** agente activo dentro de un proyecto Git. **Magic Pen session:** agente vinculado a documento/captura con revisiones.

Regla de resolución: actividad directa sencilla pasa al agente activo; una tarea compleja puede usar TaskGraph; un equipo se activa por petición explícita, mención de agentes o reglas configuradas y transparentes. La ausencia de routing confiable vuelve al agente principal; nunca inventar un especialista o un modelo accesible.

## 1.3 Personalización «full»

**Apariencia:** forma ID canónica 0–23, paleta ID 0–8, material/preset validado, brillo, tamaño y movimiento dentro de límites del renderer; preview/aplicar/descartar reversible; miniatura cacheada; animación reduce-motion; sin sobrescribir identidad principal.

**Personalidad:** nombre, idioma, rol, estilo, instrucciones, objetivos, nivel de detalle, herramientas preferidas, preferencias de verificación, formato de salida. Instrucciones no autorizan herramientas.

**Inteligencia:** manual/automático, modelo por texto/visión/voz/programación, presupuesto de tokens/coste y latencia, context window compatible, conexiones autorizadas, fallback `ask|none|allowed-profile` explícito.

**Memoria:** agentes, proyectos, conversaciones y usuario global separados; documentación de retención y procedencia; indexado por scopes y revocación.

**Computadora:** `none|api|browser|window_background|foreground|isolated_vm|remote`, aplicaciones permitidas, carpetas permitidas, acceso red, perfil navegador, policy de foco `ask|queue|isolated|deny`, caducidad de grant, horas permitidas y cuota.

**Colaboración:** especialistas permitidos, cantidad máxima, profundidad máxima de delegación, permisos de lectura/escritura por artefacto, difusión limitada de contexto, revisión obligatoria en caso de datos sensibles.

**Recursos:** prioridad, concurrencia, RAM/GPU/cpu, máximo de jobs pesados, coste diario/mensual, inactividad y suspensión.

## 1.4 Diseño de interfaz, sin regresión

- La pestaña existente «Chats y grupos» pasa a «Chats y agentes» conservando todos los comandos anteriores.
- «Nuevo» ofrece «Chat», «Agente», «Equipo»; conversión reversible de chat a agente, nunca migración destructiva.
- La configuración se abre como panel emergente de AXX: no bandeja fija externa ni rediseño del avatar.
- Ficha de agente: miniatura real, rol, modelo, presupuesto, conectores, estado de trabajo, espacio, botón abrir, pausar y editar. Menú contextual: duplicar **solo configuración no secreta**, exportar, archivar, desvincular.
- Dentro del chat, respuestas llevan agente/operación, artefactos, solicitud de permiso, diff, preview, estado y factura estimada/real. No mostrar cadenas de pensamiento privadas ni fingir pasos.
- El Code Studio puede abrirse como panel grande separado y persistente, con pestañas y arrastre; al cerrarlo los cambios sin guardar permanecen en borradores seguros.
- El modo de cursor visual únicamente muestra eventos de movimiento/acción reales y se etiqueta como *cursor virtual del agente*, no como ratón físico adicional.

## 1.5 Objetivos medibles, no promesas

Los siguientes son **umbrales iniciales de aceptación por definir tras baseline**: regresión cero en funciones legadas; 100% de acciones mutantes registradas; 100% de grants auditables; 0 escrituras cruzadas a raíces no autorizadas; 0 acciones host foreground durante política `deny`; no duplicación de efectos en prueba de crash; progreso SSE reconectable; caída de worker sin pérdida de artefactos confirmados; 30 FPS mínimo para escena 3D de referencia en hardware objetivo *si la baseline lo permite*; métricas de latencia p50/p95 sin inventar límite absoluto.

Se deben publicar números con hardware, dataset, resolución, número de participantes y método. Un valor aislado de FPS no certifica estabilidad.

## 1.6 Fuera de alcance por defecto

- Reescribir AXX completamente en Rust o cambiar de Tauri a Electron.
- Reemplazar avatar o voces, subir muestras de voz, eliminar grupos existentes.
- Crear agentes que se autoasignen permisos ilimitados.
- Ejecutar automáticamente Python de modelos en el host sin revisión ni aislamiento real.
- Afirmar «cada agente tiene su propio ratón físico en la misma sesión Windows»; los workers pueden disponer de ratón **virtual en sesión aislada**.
- Autorizar pagos, publicaciones, emails o scripts peligrosos sin política correspondiente.
- Certificar precisión estructural/eléctrica/médica a partir de escenas conceptuales.
