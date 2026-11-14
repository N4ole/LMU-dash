# Politique de sécurité

## Versions prises en charge

Seule la **dernière version publiée** (onglet [Releases](https://github.com/N4ole/LMU-dash/releases)) reçoit des
correctifs de sécurité. LMU Dash t'indique dans l'interface quand une nouvelle version est disponible.

## Signaler une faille

**N'ouvre pas d'issue publique** pour une faille de sécurité.

Utilise le signalement privé de GitHub :
**onglet [Security](https://github.com/N4ole/LMU-dash/security) → « Report a vulnerability »**
(lien direct : <https://github.com/N4ole/LMU-dash/security/advisories/new>).

Merci d'indiquer :
- la version de LMU Dash (affichée dans ⚙ Réglages, ou `LMU-Dash.exe --version`) ;
- comment reproduire le problème (requête HTTP, fichier de carte, options de lancement...) ;
- l'impact que tu envisages.

Tu recevras une première réponse sous 7 jours. Le correctif est préparé dans un avis de sécurité privé,
publié avec la nouvelle version ; tu seras crédité si tu le souhaites.

## Périmètre

LMU Dash est un serveur web **local**. Points particulièrement intéressants :

- l'API HTTP (`server.py`) : par défaut elle n'écoute que sur `127.0.0.1` et refuse les en-têtes `Host`
  étrangers (DNS rebinding) et les `POST` d'une autre origine ;
- avec `--host 0.0.0.0`, le dashboard est accessible **sans mot de passe** à tout ton réseau local :
  c'est voulu (tablette, 2ᵉ PC), à n'utiliser que sur un réseau de confiance ;
- les cartes partagées téléchargées depuis ce dépôt (`shared.py`, `store.validate_track`) : elles sont
  validées avant usage et ne servent qu'à dessiner le tracé ;
- la vérification de mise à jour (`updates.py`) : lecture seule de l'API publique GitHub Releases ;
- les workflows GitHub Actions (PR de cartes venant de forks).

Hors périmètre : le jeu Le Mans Ultimate lui-même et sa mémoire partagée, les faux positifs d'antivirus
sur l'exécutable PyInstaller non signé (vérifie plutôt son attestation :
`gh attestation verify LMU-Dash.exe --repo N4ole/LMU-dash`).
