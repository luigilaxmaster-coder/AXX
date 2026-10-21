# Axx Connect: decisión de autenticación

Consulta: 2026-10-20. Alcance: instalación personal Windows; no servicio hospedado.

## Hechos comprobados

- Codex CLI npm: `0.160.0`. Codex incluido en el cliente de escritorio: `0.163.0-alpha.10.2`. La integración fija el primero y rechaza versiones diferentes.
- `initialize` y `account/read` contra el proceso oficial local devolvieron una sesión de tipo `chatgpt`, con contexto de plan. No se leyó `auth.json`, cookies ni credenciales del navegador.
- `provider-inference-live.json` registra un turno autenticado con `gpt-6.1-sol`, eventos de texto, llamada a `axx_execute_action`, resultado real del `CommandService`/`ActionExecutor` de telemetría y respuesta posterior del modelo. El turno terminó `completed`. Una prueba desde la interfaz nativa y otra desde el host del plugin requieren evidencias separadas.
- Los esquemas en `schema/codex-0.160.0` se generaron ejecutando `codex app-server generate-json-schema --experimental --out ...` con esa versión instalada.

## Mecanismo seleccionado

Autenticación administrada por el runtime oficial de Codex, transporte local stdio y protocolo App Server. El backend usa `account/read`; inicio de sesión explícito mediante `account/login/start` de tipo `chatgpt`; cancelación de ese inicio mediante `account/login/cancel`. Desconectar Axx cierra únicamente su proceso App Server propio y persiste una exclusión local en SQLite; no envía `account/logout`. Codex conserva y renueva sus propias credenciales. Axx no recibe tokens OAuth.

Las credenciales de Codex pueden ser compartidas con otros clientes locales. Por ello la desconexión de Axx no las revoca ni modifica. El alias de compatibilidad logout también es local. Mientras la conexión esté desactivada, status no inicia procesos ni consulta autenticación; nuevas inferencias fallan DISCONNECTED hasta Reconectar Axx o iniciar sesión explícitamente. El proveedor exige una sesión ChatGPT y elimina las variables conocidas de credenciales API del entorno hijo. No cambia a API de pago, no consume créditos adicionales mediante RPC ni solicita cambios de plan.

Antes del turno consulta `account/rateLimits/read`: requiere `ordinaryUsageAllowed:true`. Un permiso ausente produce `COST_UNKNOWN`; una denegación o límite produce `LIMIT_REACHED`. La identidad de la cuenta y su época se vinculan a cada ejecución y se revalidan tras consultar cuota, antes de turn/start y antes de cada despacho. Una respuesta tardía de otra cuenta conserva sus evidencias pero termina `ACCOUNT_CHANGED`, sin validar la cuenta actual. El runtime debe devolver modelo y proveedor exactos; si falta uno se rechaza con MODEL_UNVERIFIED.

La documentación oficial distingue identidad, acceso al plan y acceso al equipo. Una sesión autenticada muestra `authenticated`; solo un turno completado habilita `inference_verified`. El catálogo de modelos no demuestra acceso a ellos.

## SIWC y elegibilidad

La guía vigente ofrece uso del plan para socios open source y determinados clientes privados; la modalidad comercial requiere acceso al programa. Esta copia de Axx es privada y no hay prueba de registro/elegibilidad SIWC propia. No se cambió la licencia ni se publicó código. No se usa registro dinámico de OSS como supuesto permiso para esta aplicación privada.

La configuración SIWC de App Server documentada utiliza un token autorizado para Responses y obliga al cliente a manejar su renovación. Es una ruta distinta de la autenticación administrada elegida aquí. Si se migra posteriormente, requiere validar la elegibilidad y el flujo oficial completo antes de activarlo.

## Dependencias experimentales y límites

App Server y sus herramientas dinámicas son experimentales. La integración opta explícitamente por `experimentalApi`, genera esquemas de su versión y separa MCP de App Server. No usa el comando retirado `codex mcp-server`.

El flujo SIWC/Responses también presenta limitaciones de vista previa: exige streaming con `store:false`, tiene herramientas y modalidades no admitidas y no otorga las conversaciones de ChatGPT. No debe usarse para prometer voz, vídeo, visión ni conectores hospedados que no se hayan probado.

Los permisos de inferencia no crean una ruta desde ChatGPT web/nube al equipo local; esa conexión depende del host local o de infraestructura autorizada independiente.

## Evidencia y límites de aceptación

- `provider-inference-live.json`: primer turno real con la telemetría del ejecutor existente.
- `http-provider-live.json`: proceso HTTP autenticado, alias preciso de telemetría, respuesta de vuelta, duplicado sin otro turno y traducción con texto imperativo sin llamadas a herramientas.
- `provider-final-live.json`: tres turnos reales; traducción de una instrucción adversa sin herramientas, interrupción real `turn/interrupt` y continuación del mismo hilo persistido. Sus hashes preceden los últimos controles de cuenta y coste.
- `provider-latest-live.json`: traducción real `Hello.` → `Hola.`, permiso de uso incluido confirmado, cuenta y época coherentes, modelo exacto y streaming hasta `completed`. Precede a la revisión C de desconexión local, plazo total de 70 segundos y controles adicionales de identidad/modelo. No certifica esas fuentes nuevas.
- `provider-revision-c-tests.txt` y `provider-revision-c-result.json`: 47 pruebas offline aprobadas y una prueba real opt-in omitida; ninguna inferencia ni modificación de la cuenta real en esta revisión.
- `provider-unit-tests.txt` y `provider-unit-test-result.json`: resultados de límites, fallos y concurrencia con dobles controlados, separados de las pruebas reales.
- `provider-isolation-diagnostic.json`: el inventario MCP del runtime agotó su límite de 20 segundos. No se afirma haber verificado un inventario vacío. Se aplican controles explícitos por configuración, entorno sin secretos de Axx, sandbox de lectura, herramientas dinámicas del registro y rechazo de callbacks fuera del ámbito.

## Fuentes oficiales consultadas

- [SIWC quickstart y elegibilidad](https://developers.openai.com/siwc/quickstart)
- [SIWC: uso del plan en clientes open source](https://developers.openai.com/siwc/token-sharing-open-source)
- [SIWC: configuración de Codex App Server](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)
- [SIWC: limitaciones de vista previa](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
- [Codex: autenticación y renovación administrada](https://developers.openai.com/codex/auth)
- [Codex App Server: autenticación, eventos, herramientas y aprobaciones](https://developers.openai.com/codex/app-server)
- [Codex SDK: cuándo usar App Server y retirada de mcp-server](https://developers.openai.com/codex/codex-sdk)
- [Referencia de configuración: MCP, plugins y herramientas](https://learn.chatgpt.com/docs/config-file/config-reference)
