# Procédure de portage — à refaire à chaque mise à jour de Crimson Desert

Ce document décrit, pas à pas, comment reconstruire le mod quand une mise à
jour du jeu déplace ses adresses internes. Il a été écrit après le portage de la
release 2.00 (build AX) vers le build 2850 de septembre 2026 ; le détail
technique de ce portage est dans [PORT-2850.md](PORT-2850.md).

> **Raccourci** : sur la machine du mainteneur, `MAJ-mod.bat` enchaîne tout
> seul les étapes 1 à 3 ci-dessous (construction, sauvegarde, installation,
> vérification de l'INI). Voir [MAJ.md](MAJ.md). Ce document reste la référence
> quand le script s'arrête sur un `STOP:`.

Principe : on ne retape jamais une adresse. `tools/retarget_ay.py` prend l'ASI
AX 2.00 (celui de Nexus) et le nouvel exécutable, **dérive** chaque valeur par
sa forme dans le binaire, et s'arrête net (`STOP:`) dès qu'une ancre est
absente ou ambiguë. Le résultat est déterministe : même entrée, même sortie,
même hash.

---

## 0. Symptômes d'une mise à jour

Le mod ne fait plus rien, et `bin64\PrivateStorageAnywhere.log` montre l'un de
ces cas :

| Ligne dans le log | Sens |
|---|---|
| `FATAL: pattern scan failed` sans `=== READY!` | un des cinq résolveurs obligatoires du mod d'origine a échoué (Handler, ModeSwitcher, vtable CanShow, SetInventory, MainCharGlobal) |
| `BLOCKED: unsafe state (mode=0x00 …)` + lignes `[MODE] cN` | l'objet mode ou son layout a bougé |
| crash au lancement ou à l'ouverture | une adresse jeu figée dans l'ASI est obsolète |
| `[INV] InventoryInfoManager NOT found` | la zone des globals de gestionnaires a bougé |
| `[PRIV] no entry` / `[PRIV] no container` | clé CampWareHouse ou offsets conteneur changés |

**Toujours copier le log avant de relancer le jeu** : il est écrasé au lancement.

---

## 1. Prérequis

- Python 3.11+ et `pip install -r requirements.txt` (capstone, pefile).
- L'ASI **AX 2.00** d'origine, sha256 `c2b9848f33a3822532c563c31965f4dff74b0d02a369ae7626d3e43056c49840`
  (le fichier `PrivateStorageAnywhere.asi` de la release Nexus 2.00.0). Le
  script refuse toute autre entrée. Le garder dans `original/` (ignoré par git).
- Le nouvel exécutable : `<jeu>\bin64\CrimsonDesert.exe`.
- Le jeu **fermé** au moment de copier l'ASI (sinon « Device or resource busy »).

---

## 2. Construire

```powershell
python tools/retarget_ay.py original/PrivateStorageAnywhere-AX-2.00.asi patched/PSA.BB.asi "<jeu>\bin64\CrimsonDesert.exe" --housing --f4 live
```

Trois niveaux, à utiliser dans l'ordre si quelque chose cloche :

| Option | Build | Ce qui est actif |
|---|---|---|
| (aucune) | AY | ouverture des 6 panneaux ; aucune écriture de capacité |
| `--housing` | AZ | + coffres F5–F9 à 1 000 |
| `--housing --f4 dry` | BA | + chemin entrepôt privé **en lecture seule** (log `[PRIV]`, aucune écriture) |
| `--housing --f4 live` | BB | + entrepôt privé configurable (`PrivateStorageSlots`) |

La sortie liste chaque valeur dérivée. Sur 2850 elle doit ressembler à :

```
ModeSwitch game+0x5cf8c0  mode object at [parent+0x1178]
layout mode=0x28 submode=0x29 flags=0x31 subtypes=0x38 dirty=0x5b  ingame=4 store=5
mainChar profile: 960 loads, first-deref +0x0:281 +0xb0:178 +0x50:142 +0xa0:84 +0x90:77 …
mainChar global game+0x6c2da48
ResolveActor votes: [('0x83d990', 169), ('0x83da20', 80)]
CampWareHouse game+0x57a3658
InventoryInfoManager vtable game+0x57a37d0
manager globals: 92 distinct, 0x6c2e288..0x6c4e590
```

Les **chiffres changeront** à chaque build du jeu (sur 2944 : `ModeSwitch 0x640dc0`, `[parent+0x1188]`, layout `0x28/0x2a/0x32/0x39/0x5c`, mainChar `0x6d69208`) ; ce qui doit rester vrai :
le profil mainChar dominé par `+0x0` avec `+0x50/+0x90/+0xa0/+0xb0` présents,
un vainqueur net pour ResolveActor (≥ 2× le second), un layout mode cohérent avec ses invariants (le script le ré-émet s'il
diffère de 2.00 — c'est arrivé sur 2944), mode 4, store 5, une seule vtable.

### Si le script s'arrête (`STOP: …`)

| Message | Cause probable | Piste |
|---|---|---|
| `could not identify ModeSwitch among BuildModeTagList's callers` | le pool de tags UI (`store`, `ingame-global`) ou `BuildModeTagList` a changé | `derive_modestate.py <exe>` seul ; vérifier `find_tag_pool` / la fusion des entrées `.pdata` chaînées (`merged_function`) |
| `layout invariant failed: …` | la struct mode a changé de forme (pas seulement bougé) | relire `ModeSwitch` : les deux octets passés à `BuildModeTagList` sont mode/sous-mode ; les compares indexés donnent flags/subtypes ; `mov byte […],1` ×2 + `cmp …,0` donne dirty. Adapter les invariants si la forme est légitime |
| `ModeSwitch … direct callers, expected 1..4` / `call sites disagree` | changement de codegen | l'offset de l'objet mode est lu sur l'instruction `mov r64,[r64+disp32]` qui précède chaque appel ; ils doivent concorder. Un prologue différent n'arrête plus le build : le hook reste désarmé (stage 2) |
| `mainChar global is not unique` | le profil d'accès a changé | ajuster les offsets attendus dans `derive_mainchar` (comparer avec le tableau §68 des FINDINGS et le profil 2850 ci-dessus) |
| `ResolveActor has no clear majority` | forme d'appel changée | inspecter les sites `rcx=[[mainChar]] ; call X` ; le corps doit contenir `mov rbx,rdx` et un `[rcx+0x50]` |
| `CampWareHouse: expected one referenced copy` | une des copies de la chaîne a gagné/perdu ses xrefs | accepter tout préfixe REX sur le `lea` (déjà fait) ; sinon choisir celle référencée par du code |
| `InventoryInfoManager: expected one …` | RTTI modifié | chercher `.?AVInventoryInfoManager@pa@@` ; TypeDescriptor → CompleteObjectLocator (offset 0) → vtable |
| `manager window … not inside one data section` | les globals de gestionnaires sont ailleurs | recompter les `mov r10,[rip+G]` devant l'idiome `shl r11,8 ; add r11,[r10+0x78]` |
| `unexpected bytes at rva …` | l'entrée n'est pas l'AX exact | vérifier le sha256 de l'ASI d'entrée |

---

## 3. Installer

1. Jeu fermé. Sauvegarder l'ASI en place : `PrivateStorageAnywhere.asi.<ancien>.bak`.
2. Copier `patched/PSA.BB.asi` vers `<jeu>\bin64\PrivateStorageAnywhere.asi`.
3. Dans `PrivateStorageAnywhere.ini`, section `[Settings]` :
   ```ini
   PrivateStorageSlots=1000
   PrivateStorageExpansions=0     ; nombre RÉEL d'extensions achetées, jamais -1 (voir §5)
   ```

---

## 4. Tester, dans l'ordre, un build à la fois

Toujours depuis le jeu normal (aucun menu ouvert), une seule touche à la fois,
puis quitter et lire le log.

**AY / AZ / BA / BB — initialisation**

```
=== Private Storage Anywhere v1.5.10 (CD 2850.BB) ===
MainCharGlobal: OK base+0x… (singleton scan, r0, modeOff=0x0)
=== READY! …
```
Pas de `FATAL`. Les avertissements suivants sont normaux : `SetTitleDir: FAIL`,
`HGM string slot: WARN`, `Type resolver: DISABLED`, `StoreSubIndex: derive failed,
keeping default 5`, `Gatherables panel-id lookup FAILED`, `[MODE] capture hook
NOT armed (stage 2 ou 3)`, `CHAN PRE/POST EXCEPTION`.

**Panneaux (tous les builds)** — F4 puis Échap, puis F5…F9 :

```
HOTKEY Private (vk=0x73) -> OPEN
=== OPENING WAREHOUSE (Private) ===
  Warehouse opened (mode=0x04 sub=0x10)
  Warehouse opened (mode=0x04 sub=0x05)
…
  Warehouse closed (mode=0x04 sub=0x05)
```
`activePanel` doit aller de 0 à 5. Un `BLOCKED` = arrêt, envoyer le log.

**AZ et suivants — coffres**

```
Inventory mgr ptr:   DEFERRED (AZ) - resolved at runtime by InventoryInfoManager vtable base+0x…
  [INV] InventoryInfoManager global at base+0x… (object …, vtable match) - housing slot patch enabled
InventoryInfo slot patch: 5 entries default 10 -> 1000
```
Le compte doit être **5**. Autre chose = arrêt. Vérifier en jeu qu'un coffre
affiche 1 000.

**BA — exécution à blanc du chemin F4** (rien n'est écrit) :

```
  [PRIV] base=240 max=1000 exp=<extensions> owner=… n=18
  [PRIV] exp=… (0x16=… tot=<capacité actuelle>) base 240 -> <1000-exp>
  [PRIV] container total <actuelle> -> 1000
```
`base=240` et `max=1000` identifient l'entrée CampWareHouse ; `tot` doit
égaler la capacité affichée en jeu. Si les valeurs sont incohérentes, ou
`[PRIV] no entry` / `no container`, **ne pas passer en `live`** : la clé (8) ou
un offset a changé (§6).

**BB — réel** : l'entrepôt affiche `n / 1000` et accepte les transferts.

Conditions d'arrêt à tout moment : gel, crash, interface bloquée → fermer le
jeu, envoyer le log, remettre le `.bak`.

---

## 5. Pourquoi `PrivateStorageExpansions` ne doit pas rester à -1

Avec `-1` (défaut de la release), le mod attend la première ouverture de F4
pour connaître le nombre d'extensions et écrire la base. Mais le conteneur de
l'entrepôt est construit **au chargement de la sauvegarde**, avec la capacité
connue à ce moment-là : l'étiquette passe bien à `/1000`, mais les transferts
sont refusés. Avec une valeur explicite, le worker écrit la base ~1 s après
`READY!`, avant le chargement — comme pour les coffres — et tout fonctionne.
Constaté et corrigé le 2026-09-15.

---

## 6. Ce qui n'est PAS dérivé (hypothèses figées, validées par le build BA)

Ces valeurs viennent de 2.00 et sont vérifiées indirectement par l'exécution à
blanc. Si BA donne des résultats incohérents, c'est ici qu'il faut regarder.

| Hypothèse | Où | Validation par BA |
|---|---|---|
| InventoryKey `CampWareHouse` = 8 | `CAMP_KEY` dans le script (`NameToKey` n'est plus ancré) | `base=240 max=1000` |
| entrée InventoryInfo : `word +0x48` base, `word +0x4A` max | wrapper AX, patcheur housing | idem, et `5 entries` |
| gestionnaire : `+0x08` compteur, `+0x58` tableau, `+0x68/+0x6C/+0x78` buckets | wrapper AX | `n=18`, entrée trouvée |
| conteneur : `word +0x10` index, `+0x14` total, `+0x16`, `+0x1A` extensions | wrapper AX | `tot` = capacité affichée |
| propriétaire : `+0x18` tableau, `+0x20` compte ; `[[acteur+0x68]+0xB8]` | wrapper AX | `owner=…`, `n=18` |
| `ResolveActor(holder,&out)` : `out+0x08` acteur, `byte out+0x10` valide | wrapper AX | `owner` non nul |
| menuMgr = `[root+0x90]` (route de repli vers l'objet mode) | telemetry / `get_mode_obj` | `mode=0x04` à l'ouverture |
| prologue de `ModeSwitch` = trois spills `48 89 5C 24 08 …` | hook de capture | asserté au build |

---

## 6 bis. Retour d'expérience 2944 (20 septembre 2026)

Deuxième portage, cinq jours après 2850 : `README`/`PORT-2944.md`. Ce qu'il a
fallu apprendre au script, et qui sert de modèle pour la prochaine fois :

| Symptôme | Cause | Correction |
|---|---|---|
| `STOP: tag pool found but 'store' is missing` | pool de chaînes réordonné | fenêtre de recherche ±0x200 dans `derive_modestate.find_tag_pool` |
| `ingame=None` | bornes des tables de saut mal appariées | chaque table bornée par le `cmp` qui précède *son* dispatch |
| `STOP: ModeSwitch prologue mismatch` | fonction recompilée | le hook de capture reste désarmé (stage 2), offset lu sur tous les appelants |
| `BLOCKED: unsafe state (mode=0x07 sub=0x10)` sur tous les panneaux | un octet inséré entre mode et sous-mode ; la règle « deux stores adjacents » a pris le mauvais octet | mode/sous-mode = les deux octets passés à `BuildModeTagList`, sans exiger l'adjacence ; layout ré-émis (stub A, `dirty`, sonde) |

Leçon : quand le log montre `BLOCKED` avec un `sub` plausible (`0x10`) mais un
`mode` absurde, c'est l'offset du mode qui est faux, pas la route vers l'objet.
Le `sub=0x10` prouve que l'objet est le bon.

## 7. Boîte à outils quand une ancre casse

Techniques qui ont marché sur 2850 (voir `PORT-2850.md` pour les détails) :

- **Identifier un global par son profil d'accès** : compter les `mov r64,[rip+G]`
  et l'histogramme des premiers déréférencements ; le global mainChar a un
  profil stable d'une version à l'autre.
- **Chasser une vtable par RTTI** : chaîne `.?AV…@@` → TypeDescriptor
  (nom − 0x10) → CompleteObjectLocator (signature 1, `pSelf` = sa propre rva)
  → qword `base+COL` en data → vtable = adresse + 8. L'identité est exacte.
- **Résoudre à l'exécution** quand la statique est bloquée : scanner une fenêtre
  de globals et comparer le vptr de l'objet pointé (c'est ce que fait `INVSCAN`).
- **Désassembler fonction par fonction via `.pdata`** (capstone) : un balayage
  linéaire depuis un point arbitraire se désynchronise et rate des sites.
- **Fusionner les entrées `.pdata` chaînées** : les fonctions du jeu sont
  découpées en plusieurs entrées consécutives.
- Une grosse section RWX au nom bizarre (`.sbss` sur 2850) est la section
  obfusquée du jeu : le code y est illisible statiquement ; ne pas s'y attarder.
- Les consommateurs d'un global connu révèlent la disposition d'une struct
  (`+0x08/+0x58/+0x78`…) et des immédiats utiles (`edx=8`).

Fichiers de travail conseillés (ignorés par git) : `original/` (AX), `patched/`
(builds + logs de test). Copier les logs de chaque étape dans
`docs/logs-<build>/` en `.txt` pour l'historique.
