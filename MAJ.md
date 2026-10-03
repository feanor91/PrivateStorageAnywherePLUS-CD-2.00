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
PrivateStorageExpansions=0
```

`PrivateStorageExpansions` doit être le **nombre réel d'extensions d'entrepôt
que tu as achetées** (0 si tu n'en as aucune). **Jamais `-1`.**

Si tu mets `-1`, l'entrepôt affichera bien 1000 places mais refusera les
transferts. Le script te prévient si ce réglage est mauvais.

---

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
