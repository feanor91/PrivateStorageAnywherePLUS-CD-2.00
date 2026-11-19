@echo off
REM Double-clique sur ce fichier SI le jeu plante ou ne se lance plus apres
REM MAJ-mod.bat. Il installe la version PRUDENTE du mod : les touches F4 a F9
REM ouvrent les panneaux, mais le mod ne touche a AUCUNE donnee d'inventaire
REM (les coffres de maison gardent leur taille normale).
REM Le jeu doit etre FERME.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0MAJ-mod.ps1" -SansAgrandissement %*
echo.
pause
