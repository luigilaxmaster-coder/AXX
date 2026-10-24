# ECC en el trabajo de Axx

## Instalación verificada

El 24 de octubre de 2026 se instaló ECC 2.2.3 mediante el mecanismo nativo
de plugins de Codex, desde <https://github.com/affaan-m/ECC>.
La copia revisada corresponde al commit
`90606c8315ee09cafc303515c5f33024db6b9882`.

```powershell
codex plugin marketplace add affaan-m/ECC
codex plugin add ecc@ecc
# Desde una copia de ECC:
node scripts/codex/check-plugin-cache.js
```

La comprobación local resolvió correctamente las skills, configuración MCP,
icono y logotipo del plugin instalado. La instalación reside en el perfil de
Codex y no se incorpora al instalador de Axx. Las nuevas skills se descubren
al iniciar una sesión nueva. La confianza de hooks tiene su propio control
en Codex; instalar el plugin no equivale a autorizar sus comandos automáticos.

## Equipo usado para esta entrega

| Responsabilidad | Guías ECC aplicadas | Propiedad de cambios |
|---|---|---|
| Voz en vivo | Verification loop, code simplifier | Captura, borrador, conversación y controles de voz |
| Capacidades | Architect, search first, verification loop | Taller, revisiones, evidencias y memoria de habilidades |
| Revisión independiente | Code reviewer | Rutas de permisos, recuperación, aislamiento y pruebas de regresión |
| Integración principal | Reglas del proyecto y entrega Windows | API, interfaz del taller, compilación, instalación y publicación |

Los agentes trabajan sobre el árbol existente y conservan cambios ajenos.
La revisión cita fallos reproducibles; las comprobaciones nativas se ejecutan
de forma secuencial para no disputarse el foco, el micrófono o la ventana.

## Alcance

ECC aporta guías de ingeniería y revisión a este trabajo. No concede permisos
al agente de Axx ni ejecuta sus herramientas. El taller de capacidades se apoya
en `ActionLearning`, `SkillMemory` y `CommandService` del propio proyecto.
La guía técnica de ese ciclo está en [SELF-IMPROVEMENT.md](SELF-IMPROVEMENT.md).

La validación distingue pruebas controladas, integración por IPC y evidencia
del ejecutable Windows instalado. Las capturas inyectadas durante diseño
no sustituyen la comprobación del paquete final.

## Revisión con Ponytail

Se aplicó la guía oficial [Ponytail](https://github.com/DietrichGebert/ponytail)
en modo `full`: seguir los llamadores y el flujo real, reutilizar componentes
existentes, evitar dependencias adicionales y conservar validación, accesibilidad
y recuperación. Esta guía se usa durante el desarrollo; no es parte del runtime.

La revisión de Magic Pen encontró un desfase real de coordenadas entre Tauri y
el backend con monitores de escalas distintas. La corrección usa el contexto DPI
del hilo de captura y restaura el anterior, sin cambiar la configuración de
Windows ni la de otros hilos. La aceptación exige repetir la captura nativa
con las dos pantallas y verificar el resultado del proveedor configurado.
