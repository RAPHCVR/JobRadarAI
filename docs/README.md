# Documentation

Ce dossier separe les documents vivants des preuves historiques. La source de verite doit rester courte: si une information change avec les runs, elle va dans `CURRENT_STATUS.md`; si elle explique comment operer le systeme, elle va dans `OPERATIONS.md`; si elle concerne la couverture des sources, elle va dans `SOURCES.md`.

## Documents Vivants

| Document | Role |
|---|---|
| [CURRENT_STATUS.md](CURRENT_STATUS.md) | Etat courant, dernier full run valide, sources actives, P0-PN et limites restantes |
| [OPERATIONS.md](OPERATIONS.md) | Commandes PowerShell, run complet, judge, link-check, history sync, snapshots et scheduler |
| [SOURCES.md](SOURCES.md) | Registre des sources actives, bloquees, hors scope et extensions candidates |
| [MARKET_STRATEGY.md](MARKET_STRATEGY.md) | Priorites pays, titres, signaux forts/faibles et contraintes personnelles |
| [BEST_PRACTICE_AUDIT.md](BEST_PRACTICE_AUDIT.md) | Audit systeme, garde-fous, architecture et reste a faire |
| [WEB_PLATFORM.md](WEB_PLATFORM.md) | Interface web privee, Docker, Kubernetes, secrets et synchronisation des runs |

## Archives

Les anciens audits dates strictement remplaces ne sont plus gardes comme documents Markdown suivis: ils restent recuperables dans l'historique Git et les snapshots locaux sous `runs/history/`. Si un futur audit apporte une preuve utile, garder au maximum une archive recente, clairement marquee non canonique, et reporter l'etat courant dans `CURRENT_STATUS.md`.

## Regles De Maintenance

- Ne pas dupliquer les compteurs de run dans plusieurs fichiers vivants sans mentionner la date exacte.
- Ne pas presenter une source testee mais non retenue comme active.
- Mettre les decisions de sources dans `SOURCES.md`, pas dans des notes eparses.
- Mettre les commandes dans `OPERATIONS.md`, pas dans plusieurs fichiers concurrents.
- Garder le `README.md` racine comme point d'entree court.
