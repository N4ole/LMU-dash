# Contribuer à LMU Dash

Merci de ton intérêt ! Il y a deux façons principales de contribuer :

1. **Partager une carte de circuit** : aucune compétence technique requise, c'est la contribution la plus utile.
2. **Améliorer le code** : corrections, nouvelles fonctions, documentation.

Avant tout, lis le [code de conduite](CODE_OF_CONDUCT.md). Pour une question ou une idée, passe par les
[Discussions](https://github.com/N4ole/LMU-dash/discussions) ; pour un bug, ouvre une
[issue](https://github.com/N4ole/LMU-dash/issues/new/choose). Une faille de sécurité se signale en privé
(voir [SECURITY.md](SECURITY.md)).

---

## 🗺️ Partager une carte de circuit

LMU Dash apprend le tracé et les secteurs d'un circuit en roulant. Une fois partagée, la carte est
téléchargée automatiquement par tous les autres joueurs : plus besoin de tour de repérage.

1. Roule sur le circuit jusqu'à ce que la carte soit **complète à 100 %** et que les **secteurs** soient appris
   (le bouton ⚙ s'entoure d'orange quand une carte est prête à être partagée).
2. ⚙ Réglages → **« Exporter la carte actuelle »** : tu obtiens un fichier `Nom_du_circuit.json`.
   Ne le modifie pas à la main.
3. Sur GitHub, ouvre le dossier [`tracks/`](https://github.com/N4ole/LMU-dash/tree/main/tracks) →
   **Add file → Upload files**, dépose le fichier, puis **Propose changes** et **Create pull request**.
   (Le lien « GitHub → Upload files » dans ⚙ t'y emmène directement.)
4. Dans la PR, tu peux utiliser le [modèle « carte »](.github/PULL_REQUEST_TEMPLATE/carte.md).

Ensuite, automatiquement :

- la PR reçoit le label **cartes** ;
- la **validation** vérifie le fichier (format, 360 points, secteurs, nom, boucle plausible, pas de doublon) ;
- un **commentaire d'aperçu** affiche le tracé dessiné et le résultat de la validation ;
- après fusion, l'index des cartes (`tracks/index.json`) est mis à jour par une PR automatique.

Règles : une PR de carte ne doit contenir **que** des fichiers `tracks/*.json` (pas `index.json`, il est généré).

---

## 💻 Contribuer au code

### Principes

- **Aucune dépendance à l'exécution** : l'application n'utilise que la bibliothèque standard Python (3.10+).
  Les outils de développement (pytest, ruff, pre-commit) sont dans `requirements-dev.txt`.
- **Compatibilité des sauvegardes** : les fichiers de `data/` (réglages, profils, cartes, records, état de course)
  des versions précédentes doivent rester lisibles. Si un changement les casse, explique-le dans la PR.
- **Français** pour l'interface, les messages et la documentation ; anglais pour les noms de workflows/jobs CI.

### Installation

```bash
git clone https://github.com/N4ole/LMU-dash.git
cd LMU-dash
python -m venv .venv
.venv\Scripts\activate            # Windows (Linux/macOS : source .venv/bin/activate)
python -m pip install -r requirements-dev.txt
pre-commit install                # vérifie ruff et les cartes à chaque commit
```

### Lancer

```bash
python server.py --demo           # données simulées, sans le jeu (fonctionne aussi sous Linux/macOS)
python server.py --demo --demo-speed 20
python server.py                  # avec Le Mans Ultimate (Windows)
```

### Vérifier

```bash
ruff check .                      # lint
ruff format .                     # mise en forme
python -m pytest                  # tests
python tools/smoke_test.py        # démarrage du serveur en --demo
python tools/validate_tracks.py   # cartes du dossier tracks/
```

La CI (GitHub Actions) relance tout cela sur Windows et Linux, Python 3.10, 3.12 et 3.13.

### Organisation du code

| Fichier | Rôle |
|---|---|
| `server.py` | serveur HTTP + SSE, API, moteur (assemble tout) |
| `readers.py` | lecture de la mémoire partagée du jeu, et mode démo |
| `strategy.py` | conso, usure, temps perdu aux stands, plan d'arrêts |
| `endurance.py` | relais, pilotes, historique des tours, CSV |
| `flags.py` | drapeaux, FCY, voiture arrêtée devant |
| `store.py` | persistance : réglages, cartes, profils, records, état de course |
| `shared.py` | téléchargement des cartes partagées depuis ce dépôt |
| `updates.py`, `version.py` | version et indicateur « nouvelle version disponible » |
| `web/index.html` | toute l'interface (une seule page, sans framework) |
| `tools/` | validation des cartes, index, aperçu SVG, build de l'exe |
| `pyLMUSharedMemory/` | bibliothèque vendorée (MIT) : ne pas modifier |

### Proposer une modification

1. Crée une branche depuis `main` (`fix/...`, `feat/...`, `docs/...`).
2. Des commits clairs, en français, à l'impératif (« Corriger le calcul du relais »).
3. Ouvre une Pull Request et remplis la checklist. La branche `main` est protégée : tout passe par une PR,
   la CI doit être verte, et l'historique reste linéaire (fusion « Squash » ou « Rebase »).
4. Ajoute une ligne dans [CHANGELOG.md](CHANGELOG.md) (section « Non publié ») si le changement est visible.

### Publier une version (mainteneur)

1. Mettre à jour `VERSION` dans `version.py` et déplacer « Non publié » vers la nouvelle version dans `CHANGELOG.md`.
2. Fusionner la PR, puis pousser le tag : `git tag v1.2.3 && git push origin v1.2.3`.
3. Le workflow **Release** construit `LMU-Dash.exe`, le teste, l'atteste et publie la release.
