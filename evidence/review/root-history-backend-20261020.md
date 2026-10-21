# Axx: revisión histórica y diferencial del backend

Fecha de lectura final: 2026-10-20 20:10:31 UTC. Revisor: `/root/backend_delta_review`.

## Alcance y propiedad

- Revisión de fuentes y recibos existentes, sin ejecutar código, pruebas, producto, GUI, audio, compilación o instalación. Este documento es la única escritura autorizada del revisor.
- Candidato actual: `C:\Users\luigi\Desktop\Axx assistant\build\phased-ux-20261020`.
- Candidato histórico incompleto: `C:\Users\luigi\Desktop\Axx assistant\build\functional-repair-0.21.7`, denominado H en este documento. Su número interno 0.21.9 no significa que se haya instalado o aceptado.
- El chat «Verifica AXX por fases» conserva integración, instalación, GUI, `backend/server.py` y Rust. El chat «Integrar comandos en Axx» trabaja comandos/voz mediante sus módulos y contratos acordados. Este documento no transfiere propiedad ni autoriza copiar el candidato histórico completo.
- No se verificó que el ejecutable instalado corresponda a estas fuentes. Los hallazgos siguientes pertenecen al snapshot leído.

## Hallazgos priorizados

### P1. La cancelación de chat no alcanza la ruta Auth actual

HECHO DE FUENTE: en el candidato actual, `backend/server.py:265` recibe `/axx-api/chat`; la rama Auth llama directamente a `self.chatgpt_adapter.chat` en la línea 279 y retorna por esa rama. `/axx-api/chat/cancel`, líneas 333–337, llama exclusivamente a `self.adapter.cancel(request_id)`. `backend/inference/chatgpt_adapter.py:83` no recibe ID de solicitud ni evento de cancelación; su llamada HTTP en la línea 133 usa un timeout, no el registro del otro adaptador.

CONSECUENCIA INFERIDA: cancelar una petición Auth mediante ese endpoint no señala la operación que está generando. No se hizo una nueva petición real ni una prueba instalada en esta revisión.

CORRECCIÓN ACOTADA A EVALUAR POR EL INTEGRADOR: unificar admisión, identidad y cancelación alrededor de todas las rutas de chat, incluyendo Auth; mantener selección explícita de proveedor/modelo, límites, rechazo de respuesta tardía y estado terminal. No convertir la cancelación en conmutación silenciosa de modelo.

### P1. La cancelación anterior a la admisión se pierde también en el router actual

HECHO DE FUENTE: `backend/inference/adapter.py:102–106` devuelve `False` cuando no existe el ID en `active_requests`, sin conservar marcador. `route`, líneas 214–220, crea y registra después una solicitud con ese mismo ID sin consultar una cancelación anterior.

SECUENCIA DEDUCIDA DEL CÓDIGO: cancel(ID) antes de route(ID) devuelve `False`; route(ID) puede admitir y despachar. No es una reproducción ejecutada ahora.

REFERENCIA HISTÓRICA: H contiene `backend/connections.py` y `backend/tests/test_chat_cancel_admission.py`; el snapshot actual no contiene `backend/connections.py`. H/evidence/chat-cancel-admission-0.21.9/ conserva `connections.patch`, `connections.before.py`, `red-green-observable.json`, `red.log`, `offline-regression.log`, `README.md` y `source-freeze.json`.

La corrección histórica retiene IDs cancelados durante 75 s, limita a 256 IDs activos/cancelados, reserva capacidad para los activos y evita expulsar marcadores vivos. Sus 29 pruebas offline son 13 nuevas y 16 existentes. Se registró RED de dos casos y GREEN sin despacho del proveedor ficticio. Son pruebas de `ConnectionManager`, no del `InferenceAdapter` de este snapshot; no se pueden atribuir automáticamente a la ruta actual ni aplicar el patch a un archivo ausente. Deben adaptarse admisión, contratos y pruebas con el propietario correspondiente.

### P1. Carrera ASR: el snapshot coincide exactamente con la fuente del RED histórico

HECHO VERIFICADO POR HASH: el archivo actual `backend/speech/offline_asr.py` tiene SHA256 `1209041D593EC5D38D4E70E5AAB53E048DD2D1D824827F77E5A6E44C3F75F3F2`, idéntico a la copia anterior y al `sha256_before` conservados en H/evidence/dictation-cancel-race/red.json y source-fix-receipt.json.

HECHO DE FUENTE ACTUAL: `transcribe` adquiere `_busy` en la línea 145. El worker se lanza en la línea 161 y `_active` se publica en la línea 164. `cancel_active`, líneas 119–123, encuentra `_active=None` durante ese intervalo y devuelve 0. La exclusión continúa ocupada hasta terminar A.

EVIDENCIA HISTÓRICA: el harness determinista detuvo la dependencia de spawn en ese intervalo. Sobre la fuente anterior: cancel=0, A devolvió un resultado inerte y B observó BUSY. Sobre la fuente corregida: cancel=1, A terminó con CANCELLED sin resultado y busy se liberó tras retirar A. Son dependencias ficticias con guard contra `subprocess.Popen`, no reconocimiento ni micrófono reales.

PORT POTENCIAL MÁS ACOTADO: solo H/backend/speech/offline_asr.py y su prueba H/backend/tests/test_asr_cancellation.py. La corrección publica registro/evento de ejecución atómicamente con admisión antes de preparar archivos o spawn; conserva el mismo evento durante spawn y serializa terminación/cierre por ejecución. El propietario debe revisar el patch contra el hash vigente, incorporar la prueba y ejecutar validación nueva sobre el candidato que empaquete.

Archivos históricos exactos:

- Fuente corregida H/backend/speech/offline_asr.py: `6DE5BC2CEE4F81B62ABE798581A6AA8478D698F416EB3DC5058C2C71909B0058`.
- Prueba H/backend/tests/test_asr_cancellation.py: `9BFF41D47420ED615B9B3334EDC9E87070FA9A06F5B2A5EC3C2561742D423041`.
- Patch H/evidence/dictation-cancel-race/asr-cancellation-fix.patch: hash documentado en source-fix-receipt.json `49C9BC3DB9183D474E29C1428E5BC4EDD4796799DE3BDD47617DA65CFECF98DE`.
- Evidencia: `red.json`, `green.json`, `scoped-tests.json`, `scoped-tests.log`, `FIX_VALIDADO.md` y `source-fix-receipt.json` en esa misma carpeta.

Los 12 contratos offline históricos pasaron: seis pruebas nuevas y seis contratos existentes. No equivalen a captura física, inserción en una aplicación destino o aceptación del nuevo paquete. Cancelar no promete que una dependencia de spawn bloqueada haya retornado; B puede seguir BUSY durante la retirada de A.

### P1. El host anuncia backend listo incluso después de fallar el arranque y no vigila muerte posterior

HECHO DE FUENTE: `src-tauri/src/lib.rs:1041–1048` guarda el error de `spawn_backend`; la línea 1050 emite `axx-backend-ready` fuera de esa condición. La observación `try_wait` de las líneas 658–666 solo pertenece al bucle de arranque. No existe `backend_supervisor.rs` ni un supervisor posterior en este snapshot. El trabajador periódico de mantenimiento, líneas 1058–1069, atiende preferencias y parada, no muerte del backend.

CONSECUENCIA INFERIDA: puede publicarse un evento de listo con arranque fallido; después de una muerte real del sidecar la conexión guardada puede quedar obsoleta. No se provocó muerte de ningún proceso durante esta revisión.

CORRECCIÓN A EVALUAR: separar ready/error, retirar la conexión al confirmar muerte del hijo propio y, si se integra recuperación, autenticar instancia nueva con token/UUID nuevos. No repetir solicitudes anteriores; una operación interrumpida puede haber producido un efecto desconocido. Un timeout HTTP aislado no demuestra muerte y no debe reiniciar por sí solo un backend vivo.

### P2. Arranque y cierre no comparten un coordinador de retirada

HECHO DE FUENTE: `lib.rs:448–453` y `resident.rs:674` llaman `app.exit(0)` directamente. `spawn_backend` crea el hijo suspendido, lo asigna a Job y lo reanuda antes de guardar `backend_child` en `lib.rs:649`. `terminate_backend`, línea 780, solo ve los recursos ya publicados. La retirada también se invoca desde `WindowEvent::Destroyed` y `RunEvent::Exit`, líneas 1097 y 1107.

RIESGO INFERIDO: un cierre normal concurrente con el intervalo anterior a la publicación puede no observar el hijo pendiente. No se ejecutó esta carrera en el snapshot actual.

REFERENCIA HISTÓRICA INCOMPLETA: H/src-tauri/src/lib.rs, nuevo backend_supervisor.rs y la ruta de salida de resident.rs proponen un coordinador común, guard RAII del hijo pendiente, retirada confirmada antes de salida y recuperación serializada. La primera revisión histórica fue rechazada por una carrera pre-Job; no usar `lib.reviewed-prejob-defect.rs` ni los freezes supersedidos como versión final.

El módulo final histórico backend_supervisor.rs tiene SHA256 `8C0084F75BE46B458218E77C030A1760433BCD30868FEACCA8222CAE5EA21DA7`. H/evidence/backend-recovery-0.21.9/rustc-policy-tests-v3.log registra 14 pruebas puras PASS. `DELIVERY.md` todavía dice 13 y parte de los metadatos puede anteceder al último ajuste: reconciliar hashes y registros antes de reutilizar. Esas pruebas con hijos ficticios no verifican HostState, Job de Windows, Tauri ni procesos instalados.

BLOQUEOS ANTES DE ACEPTAR ESE PORT: compilación y suite Cargo integrada, prueba propia pre-Job/unwind, muerte controlada únicamente del sidecar de prueba, autenticación de nueva instancia, ausencia de duplicados/reenvío, cierre normal y retirada real de procesos. El supervisor histórico no fue aceptado mediante estas pruebas nativas en este chat. No sustituir el Rust visual activo por el archivo antiguo entero.

## Hashes observados y deriva durante la revisión

Hashes SHA256 completos de la última lectura, 20:10:31 UTC; las líneas anteriores corresponden a esta lectura salvo que se indique historia. Los escritores autorizados siguen activos: volver a comparar antes de aplicar cambios.

| Archivo relativo al candidato actual | SHA256 |
|---|---|
| backend/server.py | 94A334EED5A69E0663926FA9F3A05E6F7C026BE4127BF90F7422D08D0C847693 |
| backend/inference/adapter.py | 7219F27B2ED7342C88F3A472E18FAFC0F8347370FC56BEF01D51BFF4570D407F |
| backend/inference/chatgpt_adapter.py | BEDD238D4FBAF6F1A4A4BD2424742B1C624EA40C0E88C69BF490036904DB5BD3 |
| backend/speech/offline_asr.py | 1209041D593EC5D38D4E70E5AAB53E048DD2D1D824827F77E5A6E44C3F75F3F2 |
| src-tauri/src/lib.rs | 65D73E6ABF02B0BBBC57E297532423003706FA84612EEB3EC599477B848A6E76 |
| src-tauri/src/resident.rs | 9DBBBE28C6E0E6003776EC87D2B42E10226151FC57C3C4AD91C7523030B6CDB1 |

Deriva observada en Rust durante lecturas sucesivas; no se atribuyen estos cambios al revisor:

- lib.rs: `3D70B15099EE07A06CEAED64C985F127213F7D2D095A9B3C488235D4867D707A` → `65D73E6ABF02B0BBBC57E297532423003706FA84612EEB3EC599477B848A6E76`.
- resident.rs: `42C1169A38254502A6EDB90A58DE72565E1F9ED4F7EB484473EB29CE895485A5` → `FE474E5F2872DDCC7C8780773DA6023E67BF3126195662A633C7477CB0BC5F9F` → `9DBBBE28C6E0E6003776EC87D2B42E10226151FC57C3C4AD91C7523030B6CDB1`.
- La fuente ASR mantuvo su hash durante todas las lecturas. `backend/connections.py` y `src-tauri/src/backend_supervisor.rs` permanecieron ausentes del candidato actual.

## Estado verificable de esta entrega

Este documento aporta comparación estática actual y evidencia histórica leída. No implementa los puertos ni certifica producto instalado. Los números 12/29/14 describen tres suites históricas con ámbitos diferentes; no deben sumarse para afirmar cobertura de la aplicación actual. La integración y aceptación serial pertenecen a los propietarios actuales.
