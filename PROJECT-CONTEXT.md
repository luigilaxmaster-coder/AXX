# Contexto del proyecto Axx

Actualizado: 2026-10-29.

- **Proyecto y propósito:** Axx es un asistente residente para Windows. Axx Mobile extiende al teléfono las conversaciones, el personaje y los servicios de la PC.
- **Stack:** Tauri y Rust en Windows; Python para servicios y ejecución; HTML, CSS y JavaScript para la interfaz; Capacitor para Android.
- **Fase actual:** integración coordinada de Desktop, Android, voz y Transfer. Las versiones de fuente se consultan en package.json y mobile/package.json; la descarga Windows confirmada, en release.json; la instalación real, en native-runtime.json y los recibos móviles. La evidencia física del Samsung y sus límites están en docs/mobile; no se extiende a otros teléfonos ni a una versión nueva sin comprobación.
- **Diseño y compatibilidad permanentes:** conservar la apariencia aprobada y aplicar docs/mobile/COMPATIBILITY-PROTOCOL.md. Android 0.2.8 añade caché de gotas con comparación exacta de píxeles y medición física, sin bajar calidad. Conserva la corrección de las 24 incidencias y exige 120 escenarios más doce referencias de apariencia en cada gate. SCREEN-FIXES-20261029.md separa la evidencia de navegador de instalación/hardware; no acredita soporte físico universal ni iOS nativo.
- **Restricciones clave:** conservación de la interfaz 3D, datos, credenciales y ajustes; identidad TLS verificada; permisos separados y aprobaciones del escritorio; ninguna repetición automática de operaciones inciertas.
- **Criterio de terminado:** pruebas pertinentes aprobadas, Windows instalado y verificado antes de publicarse con hashes confirmados, y Android compilado con evidencia separada de instalación y validación física.

- **Revisión móvil 0.2.9:** cámara progresiva, identidad de enlace visible en Archivos y regresiones de canvas oculto/selector de Windows. Gate incluye selector y huellas. Ver docs/mobile/FLUENCY-AND-PATHS-20261029.md; instalación y consumo/calor prolongados requieren recibos físicos separados.

- **Revisión del trackpad:** 0.2.10 falló la aceptación de entrada. Android 0.2.11 está instalada conservando datos, con gate y JVM aprobados; añade sesión renovable sin máximo total, ventanas conservadoras y diagnóstico nativo. El usuario aceptó manualmente 65 segundos con movimiento inicial/final y DETENER junto a Windows 0.22.30 R3. Otros gestos y ensayo térmico siguen sin revalidarse físicamente; STOP automático vigente. Ver docs/mobile/TRACKPAD-20261029.md.
