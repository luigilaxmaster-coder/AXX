@echo off
setlocal
set "AXX_EXE=%LOCALAPPDATA%\Programs\Axx\Axx.exe"
if exist "%AXX_EXE%" (
  start "" "%AXX_EXE%"
  exit /b 0
)
if exist "%~dp0src-tauri\target\release\Axx.exe" (
  start "" "%~dp0src-tauri\target\release\Axx.exe"
  exit /b 0
)
echo Instale Axx con el instalador Windows antes de abrir este lanzador.
pause
exit /b 1
