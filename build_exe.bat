@echo off
rem Construit LMU-Dash.exe (un seul fichier) - a lancer sur Windows avec Python 3.10+
cd /d "%~dp0"
python -m pip install -r requirements-build.txt || goto :err
python tools\build_exe.py || goto :err
echo.
echo ==> dist\LMU-Dash.exe est pret. Copie-le ou tu veux : il cree un dossier "data" a cote de lui.
pause
exit /b 0
:err
echo Echec de la construction.
pause
exit /b 1
