# Instrucciones por función · axx-contracts-1

Integración original basada en la propuesta del 29 de octubre de 2026. No importa
los prompts de la colección externa ni sus personas, códigos, supuestos de
autorización o configuraciones de modelos. No entrena pesos ni registra nuevas
herramientas. Conserva la interfaz 3D y los servicios de ejecución existentes.

## Composición y transporte

La autoridad de composición está en [`backend/prompts.py`](../backend/prompts.py).
Los módulos son constantes Python para que el empaquetador y los recibos de
fuentes los incluyan sin introducir otro cargador de recursos o dependencias.
Cada composición entrega versión, modo, caracteres y SHA256. Se rechazan módulos
desconocidos y contratos que exceden 24.000 caracteres; nunca se corta su sufijo.

| Ruta | Instrucciones y rol | Datos y límites conservados |
| --- | --- | --- |
| Conversación nativa por API/local | Núcleo + conversación + idioma y estilo; un `system` compilado por el backend. | El perfil adicional pasa a referencia del usuario. Las capacidades no se deducen de una lista documental. |
| Streaming local nativo | El mismo compositor antes de llamar al transporte local existente. | No habilita `stream=true` en el router Python. |
| ChatGPT / Axx Connect | El backend emite `developerInstructions` con núcleo y herramientas registradas. | Los textos del navegador nunca se copian a ese rol. Conserva cuenta, modelo, permisos y prohibición de fallback. |
| Voz | Conversación + módulo de voz; primera frase útil, detalles técnicos escritos. | Conserva transcripción, cancelación, síntesis y segmentación existentes. |
| Planificación | Núcleo + planificación + contrato JSON actual. | Catálogo, recetas, aplicaciones y resultados previos van en el mensaje de datos. Ocho pasos y dos inferencias como máximo. |
| Traducción | Contrato exclusivo de traducción. | Solo texto traducido; órdenes incrustadas son texto fuente. En Connect sigue sin herramientas y en hilo aislado. |
| Magic Pen / percepción | Núcleo + percepción; distinguir visible, inferido e incierto. | No ejecuta acciones. Capturas y preguntas conservan su autorización y cancelación. |
| Computer Use por Connect | Núcleo + observación vigente + restricciones reales de herramientas Axx. | No concede sesiones; conserva foco, ventanas, tickets, geometría, revocación y comprobación posterior. |
| Taller de capacidades | Contrato exclusivo de propuesta JSON + definición actual. | Contratos registrados y definición anterior son datos. Pruebas, aprobación y activación siguen separados. |
| Contenido de una habilidad | Núcleo + producción del contenido solicitado. | No interpreta el texto producido como permiso de ejecución. |

El router sigue aceptando `system/user/assistant/tool`, sin añadir `developer` a
su API. Los adaptadores existentes de OpenAI, Anthropic y Ollama mantienen su
traducción de roles. El backend HTTP no acepta texto `developerInstructions` en
el compositor público. `POST /axx-api/prompts/compose` requiere el mismo bearer,
host y origen privado que los demás servicios; recibe únicamente modo, preferencias
acotadas y, para traducción, idiomas.

El navegador de desarrollo conserva su ruta anterior cuando no hay host nativo.
No se presenta ese modo como aceptación del escritorio.

## Presupuesto, preferencias y referencias

Las preferencias admiten seis estilos, idioma `auto/es/en` y 500 caracteres de
notas de tono. No seleccionan herramientas ni conceden autoridad. En Connect se
compilan en el backend; se incluyen en la identidad de la solicitud para impedir
reutilizar un ID con otra configuración. Las notas no se guardan en los eventos
de inferencia.

La UI nativa almacena hasta 16 composiciones estáticas en memoria para evitar
otra petición local en cada turno. La clave incluye modo, idiomas y preferencias;
no contiene historial, adjuntos, respuestas ni credenciales. La caché desaparece
al cerrar el WebView.

Connect descarta mensajes antiguos completos cuando necesita espacio. Conserva
íntegra la petición actual y sus referencias. Si ese conjunto o una traducción
excede 32.000 caracteres, devuelve un error antes de inferir; ya no corta por
caracteres una condición, destino o fragmento del texto fuente. El planificador y
el taller conservan sus límites de transporte propios. Las recetas opcionales
de más de 3.500 caracteres se omiten completas, en vez de enviar un JSON cortado.

Los documentos y el texto de pantalla siguen siendo datos no confiables. Esta
separación reduce la exposición a instrucciones incrustadas; un prompt no es
una garantía de que cualquier modelo resista cualquier ataque. La autoridad de
efectos permanece en el ejecutor.

## Interpretación, memoria y recuperación

Los ejemplos españoles distinguen buscar, reproducir y señalar. El parser de
secuencias reconoce también cláusulas que empiezan con `pon`, `ponme`, `poner` y
`observa`. Por ejemplo, «pon el mouse sobre Geist en Chrome y busca Faint en
YouTube» mantiene dos acciones. Las comillas y los textos literales de escritura
conservan su protección.

No se crea una segunda memoria. Se reutilizan `SkillMemory`, procedimientos,
`learning_plans`, el contrato de objetivo y los recibos del ejecutor. La referencia
de una receta identifica su origen y declara que no verifica la ejecución actual.
El estado previo y los pasos confirmados permanecen fuera del texto generado.
No se activa reanudación automática tras reinicio ni repetición de efectos
inciertos: el usuario conserva revisión y recuperación explícitas.

Las respuestas compactas y las animaciones siguen el estado comprobado de la
operación. No se cambia el renderer ni se añade una transferencia simulada. Morph
Reach, reproducción, guardado y recepción requieren su verificador de dominio;
una animación o una búsqueda no los acredita. Esta integración no añade un
protocolo de transferencia entre dispositivos.

## Evaluación de los 28 casos propuestos

La tabla identifica la comprobación disponible; los casos con modelos o hardware
no se declaran resueltos por la presencia de una frase en el prompt.

| Caso | Comprobación y alcance |
| --- | --- |
| E01 saludo | Ruta local de voz y clasificación existente; regresión de biblioteca UI. |
| E02 explicación | Negaciones/preguntas informativas protegidas en `test_command_language`. |
| E03 abrir app | Resolución contra inventario observado; aceptación de apertura requiere Windows. |
| E04 app ausente | Resolución sin aplicación inventada en `test_action_language`. |
| E05 errores ortográficos | Casos ASR y «yotune una cncion» con consulta limpia. |
| E06 búsqueda musical | Comando de búsqueda distinto de reproducción y resultado verificado por su ruta. |
| E07 reproducción | Ruta `axx.app.youtube` separada; el reproductor debe confirmar avance, artista y título pertinentes. No certifica cualquier pista. |
| E08 Geist en Chrome | Resolución de hover exacta y conservación de la cláusula siguiente. |
| E09 dictado traducido | Traducción aislada; el insertado físico y la ausencia de envío necesitan aceptación por campo. |
| E10 archivos ambiguos | Contratos `needs_input`; no se introduce un selector arbitrario por prompt. |
| E11 ventana cambiada | Regresiones existentes de observación y Computer Use. |
| E12 coordenadas antiguas | Tickets y observaciones vigentes; no se relajan validadores. |
| E13 timeout tras efecto | Recuperación por ID sin ejecutar de nuevo, probada por biblioteca UI. |
| E14 reinicio multietapa | Persistencia de objetivo y revisión en `test_goal_cycle`; sin autoejecución al arrancar. |
| E15 fallback automático | Router existente conserva políticas y objetivo; no se añade otra conmutación. |
| E16 modelo manual/Connect | Regresiones de proveedor exacto y prohibición de sustitución. |
| E17 capacidad inexistente | JSON `needs_input/unavailable/capability_request` y validadores del taller. |
| E18 documento hostil | Referencias separadas del `system`; regresión del adaptador. Obediencia de un modelo concreto requiere prueba adicional. |
| E19 pantalla hostil | Percepción sin acciones y política de destino; el ejecutor conserva autoridad. |
| E20 perfil fuera de alcance | Endpoint privado rechaza campos privilegiados; perfil libre queda como referencia. |
| E21 receta obsoleta | Compatibilidad de habilidades y resultados previos; receta no prueba efecto actual. |
| E22 JSON de plan | Pruebas de bindings, parámetros, límites y preparación sin efectos. |
| E23 órdenes en traducción | Contrato exclusivo y aislamiento sin herramientas. |
| E24 cancelación | Pruebas de respuesta tardía, operación pendiente y ausencia de ejecución posterior. |
| E25 red/modelo | Recuperación acotada del proveedor; errores no anuncian éxito. |
| E26 archivo/animación | UI no celebra un estado succeeded sin postcondiciones; hash/contenido final por ejecutor. |
| E27 petición larga | Prueba de Connect conserva sufijo y destino; exceso rechaza sin inferir. |
| E28 sin streaming | Router conserva rechazo explícito; UI nativa envía `stream:false` a esa ruta. |

Comandos de regresión principales:

```powershell
python -m unittest backend.tests.test_prompts backend.tests.test_command_language backend.tests.test_command_sequences backend.tests.test_action_learning backend.tests.test_goal_cycle backend.tests.test_capability_workshop backend.tests.test_commands_http backend.tests.test_magic_pen -q
python -m unittest backend.connect.tests.test_provider backend.connect.tests.test_provider_capability backend.inference.tests.test_hardened_router -q
node scripts/test-prompt-contracts.cjs
node scripts/test-quick-reply.cjs
node 1.AXX/scripts/test-command-library.cjs
```

## Medición y rollback

El backend registra únicamente versión, modo, caracteres y tiempo de composición;
Connect añade un evento `prompt/compiled` con hash, sin texto del prompt. Su recibo
ya conserva duración, selección efectiva y resultado. La UI mantiene en memoria
`Axx.promptContracts.lastTiming` con modo, resultado, primer texto útil y duración
total. No guarda audio, texto, historial ni claves en esa medición.

Primer texto útil no equivale a primer audio ni a objetivo comprobado. Esta
entrega no atribuye mejoras porcentuales, p50/p95 de voz ni una respuesta hablada
en dos segundos. Una comparación de modelos requiere la misma selección,
parámetros, hardware y repeticiones, separando inferencia, síntesis y acción.

La activación acompaña al binario versionado; no hay un editor de política
privilegiada ni descarga remota de prompts. Para rollback, detener Axx e instalar
el artefacto verificado anterior 0.22.23 siguiendo `RELEASING.md`, sin borrar el
perfil. La integración no migra ni elimina datos y conserva los formatos de
habilidades y recibos. Volver a fuentes anteriores exige reconstruir y publicar
con una nueva versión: nunca sustituir bytes de un asset existente.
