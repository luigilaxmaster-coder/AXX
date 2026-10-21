# Offline only. No API keys, downloads, installs or execution-policy changes.
param([string]$PythonExecutable = 'python')
$ErrorActionPreference = 'Stop'
$routerRoot = Join-Path $PSScriptRoot '..\baseline\axx-api-router'
$routerTempState = Join-Path ([System.IO.Path]::GetTempPath()) ('axx-verify-' + [guid]::NewGuid().ToString() + '.db')
function Invoke-CheckedPython {
    param([string[]]$Arguments)
    & $PythonExecutable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python verification failed; exit=$LASTEXITCODE" }
}
Push-Location $routerRoot
try {
    Invoke-CheckedPython -Arguments @('-c', 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"')
    Invoke-CheckedPython -Arguments @('-m', 'unittest', 'discover', '-s', 'tests', '-v')
    Invoke-CheckedPython -Arguments @('demo.py')
    Invoke-CheckedPython -Arguments @('router.py', '--config', 'providers.example.json', '--state', $routerTempState, '--status')
    Invoke-CheckedPython -Arguments @('-m', 'compileall', '-q', 'router.py', 'demo.py', 'tests')
    Write-Output 'OFFLINE_BASELINE_PASS: live APIs, Axx integration and Windows installer remain unverified.'
} finally {
    Pop-Location
    if (Test-Path -LiteralPath $routerTempState) { Remove-Item -LiteralPath $routerTempState }
}
