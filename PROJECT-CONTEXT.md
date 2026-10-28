# Contexto del proyecto Axx

Actualizado: 2026-10-28.

- **Proyecto y propósito:** Axx es un asistente residente para Windows. Axx Mobile extiende al teléfono las conversaciones, el personaje y los servicios de la PC.
- **Stack:** Tauri y Rust en Windows; Python para servicios y ejecución; HTML, CSS y JavaScript para la interfaz; Capacitor para Android.
- **Fase actual:** Windows 0.22.21 instalado. Android 0.2.4 instalado en Samsung A21s: temas claro/negro, acento local y color/forma/acabado del personaje sincronizados en ambos sentidos. GPU: mediana de 50 FPS en la prueba física. Texto 100/170 %, teclado de 299 puntos y consulta ejecutada en Windows verificados. Cámara QR, entrada remota y audio físico conservan aceptación separada. Consulte release.json para el instalador publicado con recibos GitHub.
- **Restricciones clave:** conservación de la interfaz 3D, datos, credenciales y ajustes; identidad TLS verificada; permisos separados y aprobaciones del escritorio; ninguna repetición automática de operaciones inciertas.
- **Criterio de terminado:** pruebas pertinentes aprobadas, Windows instalado y verificado antes de publicarse con hashes confirmados, y Android compilado con evidencia separada de instalación y validación física.
