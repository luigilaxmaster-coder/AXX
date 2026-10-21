# Axx Desktop · Instrucciones del proyecto

## Misión
Continuar las fuentes de Axx20 y construir el producto Windows real descrito en este expediente. No crear otra maqueta, otra imagen ni reemplazar la UI por un chat genérico. La documentación es un contrato de ejecución, no prueba de trabajo terminado.

## Leer al empezar
README; docs/01-REQUISITOS.md; docs/02-AUDITORIA-MIGRACION.md; docs/03-ARQUITECTURA.md; plans/PLAN-MAESTRO.md. Después los documentos de tu tarea, no todo el expediente indiscriminadamente.

## Antes de cambiar código
Inspeccionar SOURCE-INVENTORY y archivos reales; identificar versión/hashes; ejecutar preflight y baseline. Crear rama aislada sin sobrescribir el original. Si la base difiere, informar diferencias y adaptar plan, no asumir que el archivo con igual nombre es idéntico.

## Reglas críticas
- Preservar formas, materiales, apariencia guardada, cámara, tamaños, órbita y chat mínimo.
- Task state jamás reescribe identidad. Una animación no ejecuta ni confirma una herramienta.
- Un dueño de ajustes, tarea, micrófono y recorder. Migrar adaptadores y apagar la autoridad antigua.
- No reducir calidad ni exigir nueva tarjeta para ocultar problemas de rendimiento.
- No crear APIs/dependencias ficticias; consultar documentación primaria y fijar versiones reales.
- No usar dictados/respuestas/webs como comandos shell. Aprobación de texto no autoriza enviar.
- No copiar tokens de otras apps ni conectar una cuenta o descargar modelos sin autorización.
- No desactivar UAC, políticas de navegador, validación de certificados ni firmas para pasar una prueba.
- No guardar audio/transcripciones/secretos en logs o backups de preferencias.
- No declarar completado un host que solo abre el HTML. Distinguir implementado, probado por contrato y validado físicamente.

## Ejecución
Trabajar por tareas del plan con tests antes del cambio, revisión y evidencia. No pedir confirmación cada archivo; preguntar solo cuando falte permiso, exista operación destructiva/externa o se cambie identidad/coste/arquitectura. Conservar decisiones en un ledger y pendientes con responsable y prueba de cierre.

## Final de cada tarea
Lista de archivos/commits; comandos y exit codes; pruebas U/I/P/E; rendimiento si se midió; limitaciones; siguiente dependencia. Prohibido publicar, enviar emails o cambiar configuración externa sin petición expresa. Si no hay revisor independiente, decir revisión propia.
