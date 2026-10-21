# 05 — Windows, entorno y empaquetado

## Preflight del proyecto

En PowerShell dentro del repositorio real de Axx: verificar `git status --short`, `git rev-parse --show-toplevel`, `python --version` y los gestores ya declarados en sus manifiestos. Si `python` no existe, probar `py -3.11 --version` o versión superior instalada; no descargar un ejecutable de una URL improvisada. Para el baseline se requiere Python 3.11 o superior. No cambiar globalmente Python ni reinstalar Axx sin necesidad.

Las rutas de ejemplos son relativas al paquete. La ruta real del proyecto se obtiene de la sesión; no usar rutas de otros proyectos Ztola, Dominoes o ETHOS.

## Validación offline del paquete

Desde la raíz de este paquete:

```powershell
powershell -NoProfile -File .\scripts\verify_baseline.ps1
```

Si la política local impide ejecutar scripts, leer el archivo y ejecutar manualmente sus comandos en lugar de cambiar la política global. No hace falta ExecutionPolicy Bypass.

Equivalente manual dentro de `baseline\axx-api-router`:

```powershell
python -m unittest discover -s tests -v
python demo.py
python -m compileall -q router.py demo.py tests
```

Comprobar `$LASTEXITCODE` después de cada comando: debe ser 0. Los logs de fallos simulados forman parte de los tests; no son errores de red reales. Python escribe cachés __pycache__; no incluirlas en release.

Para consultar estado sin API ni DB permanente en el código fuente:

```powershell
$routerTempState = Join-Path ([System.IO.Path]::GetTempPath()) ('axx-router-' + [guid]::NewGuid().ToString() + '.db')
python router.py --config providers.example.json --state $routerTempState --status
```

Los proveedores de ejemplo están desactivados y los modelos son campos por completar, no modelos válidos. No probar chat live antes de terminar el registro de proveedores del documento 06.

## Rutas de producción

Resolver el directorio de datos por la API real del framework. Layout conceptual: configuración no secreta, router-state.db, validación de proveedores y logs limitados bajo datos de usuario; scripts/runtime bajo recursos privados del instalador. Documentar las rutas exactas en PROJECT_MAP y en la UI de diagnóstico sin mostrar secretos.

No escribir DB en Program Files, directorio temporal por solicitud, carpeta del ZIP o cwd variable. Usar una ruta persistente estable para que los contadores no se reinicien al cambiar de carpeta. No sincronizar una DB SQLite activa por nube ni ponerla en una unidad de red como mecanismo de multi-PC.

## Credenciales

Desarrollo: variables de sesión en backend. PowerShell 7 permite captura sin eco mediante Read-Host -MaskInput; no usarlo en PowerShell 5.1. Producción: preferir mecanismo nativo existente de Axx; si falta, implementar almacén de credenciales del sistema y resolverlas en backend. Verificar la biblioteca exacta contra documentación oficial antes de añadirla.

No guardar secretos con prefijos de frontend como VITE_* ni en un JSON empaquetado. Pasar al sidecar un entorno restringido que preserve las variables necesarias de Windows (por ejemplo SystemRoot/TEMP y certificados/proxy autorizados) y solo sus claves autorizadas; no copiar todo el entorno a logs. No ofrecer key export desde UI.

## Distribución

Opción inicial dev: Python instalado explícitamente y script como recurso. Opción release sin Python del usuario: empaquetar un runtime privado o executable del sidecar usando el mecanismo ya soportado en el proyecto. Validar herramienta/versiones con su documentación al implementarlo. Esta entrega no contiene un EXE ni instalador Windows.

En Tauri, resolver la versión mayor desde Cargo.toml/tauri.conf.* antes de modificar capabilities/sidecars. En Node, usar spawn/execFile y argumentos separados; no exec con cadenas. En Rust, usar API de procesos equivalente con handles administrados. No dar acceso genérico a shell en el frontend para resolverlo.

## Deadline y cancelación

El proceso padre posee request_id, reloj monotónico y handle de cancelación. Al vencer 70 s o recibir Esc: marcar cancelado, cerrar stdin, terminar worker y recoger exit; si queda árbol hijo, usar el mecanismo de procesos de Windows adecuado al proyecto. Nunca matar todos los procesos python.exe del equipo. No aceptar stdout recibido después del estado terminal.

La cancelación local no puede retirar datos ya entregados al proveedor ni garantizar que no se facture/procese un intento anterior. Registrar estado remoto desconocido si hubo una herramienta remota; por eso se deshabilitan esas herramientas en el primer incremento.

## Diagnóstico del equipo

Medir versión Windows, arquitectura, Python/runtime, directorios accesibles, conexiones autorizadas y memoria del sidecar. Registrar equipo real y fecha. No se requiere CUDA/GPU para este módulo. No habilitar arranque automático, escucha permanente de micrófono o exposición LAN como efecto secundario de instalar el router.
