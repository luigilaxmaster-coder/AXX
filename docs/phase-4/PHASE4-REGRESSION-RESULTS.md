# Resultados de regresión · fase 4

Código de integración en 7eb0f792b5db127b843f3e4b18c047daea8a3481. Los logs de prueba están en build/phase4.

| Gate | Resultado observado |
|---|---|
| Rust en Windows | 19 aprobadas. Un helper está ignorado como prueba directa y se ejecuta desde su integración. |
| Barrido general inicial | 1663 casos, 14 omitidos, tres fallos y dos errores. Se corrigieron los cinco casos y sus suites focalizadas completaron 71 pruebas con PASS. |
| Barrido general de cierre | PASS. 1664 casos en 1887.476 segundos, 14 omitidos y cero fallos o errores. El archivo python-backend-source.txt fija el commit del proceso de prueba. |
| Python focal de cierre | PASS, 71 casos de Computer Use, CMD y PowerShell, callback Telegram y gateway MCP nativo tras las cinco correcciones. |
| Python Connect | 131 casos, uno omitido. |
| Python inferencia | 166 casos aprobados. |
| Chromium de escritorio | PASS, 42 comprobaciones. Incluye WebGL, opt-in de herramientas, correcciones aisladas por chat y paneles existentes. |
| Connect en Chromium | PASS, 39 comprobaciones. La prueba de Escape distingue cancelación de chat de la cancelación independiente de Anticipación. |
| Biblioteca de comandos y paneles internos | PASS en Chromium, 34 y 6 comprobaciones respectivamente. |
| Magic Pen, formas espaciales y técnicas, despiece, tentáculos y sintaxis | PASS. Magic Pen utilizó WebGL real en Chromium y límites de captura/inferencia nativos simulados. |
| Mutaciones | PASS de tres mutaciones sobre el commit evaluado. Detectadas la ampliación a 1000 objetos, la omisión de revocación en despacho y la eliminación del permiso existente de Computer Use. Recibo mutations-final.json. |
| Compatibilidad PC/móvil | PASS. Contrato 15, backend móvil 112 con una omisión, navegador móvil 58 y selector de escritorio 8. Recibo build/companion-validation.json con las entradas del candidato. |
| Consistencia y entrega | PASS. Versiones y README coinciden, 24 pruebas de release aprobadas y ambos scripts PowerShell válidos. |
| PDF nativo aislado | PASS, dos pruebas con Edge headless, descarga local, hash, origen y ausencia de sobrescritura. Los resets al cerrar el servidor de prueba quedaron registrados como diagnósticos del fixture. |
| Android físico | MANUAL_REQUIRED. ADB informó cero dispositivos autorizados. |

## Recuperación Windows observada

El binario Tauri de depuración compilado desde 7eb0f792b5db127b843f3e4b18c047daea8a3481 ejecutó WebView2 y Python reales en un perfil aislado. En la copia se variaron la identidad de la aplicación, los nombres de exclusión entre instancias y la instalación del atajo global. El binario de prueba tiene SHA-256 e607b7119ff78028dd545046114b7b6999e0e9fea9214c62b108c87d84a67cbd.

Se observó un hijo Python y su proceso PowerShell de espera tras una aprobación de prueba. Al terminar solo el hijo Python, el host emitió lost/ready, arrancó un único PID de reemplazo y reconectó la interfaz. La preparación sin ejecutar quedó expired. El trabajo en curso quedó unknown y visible en Comandos, con poscondiciones falsas y el proceso de espera eliminado. El permiso de chat persistió. Tras terminar el reemplazo inmediatamente, el supervisor quedó sin hijos y dejó de reintentar.

Un ensayo anterior del guion sobre d39ab2d agotó la espera del fixture porque buscaba el comando en texto y Windows lo ejecutaba como EncodedCommand. Se corrigió esa observación del guion. La ejecución sobre el commit final observó el comando codificado exacto en un perfil limpio y aprobó todas las comprobaciones. El recibo y el guion están en build/phase4/native-recovery.json y build/phase4/native-recovery.ps1. El recibo tiene SHA-256 5684bbf7cf345d3806245248e77be57b8686728d60d7e34aa0829f39145b84b0.

## Base y correcciones de las pruebas

Claude observó el gate PC/móvil fallando al consultar tarde el texto transitorio «toque». El renderer cambia el texto al vencer la ventana de interacción. Se conserva la pulsación real de Enter y se observa su transición con MutationObserver dentro del plazo existente. La ejecución PASS fue secuencial entre sus etapas, con el barrido general de Python en segundo plano y sin otros gates Chromium iniciados por la tarea. La combinación anterior de los fixtures de escritorio también mutaba directamente la identidad del chat sin cargar su contexto de memoria. El fixture moderno selecciona conversaciones reales del simulador. Las comprobaciones de compensación se alinearon con el estado visible «objetivo pendiente» de main.

## Reproducción en este checkout

Los logs preservan los comandos y los recibos de las pruebas ejecutadas. El runtime Node de esta máquina proporciona Playwright y el ejecutable Chromium usado por los contratos. El workflow de versión fija las dependencias para otras máquinas.

```powershell
$env:NO_PROXY = '127.0.0.1,localhost,::1'
python -m unittest discover -s backend/tests -v
python -m unittest discover -s backend/connect/tests -q
python -m unittest discover -s backend/inference/tests -q
$env:TAURI_CONFIG = '{"bundle":{"resources":[]}}'
cargo test --offline --locked --manifest-path src-tauri/Cargo.toml --lib
python scripts/validate_companion.py --output build/companion-validation.json
```

La prueba PDF usa AXX_TEST_BROWSER_NATIVE=1 y su propio perfil de Edge. La supervisión real se reproduce con build/phase4/native-recovery.ps1. La sonda Ollama se reproduce con build/phase4/real-provider.ps1 y requiere el modelo llama3.2:1b ya instalado. Ambos guiones usan procesos y estado de prueba propios.

El log del barrido general final tiene SHA-256 e79b46c92d55e2365be9ae650296999331c4ffcfe1ef00037cd4f376ac4ff13c.
