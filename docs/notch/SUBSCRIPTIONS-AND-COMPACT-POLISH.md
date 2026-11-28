# Coding agents, música y tamaño — 2026-11-28

Base: `07c6880`, posterior al diseño y despliegue de Antigravity. Incremento sobre ese diseño, sin sustituir sus materiales, Studio, siluetas, sonidos ni identidad 3D. Revisión propia.

## Comportamiento

- Agentes muestra Codex, Claude Code y Antigravity. El nombre del plan y la conexión permanecen visibles; al elegir una fila se despliegan sus cuotas y acciones. Una cuota ausente permanece desconocida.
- Cada proveedor se consulta de forma independiente. Un fallo no impide presentar los demás; los últimos datos conservados se identifican como anteriores. Caché backend: 30 segundos por proveedor; refresco visible: 60 segundos. No hay inferencia para consultar planes.
- Chat directo muestra el plan informado y consume las mismas fuentes de cuotas. No cambia el transporte, las aprobaciones, la conciliación de envíos ni la propiedad de las conversaciones.
- Música conserva una pista local al pausarla, permite reanudarla y dirige el avance al reproductor seleccionado. Windows y Biblioteca AXX son fuentes explícitas del MediaHub existente. Todas las sesiones Windows son accesibles mediante desplazamiento horizontal. El tiempo actual ya no duplica la duración en cada actualización.
- Forma ofrece tamaño de panel 80–110%, además de Discreto/Equilibrado/Amplio; Discreto pasa de 94% a 86%. La barra admite 184–360 px o ancho automático. El contenido y su geometría escalan juntos. El Studio de ajustes conserva su tamaño de trabajo para permitir revertir una reducción. Preferencias, presets y JSON conservan ambos campos nuevos.

## Fuentes y límites

| Cliente | Plan | Cuotas | Verificación |
| --- | --- | --- | --- |
| Codex | `account/read`, `planType` | `account/rateLimits/read` | Respuesta del cliente oficial; no acredita por separado facturación o renovación |
| Claude Code | `claude auth status`, `subscriptionType` | `statusLine.rate_limits` | Plan del cliente; cuotas recibidas de la salida de estado. API key/terceros no se presentan como suscripción Claude |
| Antigravity CLI | `statusLine.plan_tier` | `statusLine.quota` | Estado recibido del cliente, con fecha; no se leen tokens ni bases privadas del IDE |

Se probó localmente el adaptador de lectura de Claude CLI sin ejecutar una pregunta al modelo. Los detalles de la cuenta y su estado real se mantienen como evidencia privada; las capturas publicables de pruebas usan fixtures. Antigravity CLI no apareció en PATH durante la revisión: el puente está implementado, pero su sincronización real requiere conectarlo y recibir un evento del cliente. El monitor no habilita por sí mismo el transporte de chat de Antigravity.

No se convierten porcentajes en horas restantes. Las ventanas de cinco horas y semanales conservan su significado original. No se deducen vencimientos, pagos, precios, crédito alternativo ni tiempo utilizable a partir del nombre del plan. Las cuotas importadas del cliente no autorizan acciones ni facturación.

Fuentes oficiales consultadas:

- [Codex app-server](https://developers.openai.com/codex/app-server/): transporte existente del repositorio.
- [Claude CLI](https://code.claude.com/docs/en/cli-reference), [status line](https://code.claude.com/docs/en/statusline).
- [Antigravity status line](https://antigravity.google/docs/cli/statusline/), [cuotas](https://antigravity.google/docs/cli/commands/usage/), [planes](https://antigravity.google/docs/plans).

## Herramientas y contratos aditivos

Rutas autenticadas del backend existente:

```text
GET /axx-api/connect/subscriptions
GET /axx-api/connect/subscriptions?provider=codex|claude|antigravity
GET /axx-api/connect/subscriptions/setup?provider=claude|antigravity
```

El objeto de proveedor contiene `provider`, `plan`, `connection`, `source`, `verification`, `checked_at`, `stale`, `available`, `windows` y `reason`. Plan y timestamps desconocidos son `null`; `available` indica cuota numérica, independientemente de la autenticación. `verification=client_report` diferencia los eventos de statusLine de una consulta oficial. Cuotas Claude añaden su propia fuente y fecha. El agregado devuelve `providers`.

MCP y herramientas del proveedor usan los mismos contratos: `axx_subscription_status` y `axx_subscription_bridge`, ambas de consulta. El segundo devuelve configuración e instrucciones; no edita ajustes de otras aplicaciones. Los handlers dinámicos conservan los controles de admisión antes y después de la consulta.

## Conectar una salida de estado

En Agentes, elija el proveedor y pulse **Sincronizar → Copiar conexión**. El bloque se añade a la configuración de la CLI oficial indicada. Si ya existe un `statusLine.command`, hay que conservarlo e integrar el puente explícitamente; AXX no lo reemplaza.

El ejecutable empaquetado reconoce `--subscription-statusline claude|antigravity --state-dir <directorio>`. En fuentes se usa el script absoluto `scripts/subscription-statusline.py`, independiente del directorio desde el que se abra la CLI. Recibe JSON por stdin y guarda únicamente plan, cuotas y fechas en el perfil AXX correspondiente, mediante reemplazo atómico. El estado supera a anterior tras cinco minutos sin eventos. No almacena email, tokens, rutas de transcripciones ni mensajes; no ejecuta texto recibido ni comandos shell. Máximo de entrada: 64 KiB y 20 grupos de cuotas.

Un build instalado anterior no adquiere estos endpoints mediante un push de código. Este incremento conserva 0.23.5 y no reemplaza el instalador publicado ni sus hashes. La instalación y aceptación nativa de este incremento son pasos separados.

## Verificación reproducible

```powershell
python -m unittest backend.connect.tests.test_subscriptions backend.connect.tests.test_desktop_sessions backend.connect.tests.test_provider backend.connect.tests.test_http -q
node 1.AXX/scripts/notch/test-notch-core.cjs
node 1.AXX/scripts/notch/test-notch-ui.cjs
node 1.AXX/scripts/notch/test-notch-phase2.cjs
node 1.AXX/scripts/notch/test-notch-obsidian.cjs
node 1.AXX/scripts/test-static-assets.cjs
python scripts/validate_companion.py --output build/subscription-polish/companion-validation.json
```

Las capturas de suscripciones y las respuestas de la suite browser son fixtures explícitos, no evidencia de las cuentas del propietario. La suite comprueba los tres clientes, configuración sin efectos, tamaño reducido, ancho compacto, foco, privacidad y conciliación sin duplicar envíos. Core comprueba una pista local pausada y reanudable; backend valida porcentajes, caducidad, minimización, CLI ausente, caché, desconexión y rutas MCP. Companion conserva su baseline protegido y requiere un recibo exitoso independiente.
