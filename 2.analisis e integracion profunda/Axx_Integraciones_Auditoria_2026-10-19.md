# Axx — Auditoría de integraciones y plan técnico

**Fecha de revisión:** 19 de octubre de 2026  
**Objetivo:** determinar qué aportan ai-memory, CLI-Anything, BitNet, IAI Personal Memory Engine e invisible_dots al Axx existente, cómo conectarlos y qué debe probarse antes de depender de ellos.  
**Equipo de referencia:** Acer Spin 3, Intel i7 de 11.ª generación, 16 GB de RAM, Iris Xe y Windows, según la información del usuario. No se midió ni se accedió a ese equipo durante esta revisión.

## 1. Decisión recomendada

La combinación es técnicamente viable por componentes. No existe una integración completa y verificada entre los cinco repositorios y Axx. El trabajo pendiente consiste en construir adaptadores, establecer una única autoridad para cada tipo de memoria y verificar resultados reales de las aplicaciones.

| Componente | Decisión para Axx | Papel |
|---|---|---|
| ai-memory | Primera integración recomendada | Memoria explícita de proyectos, hechos, decisiones, episodios y traspaso entre agentes |
| CLI-Anything | Adoptar por aplicación y operación verificadas | Adaptadores que Axx ejecuta mediante comandos estructurados |
| IAI Personal Memory Engine | Evaluación posterior | Memoria personal especializada, después de comprobar español y Windows |
| BitNet | Experimento opcional | Inferencia o embeddings locales con versiones y resultados validados |
| invisible_dots | Trabajador opcional aislado | Tareas dentro de una VM Linux; no sustituye el controlador nativo de Windows |

La interfaz de Axx, su personaje, menú radial, dictado y atajos siguen perteneciendo a Axx. Esta propuesta cambia sus servicios internos, no su diseño.

La primera entrega útil sería: Axx + ai-memory + dos o tres acciones reales + registro de procedimientos verificados. Las demás piezas deben incorporarse cuando resuelvan una limitación medida.

## 2. Qué se verificó y qué no

Se consultaron los repositorios mediante GitHub, documentación primaria, código de implementación, scripts de instalación y pruebas. Se ejecutaron comprobaciones puntuales sobre archivos descargados. No se instalaron estos proyectos en el ordenador del usuario ni se modificó su Axx.

| Evidencia | Resultado y alcance |
|---|---|
| Blender, núcleo del adaptador de CLI-Anything | Guardar/reabrir escena JSON y generar un script Python funcionó; no se produjo una imagen |
| ai-memory, cliente TypeScript | Pasaron cinco archivos de pruebas unitarias con transporte simulado; no equivale a probar el servidor Rust |
| ai-memory, pruebas de seguridad del cliente | 12 de 14 casos pasaron; dos no pudieron abrir un puerto local por la restricción EPERM del entorno |
| IAI, filtro de idioma | Español sin etiqueta fue aceptado; ruso sin etiqueta fue rechazado y con raw:ru fue aceptado |
| IAI, configuración de embeddings HTTP | Aceptó dimensiones 640 y 1024 sin cargar un modelo; no se probó un servidor BitNet conectado |
| BitNet | Inspección estática del runtime, servidor, submódulo y configuración del modelo; sin compilación ni inferencia |
| invisible_dots | Inspección de requisitos, configuración, SDK, proveedores, memoria y API; sin arrancar una VM |

La transformación de TypeScript para ejecutar las comprobaciones no incluyó un typecheck completo. Los tests con transporte simulado prueban el contrato del cliente, no la persistencia ni el comportamiento del servidor real.

### Versiones inspeccionadas

| Repositorio | Commit revisado | Fecha del commit |
|---|---|---|
| akitaonrails/ai-memory | b18f22a7c2f3068575c70d37f13d167fed3476bb | 2026-10-18 |
| HKUDS/CLI-Anything | 34f519533bc175d2fe287ab8316b0dd99bb9cc43 | 2026-09-22 |
| microsoft/BitNet | 0b341e582afbf9e1011f24744b554c96a3477eb5 | 2026-07-27 |
| CodeAbra/iai-personal-memory-engine | c400059ac860929936719fc70a66f57ee60c712c | 2026-09-16 |
| feder-cr/invisible_dots | ef69f5e19c1b46e41e743234fa5019e39442adcb | 2026-10-15 |

Son revisiones de main. Una release publicada puede no contener todos los cambios del commit inspeccionado. Deben conservarse también versiones de dependencias, modelos y programas ejecutados; fijar únicamente el repositorio principal no hace reproducible toda la instalación.

## 3. ai-memory: integración inicial

### Aportación real

Almacena páginas Markdown versionadas y utiliza SQLite para indexarlas. Está orientado a continuidad entre agentes de programación, pero ofrece una interfaz para otros programas. Puede guardar decisiones y hechos de Axx si Axx los escribe explícitamente. No requiere un LLM generativo para escribir, leer o buscar páginas. [M1] [M2]

La conexión programática principal es MCP Streamable HTTP en http://127.0.0.1:49374/mcp. Axx debe enviar el ámbito workspace/project y comprobar errores JSON-RPC y result.isError aunque el HTTP sea 200. Las escrituras se realizan mediante MCP; la superficie /api/v1 es de lectura y se habilita aparte. [M2]

| Necesidad | Herramienta existente |
|---|---|
| Guardar una página | memory_write_page |
| Buscar | memory_query |
| Leer la evidencia completa | memory_read_page |
| Dejar y recoger contexto de otra ejecución | memory_handoff_begin / memory_handoff_accept |
| Informar utilidad de un recuerdo | memory_feedback |

### Decisiones de configuración

El proyecto intenta usar embeddings locales MiniLM de 384 dimensiones por defecto. Para un ensayo sin descargar modelos, debe establecerse embedding_provider = "none" antes del primer arranque. Se mantiene la búsqueda lexical y otras vías sin vectores, a cambio de menor capacidad de encontrar paráfrasis. [M4]

~~~powershell
$env:AI_MEMORY_EMBEDDING_PROVIDER = "none"
ai-memory serve --transport http --enable-api
~~~

Este bloque supone que el binario ya está instalado. Si el asistente de instalación ya arrancó un servidor, comprobar su estado antes de iniciar otro. El instalador oficial y los modos Windows se documentan en [M3].

Windows nativo se presenta como experimental; WSL2 tiene un nivel de soporte superior. Deben instalarse los hooks en el entorno donde se ejecuta cada agente. Esto no obliga a mover Axx a WSL: una aplicación Windows puede comunicarse con un servidor por HTTP si la conectividad y la autenticación se configuran correctamente. [M3]

### Conexión a Axx

Usaría ámbitos separados para conocimiento de desarrollo y memoria personal explícita. Cada entrada llevaría fuente, fecha, proyecto, estado de vigencia y referencias a ejecuciones, como metadatos propios de Axx.

Para una aplicación TypeScript existe AiMemoryClient. El paquete aún no está publicado en npm: se construye desde companions/ai-memory-ts y se instala el tarball generado por npm pack. Para otros lenguajes puede emplearse MCP directamente. [M5]

Ejemplo de petición MCP, con un servidor inicializado y un cliente autorizado:

~~~json
{
  "jsonrpc": "2.0",
  "id": 10,
  "method": "tools/call",
  "params": {
    "name": "memory_write_page",
    "arguments": {
      "workspace": "axx",
      "project": "integration-lab",
      "path": "facts/visual-interface.md",
      "body": "Preferencia confirmada: las herramientas de Axx se despliegan alrededor del personaje."
    }
  }
}
~~~

Después se debe buscar la página, leerla y repetir la lectura tras reiniciar el servicio. Una respuesta recibida solo acredita almacenamiento cuando se comprueba su resultado. Las actualizaciones concurrentes deben usar expected_page_id o create_only según corresponda. [M2]

No activaría inicialmente consolidación generativa ni procesos de mejora continua: primero comprobaría persistencia, ámbitos y recuperación con datos pequeños y trazables.

## 4. IAI Personal Memory Engine: memoria personal con condiciones

IAI incorpora captura literal, búsqueda, recuperación temporal, contradicciones, refuerzo y perfiles. Usa un daemon y un servidor MCP sobre stdio. El entry point iai-mcp-server inicia un wrapper Node; Axx debe ser su cliente MCP. Instalar hooks de Codex o Claude no captura las conversaciones de una aplicación Axx independiente. [I1] [I2]

Su instalación requiere Python 3.11 o 3.12, Node y componentes nativos. Windows está marcado beta. Su embedder predeterminado es bge-small-en-v1.5, orientado al inglés. [I1] [I3]

### Ensayo de instalación Windows

En un directorio de ensayo y con Python 3.12 disponible:

~~~powershell
py -3.12 -m venv .venv-iai
.\.venv-iai\Scripts\python.exe -m pip install "iai-pme==3.2.3"
.\.venv-iai\Scripts\iai-mcp.exe crypto init
.\.venv-iai\Scripts\iai-mcp.exe daemon install
.\.venv-iai\Scripts\iai-mcp.exe daemon status
.\.venv-iai\Scripts\iai-mcp.exe doctor
~~~

La configuración de Axx debe usar la ruta absoluta del iai-mcp-server instalado en ese entorno. Los comandos anteriores son una receta de evaluación, no una instalación realizada durante esta revisión. La compatibilidad de la versión publicada debe comprobarse con su documentación. [I1]

### Dos limitaciones que importan para Axx

**Español.** La documentación menciona raw:<lang>, pero el filtro revisado solo detecta determinados alfabetos no latinos. Además, capture_turn asigna language="en" y el esquema MCP de memory_capture no expone language/tags. No basta con inventar un parámetro raw:es en la llamada MCP. Hay que revisar el trayecto de captura, los metadatos y el modelo multilingual con consultas reales en español. [I2] [I4] [I5]

**Procedimientos.** El minero toolseq_mine extrae patrones de trailers textuales de herramientas. No los verifica contra una bitácora estructurada; el propio código señala esa limitación. El patrón obtenido es una etiqueta, no una receta ejecutable comprobada. No debe conceder permisos ni activar ejecución automática. [I6]

Además, memory_capture puede informar inserted, reinforced o skipped. El adaptador debe distinguirlos y registrar la razón; llamar al servidor no implica haber almacenado un recuerdo nuevo. [I2]

### Cuándo incorporarlo

Lo incorporaría si una evaluación demuestra que resuelve mejor que la memoria inicial preguntas temporales, correcciones personales o recuperación de episodios. En ese momento IAI sería la autoridad de memoria personal; ai-memory conservaría conocimiento de desarrollo. Debe definirse la migración, evitando dos copias editables de la misma preferencia.

## 5. CLI-Anything: control por aplicación

CLI-Anything aporta una metodología de generación, adaptadores existentes y un catálogo. La generación se beneficia del código fuente y de un agente de programación capaz. Una vez terminado un adaptador, ejecutarlo no exige regenerarlo con un LLM en cada petición. [C1] [C2]

La integración apropiada es un ejecutor de Axx que invoque comandos con argumentos separados, proyecto explícito, límites de tiempo y resultados estructurados. Las capacidades se registran por operación y versión de aplicación.

### Cobertura observada

| Objetivo | Situación |
|---|---|
| Blender | Adaptador existente, con límites concretos de escenas y render |
| FreeCAD | Backend y exportaciones reales presentes |
| Navegador | Adaptador Browser con sus dependencias, extensión y servicio |
| AutoCAD, Revit y SketchUp | No se encontraron adaptadores específicos en el árbol y registros inspeccionados |
| Escritorio Windows completo | Requiere una capa adicional de automatización nativa |

La ausencia de un adaptador no demuestra que sea imposible crearlo. Una API disponible puede permitir integrar software cerrado. El catálogo tampoco certifica que cada operación de cada programa funcione. [C1] [C7]

### Discrepancia de Blender reproducida

La ruta render execute llama a render_scene. Esta función escribe _render_script.py y devuelve información. No ejecuta Blender. La comprobación directa de los módulos originales produjo:

~~~json
{
  "scene_json_roundtrip": true,
  "bpy_script_valid_python": true,
  "script_created": true,
  "image_created": false
}
~~~

No había Blender instalado. Esto acredita generación de instrucciones, no renderizado. El comando de la CLI se siguió estáticamente hasta esa función; no se ejecutó el paquete CLI instalado. [C3] [C4]

Existe render_scene_headless, que sí lanza el backend. Axx puede utilizar esa ruta o ejecutar el script generado en un proceso Blender separado y verificar la salida. [C5]

También se comprobó que scene open lee el JSON de escenas de este adaptador. No es una importación general de proyectos .blend existentes. Para conservar fielmente una escena del usuario hace falta una integración que opere sobre ese documento real. [C6]

### Cómo empezar con Codex

~~~powershell
git clone https://github.com/HKUDS/CLI-Anything.git
git -C CLI-Anything checkout 34f519533bc175d2fe287ab8316b0dd99bb9cc43
.\CLI-Anything\codex-skill\scripts\install.ps1
~~~

Esto instala el flujo de generación en Codex. Axx sigue necesitando su adaptador de ejecución. La instalación y el comportamiento de cada programa deben validarse en su plataforma. [C8]

Para FreeCAD, con el ejecutable y el adaptador instalados y un proyecto del adaptador existente, se documentó en código la ruta:

~~~powershell
cli-anything-freecad --json --project pieza.json export render pieza.step --preset step
~~~

El exportador genera la macro, ejecuta FreeCAD y comprueba el archivo. Esta revisión no ejecutó FreeCAD; su adopción sigue condicionada a una exportación real en el equipo objetivo. [C9]

### Regla de éxito

Un adaptador debe distinguir:

1. Plan o script generado.
2. Backend ejecutado.
3. Archivo o cambio final comprobado.

Solo el tercer estado satisface una tarea que pide un resultado final. Si falta el programa, hay un error, una salida vacía o una versión incompatible, Axx no debe guardar la ejecución como receta válida.

## 6. BitNet: capacidad local opcional

bitnet.cpp es un runtime para modelos compatibles con BitNet. No convierte automáticamente cualquier Llama, Qwen o modelo de nube en un equivalente de 1,58 bits. El modelo generativo oficial y los modelos de embeddings son productos distintos. [B1] [B2] [B7]

Para el Acer, la ruta a evaluar es CPU x86/AVX2. El wrapper de servidor revisado fuerza cero capas GPU. No se ha validado aceleración por Iris Xe ni una velocidad concreta en ese portátil. [B3]

### Incidencias que condicionan su adopción

La incidencia #595 registra errores de enlace en Windows. Es evidencia de una instalación fallida reportada, no prueba de que todo Windows falle. [B4]

Se verificó también una diferencia entre la activación relu2 del modelo oficial y LLM_FFN_SILU en el submódulo fijado por BitNet. #588 describe el impacto. Sus cifras de calidad son mediciones de los autores de la incidencia, no de esta revisión. No procede aplicar un cambio global sin discriminar modelos, porque otros checkpoints pueden requerir otra activación. [B2] [B5] [B6]

Por esas razones, BitNet queda como candidato experimental hasta resolver y validar el conjunto runtime/modelo.

### Servidor real para Axx

Después de instalar el toolchain, descargar un GGUF compatible y compilar satisfactoriamente:

~~~powershell
python run_inference_server.py -m models/BitNet-b1.58-2B-4T/ggml-model-i2_s.gguf -c 4096 -t 2 -n 256 --host 127.0.0.1 --port 8080
~~~

El wrapper existe. El servidor del submódulo incorpora /health, /v1/models y /v1/chat/completions. Una interfaz compatible no asegura que el checkpoint utilice herramientas correctamente. [B3] [B8]

El modelo generativo tiene 4096 tokens de contexto y limitaciones fuera del inglés. Su utilidad para Axx debe decidirse mediante ejemplos en español, formato de respuesta, recuperación de memoria y selección correcta de acciones. No se ha demostrado aquí visión ni control fiable de herramientas con ese modelo. [B2] [B9]

### Embeddings y conexión a IAI

Los modelos de embeddings oficiales 270M y 0.6B producen vectores de 640 y 1024 dimensiones, respectivamente; son multilingües. No generan conversación. [B7]

IAI espera POST /embed con texts e input_type. El endpoint OpenAI-compatible de un servidor BitNet recibe otra estructura. Un puente debe traducir la petición y respuesta y conservar modelo, dimensiones, prefijos de consulta/documento, pooling y normalización. Las dimensiones 640 y 1024 fueron aceptadas por la configuración IAI; no se probó el circuito completo. [I3] [B8]

Al cambiar de modelo se deben regenerar los vectores, incluso si las dimensiones no cambian. El flujo documentado incluye parar el daemon, respaldar, configurar el nuevo proveedor, ejecutar la migración y reiniciar:

~~~powershell
iai-mcp migrate --reembed-to-configured-provider --dry-run
iai-mcp migrate --reembed-to-configured-provider
iai-mcp doctor
~~~

Los comandos se ejecutan en el entorno IAI correspondiente; el daemon debe permanecer parado durante la migración y reiniciarse antes de consultar. [I3]

No haría esta conexión un requisito del primer Axx funcional. Primero mediría si mejora la recuperación frente a la configuración más sencilla.

## 7. invisible_dots: trabajador dentro de una VM

Cada Dot tiene una VM Linux persistente. Hay cola, eventos, memoria en archivos, skills y canales. Su integración externa puede usar la API HTTP o el SDK TypeScript. El proyecto se declara alfa. [D1] [D2]

Requisitos documentados: Windows/Linux x86-64, virtualización hardware, Node 24+, Go 1.25+, QEMU y espacio libre de al menos 20 GiB. El ejemplo asigna 4 GB por Dot; el consumo de los navegadores ocurre dentro de la VM. No debe sumarse dos veces al presupuestar memoria. [D2]

### Instalación de ensayo

Con los requisitos instalados:

~~~powershell
git clone https://github.com/feder-cr/invisible_dots
cd invisible_dots
git checkout ef69f5e19c1b46e41e743234fa5019e39442adcb
npm ci
npm run build --workspace @invisible-dots/cli
node apps/cli/dist/invisible-dots.mjs doctor
node apps/cli/dist/invisible-dots.mjs setup --all
node apps/cli/dist/invisible-dots.mjs server
~~~

setup --all prepara QEMU, aceleración e imágenes; en Windows puede solicitar elevación y reinicio. La interfaz se sirve en http://127.0.0.2:3000. Es una receta documentada, no una instalación ejecutada aquí. [D2]

### Contratos útiles para Axx

El control plane usa por defecto http://127.0.0.1:8787 y un token Bearer:

| Operación | Ruta |
|---|---|
| Listar Dots | GET /api/dots |
| Enviar una petición al trabajador | POST /api/dots/:id/messages |
| Crear una tarea | POST /api/dots/:id/tasks |
| Consultar una tarea | GET /api/tasks/:id |
| Recibir eventos en vivo | GET /api/stream |
| Cancelar | POST /api/tasks/:id/cancel |

Estas rutas existen en la arquitectura y el SDK revisados. Axx debe conservar el identificador de tarea y reconciliar estados tras una desconexión. [D3] [D5]

### Límites relevantes

El esquema de configuración admite model.provider igual a openrouter. La existencia de una base URL interna para pruebas no convierte al sistema en un router listo para BitNet u Ollama. La adaptación debe cubrir proveedor, catálogo, contexto, coste y herramientas. [D4]

La VM Linux no es el escritorio Windows del usuario. Para controlar AutoCAD o la ventana actual de una aplicación Windows sigue haciendo falta un puente nativo.

El proyecto no proporciona todavía backups, snapshots y rollback como prestaciones terminadas. La aceptación con VM real documentada se realizó en Linux/KVM; el ciclo Windows se validó manualmente. [D2]

Probaría un solo Dot y una identidad de navegador al principio. Para varios trabajadores persistentes, lo evaluaría posteriormente en el homelab, midiendo RAM y concurrencia.

## 8. Arquitectura propuesta para conservar Axx

Esta sección describe diseño pendiente de implementación; sus nombres no son endpoints que ya ofrezcan los repositorios.

~~~mermaid
flowchart TD
    A["Interfaz Axx"] --> O["Orquestación y permisos"]
    O <--> M["Memoria por ámbito"]
    O --> P{"¿Procedimiento verificado?"}
    P -->|Sí| E["Ejecutor"]
    P -->|No| R["Router de modelos"]
    R --> E
    E --> W["Adaptadores Windows y CLI"]
    E --> D["Dot opcional en VM"]
    W --> V["Verificar resultado"]
    D --> V
    V --> M
    V --> A
~~~

### Componentes que todavía debe aportar Axx

**Registro de capacidades.** Declara exactamente qué operaciones existen, su ejecutable o transporte, versión compatible, requisitos, límites y tipo de resultado. El agente no puede inventar una capacidad porque un README diga “todo”.

**Registro de procedimientos.** Conserva recetas ejecutables con evidencia de sus resultados. Un SKILL.md puede explicar cómo hacer una tarea; no sustituye a la validación del procedimiento.

**Ejecutor.** Controla permisos, procesos, tiempos, cancelación y errores. Un modelo propone operaciones; la ejecución depende de los contratos y de la autorización vigente.

**Verificador.** Inspecciona el resultado según la tarea: archivo válido y dimensiones, documento reabierto, cambio de estado de una aplicación o identificador de operación devuelto por un servicio.

**Router de modelos.** Puede elegir proveedor según capacidad, disponibilidad y presupuesto. Memoria y herramientas se comparten a través de Axx; no deben quedar encerradas en el historial de un proveedor.

### Control de aplicaciones Windows

Una estrategia por capas permite ampliar cobertura:

| Programa o superficie | Integración a evaluar |
|---|---|
| AutoCAD | API .NET, AutoLISP o interfaces oficialmente disponibles para la versión |
| Revit | Add-in con API de Revit y contexto de ejecución válido |
| SketchUp | Extensión usando Ruby API |
| Controles de ventanas Windows | Microsoft UI Automation |
| Aplicaciones cubiertas por CLI-Anything | Adaptador revisado y backend instalado |
| Páginas web | API disponible o herramienta de navegador validada |

Las APIs nativas citadas existen; la implementación concreta de los puentes para Axx no está hecha. UI Automation expone muchos controles, pero la cobertura depende de lo que cada aplicación publique. [W1] [W2] [W3] [W4]

Un servicio instalado en Windows y uno dentro de la VM no comparten automáticamente localhost, rutas, sesiones ni archivos. Antes de conectar memoria a un Dot hay que definir dónde vive cada proceso y cómo cruza esa frontera.

## 9. Memoria procedimental y mejora con la experiencia

El objetivo de “hacer una acción, recordar cómo se hizo y ahorrar en la siguiente ejecución” exige conservar evidencia estructurada del ejecutor.

### Datos propuestos

| Grupo | Datos mínimos |
|---|---|
| Identidad | procedure_id, versión, objetivo y ámbito |
| Entradas | Esquema, rutas o recursos esperados y validaciones |
| Compatibilidad | Programa, versión del programa, adaptador y versión |
| Condiciones previas | Documento correcto, archivos presentes, permisos vigentes |
| Operaciones | Herramientas reales y argumentos estructurados |
| Resultado esperado | Postcondiciones observables |
| Recuperación | Límites de tiempo, cancelación y comportamiento ante resultado desconocido |
| Evidencia | Identificador de ejecución, resultados y artefactos |
| Calidad | Éxitos, fallos, duración y consumo de modelos medidos |
| Estado | Candidato, verificado, suspendido o retirado |

Son campos de diseño de Axx. No se presentan como un esquema nativo de ai-memory, IAI o invisible_dots.

### Flujo recomendado

1. Encontrar una receta compatible con objetivo, entradas y versión de la aplicación.
2. Verificar condiciones actuales y alcance de autorización.
3. Ejecutar sin replantear cada paso si la receta sigue siendo válida.
4. Comprobar el efecto real.
5. Guardar la ejecución y sus métricas.
6. Si falló, suspender el atajo afectado y registrar la causa.
7. Si aparece una mejora, ensayarla sobre copias o casos de prueba antes de sustituir la receta activa.

Una receta puede ahorrar llamadas de planificación, pero el ahorro debe medirse. No hace falta llamar a otro modelo en cada ejecución para afirmar que el sistema aprende. Registrar lo ocurrido cuesta menos que reescribir el procedimiento constantemente.

Un ejemplo apropiado para comenzar es exportar un documento a una carpeta conocida. El verificador debe identificar el documento, comprobar el archivo producido y confirmar que tiene el formato esperado. Tras un reinicio, la misma receta debe funcionar con nuevas entradas sin depender del historial de chat anterior.

## 10. Recuperación, recursos y control del coste

### Proveedores de modelos

Clasificar fallos evita rotaciones improductivas:

- Un límite temporal puede requerir espera o cambio de proveedor.
- Credenciales inválidas requieren corregir la configuración.
- Un modelo sin visión o sin herramientas no se vuelve compatible reintentando.
- Un timeout después de ejecutar una herramienta puede dejar un efecto real con resultado desconocido.

El router debe cambiar de modelo conservando el estado de la tarea. No debe repetir automáticamente una operación externa cuya ejecución ya pudo ocurrir. Usar identificadores estables, verificar el efecto y continuar desde el último paso conocido.

Si no queda ningún proveedor apto, las recetas locales ya verificadas pueden seguir funcionando. Una tarea nueva que requiere razonamiento no puede declararse resuelta solo porque exista memoria.

### Recursos del Acer

No se midieron RAM libre, CPU ni batería del portátil. La recomendación es estructural:

- Mantener Axx y una memoria como servicios ligeros.
- Ejecutar indexación y modelos opcionales cuando hagan falta.
- No reservar varias VMs desde el inicio.
- Evitar que la evaluación local bloquee dictado, animación y tareas del usuario.
- Medir consumo conjunto con las aplicaciones reales abiertas.

La eficiencia de BitNet no permite deducir que cualquier modelo enorme cabe en 16 GB. Por aritmética, 100 mil millones de pesos a 1,58 bits ya serían 19,75 GB decimales antes de contexto y otros tensores; a dos bits serían 25 GB. Tampoco demuestra que exista un modelo compatible de ese tamaño disponible para este caso.

El software local no garantiza coste total cero: un trabajador configurado para un modelo de nube sigue sujeto a disponibilidad, límites y precio del proveedor elegido.

### Autoridad de los datos

La memoria histórica aporta contexto, no autorización. Deben mantenerse separados preferencias, hechos confirmados, contenido recuperado de terceros y evidencia del ejecutor. Cada nueva versión de un hecho debe poder rastrearse hasta su fuente y fecha. Los secretos se gestionan fuera de los recuerdos y fuera de la interfaz renderizada.

## 11. Plan de implementación y criterios de aceptación

Los siguientes son criterios propuestos; no son resultados obtenidos.

| Etapa | Entrega | Prueba que decide si está lista |
|---|---|---|
| 1. Memoria | Adaptador Axx → ai-memory | Escribir, buscar, leer tras reinicio y aislar proyectos |
| 2. Correcciones | Hechos con fecha y vigencia | Una preferencia corregida prevalece sin borrar la evidencia histórica |
| 3. Acciones | Dos o tres operaciones locales | Producen resultados verificables; falta de backend genera error explícito |
| 4. Procedimientos | Reutilización de recetas | Repetir con nuevas entradas y tras reinicio; medir llamadas ahorradas |
| 5. Router | Cambio entre proveedores | Timeout o cuota no duplica herramientas ni pierde la tarea |
| 6. IAI | Comparación de memoria personal | Recuperación y contradicciones en español mejoran frente al sistema inicial |
| 7. BitNet | Proveedor local experimental | Compila, genera resultados coherentes y cumple las tareas seleccionadas |
| 8. Dots | Un trabajador aislado | Crear tarea, observar eventos, cancelar, reiniciar y reconciliar estados |

### Casos de aceptación especialmente importantes

- Buscar una preferencia mediante una frase distinta, conservando el significado en español.
- Registrar un cambio de nombre, ruta o preferencia y recuperar la versión vigente.
- Simular que una aplicación necesaria no está instalada.
- Generar un script de render sin ejecutarlo y comprobar que Axx informa “preparado”, no “terminado”.
- Validar un render real por existencia, formato, dimensiones y lectura de imagen.
- Reiniciar el orquestador después de una acción cuyo resultado todavía no se registró.
- Cambiar de proveedor a mitad de tarea y conservar los resultados ya confirmados.
- Actualizar una aplicación y comprobar que una receta incompatible no se reutiliza silenciosamente.
- Cancelar con el mecanismo de Axx y comprobar que el proceso o trabajador deja de ejecutar nuevos pasos.

## 12. Estado final de esta auditoría

La evaluación permite seleccionar una arquitectura y un orden de trabajo. Se confirmó que existen interfaces útiles y se encontraron discrepancias que impedirían recomendar una instalación indiscriminada como solución terminada.

**Recomendación:** comenzar por ai-memory y adaptadores concretos de CLI-Anything, con verificación propia de Axx. Evaluar IAI por su valor adicional en español. Mantener BitNet e invisible_dots como ampliaciones independientes hasta superar sus pruebas.

**Pendiente:** implementación en el código actual de Axx, instalación en Windows y validación integral con las aplicaciones del usuario. Este documento no afirma que esa integración ya esté montada.

## Fuentes primarias

Las referencias al código están fijadas a los commits inspeccionados. Las fichas externas y documentación de plataformas corresponden a la consulta del 19 de octubre de 2026.

[M1]: https://github.com/akitaonrails/ai-memory/blob/b18f22a7c2f3068575c70d37f13d167fed3476bb/README.md
[M2]: https://github.com/akitaonrails/ai-memory/blob/b18f22a7c2f3068575c70d37f13d167fed3476bb/docs/programmatic-memory.md
[M3]: https://github.com/akitaonrails/ai-memory/blob/b18f22a7c2f3068575c70d37f13d167fed3476bb/docs/windows.md
[M4]: https://github.com/akitaonrails/ai-memory/blob/b18f22a7c2f3068575c70d37f13d167fed3476bb/docs/local-embeddings.md
[M5]: https://github.com/akitaonrails/ai-memory/blob/b18f22a7c2f3068575c70d37f13d167fed3476bb/companions/ai-memory-ts/README.md
[I1]: https://github.com/CodeAbra/iai-personal-memory-engine/blob/c400059ac860929936719fc70a66f57ee60c712c/README.md
[I2]: https://github.com/CodeAbra/iai-personal-memory-engine/blob/c400059ac860929936719fc70a66f57ee60c712c/mcp-wrapper/src/tools.ts
[I3]: https://github.com/CodeAbra/iai-personal-memory-engine/blob/c400059ac860929936719fc70a66f57ee60c712c/docs/EMBEDDERS.md
[I4]: https://github.com/CodeAbra/iai-personal-memory-engine/blob/c400059ac860929936719fc70a66f57ee60c712c/src/iai_mcp/capture.py
[I5]: https://github.com/CodeAbra/iai-personal-memory-engine/blob/c400059ac860929936719fc70a66f57ee60c712c/src/iai_mcp/aaak.py
[I6]: https://github.com/CodeAbra/iai-personal-memory-engine/blob/c400059ac860929936719fc70a66f57ee60c712c/src/iai_mcp/lilli/cycle/toolseq_mine.py
[C1]: https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/README.md
[C2]: https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/cli-anything-plugin/HARNESS.md
[C3]: https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/blender/agent-harness/cli_anything/blender/core/render.py
[C4]: https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/blender/agent-harness/cli_anything/blender/blender_cli.py
[C5]: https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/blender/agent-harness/cli_anything/blender/utils/blender_backend.py
[C6]: https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/blender/agent-harness/cli_anything/blender/core/scene.py
[C7]: https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/registry.json
[C8]: https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/codex-skill/scripts/install.ps1
[C9]: https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/freecad/agent-harness/cli_anything/freecad/core/export.py
[B1]: https://github.com/microsoft/BitNet/blob/0b341e582afbf9e1011f24744b554c96a3477eb5/README.md
[B2]: https://huggingface.co/microsoft/bitnet-b1.58-2B-4T/blob/main/config.json
[B3]: https://github.com/microsoft/BitNet/blob/0b341e582afbf9e1011f24744b554c96a3477eb5/run_inference_server.py
[B4]: https://github.com/microsoft/BitNet/issues/595
[B5]: https://github.com/microsoft/BitNet/issues/588
[B6]: https://github.com/isHuangXin/llama.cpp/blob/390c307752ab78fd8189f359d6954c9ba1be74af/src/models/bitnet.cpp
[B7]: https://huggingface.co/microsoft/bitnet-embedding-270m
[B8]: https://github.com/isHuangXin/llama.cpp/blob/390c307752ab78fd8189f359d6954c9ba1be74af/tools/server/server.cpp
[B9]: https://huggingface.co/microsoft/bitnet-b1.58-2B-4T
[D1]: https://github.com/feder-cr/invisible_dots/blob/ef69f5e19c1b46e41e743234fa5019e39442adcb/README.md
[D2]: https://github.com/feder-cr/invisible_dots/blob/ef69f5e19c1b46e41e743234fa5019e39442adcb/docs/guide.md
[D3]: https://github.com/feder-cr/invisible_dots/blob/ef69f5e19c1b46e41e743234fa5019e39442adcb/docs/architecture.md
[D4]: https://github.com/feder-cr/invisible_dots/blob/ef69f5e19c1b46e41e743234fa5019e39442adcb/packages/shared/src/config.ts
[D5]: https://github.com/feder-cr/invisible_dots/blob/ef69f5e19c1b46e41e743234fa5019e39442adcb/packages/sdk/src/client.ts
[W1]: https://learn.microsoft.com/windows/win32/winauto/entry-uiauto-win32
[W2]: https://aps.autodesk.com/developer/overview/autocad-api
[W3]: https://blog.autodesk.io/external-access-to-the-revit-api/
[W4]: https://ruby.sketchup.com/Sketchup.html

