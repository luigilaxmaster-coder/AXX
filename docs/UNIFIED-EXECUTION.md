# Arquitectura unificada: implementación y límites

Esta entrega amplía el circuito existente de Axx. Un skill describe una
integración; no demuestra que exista un adaptador ejecutable.

## Circuito

`Chat / voz / Comandos / Axx Connect → CommandService → ActionExecutor → adaptador → verificador → SQLite`.

El servicio conserva autorización, parámetros e identidad de operación. El
ejecutor serializa escrituras en la instancia del backend y coordina las lecturas
permitidas. Persiste `running` antes del despacho; estado y recibo final se
escriben en una transacción. Una cancelación anterior al despacho impide el efecto.

Una interrupción deja `unknown`. Reutilizar el ID no repite la acción; otro ID con
los mismos parámetros de una mutación desconocida también se rechaza. Las
escrituras UIA conservan su reconciliación por lectura. Otras operaciones
desconocidas requieren revisión: no hay reconciliación automática universal.
Cancelar no revierte efectos enviados.

## Modos

El catálogo expone `delivery.default_mode` y `supported_modes`. Comandos permite
elegir los modos admitidos. `POST /axx-api/commands/prepare` acepta `delivery_mode`;
el modo queda vinculado al ID y se verifica también en el ejecutor.

| Modo | Soporte actual |
|---|---|
| `background` | Archivos autorizados, hashes, telemetría, inventarios y lecturas UIA; esas implementaciones no insertan entrada global |
| `foreground` | Foco, escritura, pulsación, lanzamiento y shell revisado; pueden afectar el escritorio activo |
| `isolated` | No disponible: falta un contexto VM con aislamiento validado |

No hay fallback entre modos. Shell no se anuncia como background: el script
aprobado podría abrir ventanas o insertar entrada. La lectura UIA no acredita
escritura universal en segundo plano.

## Observación y selección

UIA devuelve ID de observación, sesión del backend, HWND/PID, inicio del proceso
en Windows FILETIME, tiempos y coordenadas físicas del escritorio virtual. Declara
que no contiene captura. El token de control incorpora el inicio del proceso;
reutilizar un PID no conserva la identidad anterior. El worker vuelve a resolver
el control y sus condiciones antes de actuar.

`axx.desktop.window.find` recibe `window_id` hexadecimal, `pid` y `name` exacto.
Devuelve `selected`, `ambiguous` o `not_found`. Solo selecciona un botón único,
habilitado, visible y con InvokePattern en una observación completa. Devuelve
candidato y observación; no pulsa. La ejecución conserva comando y aprobación.

Esta selección es semántica. No implementa Agent S, OCR, SoM ni un VLM. Tampoco
acredita calibración visual G1/G2, TTL universal o ausencia de todas las carreras.

## Resultados

Los recibos añaden `dispatch_status` y `effect_status`. InvokePattern genérico
acredita entrega, pero deja `state=unknown`, `effect_status=unknown` y
`postconditions_passed=false`; no se promueve a receta verificada. Adaptadores
específicos pueden verificar su efecto, como Spotify al observar Pausar.

Shell distingue `exited`, `cancelled`, `timeout`, `output_limit` y truncamiento.
`verification=process_exit` solo verifica el proceso; su evidencia declara
`application_effect_verified=false`. La consulta de procesos distingue activo,
no activo y acceso denegado; observa ruta e inicio usando el mismo handle.

## Estado y pendientes

Escribe **estado de integraciones** o ejecuta `axx.architecture.status` en
Comandos. No prueba credenciales ni realiza llamadas a modelos.

| Diseño | Estado en el proyecto |
|---|---|
| Coordinación y diario | `CommandService`, `ActionExecutor` y planes de `action_learning` existentes, ampliados |
| Control semántico | UIA nativa y selección con abstención; Cua upstream pendiente |
| Grounding visual | Pendiente: modelo, pesos, captura, transformaciones y evaluación |
| Recuperación | Registro previo, cancelación y no repetición; reconciliación por adaptador |
| VM | Pendiente: imagen, acelerador, límites efectivos y canal de archivos |
| REA | Pendiente: proveedor compatible, aplicación de ensayo y adaptador probado |
| Router y memoria | Se conservan `backend/inference` y `backend/action_learning.py`; no se acreditan nuevas inferencias |
| Telegram | Pendiente; Axx Connect y control móvil no equivalen a Telegram |

Referencias de componentes candidatos: [Cua](https://github.com/trycua/cua),
[REA](https://github.com/morluto/rea),
[Invisible Dots](https://github.com/feder-cr/invisible_dots).
No son evidencia de instalación ni garantías de navegación indetectable.

## Verificación y reversión

```powershell
python -m unittest backend.tests.test_unified_execution backend.tests.test_commands_http -q
python scripts/verify-unified-windows.py
```

La prueba nativa compila una aplicación WPF desechable, consulta UIA real,
comprueba identidad, selección y abstención, crea un archivo verificado y muestrea
foco, puntero y portapapeles. Guarda recibos locales en `build/unified-native/`.
No sustituye trabajo humano durante 30 minutos ni 1.000 operaciones. La aceptación
del binario instalado se comprueba por separado.

Migración aditiva: columna nullable `delivery_mode` en el diario; se conservan
historial, ajustes y credenciales. Un binario anterior ignora esa columna. Revisar
operaciones desconocidas también después de revertir el binario.
