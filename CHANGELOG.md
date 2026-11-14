# Journal des modifications

Toutes les évolutions notables de LMU Dash sont listées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le projet respecte le
[versionnage sémantique](https://semver.org/lang/fr/). Les notes détaillées de chaque version (avec la liste
des PR) sont générées automatiquement dans les [Releases](https://github.com/N4ole/LMU-dash/releases).

## [Non publié]

Première version publique, prévue en **1.0.0**.

### Ajouté

- Dashboard second écran : vitesse, rapport, régime, courbes gaz/frein, températures, aides, chronos et delta,
  écarts, classement par classe, carburant et énergie virtuelle, pneus, freins, dégâts, météo, drapeaux.
- Carte du circuit apprise automatiquement avec toutes les voitures et les secteurs S1/S2/S3.
- Stratégie : ressource limitante, prochain arrêt, nombre d'arrêts, carburant et énergie à ajouter,
  économie suggérée ; tours sous SC/FCY exclus, temps perdu aux stands mesuré automatiquement.
- Endurance : relais, temps par pilote avec limites, historique des tours, export CSV.
- Drapeaux : FCY / Safety car, jaunes locaux par secteur (correspondance apprise), voiture arrêtée devant.
- Records par circuit et voiture, tour théorique.
- Profils joueurs et cartes partagées via ce dépôt GitHub.
- Numéro de version affiché dans ⚙ Réglages, `--version` et `GET /api/version`.
- Indicateur discret « nouvelle version disponible » (GitHub Releases, une fois par jour, désactivé par `--no-sync`).
- Exécutable Windows publié automatiquement à chaque version, avec SHA256 et attestation de provenance.

### Sécurité

- Le serveur local refuse les en-têtes `Host` étrangers (protection contre le DNS rebinding) et les `POST`
  venant d'une autre origine.
- Corps de requête mieux contrôlés (taille, longueur invalide, encodage chunked), pas de listing de dossiers,
  nombre de connexions de flux limité.

[Non publié]: https://github.com/N4ole/LMU-dash/commits/main
