# Autenticación y alcance de la suscripción

Verificación documental: 20 de octubre de 2026. La implementación elegida usa **Codex App Server local con autenticación gestionada por Codex**, no tokens extraídos de otros programas. Axx consulta las interfaces account del runtime y exige contexto ChatGPT; no cambia silenciosamente a API key, créditos o modelos locales.

La [documentación de autenticación Codex](https://developers.openai.com/codex/auth) describe el acceso gestionado y su distinción de las claves API. [App Server](https://developers.openai.com/codex/app-server) proporciona el protocolo utilizado para login, conversaciones y turnos. El runtime examinado fue 0.160.0, cuenta de tipo `chatgpt`, plan informado `promax`; el dato no se interpreta como precio ni como acceso universal.

Se completó una petición real con `gpt-6.1-sol`, herramienta local y respuesta final. [Evidencia](../../evidence/axx-connect/provider-inference-live.json). El acceso es el observado para esa cuenta/modelo/solicitud; no habilita automáticamente voz, imagen, vídeo, visión ni todos los modelos del catálogo.

## SIWC no activado para Axx privado

La ruta [Sign in with ChatGPT](https://developers.openai.com/siwc/quickstart) diferencia registro OAuth y autorización del plan. Su programa [ChatGPT plan usage para open source](https://developers.openai.com/siwc/token-sharing-open-source) no se presume aplicable a una aplicación privada sin licencia/registro elegible acreditado. Axx no se publicó ni cambió de licencia para activar ese programa. La ruta propia OAuth anterior no se usa como sustituto del runtime.

Para una futura aplicación elegible: registrar el cliente apropiado, validar state/PKCE/identidad/scopes, gestionar renovación/revocación y guardar credenciales protegidas. La [configuración SIWC de App Server](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server) es otra vía distinta; no debe mezclarse con la autenticación administrada elegida aquí. Un login no permite leer otras conversaciones de ChatGPT.

## Tres estados independientes

| Capacidad | Prueba requerida |
|---|---|
| Autenticación e inferencia | Account del runtime y turno real completado con el modelo seleccionado. |
| Instalación del plugin | Registro del host, manifiestos aceptados y descubrimiento de herramientas. |
| Acceso a la computadora | Llamada desde el host hasta la instancia real de Axx, efecto y readback devueltos. |

Una de estas pruebas no sustituye a las otras. Sesión expirada/revocada solicita login oficial. Un límite de uso termina con estado legible y no activa facturación alternativa. **Desconectar Axx** cierra únicamente el proceso App Server propio y conserva una preferencia local que impide nuevos turnos o comprobaciones de cuenta hasta Reconectar Axx o un inicio de sesión explícito. Conserva las credenciales y la sesión compartida de Codex: no llama a `account/logout` ni borra recetas o tareas. La ruta de compatibilidad `/connect/logout` también aplica solo esa desconexión local.

## ChatGPT web/nube

Este paquete es stdio local. No se registró localhost como si fuera una PC remota. [Conectar en ChatGPT](https://developers.openai.com/plugins/deploy/connect-chatgpt) admite endpoint accesible o Secure MCP Tunnel y requiere permisos del workspace. [Plugins desktop-only](https://developers.openai.com/plugins/deploy/desktop-only) tienen requisitos de distribución propios; una instalación local Codex no publica ni instala automáticamente el plugin en ChatGPT.

[Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) requiere identidad `tunnel_id`, credencial runtime, cliente local y asociaciones correctas de organización/workspace. Crear/editar exige Tunnels Read+Manage; ejecutar/seleccionar exige Read+Use. El acceso a custom MCP de ChatGPT se autoriza por separado. La credencial del túnel autentica transporte, no inferencia.

No se acreditaron aquí túnel, credencial runtime ni asociación autorizada para el workspace objetivo. Por ello ChatGPT web permanece pendiente. No se abrió puerto público ni se añadió infraestructura pagada. Antes de activarlo se debe revisar la infraestructura concreta, su coste y los permisos; la suscripción no demuestra que esos requisitos estén disponibles.
