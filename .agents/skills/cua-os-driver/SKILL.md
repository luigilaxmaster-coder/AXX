---
name: cua-os-driver
description: Control local de Axx mediante los adaptadores nativos registrados; Cua upstream pendiente.
---

# Control de escritorio de Axx

Estado: el runtime usa UIA nativa de Axx, no un SDK Cua instalado.

1. Consulta `axx.architecture.status` y el catálogo antes de preparar una operación.
2. Usa `axx.desktop.list_windows`, `axx.desktop.window.inspect` y `axx.desktop.window.find` para observar y seleccionar destinos reales.
3. Prepara mediante CommandService y su política de aprobación. El modo queda ligado al ID.
4. Background solo admite las rutas declaradas en `backend/actions/execution_contract.py`. No sustituirlas por PostMessage, un cursor dibujado o entrada global.
5. Comprueba state, dispatch_status, effect_status y postconditions_passed. Una pulsación entregada no confirma la intención.
6. Cancelar detiene futuros despachos, sin revertir efectos. No repitas un resultado unknown.

Dependencias: Windows, worker PowerShell empaquetado y proveedor UIA del destino. El shell existente usa el intérprete instalado de Windows con Job Object y límites; no presupone PowerShell 7.

Errores: background_unavailable, isolated_unavailable, control ausente o ambiguo, permiso inválido, timeout y efecto desconocido.
Prueba: `python scripts/verify-unified-windows.py` y `python -m unittest backend.tests.test_unified_execution -q`.
Contrato y límites: `docs/UNIFIED-EXECUTION.md`. La integración Cua externa requiere versión fijada y pruebas propias.
