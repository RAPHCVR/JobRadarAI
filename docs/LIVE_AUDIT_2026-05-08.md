# Live Audit 2026-05-08

Archive historique. L'etat courant et les extensions post-run sont centralises dans `docs/CURRENT_STATUS.md`; les commandes dans `docs/OPERATIONS.md`; les sources dans `docs/SOURCES.md`.

Audit realise le 2026-05-08, Europe/Paris. Le run manuel complet a ete relance apres retrait VDAB/SerpAPI du chemin actif, ajout de nouveaux ATS IA/data, ajout du link-check, du registre multi-run et des snapshots historiques.

## Verdict

- Etat runtime: OK pour crawl, exports, judge LLM, verification liens, audit et snapshot.
- Etat LLM: OK. `gpt-5.4-mini` a juge 200 offres en `balanced`, effort `medium` apres blocage reseau observe en `high`.
- Restrictivite: OK. Seuil local `min_score=35`, Business France VIE scanne large, tri final confie au judge LLM.
- P0: aucun blocage runtime detecte sur le dernier run.
- LinkedIn: ne pas activer en quotidien. Usage manuel/faible volume seulement.

## Run Frais

- Offres retenues: 2788.
- Sources OK: 43.
- Sources ignorees attendues: 2 (`adzuna`, `jobspy_api`).
- Erreurs runtime: 0.
- Remote/hybride detecte: 1303 offres, 46.7%.
- Salaire publie hors VIE: 79 offres, dont 64 >= 45000 EUR.
- Business France VIE retenus: 364, toutes avec indemnite mensuelle.
- Indemnites VIE observees: 2607 a 4427 EUR/mois.
- Shortlist LLM `balanced`: 200 offres jugees, 41 batchs, 17 `apply_now`, 57 `shortlist`, 29 `maybe`, 97 `skip`; 51 VIE inclus.
- Verification liens: 278 liens, 195 `direct_ok`, 62 `browser_required`, 21 `needs_review`, 0 `expired`.
- Queue multi-run: 127 items dedupes; start checks `{'unknown': 125, 'too_soon': 1, 'compatible': 1}`.
- Historique: 183 nouvelles offres, 163 disparues marquees `stale`, 0 `expired`.
- Registre multi-run: `runs/history/job_history.sqlite`.
- Snapshot: `runs/history/final-20260508-p2p3-complete`.

## Couverture Marche

- UK: 505.
- France: 447.
- Irlande: 350.
- Allemagne: 327.
- Belgique: 323.
- Remote Europe: 296.
- Singapour: 260.
- Pays-Bas: 189.
- Suisse: 60.
- Luxembourg: 31.

## Sources Critiques

- Business France VIE: OK, API officielle Mon Volontariat International.
- France Travail: OK via credentials locaux.
- Jooble: OK via cle locale.
- JobSpy Direct: OK via `uv run --isolated --no-project --with python-jobspy==1.1.82`, Indeed par defaut.
- Forem Open Data: OK sans cle.
- Actiris: OK sans cle.
- ATS directs: OK, 43 sources OK au total.
- OpenAI Ashby: OK apres timeout specifique a 90 s. Cause racine observee: feed officiel volumineux, environ 10.7 MB, reponse autour de 62 s lors du test direct.
- VDAB: mis de cote, acces public/partenaire non exploitable ici.
- SerpAPI: mis de cote, quota trop faible.

## Verification Liens

Le rapport `runs/latest/link_checks.md` classe:

- `direct_ok`: liens serveur directement exploitables.
- `browser_required`: agregateurs ou pages protegees/anti-bot a ouvrir manuellement avant candidature.
- `needs_review`: surtout France Travail HTTP 409 en fetch serveur; a verifier manuellement.

Aucun lien n'est classe `expired` ou `unreachable` dans le dernier run.

## Changements Appliques

- `config/sources.toml`: VDAB et SerpAPI restent desactives; ajout Cohere, ElevenLabs, Synthesia, Stability AI, Modal, Poolside; timeout OpenAI Ashby a 90 s.
- `src/jobradai/pipeline.py`: les sources optionnelles desactivees ne sont plus rapportees par defaut comme skips actifs.
- `src/jobradai/sources/ats.py`: override `timeout`/`retries` par feed ATS.
- `src/jobradai/link_check.py`: nouveau verificateur de liens.
- `src/jobradai/enrichment.py`: checks soft start/salaire/remote et brouillons RH.
- `src/jobradai/llm_judge.py`: schema `start_date_check`, `start_date_evidence` et logs de progression par batch.
- `src/jobradai/history.py`: registre multi-run avec carry-forward dedupe, statut actif/stale/expire, queue enrichie, messages RH, dashboard historique et digest.
- `src/jobradai/audit.py`: integration link-check, queue multi-run, start checks et P0/P1/P2 associes.
- `src/jobradai/snapshot.py`: snapshots historiques des exports.
- `src/jobradai/cli.py`: commandes `verify-links`, `sync-history`, `snapshot` et progression judge.
- `scripts/run_daily.ps1`: ajout link-check, sync historique, snapshot et `-JudgeTimeoutSeconds` dans le run complet.
- `scripts/run_link_check.ps1`, `scripts/sync_history.ps1` et `scripts/snapshot_latest.ps1`: scripts directs.
- Tests: ajout couverture link-check, snapshots, optional sources desactivees, timeout ATS par feed, enrichment start/salaire/remote et historique.

## P0 A PN

- P0: aucun blocage runtime detecte.
- P1: ouvrir manuellement les 62 liens `browser_required` avant candidature.
- P1: verifier salaire et remote quand l'information n'est pas publiee ou quand le LLM marque `unknown`/`weak`.
- P2: utiliser `start_date_check` comme signal soft et confirmer avec RH les dates `unknown`/`too_soon`; ne pas auto-skipper.
- P2: garder les candidatures/messages manuels; aucune action LinkedIn automatique de masse.
- P3: JobSpy API Docker uniquement si besoin d'un service permanent.
- PN: VDAB direct et SerpAPI sont hors scope actif.
