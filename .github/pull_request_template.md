<!--
Merci pour ta contribution !
Tu proposes seulement une carte de circuit ? Remplace tout ce texte par le modèle « carte » :
https://github.com/N4ole/LMU-dash/blob/main/.github/PULL_REQUEST_TEMPLATE/carte.md
(ou coche juste la section « Carte » plus bas).
-->

## Ce que change cette PR

<!-- Le quoi et le pourquoi, en quelques lignes. Lien vers l'issue : « Corrige #123 ». -->

## Type

- [ ] 🐛 Correction de bug
- [ ] ✨ Amélioration / nouvelle fonction
- [ ] 🗺️ Carte de circuit
- [ ] 📚 Documentation
- [ ] 🔧 CI / outillage

## Checklist

- [ ] J'ai lu [CONTRIBUTING.md](https://github.com/N4ole/LMU-dash/blob/main/CONTRIBUTING.md).
- [ ] `ruff check .` et `ruff format --check .` passent (ou `pre-commit run --all-files`).
- [ ] `python -m pytest` passe, et j'ai ajouté des tests si je change la logique.
- [ ] L'application ne dépend toujours que de la bibliothèque standard Python.
- [ ] J'ai testé en `--demo` (et dans le jeu si le changement touche la lecture des données).
- [ ] Les anciennes sauvegardes (`data/`) restent lisibles, ou j'explique pourquoi ci-dessous.
- [ ] J'ai ajouté une ligne dans `CHANGELOG.md` (section « Non publié ») si c'est visible par l'utilisateur.

## Carte (seulement pour une PR de carte)

- [ ] Fichier exporté depuis LMU Dash (⚙ → « Exporter la carte actuelle »), sans modification à la main.
- [ ] Carte complète à 100 % et secteurs appris.

## Captures d'écran

<!-- Si l'interface change. -->
