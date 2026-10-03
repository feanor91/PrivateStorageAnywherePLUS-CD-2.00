# Mise a jour du mod Private Storage Anywhere apres une mise a jour du jeu.
# Lance ce script en double-cliquant sur MAJ-mod.bat (a cote de ce fichier).
#
#   .\MAJ-mod.ps1            -> construit et installe la version complete
#   .\MAJ-mod.ps1 -Test      -> version "lecture seule" (n'ecrit rien dans le jeu)
#   .\MAJ-mod.ps1 -Jeu "D:\...\bin64"   -> si le jeu n'est pas trouve tout seul

param(
    [switch]$Test,
    [string]$Jeu
)

$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot

function Titre($t) { Write-Host ""; Write-Host "=== $t" -ForegroundColor Cyan }
function Ok($t)    { Write-Host "  OK  $t" -ForegroundColor Green }
function Info($t)  { Write-Host "      $t" -ForegroundColor Gray }
function Stop2($t) {
    Write-Host ""
    Write-Host "  ARRET: $t" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Rien n'a ete modifie dans le jeu." -ForegroundColor Yellow
    Write-Host "  Copie tout ce texte et envoie-le a Claude." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "  Mise a jour de Private Storage Anywhere" -ForegroundColor White

# ---------------------------------------------------------------- 1. le jeu
Titre "1/6  Le jeu"
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
    Stop2 "Je ne trouve pas le jeu. Relance avec :`n           .\MAJ-mod.ps1 -Jeu `"<chemin vers bin64>`""
}
$exe = Join-Path $Jeu "CrimsonDesert.exe"
$asiInstalle = Join-Path $Jeu "PrivateStorageAnywhere.asi"
$ini = Join-Path $Jeu "PrivateStorageAnywhere.ini"
$build = ([string](Get-Item $exe).VersionInfo.FileVersion).Split('.')[-1]
Ok "jeu trouve : $Jeu"
Info "version du jeu : build $build"

if (Get-Process -Name "CrimsonDesert" -ErrorAction SilentlyContinue) {
    Stop2 "Le jeu est en train de tourner. Ferme-le completement, puis relance ce script."
}
Ok "le jeu est bien ferme"

# ------------------------------------------------------- 2. le fichier source
Titre "2/6  Le fichier d'origine"
$ax = Join-Path $repo "original\PrivateStorageAnywhere-AX-2.00.asi"
$axHash = "C2B9848F33A3822532C563C31965F4DFF74B0D02A369AE7626D3E43056C49840"
if (-not (Test-Path $ax)) {
    Stop2 "Il manque le fichier d'origine :`n           $ax`n`n         C'est le PrivateStorageAnywhere.asi de la version 2.00 telechargee sur Nexus`n         (mod 388, fichier 'PrivateStoragePlus 2.00.0'). Remets-le a cet endroit."
}
if ((Get-FileHash $ax -Algorithm SHA256).Hash -ne $axHash) {
    Stop2 "Le fichier d'origine n'est pas le bon (empreinte differente)."
}
Ok "fichier d'origine present et conforme"

# ------------------------------------------------------------- 3. python
Titre "3/6  Python"
$py = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Info "premiere utilisation : installation de Python et des 2 bibliotheques..."
    try {
        & python -m venv (Join-Path $repo ".venv")
        & $py -m pip install --quiet capstone pefile
    } catch {
        Stop2 "Impossible d'installer Python. Installe Python depuis python.org,`n         puis relance ce script."
    }
}
& $py -c "import capstone, pefile" 2>$null
if ($LASTEXITCODE -ne 0) {
    Info "reinstallation des bibliotheques..."
    & $py -m pip install --quiet capstone pefile
    & $py -c "import capstone, pefile" 2>$null
    if ($LASTEXITCODE -ne 0) { Stop2 "Les bibliotheques capstone/pefile ne s'installent pas." }
}
Ok "Python pret"

# ------------------------------------------------------------ 4. construction
Titre "4/6  Construction du mod pour le build $build"
$patched = Join-Path $repo "patched"
if (-not (Test-Path $patched)) { New-Item -ItemType Directory $patched | Out-Null }
if ($Test) {
    $mode = "dry"; $suffixe = "BA"
    Info "mode TEST : le mod lira les valeurs sans rien modifier dans le jeu"
} else {
    $mode = "live"; $suffixe = "BB"
}
$sortie = Join-Path $patched "PrivateStorageAnywhere-$build.$suffixe.asi"
$journal = Join-Path $patched "build-$build.txt"

& $py -u (Join-Path $repo "tools\retarget_ay.py") $ax $sortie $exe --housing --f4 $mode 2>&1 |
    Tee-Object -FilePath $journal | ForEach-Object {
        if     ($_ -match "^STOP:")             { Write-Host "      $_" -ForegroundColor Red }
        elseif ($_ -match "sha256|wrote|layout|ModeSwitch|mainChar") { Write-Host "      $_" -ForegroundColor Gray }
    }

if (-not (Test-Path $sortie)) {
    Write-Host ""
    Write-Host "  Le detail complet est dans : $journal" -ForegroundColor Yellow
    Stop2 "La construction s'est arretee (voir la ligne rouge ci-dessus).`n         Une piece du jeu a change de forme : il faut adapter le script."
}
Ok "mod construit : $(Split-Path $sortie -Leaf)"
Info "empreinte : $((Get-FileHash $sortie -Algorithm SHA256).Hash.Substring(0,16))..."

# ------------------------------------------------------------ 5. installation
Titre "5/6  Installation dans le jeu"
if (Get-Process -Name "CrimsonDesert" -ErrorAction SilentlyContinue) {
    Stop2 "Le jeu s'est relance entre-temps. Ferme-le et recommence."
}
if (Test-Path $asiInstalle) {
    $sauvegarde = Join-Path $Jeu ("PrivateStorageAnywhere.asi.avant-$build.bak")
    Copy-Item $asiInstalle $sauvegarde -Force
    Ok "ancienne version sauvegardee : $(Split-Path $sauvegarde -Leaf)"
}
Copy-Item $sortie $asiInstalle -Force
Ok "nouvelle version installee"

# -------------------------------------------------------------- 6. reglages
Titre "6/6  Verification des reglages"
if (Test-Path $ini) {
    $exp = (Select-String -Path $ini -Pattern "^\s*PrivateStorageExpansions\s*=" | Select-Object -Last 1).Line
    if ($exp -match "-1") {
        Write-Host "  ATTENTION  PrivateStorageExpansions=-1 dans le fichier INI." -ForegroundColor Yellow
        Info "Mets le nombre reel d'extensions achetees (0 si tu n'en as pas)."
        Info "Sinon l'entrepot affichera 1000 mais refusera les transferts."
        Info "Fichier : $ini"
    } else {
        Ok "reglages INI corrects ($($exp.Trim()))"
    }
} else {
    Info "pas de fichier INI trouve (il sera cree au prochain lancement)"
}

# ------------------------------------------------------------------- la suite
Write-Host ""
Write-Host "  ------------------------------------------------------------" -ForegroundColor White
Write-Host "  TERMINE. Maintenant :" -ForegroundColor White
Write-Host ""
Write-Host "   1. Lance le jeu et charge ta sauvegarde."
Write-Host "   2. Appuie sur F4 (entrepot prive), puis Echap."
Write-Host "   3. Appuie sur F5, F6, F7, F8, F9 (les coffres), ferme a chaque fois."
Write-Host "   4. Si tout s'ouvre : c'est bon, tu peux jouer."
Write-Host ""
Write-Host "   Si quelque chose ne marche pas : QUITTE LE JEU D'ABORD, puis envoie"
Write-Host "   a Claude ce fichier journal (il est efface au lancement suivant) :"
Write-Host "   $(Join-Path $Jeu 'PrivateStorageAnywhere.log')" -ForegroundColor Yellow
Write-Host ""
if (Test-Path (Join-Path $Jeu ("PrivateStorageAnywhere.asi.avant-$build.bak"))) {
    Write-Host "   Pour revenir en arriere : renomme" -ForegroundColor Gray
    Write-Host "   PrivateStorageAnywhere.asi.avant-$build.bak  en  PrivateStorageAnywhere.asi" -ForegroundColor Gray
    Write-Host ""
}
