# 05 · Preparación de Windows y comandos de desarrollo

## Herramientas de desarrollo
Windows 11 x64; Git; Node.js compatible con el lockfile de la base; Rust MSVC; Microsoft C++ Build Tools con el workload de escritorio C++ y un Windows SDK; WebView2 Runtime. Los requisitos oficiales de Tauri se consultan en S01. La base fue probada con Node 22.16.0 y TypeScript 5.8.3; eso es una referencia de reproducibilidad, no una afirmación de que sean las versiones actuales más recientes. Mantener Node 22 mantenido o validar otra rama LTS antes de cambiar el lock [S43,S44].

El usuario final no necesitará Git, Node, Rust, Visual Studio ni una clave de desarrollador. El instalador debe resolver WebView2 según el modo de distribución elegido y requisitos documentados [S07].

## Preparación sin cambios ocultos
En PowerShell abre la carpeta de este expediente y ejecuta:
```powershell
& .\tools\Preflight-Windows.ps1 -OutputDirectory .\evidence\mi-pc
```
El script es de lectura de entorno y creación de informe: no instala nada, no eleva permisos, no cambia política de ejecución ni activa escucha. Si PowerShell bloquea un script, revisa su contenido y la política con el administrador; no se proporciona un bypass automático.

Extrae las fuentes mediante la herramienta de preparación, utilizando la ruta real del ZIP:
```powershell
& .\tools\Preparar-Workspace.ps1 `
  -SourceZip "$HOME\Downloads\Axx-20-proyecto.zip" `
  -Destination "$HOME\Documents\Axx-Desktop"
```
El destino debe ser nuevo. El script comprueba rutas de archivo, limita extracción y no sobrescribe proyectos. Después abre la subcarpeta que contenga `package.json`, identificada en el informe.

## Primero: reproducir la base
Desde la raíz real de las fuentes:
```powershell
node --version
npm --version
npm ci
npm run build
npm test
```
Usar `npm ci` únicamente si existe un lockfile válido y concordante; si falla, conservar el error y corregir la causa antes de recrear el lock. No ejecutar `npm audit fix --force` como parte del arranque. La lista real de scripts aparece en `reference/package.original.json`.

Para inspeccionar el prototipo: ejecutar el script `start` si está declarado en package.json, o el comando de servidor que declare su LEEME. No se denomina a ese paso "arrancar la aplicación nativa". `scripts/server20.mjs`, cuando exista, es prueba de servidor; verificar su contenido antes de tratarlo como daemon.

## Después: crear el shell nativo, solo en la rama de migración
Los siguientes son pasos de implementación M1. **No se ejecutaron ni crean por sí solos las capacidades descritas en los demás documentos.**
```powershell
git switch -c desktop/bootstrap
npm install --save-dev --save-exact @tauri-apps/cli@2
npx tauri init
```
La instalación `--save-exact` registra la versión 2.x resuelta; guardar package-lock y registrar CLI/crates/toolchain. En el asistente de init utilizar las fuentes existentes: `frontendDist` debe resolver a `../dist` respecto de src-tauri. `beforeBuildCommand` invoca `npm run build`. Para dev puede usarse el servidor local actual, pero no dejarlo como dependencia Node de la release.

Si la UI mantiene namespace/outFile inicialmente, el adaptador puede usar `withGlobalTauri: true` y la API global verificada de Tauri. No insertar imports ES sin ajustar el build. Para una migración a módulos, plan y prueba aparte. Configurar capabilities para las ventanas reales y denegar contenido remoto privilegiado [S02,S04].

## Compilar cuando M1 esté implementado
Desde la raíz que contiene src-tauri:
```powershell
npx tauri info
npx tauri dev
cargo test --manifest-path src-tauri/Cargo.toml
npx tauri build --bundles nsis
```
Estos comandos **requieren el proyecto Rust todavía por desarrollar**. `tauri init` genera un esqueleto; el contrato del producto requiere ventana/bandeja/instancia/datos/IPC y las puertas de M1. Registrar las rutas de artefactos producidas por el build real, no asumir nombre/versionado de un .exe que aún no existe.

## Fijar versiones
Crear `rust-toolchain.toml` con la versión exacta validada, Cargo.lock, package-lock y un manifiesto de modelos con hash/licencia. No actualizar toolchain, WebView2 policy ni motores de voz en mitad de una corrección de UI. Antes de publicar, ejecutar análisis de dependencias y revisar vulnerabilidades vigentes; no certificar seguridad solo por usar versiones fijadas.

## Carpeta del usuario
Datos: `%LOCALAPPDATA%\Axx\` para base, logs y manifiestos; vídeos en una carpeta elegida. Binarios: instalación por usuario separada. No escribir bases o tokens junto al exe ni en Program Files. No usar la carpeta de desarrollo como almacén del usuario.

## Incorporar el expediente a las fuentes
Desde la carpeta de este expediente, después de extraer el ZIP base, ejecuta `tools/Instalar-Expediente.ps1 -SourceDirectory` indicando la raíz real que contiene package.json. Copia la documentación a `docs/axx-desktop` y crea `AXX-LEER-PRIMERO.md`, sin sobrescribir AGENTS.md existentes ni código. El agente comienza leyendo ese archivo.
