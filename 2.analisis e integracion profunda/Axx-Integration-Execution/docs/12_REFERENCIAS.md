# 12 — Referencias y trazabilidad

Fecha de revisión documental: 2026-10-19 UTC.

## Fuentes verificadas en esta entrega

1. GitHub, commit observado: [90e4f43865e7fd1724c5f74227ba106ae01122cd](https://github.com/pacocartones/free-llm-api-hub/commit/90e4f43865e7fd1724c5f74227ba106ae01122cd). Commit fechado 2026-10-18T21:28:10Z; identifica la revisión, no una prueba de proveedores.
2. [MCP README fijado al commit](https://github.com/pacocartones/free-llm-api-hub/blob/90e4f43865e7fd1724c5f74227ba106ae01122cd/packages/mcp/README.md). Se verificó que describe consultas de solo lectura, uso desde checkout local y ausencia de publicación npm confirmada. No se ejecutó su suite aquí.
3. [Metodología fijada al commit](https://github.com/pacocartones/free-llm-api-hub/blob/90e4f43865e7fd1724c5f74227ba106ae01122cd/docs/methodology.md). 'Verificado' se refiere a comprobación documental con fecha; no garantiza salud actual. La evaluación no cubre todos los metadatos técnicos.
4. `baseline/axx-api-router/router.py`, README, configuración y tests de la versión 1 entregada anteriormente. Inspeccionados localmente; 20 tests ejecutados de nuevo. Código inventariado en MANIFEST_SHA256.json.

## Fuentes primarias que el ejecutor debe revisar al activar conexiones

- [Groq: compatibilidad](https://console.groq.com/docs/openai)
- [Groq: límites](https://console.groq.com/docs/rate-limits)
- [OpenRouter: límites](https://openrouter.ai/docs/api-reference/limits)
- [Python: subprocess](https://docs.python.org/3/library/subprocess.html)
- [Python: SQLite](https://docs.python.org/3/library/sqlite3.html)
- [Tauri: documentación oficial](https://v2.tauri.app/) solo si el proyecto inspeccionado usa Tauri 2; para otra versión usar su documentación correspondiente.

Estos enlaces son puntos de comprobación, no evidencia de que se hayan validado cuotas, SDKs, modelos o Windows para esta entrega. No se incluyen cifras actuales de planes ni IDs de modelo supuestamente gratuitos sin consulta de cuenta.

## Decisiones propias de esta especificación

Deadline 70 s, límites de captura, máximo de concurrencia, retención de logs, reverificación a 30 días y parámetros de cola son valores de diseño propuestos para implementación. No proceden de las ofertas de los proveedores ni de benchmarks del Acer. Se deben validar al integrar y actualizar docs/tests si cambian.

## Dependencias excluidas

ai-memory, CLI-Anything, BitNet, iai-personal-memory-engine, invisible_dots y otros repositorios no se integraron ni evaluaron en este paquete. Su aparición en conversaciones del proyecto no implica compatibilidad probada ni autoriza ampliar esta entrega. No se necesita ninguno para el failover básico.
