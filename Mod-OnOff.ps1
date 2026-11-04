# Active ou desactive le mod, pour repondre a la question de base quand
# quelque chose semble anormal en jeu : "est-ce le mod, ou le jeu ?"
#
# Double-clique sur Mod-OnOff.bat : le mod bascule d'un etat a l'autre.
# Rien n'est supprime, le fichier est seulement renomme.

param([string]$Jeu)

$ErrorActionPreference = 'Stop'

function Ok($t)   { Write-Host "  OK  $t" -ForegroundColor Green }
function Info($t) { Write-Host "      $t" -ForegroundColor Gray }
function Stop2($t) {
    Write-Host ""
    Write-Host "  ARRET: $t" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  Interrupteur du mod Private Storage Anywhere" -ForegroundColor White
Write-Host ""

if (-not $Jeu) {
    $candidats = @(
        "D:\SteamLibrary\steamapps\common\Crimson Desert\bin64",
        "C:\Program Files (x86)\Steam\steamapps\common\Crimson Desert\bin64",
        "E:\SteamLibrary\steamapps\common\Crimson Desert\bin64",
        "F:\SteamLibrary\steamapps\common\Crimson Desert\bin64"
    )
    foreach ($c in $candidats) {
        if (Test-Path (Join-Path $c "CrimsonDesert.exe")) { $Jeu = $c; break }
    }
}
if (-not $Jeu -or -not (Test-Path (Join-Path $Jeu "CrimsonDesert.exe"))) {
    Stop2 "Je ne trouve pas le jeu. Relance avec :`n           .\Mod-OnOff.ps1 -Jeu `"<chemin vers bin64>`""
}
if (Get-Process -Name "CrimsonDesert" -ErrorAction SilentlyContinue) {
    Stop2 "Le jeu est en train de tourner. Ferme-le completement, puis relance."
}

$actif    = Join-Path $Jeu "PrivateStorageAnywhere.asi"
$inactif  = Join-Path $Jeu "PrivateStorageAnywhere.asi.DESACTIVE"

if (Test-Path $actif) {
    if (Test-Path $inactif) { Remove-Item $inactif -Force }
    Rename-Item $actif $inactif
    Write-Host "  >>> Le mod est maintenant DESACTIVE <<<" -ForegroundColor Yellow
    Write-Host ""
    Info "Les touches F4 a F9 ne feront plus rien, et les coffres de maison"
    Info "reviennent a leur taille normale. Le jeu n'est pas modifie."
    Info ""
    Info "C'est le moment de verifier si ce que tu as vu vient du mod ou du jeu :"
    Info "lance le jeu, va ouvrir le coffre concerne normalement (en te rendant"
    Info "sur place), et compare avec ce que tu voyais avant."
    Info ""
    Info "Quand tu as fini : re-double-clique sur ce fichier pour remettre le mod."
}
elseif (Test-Path $inactif) {
    Rename-Item $inactif $actif
    Write-Host "  >>> Le mod est maintenant ACTIF <<<" -ForegroundColor Green
    Write-Host ""
    Info "Les touches F4 a F9 fonctionnent de nouveau au prochain lancement."
}
else {
    Stop2 "Je ne trouve aucun fichier du mod dans :`n           $Jeu`n`n         Lance d'abord MAJ-mod.bat pour l'installer."
}
Write-Host ""
