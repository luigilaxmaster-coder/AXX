# Corrección del selector de Ollama — 2026-10-21

## Causa y cambios
- La interfaz ofrecía Ollama local, pero no distinguía el servicio Cloud. Se añadió Ollama Cloud con su endpoint correspondiente.
- La consulta de Ollama ahora utiliza `/api/tags`, admite su catálogo nativo y excluye modelos que anuncian capacidades sin generación de texto.
- El campo de modelo se convirtió en una lista desplegable, con entrada manual separada y explicación cuando el servidor local no tiene modelos instalados.
- Se protege contra claves pegadas en el campo de modelo. Las preferencias antiguas con este patrón se limpian al iniciar.
- Se reparó la conexión existente conservando su autorización de cuota y guardando la credencial con DPAPI. No se incluyen secretos en esta evidencia.

## Comprobaciones
- Backend: 18 pruebas de configuración de proveedores y servidor aprobadas.
- Frontend general: 18 pruebas aprobadas.
- Selector de proveedores: pruebas aprobadas con catálogo Cloud, selección de otro modelo, guardado y servidor local vacío.
- Ollama instalado: responde, pero su catálogo local está vacío.
- Ollama Cloud: catálogo real con 22 modelos; inferencia autenticada real con `gpt-oss:20b` completada correctamente (véase `cloud-check.json`).
- Backend compilado: seis comprobaciones aprobadas, incluyendo consulta de catálogo, guardado, DPAPI y respuesta del modelo seleccionado mediante un servidor de prueba local (véase `packaged-verification.json`). Esta prueba del ejecutable no consume inferencias externas.
- Revisión propia de la separación de credenciales/modelos y de la conservación de la conexión seleccionada.

## Límites
No se descargaron modelos locales. La prueba de interfaz es automatizada; no constituye una inspección manual de la ventana nativa.
