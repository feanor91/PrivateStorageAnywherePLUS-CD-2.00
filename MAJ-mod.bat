@echo off
REM Double-clique sur ce fichier pour mettre a jour le mod apres une mise a jour du jeu.
REM Le jeu doit etre FERME.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0MAJ-mod.ps1" %*
echo.
pause
