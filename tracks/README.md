# Cartes partagées

Un fichier par circuit (`<nom_du_circuit>.json`) : tracé en 360 points + limites des secteurs S1/S2/S3.
LMU Dash les télécharge automatiquement : plus besoin de refaire un tour de repérage.

**Contribuer** : dans LMU Dash, ⚙ → « Exporter la carte actuelle » (quand la carte est complète à 100 % et
que les secteurs sont appris), puis *Add file → Upload files* sur ce dossier et ouvre la Pull Request.

Automatiquement, la PR est étiquetée **cartes**, le fichier est validé, et un commentaire affiche un aperçu
du tracé. Seuls les fichiers `tracks/*.json` sont acceptés ; `index.json` est généré, ne le modifie pas.
Détails : [CONTRIBUTING.md](../CONTRIBUTING.md#️-partager-une-carte-de-circuit).
