# Contexto del proyecto Axx

Actualizado: 2026-10-29.

- **Proyecto y propósito:** Axx es un asistente residente para Windows. Axx Mobile extiende al teléfono las conversaciones, el personaje y los servicios de la PC.
- **Stack:** Tauri y Rust en Windows; Python para servicios y ejecución; HTML, CSS y JavaScript para la interfaz; Capacitor para Android.
- **Fase actual:** integración coordinada de Desktop, Android, voz y Transfer. Las versiones de fuente se consultan en package.json y mobile/package.json; la descarga Windows confirmada, en release.json; la instalación real, en native-runtime.json y los recibos móviles. La evidencia física del Samsung y sus límites están en docs/mobile; no se extiende a otros teléfonos ni a una versión nueva sin comprobación.
- **Diseño y compatibilidad permanentes:** conservar la apariencia aprobada y aplicar docs/mobile/COMPATIBILITY-PROTOCOL.md. El estudio SCREEN-STUDY-20261029.md registra 120 escenarios de navegador, con 24 incidencias de adaptación futuras; no acredita soporte universal ni iOS nativo.
- **Restricciones clave:** conservación de la interfaz 3D, datos, credenciales y ajustes; identidad TLS verificada; permisos separados y aprobaciones del escritorio; ninguna repetición automática de operaciones inciertas.
- **Criterio de terminado:** pruebas pertinentes aprobadas, Windows instalado y verificado antes de publicarse con hashes confirmados, y Android compilado con evidencia separada de instalación y validación física.
