# Contratos de las cuatro recetas completas del lote 2026-10-18 08:00

Fuente: `command-library-20261019/source/AXX_2026-10-18_08-00_REVISADO_v1.zip`,
miembro `recipes.jsonl`, SHA256 del ZIP
`5d9445889c943cdfd22383ce43a719027c1c9698e218d487ba5ee7261f13d93d`.
Lectura de especificaciones; sus comandos, fixtures y pruebas no se ejecutaron.
Los cuatro IDs continúan deshabilitados. No se ha acreditado la disponibilidad
de binarios oficiales aprobados, sus versiones, el aislamiento exigido ni un
supervisor de procesos que satisfaga estos contratos. Un parser de cabecera
reducido no implementa las recetas que exigen decodificación completa.

Todos reciben `source: ApprovedImageSnapshot`, `configuration` del tipo de su
fila y `workspace: ExclusiveLocalWorkspace`, sin propiedades extra en la
configuración. El snapshot exige `path, sha256, owner_approval, format,
producer_scope`: copia local privada regular y estable, 1..20.971.520 bytes
(desde un byte hasta 20 MiB), firma y
extensión compatibles, productor conocido, ruta absoluta ASCII sin
`@ % [ ] * ?`, ADS, nombres reservados, UNC, enlaces/reparse/junction o carpeta
sincronizada. Nunca convertir dictado libre en ruta. El workspace exige
`path, approval, exclusive, new_outputs_approved`: carpeta nueva privada local
ASCII no sincronizada, sin escritores concurrentes ni informes ya existentes.

| ID (prefijo `AXX-20261018-0800-IMG-`) / operación | Configuración exacta | Observación y hallazgo |
|---|---|---|
| `0001` / `assess_tiff_page_geometry` | `expected_pages`: entero 1..16; `require_equal_dimensions`: `true` | ImageMagick debe decodificar la secuencia completa y producir exactamente N líneas `índice\|N\|TIFF\|ancho\|alto`, índices 0..N-1 únicos, dimensiones 1..4096 y N<=16. N distinto del esperado: `PAGE_COUNT_MISMATCH`; tamaños distintos: `HETEROGENEOUS_SEQUENCE`; iguales: `HOMOGENEOUS_SEQUENCE`. No usar `[0]`/rangos ni inferir SubIFD/pirámides no expuestas por el lector. |
| `0002` / `guard_png_static_consumer` | `consumer_accepts_animation`: `false` | ExifTool: `File:FileType`, `PNG:AnimationFrames`, `PNG:AnimationPlays`. FileType PNG/APNG y Frames entero>=1, Plays entero>=0: `ANIMATION_DECLARED`, incluso con un fotograma. Etiquetas ausentes: `NO_ANIMATION_TAG_OBSERVED`, outcome `INCONCLUSIVE`. `checks.static_route_blocked=true` en todos los informes; nunca certificar que es PNG estático. |
| `0003` / `assess_jpeg_baseline_contract` | `encoding_process`: `0`; `bits_per_sample`: `8`; `color_components`: `3` (enteros escalares) | Solo grupo File de ExifTool: FileType JPEG y terna completa. Se exige además decodificación ImageMagick completa con única línea `0\|1\|JPEG\|W\|H`. Terna (0,8,3) más decoder correcto: `MATCHES_THREE_FIELD_CONTRACT`; valores completos distintos: `CODESTREAM_CONTRACT_MISMATCH`. Error/warning de decoder: `INCONCLUSIVE`, aunque la cabecera sea válida. No inferir RGB/sRGB/calidad/perfil. |
| `0004` / `assess_tiff_ifd0_sample_contract` | `ifd`: `IFD0`; `samples_per_pixel`: `1`; `bits_per_sample`: `16`; `sample_format`: `1` | Solo FileType TIFF e IFD0 confirmado por el productor. Terna escalar única (1,16,1): `MATCHES_IFD0_UINT16_DECLARATION`; completa distinta: `SAMPLE_CONTRACT_MISMATCH`. Ausencias, listas o instancias ambiguas: `INCONCLUSIVE`; no suplir SampleFormat por defecto ni con IFD1/SubIFD. No decodifica muestras ni certifica estructura/rango/NaN/precisión. |

ExifTool se especifica con `-config` seguido del argumento vacío, `-j -G1:4
-s -n -a`, solo las etiquetas enumeradas, `-Warning -Error --` y la ruta
aprobada. La salida debe ser un array JSON completo de exactamente un objeto,
sin claves duplicadas. Resolver familia 1 y nombre preservando familia 4;
instancias múltiples son ambiguas, los ceros numéricos no son ausencias.
ImageMagick usa `identify`, `+ping`, `-regard-warnings`, formato de cinco campos,
límites de memoria 128 MiB, map/disk 0, ancho/alto 4096, list-length 16 y thread 1.
Los argv completos permanecen en la fuente verificada; no se importan al runtime.

El supervisor debe observar procesos, cierre de stdin, capturas íntegras y
separadas <=2 MiB cada una, entorno hijo aprobado aislado sin red/delegates ni
configuraciones heredadas no confiables. Binarios oficiales por ruta absoluta y
versión aprobadas, sin shell/PATH. Límite de informe 2 MiB, un intento por comando;
plazo de 60 segundos **blando**, sin asumir terminación/cancelación por reloj.
Control, herramienta, acceso o supervisor faltante: `UNAVAILABLE`, sin instalar
ni relajar políticas automáticamente.

Salida común `ImageDiagnosticResult`: `recipe_id, operation, run_id,
source_sha256, source_unchanged, configuration_sha256, effective_configuration,
tool_versions, processes, raw_outputs, finding, checks,
automatic_continuation_allowed, report_path, report_sha256, report_reopen_ok,
outcome`. Todos los procesos deben observarse terminales con retorno 0, sin
warnings, sin truncado y con hashes de fuente estables antes/después/al consumir.
Crear informe exclusivo, releer su JSON y calcular hash externo. Siempre
`automatic_continuation_allowed=false`, incluso si el hallazgo incompatible es
`VERIFIED`; ningún resultado autoriza convertir/importar/transmitir.

Estados: `VERIFIED` solo con hallazgo completo y evidencia común íntegra;
`INCONCLUSIVE` ante ausencia, ambigüedad, parcialidad, warning o estado incierto;
`INVALID_INPUT` fuera del contrato; `UNAVAILABLE` ante controles/dependencias
faltantes; `FAILED` para fallo terminal observado de lanzamiento/creación;
`CANCELLED` solo tras confirmar no lanzamiento o terminación de cancelación.
No repetir automáticamente una operación incierta ni declarar cambios revertidos.
