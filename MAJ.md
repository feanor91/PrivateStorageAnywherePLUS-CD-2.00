# Comment remettre le mod en marche après une mise à jour du jeu

À faire **à chaque fois que Crimson Desert se met à jour** et que le mod ne
fonctionne plus (les touches F4 à F9 ne font plus rien).

Ça prend 2 minutes.

---

## Les 3 étapes

### 1. Ferme complètement le jeu

Pas juste la fenêtre : le jeu ne doit plus tourner du tout.

### 2. Double-clique sur `MAJ-mod.bat`

Il est dans ce dossier :

```
D:\Repos\Private storage anywhere\PrivateStorageAnywherePLUS-CD-2.00\
```

Une fenêtre noire s'ouvre et travaille une vingtaine de secondes. Elle fait
tout : elle trouve le jeu, fabrique la nouvelle version du mod, sauvegarde
l'ancienne, et installe la nouvelle.

À la fin elle écrit **TERMINE** et t'explique la suite. Appuie sur une touche
pour fermer la fenêtre.

### 3. Lance le jeu et vérifie

Charge ta sauvegarde, puis :

- **F4** → l'entrepôt privé s'ouvre → Échap
- **F5, F6, F7, F8, F9** → les cinq coffres s'ouvrent → Échap à chaque fois

Si tout s'ouvre, c'est fini. Tu peux jouer.

---

## Si ça ne marche pas

### La fenêtre noire affiche « ARRET » en rouge

Ça veut dire qu'une pièce du jeu a changé de forme et que le programme ne la
reconnaît plus. **Rien n'a été modifié dans ton jeu**, tu ne risques rien.

➡️ Copie tout le texte de la fenêtre et envoie-le à Claude.

### Le jeu démarre mais les touches ne font rien, ou quelque chose cloche

1. **Quitte le jeu d'abord** (important : le fichier est effacé au lancement
   suivant).
2. Envoie à Claude ce fichier :
   ```
   D:\SteamLibrary\steamapps\common\Crimson Desert\bin64\PrivateStorageAnywhere.log
   ```

### Tu veux revenir à l'ancienne version

Dans le dossier `bin64` du jeu, il y a un fichier qui se termine par `.bak`
(par exemple `PrivateStorageAnywhere.asi.avant-2976.bak`).

Renomme-le en `PrivateStorageAnywhere.asi` (en remplaçant celui qui existe).

---

## Deux choses à ne pas perdre

**1. Le fichier d'origine.** Il est ici :

```
...\PrivateStorageAnywherePLUS-CD-2.00\original\PrivateStorageAnywhere-AX-2.00.asi
```

C'est le mod de la version 2.00 téléchargé sur Nexus. Tout est refabriqué à
partir de lui à chaque fois. **Ne le supprime pas.** Si tu le perds :
Nexus Mods → mod 388 → onglet Files → fichier « PrivateStoragePlus 2.00.0 ».

**2. Le réglage des extensions.** Dans le fichier
`bin64\PrivateStorageAnywhere.ini` :

```ini
PrivateStorageSlots=1000
PrivateStorageExpansions=100
```

- `PrivateStorageSlots` = le nombre total de places que tu veux dans
  l'entrepôt privé (F4), extensions comprises.
- `PrivateStorageExpansions` = le **nombre réel d'extensions d'entrepôt que tu
  as achetées dans le jeu**. **Jamais `-1`.**

⚠️ **À remettre à jour quand tu achètes des extensions.** Si le chiffre est
trop bas, le mod rabote ta capacité : le jeu calcule base + extensions, et le
mod le ramène de force au total indiqué. Tu perds les places payées.

Si tu mets `-1`, l'entrepôt affichera bien le bon total mais refusera les
transferts.

Le script vérifie les deux cas tout seul : il lit le nombre d'extensions que
le mod a détecté pendant ta dernière partie et te prévient s'il ne correspond
pas au réglage.

---

## Un truc bizarre en jeu ? D'abord : est-ce le mod, ou le jeu ?

C'est la première question à se poser, et elle se tranche en 5 minutes.

1. Ferme le jeu.
2. Double-clique sur **`Mod-OnOff.bat`** → il affiche « le mod est maintenant
   DESACTIVE ». (Rien n'est supprimé, le fichier est juste renommé.)
3. Lance le jeu et va voir la même chose **sans le mod** : rends-toi sur place
   et ouvre le coffre normalement, puisque F4–F9 ne répondent plus.
4. Compare avec ce que tu voyais avant.
5. Ferme le jeu, re-double-clique sur `Mod-OnOff.bat` → « le mod est
   maintenant ACTIF ».

Si c'est pareil sans le mod, c'est le jeu qui est comme ça. Sinon, envoie-moi
ce que tu as vu dans les deux cas.

## Mode prudent (facultatif)

Si tu préfères vérifier avant de laisser le mod modifier quoi que ce soit,
ouvre PowerShell dans le dossier et tape :

```powershell
.\MAJ-mod.ps1 -Test
```

Ça installe une version qui **lit** les valeurs du jeu et les note dans le
journal, sans rien modifier. L'entrepôt restera à sa taille normale. Envoie le
journal à Claude, et s'il est correct, relance `MAJ-mod.bat` normalement.

---

## Si le jeu n'est pas trouvé

Le script cherche aux endroits habituels. S'il ne trouve pas, ouvre PowerShell
dans le dossier et indique-lui le chemin :

```powershell
.\MAJ-mod.ps1 -Jeu "E:\MonDossier\Crimson Desert\bin64"
```

---

*Pour les détails techniques : [PORTING.md](PORTING.md) (la procédure
complète) et les fiches `PORT-xxxx.md` (ce qui a changé à chaque mise à jour).*
