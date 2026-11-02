# Ampliación solicitada de Axx — 2 de noviembre de 2026

La petición del usuario incorpora el inventario adjunto como alcance funcional. Sus afirmaciones sobre HeyClicky no se consideran evidencia de arquitectura ni de disponibilidad de Axx.

## Entrega en curso

0.22.36 integra el trabajo de Spatial Intelligence sobre la fuente de 0.22.35 contrastada con su recibo de compilación y el main actual. La instalación y aceptación nativa están en curso. Los cambios posteriores de otras copias no se incorporan sin revisión.

## Recorrido espacial exigido

1. Seleccionar una imagen en una aplicación y conservar captura, revisión, ventana, conversación y pieza seleccionada en una sesión.
2. Elegir una conexión existente GPT/Codex o Anthropic sin fallback silencioso.
3. Compilar planes declarativos de escena, diagrama y overlay con validación y presupuestos.
4. Construir ensamblajes procedurales reutilizables con piezas identificables y fidelidad explícita.
5. Manipular cámara, piezas y anotaciones localmente sobre el escritorio, conservando anclaje y estado.
6. Narrar pasos con subtítulos, resaltado, pausa, interrupción y reanudación en la misma pieza.
7. Admitir órdenes como «separa esta pieza», preguntas contextuales y restauración desde historial.
8. Convertir una explicación en guía: observar la aplicación, verificar postcondiciones y preparar acciones mediante CommandService cuando el usuario las solicite.
9. Resolver requisitos locales, permisos y conexiones faltantes con acciones concretas y comprobar la salida antes de declarar disponibilidad.

## Sistemas existentes que se deben reutilizar

- `MagicPenService`, `presentation_plan`, `guide_plan` y el visor local: captura, historial, planes/parches, selección de piezas, narración y guía UIA.
- `CodexProvider`, `InferenceAdapter` y el router: identidad de proveedor/modelo, autorización de coste, cancelación y esquemas.
- `CommandService`, `ActionExecutor` y sus contratos: preparación, aprobación, ejecución y postcondiciones.
- `ChatStore`, perfiles, SkillMemory, misiones y anticipación: contexto y progreso persistentes.
- `browser_bridge`: control CDP de un perfil preparado explícitamente; no equivale a una extensión instalada.
- Voz local y conversación: conservar un único dueño del micrófono y de la reproducción.

## Resto del inventario solicitado

- Agentes personales independientes, creación conversacional, colas, memoria por agente/proyecto y trabajos recuperables.
- Rutinas generales con zona horaria y administración conversacional.
- Integraciones con identidades separadas por cuenta y uso de MCP existente; la conexión de una cuenta requiere sus credenciales y permisos efectivos.
- Extensión Chrome con puente autenticado y permisos limitados a la pestaña/acción autorizada.
- Dictado contextual, diccionario personal basado en correcciones e inserción verificada.
- Continuidad entre widget/chat, previews documentales y onboarding con acciones comprobables.
- Actualización con recuperación y rollback comprobado.
- Cobertura de idiomas publicada solo cuando el motor y las pruebas la acrediten; no adoptar cifras comerciales del documento como soporte medido.

## Evidencia de cierre

Para cada capacidad se registran por separado código, contrato offline, integración IPC, inferencia real, instalación Windows y aceptación física. Una cuenta ausente, un idioma sin evaluar o un permiso denegado permanece como requisito explícito y no se declara verificado.
