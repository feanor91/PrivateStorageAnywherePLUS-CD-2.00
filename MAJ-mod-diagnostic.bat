@echo off
REM Double-clique sur ce fichier pour installer la version DIAGNOSTIC du mod.
REM Elle agrandit les coffres de maison (comme la version normale) et copie dans son journal
REM ce que le mod voit en memoire, pour verifier que l agrandissement vise les bonnes donnees.
REM Le jeu doit etre FERME.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0MAJ-mod.ps1" -Diagnostic %*
echo.
pause
