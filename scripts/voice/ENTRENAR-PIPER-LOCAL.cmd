@echo off
setlocal
set EPOCHS=%1
if "%EPOCHS%"=="" set EPOCHS=2250
echo [Axxmorcito Piper Local] Continuando entrenamiento en WSL Ubuntu-24.04 hasta epoch %EPOCHS%...
wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/luigi/Desktop/axx2/scripts/voice/wsl-train-piper.sh axx-morcito-es /mnt/c/Users/luigi/AppData/Local/Axx/speech/training/axxmorcito-piper/dataset-es es-419 %EPOCHS% 8
wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/luigi/Desktop/axx2/scripts/voice/wsl-train-piper.sh axx-morcito-en /mnt/c/Users/luigi/AppData/Local/Axx/speech/training/axxmorcito-piper/dataset-en en-us %EPOCHS% 8
echo [Axxmorcito Piper Local] Listo. Modelos instalados en %LOCALAPPDATA%\Axx\speech\piper\models\
pause
