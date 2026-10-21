param([string]$PythonExecutable = 'python', [string]$EvidenceDirectory = 'evidence\axx-connect\build')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$buildEnvironment = Join-Path $projectRoot '.venv-axx-connect-build'
$buildPython = Join-Path $buildEnvironment 'Scripts\python.exe'
# Reuse the project's already-installed native build dependencies; isolate the
# pinned MCP package. This does not install or restart the desktop application.
if (!(Test-Path -LiteralPath $buildPython -PathType Leaf)) {
    & $PythonExecutable -m venv --system-site-packages $buildEnvironment
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar el entorno de compilación.' }
}
& $buildPython -m pip install --disable-pip-version-check -r (Join-Path $projectRoot 'requirements-axx-connect.txt')
if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar el SDK MCP fijado.' }
& $buildPython -c "import PyInstaller, faster_whisper, ctranslate2, mcp; import importlib.metadata; assert importlib.metadata.version('mcp') == '1.30.0'"
if ($LASTEXITCODE -ne 0) { throw 'Faltan dependencias de compilación de Axx; conserva el entorno base y revisa la documentación.' }
& (Join-Path $PSScriptRoot 'build-windows.ps1') -PythonExecutable $buildPython -EvidenceDirectory $EvidenceDirectory
if ($LASTEXITCODE -ne 0) { throw 'La compilación de Axx Connect falló; revisa las evidencias.' }
