# Integración frontend y transporte nativo — 2026-10-19

La biblioteca usa la interfaz existente de Axx. No se cambian shaders, geometría, materiales, cámara, preferencias de identidad ni controladores de micrófono. Las pruebas de navegador usan respuestas IPC controladas y no certifican micrófono, altavoz o acciones físicas.

## Archivos

- `1.AXX/scripts/command-library.js`: catálogo con búsqueda y disponibilidad, parámetros tipados, resolver de texto/voz, preparación correlacionada, aprobación explícita, cancelación por ID preasignado, consulta de resultados y protección contra respuestas tardías. Reutiliza el panel de archivos y la entrada real `Axx.companion.send` sin sustituir el chat.
- `1.AXX/Axx.html`: cuatro modificaciones de este trabajo: validación URI de consultas codificadas; nombre/descripción del acceso existente `files`; usar `action_operation_id` para guardar una receta comprobada; cargar el módulo al final.
- `1.AXX/scripts/test-command-library.cjs`: 19 verificaciones finales de contratos UI/IPC aislados.
- `1.AXX/scripts/test-desktop-frontend.cjs`: sirve el nuevo módulo, usa fixtures de la política de comandos y añade apertura de la biblioteca en la UI original. Corrige el sondeo del caso que desactiva RAF: `polling: 50` observa con reloj independiente en lugar de esperar precisamente el RAF desactivado.
- `src-tauri/src/lib.rs`: este agente añadió `/commands/execute` al contador activo, cancelación global incondicional de comandos preparados, timeout rápido de cancelación y regresión HTTP403.

## Cambios simultáneos preservados

La comparación con la copia `before` muestra además un cambio en la primera etiqueta HTML (`class="axx-resident"` y script inicial) que este agente no realizó. Tampoco cambió versiones. `Cargo.toml` pasó a 0.20.3 y apareció un tratamiento de HTTP >=400 en `request_backend` durante la tarea; se preservaron. El nuevo test HTTP403 pasó en su primera ejecución válida, por lo que no se afirma haber observado su fase roja.

## Verificación

- `node 1.AXX/scripts/test-command-library.cjs`: exit 0, 19 comprobaciones, ninguna excepción no capturada. Registro final `frontend-library-reviewed.log`; ejecuciones anteriores quedan en `frontend-library-final.log` y `frontend-command-library.log`.
- `node 1.AXX/scripts/test-desktop-frontend.cjs`: exit 0, 18 comprobaciones, ninguna excepción no capturada; conserva 24 formas y nueve paletas. Registro final `frontend-production-final.log`; la ejecución anterior de 17 queda en `frontend-production-contract.log`.
- `cargo test --manifest-path src-tauri/Cargo.toml tests::private_transport_rejects_http_errors_instead_of_reporting_json_as_success -- --exact --nocapture`: exit 0, 1 prueba.
- `cargo test --manifest-path src-tauri/Cargo.toml -- --skip tests::explicitly_escaped_user_target_survives_owned_job_cleanup`: exit 0, 9 pruebas aprobadas, 1 helper ignorado, 1 prueba excluida.

Antes de corregir el sondeo, la suite frontend falló intermitentemente en su observación de arranque con RAF desactivado, incluido el baseline anterior a los cambios. Una ejecución completa también pasó antes de la corrección; no se atribuye la falla al catálogo.

La revisión independiente encontró respuestas tardías que podían reabrir una aprobación antigua o sobrescribir el resultado nuevo, y un error de integración en la reutilización de recetas sin parámetros. Se corrigieron mediante revisión de observación, descarte de errores de generaciones antiguas, correlación de cancelación y filtrado de entradas por el esquema real. Las regresiones de recuperación, esquema y cancelación pendiente fallaron antes del arreglo (`frontend-recovery-review-red.log`, `frontend-recipe-review-red.log`, `frontend-cancel-recovery-review-red.log`) y pasan en la suite final. La recuperación queda bloqueada mientras la cancelación de esa generación está pendiente; la cancelación repetida es idempotente y el listener de escritorio tiene un solo dueño. El backend expone ahora el esquema seguro en GET `/recipes`. También se verifican calculadora y temporizador originales con el resolver denegado: las acciones locales reconocidas usan su parser local cerrado y no dependen del catálogo ni se envían a inferencia.

## Limitación de prueba Windows

La ejecución inicial de `cargo test --manifest-path src-tauri/Cargo.toml` terminó con 9 aprobadas, 1 ignorada y una falla en la limpieza de `explicitly_escaped_user_target_survives_owned_job_cleanup`: el fixture no pudo completar `taskkill /F /T /PID` de su proceso dedicado. Esa prueba crea `cmd.exe /D /C "ping -n 60 127.0.0.1 > NUL"`. El intento posterior de observar exclusivamente ese comando mediante `Get-CimInstance Win32_Process` fue denegado por el sistema (`Accesso negato`). No se repitió el fixture ni se terminaron procesos sin su PID. El estado final de aquel proceso de hasta 60 segundos no se pudo confirmar; no es una certificación de limpieza de procesos Windows.

## Uso y límites

Desde el chat, `/comandos texto` abre la búsqueda. `estado del sistema` o `estado de axx` utilizan los mismos IDs que el texto dictado; `/comando ID {JSON}` prepara parámetros explícitos. La voz existente coloca texto y conserva su permiso de sesión. La creación de archivos necesita el botón de aprobación que muestra parámetros e ID. Dictar «sí» no aprueba. Los botones antiguos de acciones y reutilización de recetas pasan por preparación. Blender permanece bloqueado. Un error de autorización no se transforma en una solicitud de inferencia ni en una confirmación de éxito.

Ante una respuesta de ejecución perdida, se conserva el ID y se consulta el resultado antes de reintentar. Escape invalida la aprobación local y pide cancelación del comando. Una cancelación solicitada no se presenta como prueba de que no hubo efecto.
