# AXX Live Spatial Intelligence & Canvas-First Status

Este documento registra la auditoría técnica, la línea base y el estado de implementación del subsistema **Live Spatial Intelligence** en Axx, integrando Magic Pen, enrutamiento híbrido de proveedores (2D universal / 3D exclusivo GPT-6.1 Sol Fast) y la capa declarativa de presentación.

---

## 1. Matriz de Componentes y Estado

| Subsistema | Archivo Propietario | Contrato / Protocolo | Dependencias | Estado |
| :--- | :--- | :--- | :--- | :--- |
| **DPI Nativo & Captura Windows** | `backend/magic_pen.py`, `src-tauri/src/magic_pen.rs` | `PER_MONITOR_AWARE_V2`, `SetWindowDisplayAffinity(0x11)` | `user32.dll`, Tauri IPC | **VERIFIED** |
| **Persistencia & Idempotencia** | `backend/magic_pen.py` | SQLite `requests.sqlite`, SHA-256 de captura | `sqlite3`, `hashlib` | **VERIFIED** |
| **Discriminador de Modelos (Gating)** | `backend/spatial_plan.py` | `is_gpt_fast_model(provider, model)` | Ninguna (Pure Python) | **VERIFIED** |
| **Esquema SpatialPresentationPlan** | `backend/spatial_plan.py` | `validate_spatial_plan`, `extract_or_build_spatial_plan` | Pydantic/Dict, JSON | **VERIFIED** |
| **Endpoints Backend Pen & Spatial** | `backend/server.py`, `backend/magic_pen.py` | `/axx-api/pen/start`, `/query`, `/spatial_plan` | HTTP Bearer Token | **VERIFIED** |
| **Capa Pasiva 2D Overlay** | `1.AXX/capture-overlay.html`, `1.AXX/scripts/` | SVG / Canvas overlay click-through | WebView2, Win32 | **PARTIAL** |
| **Runtime Three.js Procedural** | `1.AXX/scripts/spatial/` | `SceneRuntime`, mallas paramétricas | Three.js local | **PARTIAL** |
| **Tríada: Guía & Computer Use** | `backend/actions/executor.py`, `backend/actions/uia_observer.ps1` | `ActionExecutor`, contratos tipados UIA | Windows UIA | **EXISTS** |

---

## 2. Política de Modelos y Salvaguardas

1. **Magic Pen permanece agnóstico y compatible con Ollama:**
   - Proveedores locales como `Ollama` (`gemma4:31b`, `qwen3:4b`, etc.) o `LM Studio` funcionan de forma transparente en Magic Pen.
   - Generan automáticamente planes `SpatialPresentationPlan` en modo `overlay_2d`, con recuadros delimitadores, flechas, etiquetas y resumen de audio, con `scene_3d: None` y `spatial_3d_allowed: False`.
   - No se exige a los modelos locales esquemas 3D complejos, eliminando alucinaciones sintácticas y tiempos de espera excesivos.
2. **Exclusividad de la Síntesis 3D para GPT-6.1 Sol Fast:**
   - La generación declarativa de escenas interactivas 3D Three.js (`interactive_3d`, mallas procedurales, vistas explosionadas y jerarquías semánticas) está estrictamente restringida a `gpt-6.1-sol-fast` (o modelos GPT rápidos con *Structured Outputs* nativos).
   - Cualquier intento de forzar `mode: "interactive_3d"` en un modelo no autorizado es degradado inmediatamente a `overlay_2d` en el backend por el validador semántico.
3. **Validación Defensiva (Zero-Execution Sandbox):**
   - El modelo nunca emite código JavaScript ni Python ejecutable; emite únicamente datos declarativos.
   - Límites duros: máximo 128 primitivas 3D, 64 anotaciones 2D, coordenadas finitas y primitivas restringidas a la allowlist (`box`, `cylinder`, `sphere`, `tube`, `shaft`, `piston`, `pcb`, `chip`, `wire`, `arrow`).

---

## 3. Verificación de Tests Automatizados

La suite completa de tests de Magic Pen y Spatial Plan fue ejecutada y verificada:

```powershell
python -m unittest backend.tests.test_magic_pen backend.tests.test_magic_pen_http backend.tests.test_spatial_plan backend.tests.test_spatial_http -v
```

* **Resultado:** 39 tests ejecutados, **39 pasando exitosamente** (0 fallos, 0 errores, tiempo: 11.53 s).
* **Casos probados:**
  1. Captura física DPI y restauración ante errores.
  2. Idempotencia y durabilidad de cancelación.
  3. Gating estricto: rechazo de 3D en Ollama/modelos locales y degradación elegante a 2D.
  4. Generación y aceptación de 3D con `gpt-6.1-sol-fast`.
  5. Desinfección de inyecciones `<script>` y rechazo de primitivas fuera de allowlist.
  6. Endpoint HTTP autenticado `/axx-api/pen/spatial_plan` para consultas directas desde el frontend.

