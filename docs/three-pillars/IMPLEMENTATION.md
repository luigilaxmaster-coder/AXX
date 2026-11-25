# Magic Pen, Acts y Code Studio

Esta entrega completa recorridos dentro de los sistemas existentes. Conserva el
avatar, el diseño protegido, ChatStore, CommandService, los permisos por Act,
el diario de cambios de archivos y la API móvil `/v1`.

## Uso

1. En Chats, abre **Acts**. Crea perfiles independientes o consulta sus chats,
   equipos y actividad. Cambiar de Act conserva el mismo chat, grupo y borrador.
   La miniatura SVG está identificada como vista aproximada.
2. Configura el modelo y la voz del perfil. Para notas persistentes privadas,
   selecciona memoria del agente y guarda notas explícitas: se pueden corregir y
   olvidar. Tienen revisión y caducidad; se sirven las más recientes hasta 8000
   caracteres por turno. Duplicar/importar no copia notas, permisos ni credenciales.
3. En Magic Pen, abre un modelo y selecciona una pieza. **Editar pieza** habilita
   el documento editable. Cambia material, color o escala, deshaz/repite, crea un
   giro o revisa una propuesta de un Act antes de aplicarla.
4. **Assets y piezas** permite insertar componentes locales e importar GLB propios
   indicando licencia y créditos. Los archivos quedan en caché por hash. El visor
   utiliza sus mallas y texturas PBR embebidas. No descarga recursos referenciados.
5. **CAD paramétrico** añade tres sólidos de ejemplo en mm. Las cotas iniciales
   están marcadas como supuestas. Selecciona una pieza, edita sus cotas y pulsa
   **Aplicar cotas CAD** para regenerar STEP y GLB con OpenCascade. La comprobación
   de sólidos y dimensiones no constituye validación estructural.
6. Utiliza sección, separación de piezas y el cursor de animación. **GLB** guarda
   los buffers geométricos reales; **Vídeo 3D · 5 s** renderiza 50 fotogramas del
   canvas y comprueba su codificación/decodificación. La exportación geométrica
   conserva factores PBR; no incorpora mapas de textura del asset importado.
7. En Code Studio abre un proyecto Git, guarda sus borradores y selecciona uno o
   varios archivos de contexto. La selección de una función conserva rango,
   hash, procedencia y diagnóstico en un `CodeContextPacket` del servidor.
8. Delega al Act con permisos `axx.code`. Sus propuestas se aplican en su propio
   worktree. Revisa el diff, ejecuta pruebas y pide revisión a otro Act. La
   integración exige recibos de esos mismos bytes y respeta HEAD/CAS.
9. El depurador Python solicita aprobación para iniciar el archivo seleccionado;
   permite breakpoint, pila, variables locales y pasos. No admite evaluación,
   attach ni terminales solicitados por el adaptador.

## Proveedores opcionales

Los modelos utilizan las conexiones ya elegidas por el propietario. Codex tiene
un propósito aislado `act_inference`: hilo temporal, modelo exacto confirmado por
el runtime y ninguna herramienta. El modelo responde o propone; AXX ejecuta los
efectos autorizados. No sustituye el modelo global.

Para Python LSP/DAP, instala en el intérprete local seleccionado:

```powershell
python -m pip install -r requirements-code-tools.txt
```

Se detectan Python en PATH y las instalaciones oficiales registradas conforme a
[PEP 514](https://peps.python.org/pep-0514/). Estos procesos son herramientas del
proyecto y no un sandbox. Su ausencia produce un estado no disponible o el
análisis AST existente; no se descarga un proveedor automáticamente.

Asset Gate es opcional. La interfaz prepara una búsqueda únicamente si existe
un MCP habilitado que exponga `search_assets` de solo lectura. Muestra conexión,
consulta y operación para aprobación y usa CommandService. No instala servidores,
genera assets de pago ni autoriza descargas por la respuesta de un modelo.
En el entorno de desarrollo no había una conexión Asset Gate seleccionada: su
servicio remoto permanece pendiente; el catálogo y los GLB locales sí se prueban.

## Persistencia y límites

- Las tablas nuevas se crean de forma aditiva en las bases existentes. No se
  borran chats, proveedores, emparejamientos ni preferencias globales.
- Escenas: recibos duraderos por operación y argumentos; CAS; undo/redo atómico.
  El mismo identificador con parámetros diferentes se rechaza.
- Código: contexto del servidor válido una hora, hasta ocho archivos y 64 KB;
  bloqueo adicional de archivos de credenciales y redacción de patrones comunes.
  Esa redacción no garantiza detectar todos los secretos escritos en código.
- Pruebas Windows: procesos propios bajo Job Object, salida acotada a 64 KB por
  canal, plazo de 1–120 s y recibos de fallo/cancelación. Un report_id no repite el
  proceso. La custodia del proceso no revierte efectos ejecutados por las pruebas.
- Equipos: run_id duradero y recuperación por `teams/result`. Una repetición
  concluida devuelve su resultado; una ejecución interrumpida exige inspección.
  Cancelar descarta propuestas tardías y conserva los efectos previos.
- Rutinas: scheduler conectado a inferencia real; reclamación atómica de cada
  vencimiento. Un trabajo en curso al reiniciar queda interrumpido, sin repetición
  automática. Los efectos externos siguen sujetos a aprobación.
- Olvidar el chat elimina vínculos/eventos y suprime resultados de equipos y
  rutinas. Las notas privadas del Act tienen su propia acción de olvido.
- GLB: archivos autocontenidos, 250.000 triángulos por asset, sin URI externa,
  jerarquías cíclicas, skins ni decodificadores descargados. Texturas PNG/JPEG
  embebidas con límites de píxeles; presupuesto adicional por visor.

## Verificación

Las pruebas con modelos controlados son integración local, no inferencia real.
`test_code_codex_real.py`, habilitado mediante `AXX_REAL_CODEX=1`, verifica con dos
modelos reales el parche en disco, las pruebas, el veredicto independiente y la
integración. La elección global se comprueba al final. No usa claves API de pago.

```powershell
python -m pytest backend/tests/test_three_pillars_integration.py backend/tests/test_team_lifecycle.py backend/tests/test_act_lifecycle.py backend/tests/test_offline_glb.py backend/tests/test_code_context.py backend/tests/test_code_tools_real.py backend/tests/test_code_test_receipts.py
python -m pytest backend/connect/tests/test_provider_capability.py
python scripts/validate_companion.py --output build/three-pillars/companion-validation.json
```

Evidencias privadas de desarrollo: `build/three-pillars/`. La matriz de aceptación
se conserva junto a este documento. Las pruebas de navegador no sustituyen la
aceptación de WebView2/sidecar frozen, audio de Windows, GPU y DPI físicos, ni
hardware Android. La versión instalada y la descarga publicada se verifican
separadamente mediante `docs/RELEASING.md`.
