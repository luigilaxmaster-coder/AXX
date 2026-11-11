# Fase 7 · IA y proveedores (Incremento 3)

Capturas: `screenshots/before-ai-*` → `screenshots/after-ai-*`.

## Pantalla principal
1. **Modelo en uso** (`#p7-ai-now`, siempre visible)
   - Modelo y ruta (`#p7-ai-model`, `#p7-ai-route`).
   - Estado (`#p7-ai-state`): «Respuesta comprobada» **solo** si `brain.connected && brain.inferenceVerified === true`; si no, «Conectado · respuesta sin comprobar», «Sin comprobar» o «Sin modelo». Nunca se deduce de la configuración.
   - **Coste** (`#p7-ai-cost`) y **Capacidades** (`#p7-ai-caps`), marcadas como *declaradas*.
   - **Probar conexión** (`#p7-ai-test`).
   - «Modelo activo» (`#ai-model`) y mensaje de conexión (`#ai-status`), movidos aquí.
2. **Cambiar o conectar**: Modelo local · Cuenta ChatGPT · Por API (las pestañas `tab-mode-*` existentes). Solo se muestra el subpanel elegido, que sube al principio del scroll.
3. **Opciones avanzadas** (`#p7-ai-advanced`): `ai-chat-tools`, `keep-history`, `voice-autosend`, ayuda.

## Las seis preguntas
| Pregunta | Dónde |
|---|---|
| Qué modelo usa AXX | título de la tarjeta |
| Si realmente funciona | insignia de estado + resultado de la prueba |
| Cómo cambiarlo | «Modelo activo» y «Cambiar o conectar» |
| Cómo conectar otro proveedor | pestaña «Por API» |
| Qué capacidades tiene | fila Capacidades (+ ficha `model-profile` existente) |
| Si puede generar costes | fila Coste |

## Probar conexión: mecanismos reutilizados
- Conexión API guardada (manual): pulsa el `#provider-probe` de `providers.js` (inferencia real + confirmación de ruta). Si `providers.js` aún no ha cargado las conexiones, se pulsa antes su `#provider-refresh`.
- ChatGPT, local directo o automático: `Axx.companion.connect()`. Para ChatGPT eso ya incluye la inferencia `AXX_CONNECT_OK`; para el resto solo detecta el servidor y el texto lo dice: «El servidor responde. La respuesta del modelo se comprobará con tu primera pregunta».

## Regla de coste (solo lectura de `/axx-api/providers`)
ChatGPT → cuota de la suscripción · automático → rutas gratuitas externas · `kind: ollama` o `cost_evidence: direct_local` → sin coste · `billing_allowed` → puede consumir saldo · `free_confirmed`/`free_tier` → declarada gratuita · `paid` → de pago sin autorización · resto → «Coste sin verificar».

## Controles pertinentes
`#gateway-controls` (FreeLLMAPI) solo se muestra con la plataforma FreeLLMAPI. Dentro de «Por API» la cabecera duplicada de `.provider-overview` (modelo/estado) se oculta por CSS; su botón «Probar respuesta» y su resultado permanecen junto al formulario.

## Cambios en `Axx.html` (vista `view-ai`)
Solo los rótulos de las tres pestañas: «Modelo local», «Cuenta ChatGPT», «Por API · Otro proveedor con clave». Sin cambios de ids, `data-ai-mode` ni handlers.

## Qué NO cambia
Proveedores, autenticación, almacenamiento de claves, modelos, backend, selección automática/manual, modelos por tarea, candidatos, cuotas y `providers.js` (sin editar).

## Contratos conservados
`test-providers.cjs` L55–80 y L138–145 siguen pasando; la suite se detiene en el mismo punto que en el baseline (L148, fallo preexistente de Fase 6).
