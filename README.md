# JobRadarAI

Radar local pour trouver, filtrer et classer des offres **data / IA / LLM orchestration / recherche appliquee** sur France, Europe elargie, Irlande, Suisse, Belgique, Allemagne, Nordics, UK et Singapour.

Le projet est volontairement local et humain-dans-la-boucle:

- sources propres d'abord: APIs officielles, APIs publiques, ATS directs;
- scrapers seulement en fallback controle;
- pas de bulk connect, bulk message ou auto-apply LinkedIn;
- scoring explicable par fit technique, marche, langue, visa, salaire/devise normalisee, remote/localisation, dates, VIE, niveau et annees d'experience requises;
- judge LLM optionnel pour trier la shortlist finale, avec score combine LLM-majoritaire (`40%` local, `60%` LLM);
- exports HTML, Markdown, CSV, JSON et SQLite;
- ledger multi-run pour conserver les offres pertinentes, detecter les nouvelles, les retours, les stale et les expired.

## Documentation Canonique

- Etat courant et verdict P0-PN: [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md).
- Commandes, run quotidien, judge, link-check, historique et scheduler: [docs/OPERATIONS.md](docs/OPERATIONS.md).
- Sources actives, sources bloquees, ATS et backlog d'extensions: [docs/SOURCES.md](docs/SOURCES.md).
- Strategie marche, titres et signaux de scoring: [docs/MARKET_STRATEGY.md](docs/MARKET_STRATEGY.md).
- Audit best-practice et garde-fous systeme: [docs/BEST_PRACTICE_AUDIT.md](docs/BEST_PRACTICE_AUDIT.md).
- Plateforme web hebergee Kubernetes: [docs/WEB_PLATFORM.md](docs/WEB_PLATFORM.md).
- Index complet des docs: [docs/README.md](docs/README.md).

## Etat Court

Dernier full run valide documente: **2026-05-10 19:26 Europe/Paris**. Derniere regeneration queue/audit/liens: **2026-05-11 17:31 Europe/Paris**, sous `20260511-170036-hard-audit-residual7-final`, apres onze augments LLM cibles sur les VIE, la watch non jugee, les poches rescue non-VIE et les residuels manuels/entreprises a risque de faux negatif.

- 5493 offres retenues.
- 58 sources OK, 2 sources ignorees attendues, 0 erreur.
- 509 missions VIE Business France.
- 2733 jugements LLM exploites: 1200 en base `wide` + 1533 augments cibles, batch 10/concurrence 1 sur la base large; les passes cibles gardent fallback interdit.
- Quality gate LLM stricte: 0 `fallback_default` / 2733; transport `auto` via OpenAI SDK + `base_url` codexlb, fallback REST controle; la derniere passe residual7 a utilise `raw`/effort `low` pour eviter un blocage SDK.
- 1318 liens verifies en mode priority-aware, incluant les augments.
- 300 items dans la queue multi-run dedupee: 86 `apply_now`, 214 `shortlist`, triee par priorite LLM puis `COALESCE(last_combined_score, score)`.
- 170 missions dans `vie_priority_queue.md/json`, toutes jugees LLM: 2 `apply_now`, 50 `shortlist`, 118 `maybe`.
- 0 offre restante dans `unjudged_watch_queue.md/json`: les 79 signaux IA/data/software detectes ont ete juges dans l'augment cible.
- 0 VIE-like non juge restant; 2760 offres non jugees LLM restent dans le corpus. Apres residual7, il ne reste pas de bucket actionnable A/B detecte; le residuel strict est **271 weak-signal** et **2489 low-signal/noise**, pas une certitude absolue que chaque item est du bruit.
- Tache Windows `JobRadarAI-Daily`: **desactivee**.

Le full run inclut les extensions ajoutees pendant l'audit: Bundesagentur Jobsuche, SmartRecruiters durci, Delivery Hero filtre, correction du matching marche par alias bornes, JobTechDev Sweden, NAV Arbeidsplassen Norway, EURAXESS, Doctorat.gouv.fr, AcademicTransfer, WeWorkRemotely RSS, SwissDevJobs, GermanTechJobs, champs structures `deadline`/`language_check`/`remote_location_validity`/`required_years`/`experience_check`/salaire annualise EUR, extension graduate/early-career/doctorat industriel-CIFRE, et extension opportuniste Autriche/Nordics/Espagne/Portugal/Estonie/Pologne/Tchequie.

Extension titres validee par full run: les requetes couvrent aussi `ML Engineer`, `AI/ML Engineer`, `ML Ops Engineer`, `AI Research Engineer`, `LLM Research Engineer`, `LLM Application Engineer`, `Analytics Engineer`, et une veille niche `Applied Scientist`/interpretability/explainability/AI safety/knowledge graph/semantic web. Le premier run large confirme que ces ajouts remontent des roles pertinents sans explosion de bruit dans la queue.

## Lancer

Depuis PowerShell:

```powershell
cd C:\Users\Raphael\Documents\JobRadarAI
$env:PYTHONPATH = "src"
uv run --no-project --with-editable . -- python -m jobradai run --max-per-source 1200
```

Run complet conseille quand tu veux une shortlist finale exploitable:

```powershell
.\scripts\run_daily.ps1 -Judge -JudgeRequired -JudgeLimit 1200 -JudgeBatchSize 10 -JudgeConcurrency 1 -JudgeSelectionMode wide -JudgeEffort medium -JudgeTransport auto
```

Run tres large ponctuel avant une grosse session candidature:

```powershell
.\scripts\run_daily.ps1 -Judge -JudgeRequired -JudgeLimit 2000 -JudgeBatchSize 10 -JudgeConcurrency 1 -JudgeSelectionMode wide -JudgeEffort medium -JudgeTransport auto -JudgeTimeoutSeconds 600
```

## Tester

```powershell
cd C:\Users\Raphael\Documents\JobRadarAI
$env:PYTHONPATH = "src"
uv run --no-project --with-editable . -- python -m unittest discover -s tests
```

## Interface Web

Interface privee mobile/desktop: `https://jobs.raphcvr.me` une fois deployee.

Local:

```powershell
cd C:\Users\Raphael\Documents\JobRadarAI\web
npm install
npm run build
cd ..
.\scripts\run_web.ps1
```

Kubernetes:

```powershell
docker build -t ghcr.io/raphcvr/jobradarai-web:latest .
docker push ghcr.io/raphcvr/jobradarai-web:latest
.\scripts\deploy_web_k8s.ps1
.\scripts\sync_web_data.ps1
```

Les donnees de runs, CV et secrets ne sont pas commites ni bakees dans l'image. Voir [docs/WEB_PLATFORM.md](docs/WEB_PLATFORM.md).

Pour rapatrier les statuts/notes saisis dans l'interface:

```powershell
.\scripts\pull_web_state.ps1
```

## Fichiers Importants

- `config/profile.toml`: profil cible, contraintes, titres et poids de scoring.
- `config/markets.toml`: scoring marche, praticite, langue, visa et salaire.
- `config/sources.toml`: sources, requetes, ATS directs et limites de crawl.
- `config/secrets.example.env`: modele de credentials; copier en `config/.env` si besoin.
- `scripts/run_daily.ps1`: orchestration run + judge + link-check + historique + audit + snapshot.
- `runs/latest/`: exports du dernier run, ignore par git.
- `runs/history/job_history.sqlite`: ledger multi-run, ignore par git.
- `runs/latest/vie_priority_queue.md`: lane VIE separee pour ne pas comparer une indemnite VIE a un brut CDI.
- `runs/latest/unjudged_watch_queue.md`: lane de surveillance pour les offres non jugees LLM mais potentiellement interessantes; vide sur l'etat courant apres augment cible.

Les credentials restent dans `config/.env` ou variables d'environnement, jamais dans le code.

## Sources

Sources propres actives: Business France VIE, France Travail, Forem, Actiris, Bundesagentur Jobsuche, JobTechDev Sweden, NAV Arbeidsplassen Norway, EURAXESS, Doctorat.gouv.fr, AcademicTransfer, Jooble, APIs remote publiques, WeWorkRemotely RSS, SwissDevJobs, GermanTechJobs, ATS directs Greenhouse/Lever/Ashby/SmartRecruiters, requetes opportunistes CIFRE/industrial PhD sur les moteurs existants, et JobSpy Direct sur Indeed en fallback controle.

Sources volontairement hors routine: LinkedIn, VDAB direct, SerpAPI Google Jobs, Glassdoor via JobSpy, ANRT sans compte, ABG, Campus France Doctorat, DAAD/PhDGermany, EURES API, JobsIreland API, Veolia SmartRecruiters large. Welcome to the Jungle est documente comme extension P2 possible via sitemaps + JSON-LD, pas via recherche interne.

Voir [docs/SOURCES.md](docs/SOURCES.md) pour le detail.

## Garde-Fous

- Pas d'action LinkedIn automatisee en masse.
- Pas de secrets dans le repo.
- Les sources officielles/ATS priment sur les scrapers.
- Les exports gardent les raisons de scoring.
- `start_date_check` reste un signal soft: confirmer avec RH, ne pas auto-skipper.
- Les VIE sont exposees dans une lane dediee; la queue principale reste CDI/VIE mixte mais n'est plus le seul endroit ou regarder les VIE.
- Les offres non jugees LLM mais a fort signal IA/data/software sont exposees dans `unjudged_watch_queue.md`; sur l'etat courant cette lane est vide, mais elle evite qu'un futur `JudgeLimit` recree un angle mort silencieux.
- `deadline`, `language_check`, `remote_location_validity`, `required_years`, `experience_check` et la normalisation devise/salaire sont des signaux de priorisation, pas des hard filters aveugles; `experience_check=too_senior` deterministe sort de la queue actionnable sauf override LLM `junior_ok` ou `stretch`.
- Les offres PhD/doctorat sont opportunistes: un CIFRE/industrial PhD data/AI/R&D peut etre shortlist, mais un doctorat academique sans entreprise, salaire ou fit technique clair reste a verifier ou low-fit.
- Le judge LLM passe par l'OpenAI SDK en mode `auto` quand disponible, avec `base_url` custom codexlb, sortie JSON Schema stricte, fallback REST controle et quality gate: un run avec trop de `fallback_default` echoue au lieu de polluer la queue.
- Le judge LLM aide a prioriser, mais ne remplace pas la verification humaine avant candidature.
