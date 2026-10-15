@echo off
REM Double-clique pour DESACTIVER le mod, re-double-clique pour le REACTIVER.
REM Sert a verifier si un comportement bizarre vient du mod ou du jeu.
REM Le jeu doit etre FERME.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Mod-OnOff.ps1" %*
echo.
pause
