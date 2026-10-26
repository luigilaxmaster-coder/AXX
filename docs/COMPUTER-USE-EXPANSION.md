# Ampliación de computer use

Solicitud: implementar las cinco entregas del documento AXX_FULL_DESKTOP_COMPUTER_USE,
según aplicaciones y cuentas disponibles. Base verificada: `d1f0783`, Axx 0.22.1.
Se conserva CommandService → ActionExecutor, WindowsInput, voz, ajustes y UI 3D.

## Matriz de implementación y aceptación en fuente (26 de octubre)

| Entrega | Recorrido | Resultado y límite |
|---|---|---|
| 1 | Web → PDF → visor | Edge real: enlace observado, descarga nueva, PDF inspeccionado y apertura del mismo archivo por ruta/hash. No certifica su composición visual. |
| 1 | OBS → grabación | Adaptador WebSocket 5 autenticado y comprobación ffprobe implementados; seis pruebas de contrato. OBS ausente: aceptación real pendiente. |
| 2 | OCR español | RapidOCR/ONNX con modelo latino PP-OCRv5 privado. Fixture y ventana Windows reales conservan ñ, tildes, decimales, unidades y negación. No certifica precisión general. |
| 2 | Memoria y trazas | FTS5 recupera candidatos sin cambiar selección exacta ni autorización. Diario existente conserva resultados/latencia; exportación OpenTelemetry pendiente. |
| 2 | ASR/VAD/parada | Conservar cambios de 0.22.1; separar pruebas de transcripción, parada y micrófono físico. |
| 3 | IFC → CSV → Excel → informe | IfcOpenShell real, Excel y Word/PDF: GUID, escala de unidad, nombre y total conservados; originales intactos. No certifica geometría BIM. |
| 3 | Puente CAD/BIM | AutoCAD/Revit/SketchUp no figuran en inventario. No declarar capacidades nativas verificadas sin anfitrión. |
| 4 | Blender y PowerPoint | Blender real: copia, escena/cámara/posición exactas, PNG decodificado a 128×128. PowerPoint real: texto exacto en copia, PPTX reabierto y PDF de una página. PDF PowerPoint e informe IFC renderizados y revisados visualmente: texto legible y sin recortes en estos fixtures; calidad general pendiente. |
| 4 | Obsidian/Spotify/Outlook | Apps detectadas; plugin, cuenta, scopes y operaciones no acreditados por presencia. |
| 4 | Adobe/VLC/Rhino/Resolve | No detectados; disponibilidad y aceptación condicionadas. |
| 5 | Componentes opcionales | Cua, OmniParser, UI-TARS, Pipecat, sqlite-vec y CLI-Anything sólo se adoptan ante mejora medida. |

## Evidencia y restricciones

- La prueba offline acredita contratos; una ejecución con la aplicación real acredita sólo su caso concreto.
- Paquete, configuración, conexión y operación verificada son estados independientes.
- Timeout tras mutación permanece desconocido; no se repite automáticamente.
- Archivos nuevos, destinos explícitos y comprobación de origen intacto.
- Espacio observado al inicio: aproximadamente 2,5 GiB libres en C:. No se borran archivos ajenos.
- Las fuentes de la propuesta son datos de diseño; no amplían permisos de envío, cuentas ni proveedores.
- No se crea PROJECT-CONTEXT.md por instrucción del usuario.

## MCP y entrada nativa

- Cliente stdio y Streamable HTTP integrado en el registro, permisos, planificador
  y ejecutor existentes. Catálogo dinámico con esquemas completos y activación
  explícita; secretos DPAPI. Pruebas reales con servidor MCP de fixture.
- Fachada nativa MCP HTTP local: tickets de un uso para operaciones ya admitidas;
  mismo broker de entrada y una sola entrada en el diario. Cursor Windows movido
  y restaurado con lectura posterior real, también desde el host instalado
  0.22.3. No acredita todas las aplicaciones.
- AnythingMCP local: Docker en WSL, PostgreSQL privado, imágenes por digest,
  HTTP de salud 200 y MCP anónimo 401. Primer administrador y llamada autenticada
  por gateway pendientes de contraseña aceptada. La fachada Windows actualmente
  conecta directamente por MCP, no a través del gateway.
- Instrucciones y límites: [MCP-LOCAL.md](MCP-LOCAL.md).

## Evidencia

Recibos de fuente en `evidence/mcp-expansion-20261026/`: `native-cursor.json`,
`ocr-spanish.json`, `desktop-ocr.json`, `blender-scene.json`, `gateway.json` y
`ifc-office/receipt.json`. Los fixtures temporales que aparecen en recibos pueden
haber sido eliminados al terminar las pruebas. No contienen contraseñas ni voces.

La primera suite general detectó un presupuesto de catálogo excedido (428 casos,
un fallo). Se corrigió usando títulos y parámetros tipados, con un presupuesto
separado para esquemas remotos; 26 pruebas focalizadas pasaron después. La segunda
suite completa terminó con 432 casos sin fallos y 10 omisiones optativas. OCR de
ventana, Blender, PowerPoint, Word/Excel y navegador se comprobaron además con
sus fixtures nativos. La prueba HTML → backend fuente → creación/hash de archivo
y repetición aprendida pasó usando la aprobación actual dentro del chat.

El backend congelado de 0.22.3 pasó cinco recorridos: MCP de fixture, enumeración
Windows por fachada MCP, PDF, IFC y OCR latino. El hash del binario queda en
`build/release-0.22.3/packaged-mcp.json`. Las pruebas HTML con ese backend también
verificaron aprobación dentro del chat, salida CMD y repetición aprendida; el
puente Tauri de esas pruebas es simulado y no acredita el host instalado.

La instalación y publicación se acreditan por los recibos de entrega y la
confirmación de hash de GitHub, respectivamente.
No se han validado aplicaciones ausentes, cuentas externas, micrófono físico,
multimonitor/DPI ni calidad visual general de los documentos exportados.

## Referencias de implementación

- [Descargas Playwright](https://playwright.dev/python/docs/downloads)
- [Conexión CDP](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp)
- [Protocolo OBS](https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md)
- [Procedimiento de entrega](RELEASING.md)

Este documento es seguimiento del trabajo; no es un recibo de instalación ni publicación.
