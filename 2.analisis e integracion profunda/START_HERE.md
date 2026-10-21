# Axx — paquete de ejecución e integración

Fecha: 2026-10-19. Versión documental: 1.0. Alcance: integrar el router existente en el Axx existente, validarlo con dos proveedores y preparar ampliaciones independientes.

## Acción inmediata

Entrega esta carpeta completa al agente que tenga abierto el repositorio real de Axx. Pídele ejecutar `PROMPT_MAESTRO_INTEGRACION.md`. Debe empezar por inspeccionar el proyecto y completar `templates/PROJECT_MAP.md`, sin pedir de nuevo requisitos ya definidos. Resolverá el stack y los puntos de conexión leyendo archivos reales.

Este paquete autoriza trabajo de implementación, pruebas y conexión dentro del proyecto indicado por el usuario. No autoriza eliminar otros proyectos, activar pagos, publicar contenido o instalar otra aplicación en lugar de Axx. Las credenciales se introducen localmente; el agente no debe pedir que se peguen en el chat.

## Contenido y orden de lectura

| Documento | Finalidad |
|---|---|
| [Estado y auditoría](docs/01_ESTADO_Y_AUDITORIA.md) | Hechos del baseline, límites y defectos a corregir antes de publicar |
| [Especificación](docs/02_ESPECIFICACION.md) | Requisitos, arquitectura y límites de responsabilidad |
| [Contratos](docs/03_CONTRATOS.md) | Entrada/salida real, configuración, errores y contrato del adaptador por implementar |
| [Plan ejecutable](docs/04_PLAN_IMPLEMENTACION.md) | Tareas ordenadas, archivos lógicos, pruebas y evidencias |
| [Windows y empaquetado](docs/05_WINDOWS_Y_EMPAQUETADO.md) | Preflight, ejecución y distribución del sidecar |
| [Proveedores](docs/06_PROVEEDORES_Y_CATALOGO.md) | Altas, comprobación de gratuidad y uso opcional del catálogo/MCP |
| [Pruebas](docs/07_ACEPTACION_Y_PRUEBAS.md) | Matriz de aceptación y criterios para declarar integración completa |
| [Operación](docs/08_OPERACION_Y_ROLLBACK.md) | Observabilidad, diagnóstico, recuperación y reversión |
| [Memoria](docs/09_MEMORIA_PROCEDURAL.md) | Segundo incremento: recetas verificadas, sin aprendizaje ficticio |
| [Cuotas y cola](docs/10_CUOTAS_Y_COLA.md) | Segundo incremento: cuota por cuenta y tareas diferibles |
| [Agente ejecutor](docs/11_REGLAS_DEL_EJECUTOR.md) | Instrucciones contra rutas, APIs y resultados inventados |
| [Referencias](docs/12_REFERENCIAS.md) | Evidencia y fuentes fijadas a commit |
| `baseline/axx-api-router/` | Código real entregado anteriormente y sus 20 pruebas |
| `templates/` | Formularios de proyecto, validación de proveedor, tareas y estado de entrega |
| `scripts/verify_baseline.ps1` | Verificación offline para Windows PowerShell, sin instalar ni configurar APIs |

## Estados que no deben confundirse

- IMPLEMENTADO_LOCAL: existe código y pasa pruebas locales.
- ESPECIFICADO: comportamiento decidido, pero aún sin implementación.
- INTEGRADO_DEV: Axx usa el adaptador en desarrollo y se ha demostrado el flujo.
- VALIDADO_LIVE: pruebas mínimas reales con cuentas autorizadas y modelos concretos.
- VALIDADO_WINDOWS: binario empaquetado probado en Windows en el equipo de destino.
- RELEASE_READY: todos los criterios obligatorios del incremento están satisfechos.

Actualmente: baseline IMPLEMENTADO_LOCAL; integración, conexiones reales y empaquetado NO EJECUTADOS. Los documentos no convierten una función especificada en una función instalada.

## Qué debe quedar funcionando en el primer incremento

Chat de Axx → backend existente → adaptador → router → proveedor A; si A devuelve un error elegible, proveedor B; respuesta completa → misma conversación. Estado consultable; cancelación por Esc; persistencia de contadores; ausencia de claves en frontend; función desactivable con rollback. No se cambia la forma, los shaders, la barra, la disposición radial ni los atajos existentes.

Memoria procedural, cuotas remotas y cola son incrementos posteriores con contratos propios. No bloquear el primer incremento por construirlos todos a la vez.
