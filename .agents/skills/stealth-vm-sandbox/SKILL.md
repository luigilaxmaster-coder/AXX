---
name: stealth-vm-sandbox
description: Requisitos de escritorio aislado en Axx; VM no integrada y ninguna garantía de invisibilidad antibot.
---

# Contexto aislado pendiente

Se conserva el identificador del skill por compatibilidad; stealth no es una garantía.
Estado: no hay contexto VM validado. Una solicitud delivery_mode=isolated se rechaza con isolated_unavailable; nunca se ejecuta en el host como sustitución.

Para habilitarlo: imagen y versión verificadas, acelerador disponible, identidad del invitado, límites efectivos de recursos, archivos compartidos explícitos, política de red y canal de artefactos. Una VM Linux no contiene automáticamente las aplicaciones Windows del usuario. No compartir todo el perfil ni incorporar credenciales por defecto.

Separar navegación persistente de análisis desechable. Detectar desafíos web, conservar el estado y esperar intervención o una integración compatible; no prometer inmunidad a Cloudflare. Restaurar un disco no revierte mensajes o cambios en servicios externos.

Pruebas pendientes: acelerador ausente sin fallback, límites efectivos, accesos permitidos y denegados, reinicio y recuperación de artefactos. Consulta `axx.architecture.status` y `docs/UNIFIED-EXECUTION.md`.
Referencia candidata: https://github.com/feder-cr/invisible_dots . No está instalada por este skill.
