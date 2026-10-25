---
name: agent-s-vision-grounding
description: Selección semántica UIA con abstención en Axx; Agent S, SoM y grounding visual aún no integrados.
---

# Observación y grounding

Estado: existe selección semántica ejecutable; no hay adaptador Agent S ni modelo visual calibrado.

Usa `axx.desktop.window.find` con HWND hexadecimal, PID y nombre exacto. Su resultado puede ser selected, ambiguous o not_found. Un árbol truncado impide seleccionar. No conviertas un candidato en una acción: usa el comando registrado y conserva aprobación y destino.

La observación incluye ID, sesión, proceso e inicio, ventana, tiempos y coordenadas físicas. Los tokens incluyen el inicio del proceso. No apliques un factor DPI global a UIA. Una caja OCR no demuestra un control interactivo.

Para incorporar visión faltan captura vinculada a observación, modelo y pesos con hash/licencia, transformaciones de recorte y escala, selección con abstención y evaluación en aplicaciones reales. No inventes un endpoint ni llames a un VLM que no esté configurado.

Pruebas actuales: `backend/tests/test_unified_execution.py` y `scripts/verify-unified-windows.py`. Los gates G1/G2 del diseño siguen pendientes; la prueba UIA no los sustituye.
Ver `docs/UNIFIED-EXECUTION.md`.
