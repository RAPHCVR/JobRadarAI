# Audit Best Practice

Derniere mise a jour: **2026-05-08**.

## Verdict

Le bon design pour ce besoin est un radar local multi-sources avec priorite aux sources propres:

1. APIs officielles et ATS publics.
2. Agregateurs a cle seulement quand ils couvrent vraiment les marches cibles.
3. Scrapers controles en fallback.
4. LinkedIn en lecture prudente ou brouillons humains, jamais en actions automatiques de masse.

Le projet suit ce modele. Il est utilisable en routine manuelle ou quotidienne desactivee/reactivable, avec exports HTML/Markdown/CSV/JSON/SQLite, logs, audit marche/VIE/langues, judge LLM, verification liens, registre multi-run et snapshots historiques.

## Etat Runtime Valide

Dernier run complet valide: **2026-05-08 18:49 Europe/Paris**.

- 2788 offres retenues.
- 43 sources OK.
- 2 skips attendus: Adzuna sans credentials, JobSpy API local injoignable.
- 0 erreur source.
- 364 VIE retenus.
- 200 offres jugees par le LLM en `balanced`.
- 278 liens verifies.
- Snapshot: `runs/history/final-20260508-p2p3-complete`.
- Registre multi-run: `runs/history/job_history.sqlite`.
- Queue dedupee: `runs/latest/application_queue.md`, 127 items sur le dernier run.
- Historique: 183 nouvelles offres, 163 disparues marquees `stale`, 0 `expired`.
- P0: aucun blocage runtime detecte.

## Repos Et Systemes Audites

- `speedyapply/JobSpy`: meilleure brique open-source pratique pour Indeed/Glassdoor/LinkedIn/Google/ZipRecruiter; utilisee en mode direct via `uv`, sans `.venv` projet. LinkedIn reste desactive par defaut.
- `rainmanjam/jobspy-api`: option Docker/FastAPI si on veut un service local permanent avec API key, cache, rate limiting et proxy. Pas necessaire ici tant que le mode direct uv suffit.
- `stickerdaniel/linkedin-mcp-server`: MCP LinkedIn mature pour profils, jobs et messages, mais avec risque ToS et absence de rate limit fort. Non integre volontairement.
- `ChanMeng666/server-google-jobs`: MCP Google Jobs via SerpAPI. Mis de cote ici car le quota SerpAPI est trop faible pour la routine.
- Petits scrapers ATS publics Greenhouse/Lever/Ashby: aucun projet public trouve ne justifie de remplacer le code local. La bonne approche reste de garder des parsers simples et d'ajouter des boards verifies.

## Sources Officielles Et ATS

- France Travail: actif et revalide en live, meilleur socle France.
- Business France VIE: actif sans cle via l'API officielle Mon Volontariat International.
- Le Forem Open Data: actif sans cle via ODWB/Opendatasoft; apporte Wallonie-Bruxelles et une couverture partielle VDAB traduite.
- Actiris: actif sans cle via endpoint JSON du site officiel.
- Jooble: actif, bon complement multi-pays.
- Greenhouse, Lever, Ashby: actifs via endpoints publics, meilleur ratio fiabilite/volume pour entreprises tech/IA.
- SmartRecruiters, Workable, Recruitee, Personio XML: supportes par le code pour ajouts ponctuels.
- Cohere, ElevenLabs, Synthesia, Stability AI, Modal et Poolside: ajoutes apres verification endpoint live.
- OpenAI Ashby: actif avec timeout specifique a 90 s, car le feed officiel est volumineux.
- SerpAPI Google Jobs: desactive volontairement; quota trop faible.
- VDAB: desactive volontairement; acces public/partenaire bloque, pas une action restante.
- Adzuna: optionnel; moins prioritaire que les sources officielles/ATS deja actives.
- LLM judge OpenAI-compatible: implemente avec `gpt-5.4-mini`, effort `high`, batchs de 5 pour eviter les timeouts proxy.

## Garde-Fous Mis En Place

- Credentials uniquement dans `config/.env`, ignore par git.
- Pas de `.venv` projet; JobSpy tourne via `uv run --isolated --no-project`.
- Dedupe soft/loose avec priorite aux sources officielles/ATS.
- Filtrage marche: France, Irlande, Suisse, Belgique, Singapour, Pays-Bas, Luxembourg, UK, Allemagne, Remote Europe.
- Correction de geographie pour eviter les faux positifs type `US-CA-Dublin`.
- Penalites titre pour roles non coeur: product/program manager, account, business development, customer success, marketing, recruiting, solution/support engineering.
- Penalites de niveau pour profil junior/new-grad: senior, lead, principal, architect, VP, et exigences 3+/5+ ans.
- Requetes sources FR/EN: `Ingénieur IA`, `Ingénieur Data`, `Machine Learning Engineer`, `Data Scientist`.
- JobSpy Direct ne supprime plus les roles junior/graduate; seulement les stages/alternances non cibles.
- Business France VIE scanne largement l'API officielle paginee; le tri metier se fait par score + LLM.
- Forem et Actiris appliquent un filtre local minimal apres recherche source pour garder les signaux data/IA/LLM/research.
- Tokenisation scoring multi-mots: `distributed systems`, `data quality`, `GitHub Actions`, `Azure DevOps`, etc.
- Seuil local a 35 pour garder un corpus de revue large; shortlist finale par judge LLM et priorites explicites.
- Jobicy rate-limit 429 traite en best-effort.
- `runs/latest/audit.md` verifie P0/P1/P2, langues, VIE, visa, salaire, remote et liens.
- L'audit remonte explicitement un P0/P1 si le corpus est vide, si `sources.json` est absent/illisible, si la shortlist est stale, ou si le link-check manque.
- Les timeouts socket du judge LLM sont convertis en erreur controlee pour permettre fallbacks endpoint et retries.
- Le script quotidien retente le judge, verifie les liens, regenere l'audit et snapshotte le resultat.
- Le script quotidien synchronise un ledger multi-run dedupe entre les liens et l'audit.
- `runs/latest/jobs.sqlite` reste un snapshot du run courant; les offres pertinentes anciennes sont conservees dans `runs/history/job_history.sqlite` avec `first_seen`, `last_seen`, `seen_count`, `absent_count`, `presence_status`, dernier statut lien et derniere priorite LLM.
- La queue expose `start_date_check = compatible | too_soon | unknown` comme signal soft, plus `application_messages.md`, `history_dashboard.md` et `weekly_digest.md`.
- Le judge LLM logge la progression par batch et `run_daily.ps1` expose `-JudgeTimeoutSeconds`; pour un run ponctuel large, `JudgeLimit 200` + `JudgeEffort medium` est plus stable que `high` sur le gateway actuel.
- Les exports CSV neutralisent les formules Excel et le dashboard n'accepte que des liens HTTP(S).
- Les erreurs HTTP redigent secrets en query/path/body.
- LinkedIn non automatise en masse.

## Reste A Faire

- `P0`: aucun blocage runtime detecte sur le dernier run complet.
- `P1`: verifier manuellement les 62 liens `browser_required` avant candidature, surtout Indeed/JobSpy et pages protegees Ashby.
- `P1`: verifier manuellement salaire et remote quand l'offre ne publie pas l'information ou quand le LLM marque `unknown`/`weak`.
- `P2`: confirmer avec RH les dates de demarrage `unknown`/`too_soon`; ne pas filtrer automatiquement sur ce signal.
- `P2`: garder les candidatures/messages en validation humaine; aucune action LinkedIn automatique de masse.
- `P3`: demarrer `rainmanjam/jobspy-api` en Docker seulement si tu veux une API JobSpy permanente au lieu du mode uv direct.
- `PN`: VDAB direct et SerpAPI ne sont plus des pistes actives. On les garde hors scope tant que l'acces VDAB reste bloque et tant que le quota SerpAPI reste trop faible.
