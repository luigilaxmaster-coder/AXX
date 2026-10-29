# Android 0.2.4 · Personalización y sincronización

Validación: 2026-10-28. Samsung SM-A217M / A21s, Android API 31; Windows instalado 0.22.21.

## Cambio entregado

- Tema claro o negro y acento local persistentes; las barras nativas siguen el tema. Contraste del texto y selección visible incluso con acentos blanco o negro.
- Color, forma y acabado del personaje compartidos con el PC. Se usa el ejecutor de identidad existente, con el permiso de control del teléfono, identificadores idempotentes ligados al dispositivo y comprobación del resultado. La app espera también el snapshot real antes de indicar sincronización.
- Rasterización GPU de la geometría, movimiento y tabla de material existentes en el escritorio; respaldo CPU ante indisponibilidad o pérdida de contexto. Se evita regenerar el material cuando no cambia.
- Los colores y el material siguen llegando durante la interacción; solo se reserva temporalmente la cámara mientras se gira el personaje.

## Comprobado

| Prueba | Resultado |
| --- | --- |
| Instalación Android | 0.2.4-companion, código 25; actualización en sitio, enlace y borrador conservados |
| Apariencia local | Claro → negro → claro → negro, acento violeta y persistencia al recargar comprobados en el Samsung |
| Teléfono → PC → teléfono | Paleta, forma y acabado cambiados desde los selectores reales; identidad instalada y snapshot coincidentes |
| PC → teléfono | Cambio independiente de paleta recibido en el Samsung; identidad original restaurada al finalizar |
| Fluidez GPU | 420 × 550; muestras 46, 51, 49, 51, 48, 51, 49, 51 FPS; mediana 50 FPS, dibujo mediano 17,95 ms, cero fallos |
| Texto y teclado nativos | 100 % y 170 %, cuatro pestañas sin desbordamiento; teclado de 299 puntos con Enviar por encima de la navegación |
| Acción desde el teléfono | Consulta del sistema ejecutada y postcondiciones verificadas en Windows |
| Pruebas de fuente | 59 de servicio y 17 de interfaz; TLS/permisos, aislamiento de recibos, idempotencia, errores de guardado, contraste y equivalencia GPU/CPU |
| Windows instalado | Hashes de binarios, registro, atajos, backend autenticado y presencia nativa observada; personalización adicional por TLS aislado hacia el ejecutor instalado |

APK SHA-256: `12c2fba4348f229f514e06573bf0db8fa948f631da4b8a1c20da07741bdb4b41`.
Es un APK de prueba local; no se presenta como publicación Android en una tienda.

Los recibos y capturas privadas quedan en `build/mobile-024/`; la copia de recuperación conserva datos actuales, WebView e instalación. Cachés descargables y copias históricas de QA están excluidas de esa copia; sus originales no se eliminan.

## Límites

Los snapshots visibles se consultan cada dos segundos; cada dispositivo anima localmente la identidad compartida. No es una transmisión de los fotogramas del PC. La medición de fluidez corresponde a esta escena y este teléfono. Los temas de la superficie son locales al teléfono; la paleta, forma y material pertenecen al PC.

El Samsung aplica un tinte cálido a la captura completa, incluidas las barras del sistema. La superficie web negra comprobada es `rgb(9, 11, 16)`; la app no modifica los ajustes globales de pantalla.

El escaneo óptico del QR sigue aplazado por el usuario. Audio físico y efecto de todos los gestos de control remoto conservan validación separada. Una consulta ejecutada no acredita todos los comandos ni todas las integraciones de escritorio.
