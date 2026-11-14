@echo off
rem Publie sur GitHub les cartes de circuit apprises pendant tes sessions.
rem A lancer depuis ton clone du depot. Si l'exe est ailleurs :  pousser_cartes.bat --data "D:\LMU\data"
cd /d "%~dp0"
python tools\push_tracks.py %*
pause
