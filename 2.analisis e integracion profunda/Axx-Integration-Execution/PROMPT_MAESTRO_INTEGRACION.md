# Orden de ejecución para Codex / Antigravity

Trabaja en el repositorio real de Axx ya abierto. Integra el router de este paquete en el asistente existente. El objetivo es una integración verificable en Windows, no una maqueta ni una nueva aplicación.

Lee START_HERE y los documentos 01–08 y 11–12. Completa PROJECT_MAP con archivos/rutas y comandos que existan. Si no hay repositorio abierto, solicita únicamente la ruta o acceso al código: no inventes su estructura. Respeta las instrucciones locales aplicables y preserva cambios previos del usuario. No instales dependencias de terceros si el stack existente permite resolver la conexión.

Ejecuta el plan del documento 04 en orden. Implementa primero las correcciones del baseline señaladas en 01, con pruebas de regresión; después el adaptador, estado, cancelación, conexión al chat y empaquetado. Sigue el camino Python si ya existe backend Python; si el host usa Rust o Node, invoca un sidecar privado mediante procesos sin shell. No añadir FastAPI, puertos ni un segundo servidor por costumbre.

Preserva el cuerpo 3D Obsidian de Axx, botones radiales, paneles anclados, barra única, posiciones y tamaños persistidos. Mantén Alt+Mayús+A, doble invocación para volver a base y Esc para detener. Conserva Dictar y su traducción con original/resultado sin autoenvío, Música, Grabar, temporizador y Morph Reach. Esta tarea modifica inferencia y muestra estado discreto; no rediseña esas funciones ni las declara implementadas si no existen en el proyecto.

Nunca incluyas claves en código, frontend, logs, screenshots o informes. Usa el almacén local de secretos existente o variables de entorno de sesión. Modelos y cuotas deben comprobarse en cuentas autorizadas. Configura dos proveedores compatibles reales, sin activar facturación; si faltan credenciales, deja esa prueba BLOCKED_CREDENTIALS y continúa las pruebas offline y el trabajo independiente.

No ejecutes herramientas propuestas por un modelo sin validación del ejecutor local. En solicitudes que puedan invocar herramientas nativas del proveedor, desactiva ese modo hasta disponer de idempotencia comprobada. Cambiar de modelo no permite repetir una acción externa cuyo resultado es desconocido.

No confundas el MCP del catálogo con un router de inferencia. El catálogo es opcional y no debe ser dependencia del arranque ni habilitar destinos automáticamente. No integrar repositorios de memoria, BitNet u otros sistemas ajenos como parte de este incremento.

Al terminar, actualiza DELIVERY_STATUS con: archivos modificados, comandos exactos y salidas, pruebas offline/live/Windows separadas, limitaciones, ruta del artefacto, instrucciones de ejecución y rollback. Adjunta evidencia de una conversación real en Axx, un failover controlado, cancelación y reinicio. No declare RELEASE_READY mientras falte cualquiera de los criterios del documento 07. No pidas confirmaciones rutinarias ya cubiertas por esta orden; pregunta solo por información que bloquee una acción concreta.
