# Axx residente: estado de frontend y límites de validación

Fecha: 19 de octubre de 2026. Proyecto: `C:\Users\luigi\Desktop\Axx assistant`.

## Fuente congelada para la distribución

| Recurso | SHA-256 |
|---|---|
| `1.AXX/Axx.html` | `1CC9A0E4F2B54C9B3012226B39E832882B266EF2BCBAB9B3302B7C1FA592AD45` |
| `1.AXX/scripts/native-voice.js` | `E61076C5081F8C442C054097731A7A15A25A1817E8035C6DAABEDB7594537555` |

`Axx.html` carga `scripts/native-voice.js` como recurso interno. Ambos deben estar incluidos en `frontendDist: ../1.AXX`. No se necesita una biblioteca JavaScript adicional para estos cambios. El archivo `native-voice-fallback.draft.js` no se carga en producción.

El respaldo anterior al modo residente está en `%LOCALAPPDATA%\Axx\backups\resident-20261019\Axx-before-resident.html`. No se restauraron otros cambios ni se alteraron credenciales o datos de memoria.

## Cambios implementados

- El arranque nativo presenta el cuerpo líquido sobre una superficie transparente. Se ocultan la cabecera, AXX/IDENTITY, navegación de modos, escenario y controles permanentes de regreso. La personalización sigue accesible desde herramientas/Ajustes, con las formas, paletas y controles originales de material y cámara.
- `ResidentDesktop` solicita al host una ventana ajustada a la unión del cuerpo y los controles abiertos mediante `desktop_layout`. Entrega el anclaje local del cuerpo para que el host compense el origen al ampliar o contraer. La geometría utiliza el espacio de monitor comunicado por el host; la posición global no se obtiene limitando el cuerpo a `innerWidth` o `innerHeight`.
- La posición de página del antiguo estudio y su seguimiento local se desactivan en modo nativo. Superar siete píxeles al arrastrar el cuerpo produce una llamada nativa `window_action: drag`; soltar después de mover no abre herramientas.
- Se conservan los paneles y cuadernos originales. Sus superficies visibles forman parte de la geometría compacta. Al cerrar el chat mediante su control de cierre se repliegan los controles y permanece el cuerpo.
- El primer dibujo se realiza explícitamente con el renderer existente. La petición de visibilidad no depende de `requestAnimationFrame`, que puede suspenderse mientras WebView2 está oculto. `Axx.resident.startup` distingue dibujo del cuerpo, envío de disponibilidad, confirmación y error. El proveedor de IA puede seguir pendiente mientras aparece el cuerpo.
- Los huecos se entregan al host como máscara alfa del cuerpo y regiones de controles concretos. El frontend por sí solo no prueba paso de clics entre procesos Windows.
- `BrainClient` filtra el catálogo de modelos usando exclusivamente proveedores cuyo estado de metadatos sea `ready_locally`. `missing_key`, `disabled` y los demás estados no habilitan modelos utilizables. La elegibilidad local no autentica ni verifica inferencia; `inferenceVerified` solo cambia tras una respuesta de texto final válida.
- El chat usa un solo transporte nativo `backend_request`, JSON final sin simular streaming y cancelación correlacionada. Los secretos permanecen en el host.
- Los controles de acciones y memoria siguen dentro de Ajustes. Permiten crear un archivo con comprobación SHA-256, guardar un procedimiento comprobado, reutilizarlo con nuevas entradas, buscar en ai-memory y leer su registro completo. Las rutas de búsqueda/lectura indican `execution_allowed: false`.
- El lector existente puede solicitar WAV mediante Windows SAPI y utiliza reproducción, pausa y parada reales de `HTMLAudioElement`. El selector informa las voces instaladas; no se inventa una voz española.
- El dictado existente puede utilizar `getUserMedia` y `MediaRecorder` con permiso explícito, hasta 55 segundos y 1,4 MB, para el ASR local del backend. Normaliza el idioma y entrega el texto confirmado a los callbacks y destinos originales. Este adaptador no envía el chat automáticamente.

## Prueba ejecutada en esta revisión

Comando:

```powershell
node 1.AXX/scripts/test-desktop-frontend.cjs
```

Resultado observado: **16 comprobaciones aprobadas, código de salida 0, cero excepciones no capturadas**. El test carga el HTML completo y el JavaScript de producción en Chromium con un contrato IPC controlado y explícitamente simulado. Esto no es una prueba física de WebView2, micrófono, altavoces, monitores ni proveedor remoto.

| Comprobación | Evidencia y alcance |
|---|---|
| Arranque completo | No hay excepción no capturada ni mensaje de fallo de inicialización. |
| Transparencia DOM | `html` y `body` tienen fondo transparente. |
| Solo cuerpo al arrancar | Cero botones visibles; la captura PNG con fondo omitido tiene cero píxeles con alfa mayor que cero fuera del canvas y sí contiene cuerpo renderizado. |
| Ventana compacta | Para cuerpo de 280 unidades solicita 304 × 304; abrir/cerrar el chat adapta la geometría sin alterar ese tamaño del cuerpo. |
| Panel alcanzable | El rectángulo completo del chat queda dentro de las dimensiones compactas solicitadas. |
| Arrastre | Eventos de puntero sobre píxeles opacos invocan el arrastre nativo exactamente una vez después del umbral; soltar no abre un módulo. |
| Identidad | Permanecen 24 formas y 9 paletas; un estado temporal de tarea no reemplaza forma ni paleta canónicas. |
| Catálogo sin acceso | Incluso con catálogo no vacío, `missing_key` y `disabled` dejan `connected=false`, lista utilizable vacía e inferencia sin verificar. |
| Chat | Una petición nativa JSON, metadatos de ruta conservados y una cancelación correlacionada que descarta respuesta tardía. |
| Acciones/memoria | Los controles visibles llaman los contratos de ejecutar, registrar, reutilizar, buscar y leer. |
| Cuaderno | Una superficie orgánica nueva participa en la unión compacta y queda dentro de ella. |
| Lectura | Un WAV PCM de prueba se decodifica y emite `playing` y `ended`; no se deduce salida audible del altavoz. |
| ASR | Se comprueban idioma normalizado, entrega de texto y ausencia de envío automático; el resultado ASR del test es una fixture, no reconocimiento de un micrófono físico. |
| WebView oculto | Con todos los callbacks RAF suspendidos y el backend aún pendiente, se dibuja el cuerpo y se completa el contrato de disponibilidad nativa. |

## Evidencia nativa que debe completar la entrega

El trabajador nativo comunicó una recepción auténtica de `desktop_layout` de 304 × 304 y `ready=true` en el candidato intermedio compilado con el HTML AB40. El host registró ventana visible, posición física `(1450, 550)` y tamaño físico `380 × 380` con escala 125 %. Esto acredita el recorrido IPC y la orden nativa de mostrar para ese candidato; no sustituye una captura del escritorio ni certifica todavía el binario final con hash `1CC9…AD45`.

La comprobación de la aplicación instalada, desplazamiento sobre otras aplicaciones, foco, paso de clics/rueda, atajos, recuperación tras reinicio, monitores y escritorios virtuales corresponde a la evidencia de ejecución de la entrega principal. Este documento no la atribuye a los tests de Chromium.

## Capacidades conservadas y dependencias pendientes

| Capacidad | Estado preciso de este frontend |
|---|---|
| Inferencia remota | Transporte y estados conectados. No se ha probado aquí una respuesta real de un proveedor gratuito ni se afirma disponibilidad sin credencial. |
| Lectura Windows | Adaptador conectado a SAPI. Falta prueba audible del equipo en esta revisión del frontend. Las voces enumeradas por el backend no incluyen español según la comprobación comunicada por su trabajador. |
| Dictado local | Adaptador conectado al ASR empaquetado y destinos originales. Permiso y captura de un micrófono real deben verificarse en la aplicación instalada. |
| Traducción | Se conservan los motores originales de navegador/proveedor y sus errores. Este adaptador de micrófono solicita `task: transcribe`; no presenta como activa traducción simultánea ni traducción general sin un motor disponible. |
| Audio/vídeo importado | Se conservan reproducción e importación SRT/VTT. El endpoint de ASR no convierte por sí solo el selector de archivos anterior en transcripción directa de archivos desde ese panel. |
| Música local | Controles originales conservados. La reproducción audible y reacción del cuerpo a audio real requieren verificación de ejecución. |
| Spotify/otras pestañas | No se presentan conectados sin integración. Se conserva el error explícito del backend y la dependencia del puente de pestañas. |
| Grabación | Se conservan `ScreenSession`, `MediaRecorder`, selección de pantalla y guardado. La cancelación contempla el estado real `running`. Permiso, captura y archivo reproducible requieren aceptación instalada. |
| Temporizador | Se conserva la autoridad original y su puente nativo. La persistencia/alarma en Windows requiere evidencia de ejecución. |
| Morph Reach | Las solicitudes de lanzamiento reconocen un recibo `dispatched`; no convierten ese recibo en prueba de una ventana de destino visible. |
| Memoria procedural | Controles nativos conectados. La prueba real del servidor oficial y del adaptador está en las evidencias de ai-memory; la comprobación final desde la instalación pertenece a la entrega principal. |
| Hey Axx y ampliaciones futuras | Siguen futuras; el cambio residente no las activa. |

Revisión de código propia más observaciones del trabajador nativo. No se presenta como revisión externa independiente.
