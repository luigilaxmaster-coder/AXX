# Contexto del proyecto Axx

Actualizado: 2026-10-28.

- **Proyecto y propósito:** Axx es un asistente residente para Windows. Axx Mobile extiende al teléfono las conversaciones, el personaje y los servicios de la PC.
- **Stack:** Tauri y Rust en Windows; Python para servicios y ejecución; HTML, CSS y JavaScript para la interfaz; Capacitor para Android.
- **Fase actual:** entrega conjunta de voz y móvil en Windows 0.22.16 y Android 0.2.1. La instalación y publicación de Windows se verifican con recibos; la instalación y validación física Android están pendientes.
- **Restricciones clave:** conservación de la interfaz 3D, datos, credenciales y ajustes; identidad TLS verificada; permisos separados y aprobaciones del escritorio; ninguna repetición automática de operaciones inciertas.
- **Criterio de terminado:** pruebas pertinentes aprobadas, Windows instalado y verificado antes de publicarse con hashes confirmados, y Android compilado con evidencia separada de instalación y validación física.
