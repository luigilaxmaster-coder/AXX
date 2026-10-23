# FreeLLMAPI en Axx

Axx integra **FreeLLMAPI 0.16.9**, revisión
`26484157fd15f5fb66f54d3a86f568997ea304de`. La memoria, los comandos y sus
autorizaciones permanecen en Axx. El gateway se ocupa únicamente de inferencia.

## Instalación y conexión

Para una instancia existente, elige FreeLLMAPI en Conexiones e indica su URL
real terminada en `/v1` y su clave unificada. El puerto debe ser el de esa
instancia; Axx no supone que un servidor encontrado en un puerto sea suyo.
Axx conserva esa clave con el almacén DPAPI existente y no inicia ni termina
procesos externos.

El inicio gratuito prepara una instalación administrada automáticamente si falta.
No exige instalar herramientas de desarrollo ni introducir una clave personal.
El mismo instalador también puede ejecutarse para diagnóstico:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-freellmapi.ps1
```

El script usa el código oficial de una revisión fijada, `npm ci` y `npm run build`.
Reutiliza Node 20.18–24.x compatible, incluso si está en Program Files fuera del
PATH. Si falta, descarga el ZIP oficial Node 24.14.0 para Windows x64 y verifica
SHA256 y `SHASUMS256.txt`; no requiere Git para una instalación nueva. Descarga
el archivo de GitHub de la revisión fijada y comprueba su hash antes de extraerlo.
Se instala en `%LOCALAPPDATA%\Axx\gateways\freellmapi-26484157` y registra su
ubicación en `freellmapi-install.json`. Registra hashes de los archivos fuente
y conserva cualquier instalación modificada. Los hashes fijados son:

- Node ZIP: `313fa40c0d7b18575821de8cb17483031fe07d95de5994f6f435f3b345f85c66`.
- Código fuente ZIP: `0511c5372e3be30bf7013dd34285e0dae82d0a4fc0b00fe7eede203a1f8e9883`.

La preparación corre oculta, tiene un plazo de diez minutos y puede cancelarse
al cerrar Axx, terminando también sus procesos hijos. Necesita conectividad a
los sitios oficiales y al registro npm.

Pulsa el botón para iniciar el gateway administrado en Conexiones. Axx reserva
un puerto local disponible, lo guarda y lo muestra. Los siguientes arranques usan
ese puerto; si otro proceso lo ocupa, Axx informa del conflicto. La base vive en
`freellmapi-runtime/freeapi.db` dentro del directorio de estado de Axx; sus secretos de cifrado y acceso
administrativo se guardan en `managed-secrets.bin`, protegido por DPAPI.
Conserva ambos al actualizar. Un bloqueo exclusivo impide que dos instancias
administren la misma base. El servicio inicia oculto y pertenece al proceso
residente de Axx mediante el administrador de procesos existente. Cerrar Axx
lo termina; al reiniciar Axx se recupera si seguía habilitado. Detener
desactiva ese inicio automático. Un fallo de conexión no impide usar comandos
locales de Axx.

La instalación inicial no importa cuentas personales. Para una cuenta opcional, selecciona una conexión
guardada y gratuita de Axx y pulsa **Añadir esta conexión gratuita al gateway**.
Solo se transmite al gateway elegido la clave de esa conexión, desde el backend.
Debe usar protocolo OpenAI, tener contexto configurado, gratuidad explícita y
facturación desactivada. El alta usa `/api/keys/custom` con el modelo y capacidades
guardadas y confirma el contexto mediante `/api/models/:id`. No ejecuta inferencia.
No importa todas las conexiones ni copia claves al frontend.

## Inicio anónimo predeterminado

`bootstrap_keyless` consulta los catálogos públicos actuales de Kilo Gateway,
OVHcloud AI Endpoints y AI Horde. Usa únicamente sus endpoints fijados: nunca
lee claves personales para estas consultas o pruebas. Cada candidato debe
devolver la respuesta esperada a un mensaje sintético público y publicar un
contexto válido. La disponibilidad no se deduce de las semillas del gateway.

Kilo requiere `isFree:true`, precios de entrada/salida cero y un ID `:free` del
catálogo actual; no se emplea el alias que decide automáticamente otro modelo.
OVH ofrece una vía anónima limitada por IP, separada de los precios autenticados
que publica su catálogo. AI Horde usa el identificador anónimo público documentado
`0000000000`; si no publica contexto suficiente, su candidato queda pendiente.

Solo entonces se habilita la cuenta anónima del proveedor y se registra el
modelo comprobado. Si el gateway ya tiene una clave personal de ese proveedor,
se conserva y esa ruta no se prepara automáticamente. Antes de cada invocación,
la verificación de `gateway_keyless` confirma que todas las cuentas habilitadas
del proveedor son anónimas; añadir una cuenta personal invalida esa ruta.

Las conexiones se guardan primero como `candidate_only:true`. La prueba de
conectividad no las activa: el evaluador de tareas debe superar su prueba
representativa antes de aplicarlas. Todas usan `allow_sensitive:false`.
Son servicios públicos: Kilo indica que puede utilizar los mensajes gratuitos
para entrenamiento. Axx conserva solo metadatos, tiempos y hashes de las pruebas.
Reutiliza esa evidencia durante seis horas, revalidando los perfiles; un resultado
sin rutas se conserva cinco minutos para evitar solicitudes repetidas.

En la comprobación real del 23 de octubre de 2026, Kilo devolvió respuestas válidas
sin cuenta para `liquid/lfm-2.5-2.6b:free` y `cohere/north-mini-code:free`, y OVH para
`Mistral-Small-3.2-24B-Instruct-2506`. AI Horde respondió una vez con salida truncada;
su catálogo carecía de contexto y no se activó. Estos resultados son evidencia
fechada, no garantías de disponibilidad futura ni de calidad para cualquier tarea.

## Perfiles de tareas y modo gratuito

La API de inferencia usa la clave unificada. Administrar perfiles usa una sesión
del panel distinta; el gateway administrado obtiene esa sesión en el backend.
Para una instancia externa hace falta una sesión administrativa autorizada.
Axx puede guardarla con DPAPI y vuelve a comprobar su validez. Cuando expira,
se requiere renovar la sesión; no se restablece la contraseña externa.

Se crean perfiles reales mediante `POST /api/profiles` con `empty:true`, se
asignan miembros con `PUT /api/profiles/:id/reorder` y se leen de nuevo. Los
perfiles son `axx_parameters`, `axx_chat`, `axx_plan`, `axx_vision`, `axx_code`,
`axx_writing` y `axx_repair`; traducción comparte `axx_writing`. Los IDs de
inferencia tienen el prefijo real `auto:`, por ejemplo `auto:axx_plan`.
Los perfiles existentes que Axx no creó se conservan.

Marca los IDs de modelos cuyas cuentas confirmas gratuitas. Esa confirmación
debe referirse a las cuentas y rutas reales, no al nombre del gateway. Axx crea
candidatos por velocidad para parámetros/conversación y por inteligencia para
planificación/código/redacción/reparación, usando los rangos del catálogo. Visión
exige `supportsVision`. La configuración de perfiles no demuestra calidad del
resultado; la selección posterior incorpora las métricas propias de Axx.

Para evaluar un candidato de un perfil con varios modelos, Axx crea un perfil
aislado `auto:axx_e_<código de tarea>_<hash>`, dentro del máximo oficial de veinte
caracteres. Incluye exactamente un grupo canónico disponible, cuyos miembros ya
deben estar en la lista gratuita confirmada. No cambia los perfiles habituales.
Al repetir la evaluación reutiliza ese perfil únicamente si sus miembros siguen
coincidiendo; si alguien lo cambió, rechaza la evaluación sin sobrescribirlo.
La procedencia de conexiones importadas se conserva mediante el registro local
de importación, sin deducir el proveedor a partir de un nombre mostrado.

Antes de guardar o usar automáticamente un perfil, Axx verifica en vivo:

- La versión 0.16.9 cuyo contrato se ha contrastado y probado.
- Su existencia y sus miembros habilitados; todos deben estar en la lista de
  gratuidad confirmada y no pueden añadirse modelos nuevos automáticamente.
- Capacidades comunes y el **menor** contexto de sus miembros.
- Al menos una ruta concreta lista, y un límite de intentos del gateway válido.

`GET /v1/models?execution_status=ready` también incluye `auto`, `fusion`, perfiles
y otros alias sintéticos. Axx los presenta aparte: no los cuenta como modelos
ejecutables. Con **Unify** activo, el catálogo puede acreditar un grupo sin
identificar qué cuenta está lista. En esta revisión Unify está siempre activo:
el antiguo ajuste para desactivarlo ya no cambia ese comportamiento. Axx consulta
`/api/fallback?profile=<id>` para conocer los miembros reales de cada grupo y
solo admite su disponibilidad si el grupo completo está dentro del perfil
gratuito confirmado. Las conexiones importadas reciben un nombre específico de
Axx para evitar agruparlas accidentalmente con otras cuentas del catálogo.
El selector muestra grupos disponibles, mediante `group_ready`, `canonical_id`
y `group_member_ids`; las semillas habilitadas sin cuentas disponibles no se
ofrecen como rutas listas. Este estado describe el grupo, no acredita por sí solo
la disponibilidad de cada miembro ni su gratuidad.
Una versión distinta conserva la conexión manual, pero requiere validar su
contrato antes de habilitar perfiles automáticos. Las peticiones con imágenes
también requieren configurar en Axx una reserva de tokens por imagen conocida;
el indicador de visión del catálogo no proporciona esa cifra.

El gateway administrado configura inicialmente tres fallos upstream consecutivos
y veinte segundos para la cadena. El inicio anónimo de una base sin cuentas
personales fija **un intento por petición** mediante la API oficial de guardrails;
así Axx puede pasar a otro candidato dentro de su presupuesto total de tres.
Se conservan los demás ajustes. La verificación lee el límite efectivo en
`GET /api/settings/guardrails`, ya que una configuración del panel puede
prevalecer sobre el entorno. Axx descuenta ese presupuesto completo y conserva
su propio plazo de transporte; no multiplica los reintentos del gateway.
La revisión integrada aborta el trabajo upstream al desconectarse el cliente.
Los sondeos proactivos de inferencia permanecen desactivados en el proceso
administrado. La recuperación de cuotas vuelve a reflejarse en el catálogo.

## Contratos y diagnóstico

`backend/inference/freellmapi.py` ofrece `FreeLLMAPIService(state_dir,config_path)`:
`status`, `discover`, `candidate_catalog`, `profiles`, `credentials`, `import_provider`, `start`,
`reconnect`, `stop` y `close`. `verify_provider(provider,timeout)` verifica un
perfil antes de invocarlo. Las rutas de Axx están bajo `/axx-api/freellmapi/` y
usan la autenticación nativa existente.
`bootstrap_keyless` prepara las rutas anónimas; `cancel_bootstrap` interrumpe su
preparación e instalación. `evaluation_provider` aísla un grupo para evaluarlo.

- `connected:true` acredita conexión y catálogo, no una inferencia exitosa.
- `ready_count:0` con perfiles visibles suele significar que faltan cuentas o
  capacidad. Los perfiles vacíos se muestran sin marcarse verificados.
- Un 401/403 administrativo suele indicar una sesión expirada o una clave
  unificada usada donde se requiere sesión de panel.
- Un puerto ocupado no se toma como prueba de que el proceso pertenece a Axx.
- No borres ni reemplaces `managed-secrets.bin` para resolver un error de
  descifrado. La base existente necesita su clave original.

Las pruebas automatizadas cubren catálogos sintéticos, cambios de endpoint,
secretos, perfiles, importación explícita y rechazo de rutas sin evidencia.
Cuando existe la instalación Windows, una prueba adicional inicia un gateway
real con base aislada, importa un servidor de prueba local, ejecuta una respuesta
simulada a través del perfil y comprueba exclusión entre instancias, cierre,
reinicio y puerto persistido. Los tests de inicio anónimo comprueban también
cuentas personales excluidas, evidencia reutilizada, presupuestos y cancelación.
Las pruebas públicas reales usan mensajes sintéticos, sin cuentas pagadas ni
claves personales. Una instalación adicional limpia se comprobó con Node
descargado, código ZIP, compilación, repetición idempotente y arranque real.

Contrato contrastado con las fuentes oficiales fijadas:
[instalación](https://github.com/tashfeenahmed/freellmapi/blob/26484157fd15f5fb66f54d3a86f568997ea304de/docs/en/install/01-install.md),
[REST](https://github.com/tashfeenahmed/freellmapi/blob/26484157fd15f5fb66f54d3a86f568997ea304de/docs/en/api/01-rest-api.md),
[perfiles](https://github.com/tashfeenahmed/freellmapi/blob/26484157fd15f5fb66f54d3a86f568997ea304de/server/src/routes/profiles.ts),
[límites](https://github.com/tashfeenahmed/freellmapi/blob/26484157fd15f5fb66f54d3a86f568997ea304de/server/src/lib/guardrails.ts).
Acceso público contrastado con [Kilo](https://kilo.ai/docs/gateway/authentication),
[AI Horde](https://oai.aihorde.net/) y los
[adaptadores oficiales de FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi/blob/26484157fd15f5fb66f54d3a86f568997ea304de/server/src/providers/index.ts).
