# LMU Dash — dashboard second écran pour Le Mans Ultimate

Un petit serveur (Python, aucune dépendance) + une page web plein écran. Il lit la mémoire partagée
native de LMU et affiche : vitesse/rapport/régime, courbes gaz/frein, températures, aides, chronos et
delta, écarts, classement par classe, carburant + énergie virtuelle, pneus, freins, dégâts, météo,
drapeaux, carte du circuit avec toutes les voitures, stratégie, chrono d'endurance.

## Installation
### Option A — LMU-Dash.exe (un seul fichier)
1. Dans LMU : Settings → Gameplay → **Enable Plugins**.
2. Double-clique sur `LMU-Dash.exe` : le navigateur s'ouvre sur http://localhost:8765.
3. Glisse la page sur ton 2e écran, F11.

Le .exe doit être construit **sur Windows** (impossible depuis Linux) :
- soit `build_exe.bat` (Python 3.10+ installé) → `dist\LMU-Dash.exe` ;
- soit GitHub : onglet *Actions → Release → Run workflow* (construit et teste l'exe, puis télécharge l'artefact).
  Les versions officielles sont publiées automatiquement dans *Releases* à chaque tag `vX.Y.Z`.
Windows Defender / un antivirus peut râler sur un .exe PyInstaller non signé : c'est un faux positif classique.

### Option B — avec Python
`lancer.bat` (ou `python server.py`). `lancer_demo.bat` = données simulées pour tester sans le jeu.

Options : `--demo`, `--demo-speed 25`, `--host 0.0.0.0` (tablette/2e PC : `http://IP_DU_PC:8765`),
`--port`, `--no-browser`, `--data-dir`.

## Stratégie
Ressource limitante (carburant / énergie virtuelle / pneus), prochain arrêt, nombre d'arrêts pour finir,
carburant **et énergie** à ajouter, économie suggérée pour éviter un arrêt.
- Les tours sous Safety Car / FCY ne comptent pas dans la conso ni l'usure.
- **Temps perdu aux stands mesuré automatiquement** (tour d'entrée + tour de sortie − 2 tours de référence,
  moyenne des 3 derniers arrêts) ; avant le premier arrêt, l'estimation des réglages est utilisée.
- Course au temps : on finit au premier passage de ligne après la fin du chrono (tour de plus pris en compte).
- Seuil « pneu fini » réglable, global ou par gomme (ex. `Soft=30, Hard=22`).

## Alertes
Bandeau + halo rouge pour les alertes critiques, bips optionnels (🔔 en haut à droite ; clique une fois sur la
page pour que le navigateur autorise le son) : carburant/énergie bas, surchauffe, pneus finis ou crevés,
BOX, drapeaux/Safety car/rouge, dégâts, pénalité, pluie, limites de relais/pilote. Chaque alerte se coupe dans ⚙.

## Endurance (🏁)
Pilote actuel, chrono du relais, temps cumulé par pilote (avec limite réglable), tableau des relais,
derniers tours, export CSV tours/relais. Le pilote est détecté par le jeu à l'arrêt aux stands.

## Drapeaux
Une seule logique côté serveur (`flags.py`) alimente la bannière, la carte et les alertes : FCY / Safety car avec son
état (stands fermés/ouverts, dernier tour), jaune local **dans ton secteur / le prochain / ailleurs**, voiture à
l'arrêt devant toi (distance + secteur, entourée en jaune sur la carte), drapeau bleu, rouge. Le jeu ne dit pas si
`mSectorFlag[0]` est S1 ou S3 : le dashboard l'apprend tout seul en croisant jaune local et voiture à l'arrêt
(valeur mémorisée dans `settings.json`, clé `flagMap`).

## Records
Meilleur tour et meilleurs secteurs par circuit + voiture, toutes sessions confondues (`data/records.json`),
tour théorique, affichés dans « Course & chronos » et dans 🏁. Seuls les tours propres comptent (pas de stand,
pas neutralisé, pas invalidé).

## Profils et cartes partagées
- **Profils (👤)** : chaque joueur a son dossier (`data/profiles/<nom>/`) avec ses réglages, records, état de course et
  archives. Changement de profil en un clic, ou `--profile Nom` au lancement. Un profil est local au PC (pas de mot
  de passe, rien n'est envoyé). Tes anciennes données sont reprises dans le profil « Joueur ».
- **Cartes et secteurs communs** : au démarrage, l'app télécharge depuis le dépôt GitHub (`--shared-repo owner/nom`,
  par défaut `N4ole/lmu-dash`, dossier `tracks/`) les circuits qui lui manquent : plus de tour de repérage.
  Chaque fichier est validé (360 points, secteurs cohérents) avant utilisation ; `--no-sync` désactive.
- **Contribuer** : quand une carte est complète avec ses secteurs, ⚙ prévient (liseré orange). « Exporter la carte
  actuelle », puis dépose le fichier via *Upload files* sur GitHub (Pull Request). Une vérification automatique
  (`.github/workflows`) contrôle le fichier avant fusion, puis l'index `tracks/index.json` se met à jour tout seul.

## Publier tes cartes sur GitHub (propriétaire du dépôt)
Première fois, dans le dossier du projet :
```
git init -b main
git add .
git commit -m "LMU Dash"
git remote add origin https://github.com/N4ole/lmu-dash.git
git push -u origin main
```
Ensuite, après avoir roulé pour mapper un circuit (carte à 100 % + secteurs appris) : double-clique `pousser_cartes.bat`
(ou `python tools/push_tracks.py`). Il valide les cartes complètes, les copie dans `tracks/`, met l'index à jour,
fait le commit et le push. `--data "D:\LMU\data"` si ton .exe est ailleurs, `--dry-run` pour voir sans rien faire,
`--force` pour remplacer une carte déjà publiée. Les autres joueurs les récupèrent automatiquement au lancement.

## Persistance
Tout est sauvegardé dans le dossier `data/` à côté du programme (ou `%APPDATA%\LMU-Dash`) :
réglages (`settings.json`), cartes de circuits apprises (`tracks/`), état de course (`state.json`, repris
automatiquement après un plantage s'il a moins de 30 min), archives CSV de chaque session (`sessions/`).
⚙ → « Nouvelle session » remet relais/conso à zéro après archivage.

## Notes
- La carte montre les 3 secteurs en couleur (S1 bleu, S2 violet, S3 vert) ; un secteur sous drapeau jaune clignote en jaune (tout le tracé en FCY / Safety car). Les limites de secteurs sont apprises dès le premier tour complet, puis mémorisées par circuit.
- Le tracé s'apprend avec la position de toutes les voitures ; ⟳ pivote, ⇋ miroir (mémorisé par circuit), ⌫ réapprend.
- Lecture mémoire basée sur pyLMUSharedMemory (MIT, dossier `pyLMUSharedMemory/`).
