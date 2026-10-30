# Protocolo permanente de compatibilidad Axx Desktop / Mobile

Vigente desde el 29 de octubre de 2026. Contrato de transporte: `axx-companion-v1`. No cambia la apariencia aprobada ni añade ejecución remota arbitraria.

## Resultado exigido

Una actualización conserva identidad visual, datos, enlace, permisos y operaciones. Desktop y teléfono avanzan como un sistema coordinado, con versiones de producto independientes. No se promete ausencia absoluta de fallos: se impide publicar mediante el flujo oficial cuando faltan comprobaciones, se conserva el último estado confirmado y se separan los resultados de código, instalación y hardware.

| Elemento | Autoridad y regla |
| --- | --- |
| Personaje: color, forma, material, cámara y estado | El PC es la autoridad. El teléfono presenta snapshots y envía cambios tipados al ejecutor existente. Confirma recibo y estado real antes de indicar sincronización. |
| Tema, acento y tamaño de texto del teléfono | Preferencias locales persistentes. Una actualización del PC no las sustituye. |
| Conversación y herramientas | Se comparte lo autorizado por el usuario y por los permisos efectivos. Una capacidad nueva no concede acceso ni habilita un comando automáticamente. |
| Enlace y confianza | Conservar identidad TLS, device ID y credenciales. Cambiar de PC/certificado exige reconciliar o enlazar conscientemente; no se omite la verificación. |
| Envíos y transferencias | Conservar sus IDs y recibos. Tras timeout, consultar el mismo ID; nunca repetir automáticamente un efecto incierto. |

## Compatibilidad del API

`mobile/companion-contract.json` registra las rutas conservadas, los campos de snapshot, las variantes opcionales y la matriz exigida. `/v1` mantiene rutas, métodos, permisos, tipos y significado de campos. Se permiten nuevos campos opcionales en respuestas; el cliente debe ignorar los desconocidos. En solicitudes se conserva la validación estricta existente.

`appearance` e `inference` pueden ser null durante el arranque o sin configuración; no equivalen a pérdida de datos. El teléfono conserva el último personaje válido y evita inventar una sincronización. Un permiso denegado o una función ausente debe producir un estado recuperable, sin borrar el enlace ni ampliar permisos.

Un cambio incompatible se implementa en un API nuevo, manteniendo el anterior durante una migración comprobada. Antes de retirarlo se prueba el cliente vigente y el anterior, se establece el plazo de transición y se comunica la actualización necesaria. Renombrar `/v1` o alterar silenciosamente un payload no es una migración.

El manifiesto y los tests actuales no añaden un handshake de negociación al runtime. Las capacidades/permisos y los endpoints existentes siguen determinando qué puede usar el teléfono. Introducir negociación o una retirada de v1 requerirá una implementación y pruebas específicas.

## Diseño protegido

`mobile/design-baseline.json` conserva huellas normalizadas de diez superficies: estilos embebidos y hojas compartidas del escritorio, inicio móvil, estilos de móvil/control remoto, tema local, rasterizador del personaje y tema Android. Se comprueban además navegación, borrador, controles visibles, teclado y formatos de pantalla.

Un hash distinto detiene el gate. No se actualiza la referencia para ocultar un fallo. Solo una petición explícita del usuario autoriza cambiar el diseño protegido; la revisión debe identificar qué cambió, por qué conserva las funciones y qué capturas/pruebas lo respaldan. Los cambios de lógica no deben modificar esas superficies sin necesidad. Esto es una protección de fuentes y estructura, no una comparación de píxeles de todas las herramientas nativas.

## Comprobación automática y recibos

Preparación del entorno:

```powershell
python -m pip install -r requirements-companion-tests.txt
python -m playwright install chromium
```

Sobre la integración final, antes de publicar:

```powershell
python scripts/validate_companion.py --output build/companion-validation.json
```

El comando exige cuatro grupos aprobados:

1. Contrato y pruebas negativas: cambio visual, ruta retirada, versiones Android incoherentes, versionCode inferior, recibo ausente/obsoleto o comprobación fallida.
2. Extracción y procedencia: `node mobile/build.mjs` toma la geometría/material actuales del escritorio y genera `companion-build.json`, con versiones, versionCode y hashes. Se verifica que no se use un renderer antiguo.
3. Servicio: pruebas de backend móvil, con contratos TLS reales en almacenamiento aislado, esquema de snapshot y denegación antes de mutar.
4. Interfaz: tests con transporte nativo declarado como fixture, formatos v1 anteriores/aditivos, borradores, permisos, acciones y matriz de pantalla exigida.

El recibo contiene versiones, estados y hashes normalizados de fuentes/pruebas, sin credenciales ni datos del teléfono. Detecta cambios durante la validación o posteriores. Excluye assets/WWW/Cordova generados; esos se reconstruyen y verifican por separado. Las capturas de los tests se escriben en temporales, sin sobrescribir evidencia privada del usuario.

GitHub ejecuta el gate en cada push y pull request. El script de publicación lo exige también localmente, antes de cualquier llamada de publicación:

```powershell
python scripts/release.py publish --build-result build/release-current/build-result.json --install-result build/release-current/installed-runtime.json --companion-result build/companion-validation.json --notes docs/releases/X.Y.Z.md --dry-run
```

Después se usa el mismo comando sin `--dry-run`, desde `main` limpio y sincronizado. No se publica un recibo antiguo para fuentes nuevas. No se han cambiado las reglas administrativas de protección de ramas de GitHub; el flujo debe seguir este script y revisar el resultado de CI.

## Entrega según el tipo de cambio

| Cambio | Entrega necesaria |
| --- | --- |
| Solo PC, conservando v1 y funciones del cliente | Gate conjunto y actualización Windows verificada. El APK compatible puede permanecer instalado; no necesita una versión idéntica a Windows. |
| Interfaz/lógica móvil o renderer que debe llegar al teléfono | Reconstruir assets, incrementar la versión Android cuando se entrega nuevo APK, compilar, verificar hashes/firma, actualizar en sitio y probar conservación de estado. |
| Permisos, transporte, almacenamiento, voz o archivos nativos | Lo anterior, más pruebas físicas del módulo y escenarios de denegación, desconexión y recuperación. |
| Nuevo formato de teléfono, plegable o iOS | Aplicar el estudio de pantallas y añadir aceptación nativa de ese formato. Una simulación de viewport no basta. |
| Cambio incompatible o migración de datos | Detener entrega normal; añadir protocolo/migración compatible, copia verificada, pruebas de actualización y recuperación antes de publicar. |

Las actualizaciones Android deben conservar identidad de aplicación y una firma admitida por el sistema; versionCode debe avanzar en entregas sucesivas. El gate comprueba el código frente a la referencia aprobada; el responsable de entrega debe contrastarlo también con el último APK distribuido. [Versionado Android](https://developer.android.com/studio/publish/versioning), [firma de aplicaciones](https://developer.android.com/studio/publish/app-signing).

Una actualización de estado del PC llega por los mecanismos actuales de sincronización. Una actualización de código nativo requiere distribuir e instalar el binario: este protocolo no instala APK silenciosamente ni descarga código ejecutable por el canal de comandos. El build web y la sincronización del proyecto nativo son pasos distintos en Capacitor. [Flujo oficial](https://capacitorjs.com/docs/basics/workflow).

## Actualización, fallo y recuperación

Antes de instalar: identificar la versión/instancia real, terminar o reconciliar operaciones activas, crear copia comprobada de datos/WebView/instalación y conservar la firma y la identidad TLS. No usar desinstalación, limpieza de datos ni regeneración de credenciales como método de actualización.

Después: comprobar PC activo, teléfono reconectado, mismo enlace y borrador, tema/tamaño conservados, apariencia en ambos sentidos, consulta real y reanudación de transferencias sin duplicación. Reiniciar ambos y comprobar otra vez. Solo después se distinguen fuente subida, Windows publicado con digest confirmado y Android instalado físicamente.

Si falla un gate, no se publica por este flujo. Si falla la instalación, mantener el binario anterior y los datos respaldados. Si la migración cambia el esquema de datos, no bajar de versión a ciegas: usar recuperación ensayada con la copia correspondiente. Un resultado incierto se consulta/reconcilia, no se certifica ni se reenvía.

Un único responsable coordina versiones, build, instalación y publicación. Los demás cambios se integran antes del último recibo; no se cruzan instaladores ni se reemplaza un artefacto publicado con bytes distintos.

## Alcance medido y pendientes

La matriz exigida cubre los diez formatos del estudio: 280/320/339/390/440 en vertical, 568 × 320 y 844 × 390 en horizontal, y ventanas de 600/840/1024 píxeles CSS. Todos se cruzan con temas claro/negro, texto 100/170/200 %, DPR 1/3 y compositor con teclado de 299 puntos: **120 escenarios obligatorios**. El test exige también la presencia de los 24 escenarios que fallaban; no pueden excluirse para conseguir un resultado positivo.

La [corrección responsive de Android 0.2.7](SCREEN-FIXES-20261029.md) conserva las doce referencias previas de apariencia y añade su comparación de geometría, colores, tipografía y bordes al gate. El informe original de fallos se mantiene como histórico, junto al resultado corregido. Pasar estos escenarios de navegador no certifica un iPhone o plegable físico.

El gate acredita fuente, contratos y navegador. APK/AAB, firma, instalación, micrófono/altavoz, QR óptico, input físico, bisagra, safe areas nativas, WebKit y rendimiento GPU real requieren recibos separados. Ninguna prueba individual acredita todas las funciones de todos los teléfonos.

Las optimizaciones del renderer deben conservar calidad y aportar regresiones de imagen. La [caché de gotas de Android 0.2.8](PERFORMANCE-20261029.md) exige 81 comparaciones exactas de píxeles contra el recorrido original y comprueba que no se repite la geometría base ni se reduce calidad/adaptación. La medición física de tiempo de dibujo se mantiene separada de una garantía de FPS sostenidos.

La [revisión de cámara y carpetas de Android 0.2.9](FLUENCY-AND-PATHS-20261029.md) añade regresiones de corrección progresiva, camino corto de cámara, prioridad del gesto, movimiento reducido y canvas oculto. El gate ejecuta también el test del selector de archivos de Windows y registra las huellas de ese código y su prueba: un cambio posterior invalida el recibo. Se exigen enlaces del mismo modelo distinguibles, conservación de selección/borradores y rutas entre comillas sin conceder permisos automáticamente.

Para acreditar consumo y calor se requiere un registro físico prolongado sin alimentación externa real, con visibilidad, aplicación en primer plano comprobada también desde Android, calidad, temperaturas, estado térmico y carga medida. La visibilidad declarada por el WebView por sí sola no acredita qué aplicación está mostrando Android. Un ensayo conectado al USB o incompleto no demuestra descarga de batería. La referencia con imagen quieta es solo un control de ensayo y no cambia la calidad ni la configuración entregadas.

El [trackpad de Android 0.2.10](TRACKPAD-20261029.md) exige regresiones de renovación sin repetir entrada, respuestas tardías entre sesiones, captura perdida y salida de la app. Nunca se recupera automáticamente si hay entrada en vuelo/en cola, botones o teclas retenidos, o un estado nativo desconocido. La confirmación posterior debe comprobar otra vez teclas/botones y la misma identidad de sesión. Caducidad, prioridad local y DETENER se conservan; el efecto real se valida aparte en una ventana propia.

La continuidad de Android 0.2.11 exige una sola adquisición durante renovaciones sucesivas sin máximo total, arranque lento y rechazo de ACK tardíos o ventanas inválidas. `request_window_ms` es opcional y conserva el watchdog: no concede una sesión nueva al recibir una respuesta. Solo el indicador de `source=remote` admite caché prolongada; automatización, entrada directa y fuentes desconocidas deben seguir caducando si falta su heartbeat de material durante cinco segundos, aunque se renueve el lease. Se ejecutan también los tests JVM del transporte antes de entregar el APK; presupuestos de red, ventana del cliente y TTL nativo se validan por separado. La aceptación física exige al menos 60 segundos de una única sesión con gestos, clics, DETENER y reconexión, además de los recibos de instalación y conservación.
