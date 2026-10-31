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
| `[PRIV] no entry: stage 6` ou `stage 7` | la clé (`CAMP_KEY`, hypothèse figée à 8) n'est pas dans la table du gestionnaire |
| `[PRIV] no entry: stage 3`, `4`, ou `8` à `12` | un offset du gestionnaire ou de l'entrée a bougé ; le numéro dit quelle lecture a cassé (voir `PRIV_FAIL_SITES` dans le script) |
| pas de ligne `InventoryInfo slot patch: N entries default 10 -> 1000` | le patcheur d'emplacements a renvoyé ≤ 0 : les cinq coffres de maison restent à 10. Même structure que ci-dessus ; comparer avec `[DBG] slot patcher -> %d` |
| `HOOK CanShow: ABORT` ou `prolog boundary not detected` | le prologue de CanShow n'offre plus 14 octets propres. Le hook passe par la vtable : si cette ligne apparaît, c'est que le hook vtable a renoncé — lire la ligne `CanShow:` juste au-dessus |
| `CanShow: slot unknown` | la case de vtable n'a pas été enregistrée : le résolveur n'est plus passé par `0x9965`, ou la forme de son chemin a changé |
| `CanShow: slot base+0x… now holds 0x…` | quelqu'un d'autre a écrit dans la case entre sa lecture et le hook (autre mod, protection) |
| l'ATH disparaît mais aucun coffre ne s'ouvre ; le log s'arrête après `Warehouse opened`, sans `AUTO-CAPTURED` | CanShow n'est pas accroché : le jeu refuse d'ouvrir un entrepôt loin de son coffre |

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

Et il doit rester **exact** : c'est le nombre d'extensions réellement
achetées. S'il est trop bas, le mod rabote la capacité (le jeu calcule
base + extensions, le mod force le total demandé). Observé le 2026-10-15 :
l'INI disait 0, le joueur en avait acheté 100, et le journal montrait
`[PRIV] container total 1100 -> 1000` — 100 places perdues à chaque ouverture.
`MAJ-mod.ps1` compare désormais l'INI au `[PRIV] base=… exp=N` du dernier
journal et prévient.

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

✅ Sur 3460, les numéros d'étape (§6 quater) ont tranché : **une seule ligne de
ce tableau est fausse**, celle de l'entrée InventoryInfo. Tout le reste de la
chaîne — y compris `CAMP_KEY = 8`, que je croyais coupable — tient encore.
C'est l'intérêt de numéroter : la réponse est arrivée en un seul essai.

| Hypothèse | Où | Validation par BA |
|---|---|---|
| InventoryKey `CampWareHouse` = 8 | `CAMP_KEY` dans le script (`NameToKey` n'est plus ancré) | `base=240 max=1000` — ✅ **toujours juste sur 3460** (l'étape 7 n'a pas déclenché : la clé 8 est bien dans le bucket) |
| entrée InventoryInfo : base et max | wrapper AX, patcheur housing | `base=240 max=1000`, et `5 entries` — ❌ **a bougé sur 3460** : `+0x48/+0x4A` → **`+0x10/+0x14`** (plus adjacents). C'est `ENTRY_BASE`/`ENTRY_MAX` dans le script, appliqué à 7 sites. Se redérive avec `--dump-mgr` |
| gestionnaire : `+0x08` compteur, `+0x58` tableau, `+0x68/+0x6C/+0x78` buckets | wrapper AX | `n=18`, entrée trouvée — ✅ **toujours juste sur 3460** (étapes 3-4 et 9-10 passées ; le compte est passé de 18 à 24) |
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

## 6 ter. Retour d'expérience 3446 (30 octobre 2026)

Premier portage où le jeu **plante au lancement** : `PORT-3446.md`. Quatre
allers-retours, quatre causes distinctes, dans cet ordre.

| Symptôme | Cause | Correction |
|---|---|---|
| `STOP: layout invariant failed: dirty == subtypes + 0x23` | la table des sous-modes est passée de 17 à 18 entrées | l'écart `dirty - subtypes` est dérivé (`2n + 1`), et les deux tables sont distinguées par celle qui émet `ingame-global`, plus par leur taille |
| plantage au lancement | `HOOK CanShow` tombait sur le repli « 14 octets fixes » : coupe une instruction en deux et déplace un `je rel8` | `mov esi,0xE` (5 octets) devient `jmp` vers le chemin ABORT du mod : plus jamais de longueur devinée |
| plus de `=== READY!`, aucune touche | l'appelant traite un hook CanShow raté comme fatal | corrigé par la vraie solution ci-dessous (le caractère fatal est conservé) |
| `BLOCKED: unsafe state (mode=0x04 sub=0x11)` | le sous-mode « jeu normal » est passé de 16 à 17 | la borne du garde-fou est dérivée : l'entrée de la table qui émet `interaction` |
| panneaux silencieux : l'ATH disparaît, rien ne s'ouvre, le log s'arrête après `Warehouse opened` | CanShow n'était pas accroché du tout ; sans ce détour le jeu refuse d'ouvrir un entrepôt loin de son coffre | **accrocher la case de vtable** au lieu du prologue (voir ci-dessous) |

Leçon la plus importante : **le hook CanShow n'est pas optionnel**, et son
prologue n'a plus besoin de s'y prêter. Le mod retrouve déjà CanShow en lisant
la vtable de `UIGamePlayControlRootWarehouse2` ; cette case est de la donnée
ordinaire. On y écrit l'adresse du détour, et on dirige le pointeur « appeler
l'original » du détour (`0x40950`, que l'installeur de prologue remplissait
avec son tremplin) directement sur CanShow. Le code du jeu n'est pas touché.
L'installeur d'origine reste en place comme repli si la case est inconnue.

Signature d'un panneau qui ne monte pas, à comparer au log d'un build qui
marche : la ligne `AUTO-CAPTURED warehouse controller` manque, et le second
`Warehouse opened (… sub=0x05)` n'arrive jamais. Le sous-mode reste celui du
jeu normal — autrement dit le jeu n'est jamais entré dans l'écran d'entrepôt.

## 6 quater. Retour d'expérience 3460 (31 octobre 2026)

Mise à jour du jeu le lendemain de 3446, et premier essai réel du hook
vtable : `PORT-3460.md`.

| Symptôme | Cause | Correction |
|---|---|---|
| `CanShow: slot unknown`, puis `ABORT` | le garde-fou exigeait que la case de vtable contienne l'adresse annoncée par le résolveur. Elle contient un **tremplin** de 5 octets (`e9 … jmp CanShow`), que le résolveur suit avant d'annoncer la destination finale : la comparaison ne pouvait que échouer | enregistrer aussi le **contenu brut** de la case (`.psdata+80`), comparer la case à ça, et donner cette même valeur au détour comme « original » |

Leçon : **une case de vtable ne contient pas forcément la fonction.** Un
binaire lié en incrémental y met souvent un tremplin `jmp rel32`. Appeler le
tremplin ou appeler la fonction revient au même, donc la bonne question n'est
pas « est-ce bien CanShow ? » mais « est-ce toujours ce que j'y ai lu ? ».
C'est ce que le garde-fou vérifie maintenant, et le message d'échec imprime la
case et son contenu au lieu d'un simple « unknown ».

Rien d'autre n'a changé de forme entre 3446 et 3460 : toutes les dérivations
sont passées, seules les adresses ont bougé. Les trois sites `expect` des
éditions CanShow correspondaient octet pour octet.

**Confirmé en jeu** : le hook vtable fonctionne, les six panneaux s'ouvrent et
se ferment, chacun lié à son propre inventaire, sur onze cycles. La crainte
d'un appel direct ou d'une classe dérivée était infondée : une seule case de
vtable suffit.

**Reste ouvert : aucune capacité n'est écrite.** Mesuré en jeu : F4 553/1000,
F5 193/10, F6 79/10, F7 102/10, F8 0/10, F9 257/1237. Ce sont donc **les cinq
coffres de maison** qui sont cassés — l'inverse de ce que le journal laissait
croire — revenus à leurs dix emplacements d'origine tout en contenant encore
les objets qu'une session précédente y avait laissé entrer.

⚠️ **Leçon de méthode** : le journal disait `[PRIV] no entry` (entrepôt privé)
et `housing slot patch enabled` (coffres), ce qui pointait exactement à
l'envers. Ce qui a tranché, c'est **la comparaison avec un journal qui
marchait** : la ligne `InventoryInfo slot patch: 5 entries default 10 -> 1000`,
présente ligne 42 sur 2850 et 2976, est absente sur 3460. Elle est écrite dès
que le patcheur renvoie un nombre positif, sans dépendre du mode verbeux —
donc il n'a rien corrigé. Et **demander à l'utilisateur les chiffres affichés
en jeu** a coûté dix secondes et corrigé le diagnostic.

Les deux pannes lisent la même structure : le patcheur veut `[mgr+0x58]`
(tableau), `[mgr+8]` (compte) et la capacité de base de l'entrée (qu'il
réécrit de 10 à 1000) ; le parcours veut en plus `[mgr+0x68]/[mgr+0x6C]/
[mgr+0x78]`. **Résolu en deux mesures** :

1. Les douze numéros d'étape ont donné **étape 12** — la dernière. Tout le
   reste de la chaîne est donc innocenté, `CAMP_KEY = 8` compris.
2. Le relevé des 24 entrées (`--dump-mgr`) a localisé la paire : `dword
   [entrée+8]` est la clé (l'entrée *j* porte la clé *j+1*), donc la clé 8 est
   `entry[7]`, et elle lit **240 à +0x10** et **1000 à +0x14** — exactement le
   `base=240 max=1000` des versions qui marchaient, deux nombres connus qui
   tombent ensemble. AX les lisait à `+0x48/+0x4A`.

Correction : 7 sites, tous en déplacement 8 bits, donc seul l'octet de
déplacement change — longueur et garde-fous intacts. Et les deux écritures
sont auto-limitées, ce qui rend un mauvais offset inoffensif plutôt que
destructeur : le parcours n'écrit qu'après que les étapes 11 et 12 ont accepté
la valeur comme une capacité entre 1 et 2000, et le patcheur n'écrit que là où
il a lu exactement 10.

À surveiller : le patcheur trouve maintenant **huit** inventaires à 10 et non
cinq (le jeu a ajouté les entrepôts Spagnola, Xamaca et Dragnar), et le code
propriétaire/conteneur situé après l'étape 12 n'a encore jamais tourné sur
3460.

Deux choses apprises en cherchant la clé statiquement, pour ne pas les
refaire : le pool de noms `InventoryInfoKey` est à `game+0x5C64760` (22 noms,
`CampWareHouse` en 4ᵉ position), et chaque nom est référencé deux fois par une
fonction d'enregistrement vers `game+0x1D99A6`. Mais les immédiats qu'on y
trouve sont des **longueurs de `std::string`**, pas des clés, aucun tableau de
pointeurs n'indexe le pool, et ni l'ordre du pool ni celui de
l'enregistrement ne donne 8. **La clé ne se dérive pas par là.**

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
- **Accrocher une vtable plutôt qu'un prologue** quand les octets manquent :
  l'ASI et le jeu sont trop éloignés pour un `jmp rel32`, donc tout hook inline
  coûte 14 octets (`jmp [rip+0]` + adresse). Une case de vtable n'en coûte
  aucun : `VirtualProtect` sur 8 octets, on y écrit le détour, et on aiguille
  le pointeur « original » du détour sur **ce que la case contenait**, sans
  chercher à savoir ce que c'est : une case de vtable contient souvent un
  tremplin `jmp rel32` vers la fonction, et l'appeler revient au même. Ne
  jamais comparer une case à une adresse dérivée autrement.
- **Greffer du code** dans la queue libre de `.pstext` (section 0x2000 du mod,
  marge restante affichée par le build) avec données dans `.psdata` ; voler
  une instruction existante en `jmp rel32` + `nop` et la rejouer dans le stub
  permet de capter un registre vivant que le mod ne conservait pas. Quand la
  queue se remplit : raccourcir les chaînes de log du script récupère quelques
  dizaines d'octets, et il reste une plage de 1985 octets nuls non référencés
  à `0x4683F..0x47000` (vérifié : aucun saut, aucun pointeur absolu n'y mène).
  `.psdata` est RW, pas exécutable : pas de code dedans.
- **Un message pour N causes ne diagnostique rien.** Quand un garde-fou a
  plusieurs sorties vers le même log, donner à chacune son numéro coûte dix
  octets par site (`mov edx,N ; jmp queue`) sans changer l'opcode ni la
  longueur du `jcc` d'origine : la version suivante dit laquelle a refusé.
  C'est ce qui a débloqué le hook CanShow, et c'est en place pour `[PRIV]`.
- **Fusionner les entrées `.pdata` chaînées** : les fonctions du jeu sont
  découpées en plusieurs entrées consécutives.
- Une grosse section RWX au nom bizarre (`.sbss` sur 2850) est la section
  obfusquée du jeu : le code y est illisible statiquement ; ne pas s'y attarder.
- Les consommateurs d'un global connu révèlent la disposition d'une struct
  (`+0x08/+0x58/+0x78`…) et des immédiats utiles (`edx=8`).

Fichiers de travail conseillés (ignorés par git) : `original/` (AX), `patched/`
(builds + logs de test). Copier les logs de chaque étape dans
`docs/logs-<build>/` en `.txt` pour l'historique.
