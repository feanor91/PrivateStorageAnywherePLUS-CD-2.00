@echo off
REM Double-clique sur ce fichier pour installer la version DIAGNOSTIC du mod.
REM Elle ne modifie rien dans le jeu : elle copie dans son journal ce que le jeu
REM contient en memoire, pour retrouver comment reparer l agrandissement des coffres.
REM Le jeu doit etre FERME.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0MAJ-mod.ps1" -Diagnostic %*
echo.
pause
