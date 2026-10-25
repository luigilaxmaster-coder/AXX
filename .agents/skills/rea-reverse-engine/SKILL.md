---
name: rea-reverse-engine
description: Diagnóstico previo a una integración REA; no hay proveedor REA ejecutable registrado en Axx.
---

# Diagnóstico y futura integración REA

Estado: no integrado. Compruébalo mediante `axx.architecture.status`.

Antes de investigar binarios, verifica si la acción ocurrió, si cambió la ventana y si existe API, CLI o accesibilidad adecuada. Tres fallos no autorizan repetir ni descompilar automáticamente.

Herramientas actuales: `axx.process.inspect` observa estado, ruta e inicio del proceso cuando Windows permite consultarlos; `axx.file.sha256` verifica archivos seleccionados con aprobación. Un HWND no es un archivo de entrada para un decompilador.

La integración pendiente necesita proveedor/versiones reales, descubrimiento de herramientas y esquemas, artefactos copiados y hashes, presupuesto de análisis y un informe que distinga hechos, inferencias y desconocidos. Un canal IPC encontrado en ASAR no constituye una API utilizable ni autoriza acceder a sesiones privadas. No ejecutes código extraído.

Cierre: una aplicación de ensayo, informe reproducible y adaptador probado por separado antes de registrarlo. No se ha aprobado ese gate.
Referencia: https://github.com/morluto/rea . Contrato: `docs/UNIFIED-EXECUTION.md`.
