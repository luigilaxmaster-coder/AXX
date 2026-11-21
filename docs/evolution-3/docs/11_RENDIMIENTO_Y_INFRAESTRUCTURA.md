# 11 — Rendimiento, infraestructura y costes

## 11.1 Contexto del dispositivo y principio de optimización

Hardware objetivo inicial declarado previamente: Acer Spin 3, Intel i7 de 11.ª generación, Iris Xe y 16 GB RAM. No se conoce la disponibilidad efectiva de VRAM compartida, drivers, espacio SSD ni si Hyper-V/Windows Sandbox están habilitados. No afirmar aptitud para varias VMs o LLM 50B sin inventario real. Operación inicial: un renderer residente activo, Code Studio cargado bajo demanda, modelos auxiliares pequeños locales y modelos grandes remotos autorizados.

## 11.2 ResourceGovernor

`ResourceBudget`: CPU concurrent task limit, process count, RAM hard/soft, GPU device memory, render quality, provider token/currency limit, network egress, disk quota, foreground lease, capture bandwidth. Prioridad: interactividad usuario/voz/entrada > avatar residente > computación de usuario en foreground > tareas pesadas background > renders y reindexado. Escenas ocultas liberan WebGL; gestión de context loss. Medición por PID/job/sesión y reportes p50/p95.

## 11.3 Perfiles recomendados (propuestas)

| Perfil | Política | Uso |
|---|---|---|
| Eco | 1 agente activo de ejecución, sin VM local, render básico, índices diferidos | batería/equipo ocupado |
| Balanceado | hasta 2 agentes inferencia si recursos, 1 heavy job, lazy UI | hardware objetivo inicial |
| Máximo | hasta límites medidos del servidor, parallel workers, GPU según inventario | VM o nodo dedicado |

No son cuotas universales ni resultados comprobados. CPU, RAM y GPU deben medirse después del baseline. Un modelo de 50B/100B requiere acceso nube/infraestructura dimensionada por cuantización/contexto; OpenVINO sobre Iris Xe se usa preferentemente para tareas auxiliares compatibles, con benchmark A/B.

## 11.4 Planificador de coste

`CostLedger`: asignaciones por usuario/agente/proyecto/tarea/proveedor; número de tokens prompt/output/cache cuando proveedor informa; estimación vs uso real; límites diarios/mensuales; no fallback a proveedor de pago automáticamente. Renders externos, generación `asset-gate` y API de terceros requieren opt-in y cuota. `estimated_cost` no sustituye coste facturado; si no hay metering, estado `unknown_cost` visible.

## 11.5 Infraestructura por nivel

**Nivel 0 (PC):** AXX host + SQLite + avatar + UI + MCP + Git worker liviano + browser perfiles bajo demanda. Requiere interrumpir cargas pesadas que interfieran con voz.

**Nivel 1 (homelab):** servidor de tareas dentro LAN con CPU/RAM/NVMe, CodeWorker, CAD, renders, navegador aislado; acceso mediante mTLS/Tailscale/VPN aprobado. No exponer puertos privilegiados a internet.

**Nivel 2 (nube/VPS):** workers para LLM, CAD/video/VM según GPU y licencias; almacenamiento cifrado, expiración de sesiones, presupuesto, auditoría de transferencia. VPS sin GPU no hace mágicamente inferencia local rápida 100B. Costes y legalidad de assets independientes.

## 11.6 Política de memoria gráfica

No lanzar un canvas WebGPU por agente; miniaturas precalculadas o en caché por forma/paleta; un avatar activo con animación, Magic Pen/Code Studio priorizados cuando visibles. Renderer de escenas libera texturas, geometrías, materiales, event listeners y context al cerrar/ocultar; reabre desde SceneDocument, no desde estado implícito de JS. Evitar duplicación de Three.js incompatible en el mismo contexto WebView.

## 11.7 Observabilidad

Métricas: tiempo desde dispatch a primer evento, tiempo hasta primer texto/voz útil, latencia de tool, p95, fallos de modelos, retries, tokens/coste, CPU/RAM/GPU, FPS, colisiones de leases, conflictos de archivos, stale observations, timeouts de VM, replay SSE, tiempo de reanudación, colisiones de escena, verificador. Logs con `correlation_id`, `agent_id` y `task_id` sin datos sensibles. Activación diagnóstica con límite de tamaño/retención.

## 11.8 Escenarios de degradación

Sin Internet: conservar chats y workspaces; proveedores nube se muestran no disponibles; no cargar modelo distinto sin permiso. Sin GPU: vistas estáticas o renderer de calidad reducida con notificación de modo; no prometer 3D interactivo completo. Sin VM: `isolated` devuelve no disponible. Sin LSP: editor de sintaxis funciona, se indica falta de IntelliSense. Fallo Asset Gate: fallback a catálogo local, no generar con coste sin consentimiento. Sin permiso file root: no leer. Sin micrófono: chat texto continúa. Servicio backend caído: no se muestran tareas como completadas.

## 11.9 Benchmark reproducible

Dataset fijo de 20 operaciones de chat, 10 tareas de código, 10 ediciones Magic Pen, 5 workflows multiagente y 5 Computer Use controladas, junto a ejecución idle y durante dictado. Capturar versión, hora, hardware, CPU load, proceso, RAM, perfil de energía, pantalla/DPI y proveedores. Repetir al menos 3 rondas por modo; registrar medianas/p95 y errores, no comparar muestras con datos distintos. Los objetivos se fijan después de recoger baseline.
