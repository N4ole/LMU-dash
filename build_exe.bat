@echo off
rem Construit LMU-Dash.exe (un seul fichier) - a lancer sur Windows avec Python 3.10+
cd /d "%~dp0"
python -m pip install --upgrade pyinstaller || goto :err
python -m PyInstaller --noconfirm --clean --onefile --name LMU-Dash ^
  --add-data "web;web" ^
  --hidden-import readers --hidden-import strategy --hidden-import endurance --hidden-import store --hidden-import flags --hidden-import shared --hidden-import pyLMUSharedMemory.lmu_data ^
  server.py || goto :err
echo.
echo ==> dist\LMU-Dash.exe est pret. Copie-le ou tu veux : il cree un dossier "data" a cote de lui.
pause
exit /b 0
:err
echo Echec de la construction.
pause
exit /b 1
