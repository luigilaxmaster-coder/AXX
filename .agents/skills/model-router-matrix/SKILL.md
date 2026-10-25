---
name: model-router-matrix
description: Utilizar el router existente de Axx y sus evaluaciones por tarea sin asumir disponibilidad de modelos.
---

# Selección de modelos en Axx

Implementaciones: `backend/inference/router.py`, `model_candidates.py`, `provider_settings.py` y adaptadores existentes. Conserva configuración, credenciales oficiales y preferencias de coste.

Las consultas deterministas y comandos registrados no necesitan un modelo. Para inferencia usa la función pública existente del adaptador y su esquema, después de inspeccionarlos; no hardcodees un modelo de una tabla histórica. Un candidato de catálogo no equivale a autenticación, modalidad compatible o inferencia verificada.

Selecciona únicamente proveedores y modalidades que admita la solicitud. Conserva objetivo, pasos confirmados e IDs de operación fuera de la conversación del proveedor. Un failover no autoriza repetir efectos unknown. No descargues pesos ni uses rutas pagadas como sustitución silenciosa.

Pruebas: `backend/inference/tests/` y `backend/tests/test_action_learning.py`. Esta integración no acredita nuevas inferencias ni cifras de latencia. Consulta el estado real en Proveedores y registra el resultado de la generación exacta.
Ver `docs/UNIFIED-EXECUTION.md`.
