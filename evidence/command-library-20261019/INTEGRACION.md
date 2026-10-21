# Integración de biblioteca en Axx Desktop

Trabajo local del 19 de octubre de 2026. Este informe distingue importación,
adaptadores implementados y comprobación física. No se publicó nada en Drive,
no se cambiaron cuentas/permisos, no se instalaron paquetes y no se activó escucha.

## Fuentes y estado anterior

La raíz del proyecto no contiene `.git`; no fue posible crear rama ni comparar
cambios mediante Git. `before/` y `before-manifest.json` conservan 39 archivos
de fuente con sus SHA256; `before-binaries/` conserva los binarios anteriores.
La aplicación existente es Tauri 2, con frontend `1.AXX/Axx.html`, servicio
Python privado autenticado en loopback, ejecutor y memoria SQLite.

Se observaron cambios simultáneos de procedencia externa durante la tarea:
versiones `0.20.3` en package/Cargo/config, clase inicial `axx-resident` en HTML
y rechazo HTTP >=400 en Rust. Se preservaron; no se atribuyen a esta integración.
La primera compilación intermedia fue rechazada correctamente por el control de
inventario cuando cambió `backend/commands.py` durante la revisión. Ese binario
intermedio no constituye una entrega verificada.

## Conteos comprobados

| Concepto | Cantidad |
|---|---:|
| IDs documentales importados | 7.562 |
| Principales nominales | 7.351 |
| Revisados documentalmente | 2.447 |
| Heredados sin recertificación completa | 4.904 |
| Suplementos excluidos de los principales | 211 |
| Recetas completas incluidas en el ZIP del último lote | 4 |
| Recetas importadas habilitadas / verificadas en ejecución | 0 / 0 |
| Adaptadores locales habilitados | 3 |
| Adaptadores locales bloqueados | 1 (Blender) |
| Total visible / bloqueado | 7.566 / 7.563 |

El ZIP autorizado tiene SHA256
`5d9445889c943cdfd22383ce43a719027c1c9698e218d487ba5ee7261f13d93d`.
El catálogo normalizado tiene SHA256
`8fa6bec7b0bfe59690e2510a7348b25a8b7ec9a8581822c1d628fa72161c1c47`.
La revisión comprobó las 15.102 frases documentales: resuelven a registros
deshabilitados, sin colisiones con adaptadores habilitados. Véase `README.md`
para reproducción de la importación y `../source-summary.md` para los contratos
de los cuatro diagnósticos de imagen que siguen pendientes.

## Comportamiento implementado

`backend/commands.py` carga el catálogo como datos y selecciona adaptadores
exclusivamente mediante una tabla cerrada en código. El material importado no
puede introducir ejecutores, permisos ni código. Texto y voz usan los mismos IDs:

| ID | Adaptador real | Permiso |
|---|---|---|
| `axx.system.telemetry` | `system_telemetry` | Consulta local |
| `axx.process.inspect` | `process_state_inspector` | Consulta local de PID entero |
| `axx.artifact.write` | `file_artifact_writer` | Botón de aprobación por operación y parámetros |

La interfaz conserva el avatar, formas y ajustes, y agrega Biblioteca en el
panel de archivos existente. `/comandos texto` busca y `/comando ID {JSON}`
prepara parámetros tipados. «Estado del sistema», «información del sistema» y
«estado de Axx» resuelven sin pasar por un modelo. El dictado coloca texto;
enviar usa la misma ruta y una escritura nunca se aprueba con un «sí» reconocido.
No se activó el micrófono para esta tarea.

La preparación persiste ID, parámetros inmutables y caducidad. La aprobación
solo sirve para ese ID. La ejecución usa el ejecutor existente y sus
postcondiciones; el resultado incluye el ID de acción, evidencia y duración.
La consulta posterior recupera el estado sin repetir efectos. Una interrupción
de ejecución queda `unknown`; una preparación abandonada caduca al reiniciar.
Escape/cancelar invalida respuestas tardías y respeta cancelación anterior al
despacho. Una operación atómica ya iniciada puede completar: la aplicación
consulta el resultado y no afirma que se deshizo el efecto.

Las rutas antiguas de acciones y recetas no pueden saltarse la política de
escritura ni activar Blender. Las recetas guardadas de un paso compatible se
resuelven mediante `/recipes/prepare` y exigen la misma aprobación. Las recetas
múltiples o sin adaptador quedan bloqueadas. Las escrituras crean exclusivamente
archivos nuevos en `artifacts`; se rechazan sobrescrituras, ADS, nombres Windows
reservados, escapes y componentes reparse detectados. El archivo se relee y su
SHA256 se comprueba. La inspección de procesos usa API nativa, sin aceptar un
error de `tasklist` como evidencia de inactividad.

## Validación y evidencia

Las pruebas se ejecutan con dependencias ya presentes. Los logs RED/GREEN
corresponden a esta integración; no son pruebas antiguas de los ZIP.

```powershell
& 'C:\Users\luigi\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s backend -p 'test_*.py' -v
python -m unittest scripts.test_import_command_library -v
node 1.AXX/scripts/test-command-library.cjs
node 1.AXX/scripts/test-desktop-frontend.cjs
cargo test --manifest-path src-tauri/Cargo.toml -- --skip tests::explicitly_escaped_user_target_survives_owned_job_cleanup
```

El backend final pasa 72 pruebas en Python 3.12, incluida síntesis local a WAV
sin reproducción. El importador pasa 15 pruebas. Los recuentos finales de UI,
Rust, compilación y prueba del binario se registran en `RESULTADOS.json` al
cerrar la entrega. Las pruebas UI usan navegador headless y fixtures de IPC;
no certifican clic físico, micrófono ni WebView2 instalado.

El baseline con Python 3.14 sin elevación mostró un error SAPI 502 por acceso al
proceso de Windows y un falso negativo de PID ya corregido. Con Python 3.12 y
permisos de ejecución del entorno, SAPI y toda la suite pasan. La suite Rust
completa detectó un fallo previo al limpiar su propio fixture de proceso
breakaway; la ejecución final excluye únicamente ese test y conserva la
limitación. No se hizo una terminación amplia por nombre de proceso.

Resultado final de esta ejecución: 72 backend, 15 importador, 19 biblioteca UI,
18 interfaz original y 20 comprobaciones del backend congelado, con exit 0.
El ejecutable aislado verificado es `verified-package/axx-backend.exe`, SHA256
`90e704b164e4fb8184407ee2a5e378aeb39da6da58245edd38ce00a18e56feb0`.
Su fuente privada tiene 58 archivos; el manifiesto de snapshot coincide antes
y después de compilar y con las fuentes actuales. Véanse
`verified-package-report.json` y `frozen-source-verification.json`.

La prueba del ejecutable compartido anterior falló al comprobar el esquema de
recetas (13 comprobaciones previas aprobadas). Una inspección independiente del
archivo mostró código embebido anterior a la última modificación de fuente,
pese al recibo compartido. No se acepta ese binario ni su instalador como
validación de esta integración. La construcción aislada cerró ese fallo y pasó
las 20 comprobaciones. Los informes anteriores se conservan para trazabilidad.

El restage final sigue bloqueado: otro proceso posee
`build/.windows-delivery.lock`. La herramienta de staging se detuvo al adquirir
el bloqueo, antes de copiar o sustituir binarios compartidos. Estado pendiente,
no una denegación de permisos. Al terminar normalmente la otra compilación:

```powershell
powershell -NoProfile -File scripts/stage-command-backend.ps1
powershell -NoProfile -File scripts/build-windows.ps1 -SkipBackend -EvidenceDirectory evidence/command-library-20261019/build-verified-release
```

El staging exige el informe de ejecución aprobado, compara SHA256 y el snapshot,
y conserva primero los binarios/recibo existentes. Después del build hay que
comprobar que su hash de backend coincide con el del informe verificado.
No se debe usar el instalador compartido anterior como entrega final del catálogo.

Revisión independiente del runtime: se encontraron y corrigieron bypass de
permiso, cancelación en espera, idempotencia de rutas Windows y tolerancia a
catálogo malformado. Revisión UI independiente: se verificaron estados tardíos,
reutilización de recetas y continuidad de herramientas locales. Sus regresiones
se añadieron antes de la corrección.

## Límites y siguiente paso

Esta integración no implementa miles de adaptadores ausentes. Los cuatro
diagnósticos de imagen requieren snapshots aprobados por hash, herramientas
oficiales aprobadas y supervisión/aislamiento definidos en sus contratos. Un
parser de cabecera reducido no satisface esos contratos. Blender permanece
bloqueado en el catálogo y en los transportes antiguos. Inferencia remota,
servicios externos y micrófono físico no forman parte de la validación nueva.

No se instaló ni actualizó la aplicación de `%LOCALAPPDATA%\Programs\Axx`.
El lanzador original puede seguir abriendo esa copia anterior. El instalador
concreto generado queda disponible para aprobar una actualización local por
separado. No se declara que la copia instalada esté actualizada.

## Reversión

Conservar `before/`, `before-manifest.json` y `before-binaries.json`. Los datos
de prueba se crean en carpetas temporales; el estado real del usuario no se usó.
La migración solo añade la tabla `command_runs` cuando se ejecuta el servicio.
No es necesario borrarla para volver al código previo.

Para revertir, cerrar la instancia de prueba y restaurar únicamente los cambios
de esta integración en backend, spec y módulo de biblioteca usando el inventario
`RESULTADOS.json`. Retirar el script final de biblioteca y sus cambios puntuales
del HTML/Rust; no restaurar todo el HTML sobre cambios simultáneos del usuario.
Restaurar los binarios anteriores mediante las rutas explícitas de
`before-binaries.json`, verificando sus hashes. No borrar preferencias, recetas,
SQLite ni directorios externos. Los JSON de catálogo y scripts nuevos pueden
retirarse sin migrar ni ejecutar recetas. No se realizó una desinstalación.
