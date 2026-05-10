# Etat Courant

Derniere validation run: **2026-05-10 20:00 Europe/Paris**, full rebaseline manuel `20260510-173933` conserve, puis regeneration queue/history/audit apres correctif VIE.

Derniere validation plateforme web: **2026-05-10 20:07 Europe/Paris**, image `ghcr.io/raphcvr/jobradarai-web:sha-5ca3919` deployee et `runs/latest` synchronise sur Kubernetes sous `https://jobs.raphcvr.me`.

Commande utilisee pour la base large:

```powershell
.\scripts\run_daily.ps1 `
  -Judge -JudgeRequired -JudgeLimit 1200 -JudgeBatchSize 10 -JudgeConcurrency 1 `
  -JudgeSelectionMode wide -JudgeEffort medium -JudgeTransport auto `
  -JudgeMaxFallbackRatio 0 -JudgeMaxAttempts 1 -JudgeTimeoutSeconds 900 `
  -LinkCheckLimit 240 -LinkCheckTimeoutSeconds 10 -LinkCheckWorkers 12 `
  -HistoryRecheckStaleLimit 80
```

## Resultat

- Offres retenues: **5493**.
- Sources OK: **58**.
- Sources ignorees attendues: **2**.
- Erreurs source: **0**.
- Remote/hybride detecte: **2180** offres, soit **39.7%**.
- Salaire publie hors VIE: **899** offres, dont **793** >= 45k EUR/an.
- Deadlines publiees: **967**.
- Salaires normalises EUR/an: **893**.
- Annees d'experience extraites: **1285**.
- VIE Business France retenus: **509**, indemnite mensuelle observee **2610** a **4427** EUR.
- Judge LLM: **1200** offres jugees en mode `wide`, effort `medium`, batch 10, concurrence 1.
- Transport LLM: `auto` via OpenAI SDK quand possible, `base_url=https://codex.raphcvr.me/v1`.
- Qualite LLM: **0 fallback_default / 1200**, quality gate stricte `-JudgeMaxFallbackRatio 0`.
- Endpoints LLM: **117** batchs `responses_sdk`, **4** batchs fallback REST `responses`, aucun fallback de jugement.
- Verification liens: **555** liens verifies.
- Queue multi-run: **300** items dedupes, tous `active`, triee par priorite LLM puis `COALESCE(last_combined_score, score)`.
- Lane VIE dediee: **240** missions priorisees, dont **77** deja jugees LLM et **163** VIE techniques non jugees.
- Snapshot final: `runs/history/20260510-173933-vie-fix`.
- Registre multi-run: `runs/history/job_history.sqlite`, fresh rebaseline, **5493** offres connues, **0** missing/stale/expired au demarrage.
- Tache Windows: `JobRadarAI-Daily` **desactivee**.
- Plateforme web: pod `jobradarai-web` **Running 1/1**, image `sha-5ca3919`, HTTPS `/api/health` OK, PVC synchronise avec `run_name=20260510-173933`, `queue_count=300`, `vie_queue_count=240`, `llm_count=1200`.

Exports principaux:

- Dashboard: `runs/latest/dashboard.html`.
- Rapport: `runs/latest/report.md`.
- Shortlist LLM: `runs/latest/llm_shortlist.md`.
- Digest graduate/early-career/doctoral: `runs/latest/graduate_programs.md`.
- Verification liens: `runs/latest/link_checks.md`.
- Queue multi-run: `runs/latest/application_queue.md`.
- Lane VIE dediee: `runs/latest/vie_priority_queue.md`.
- Messages RH brouillons: `runs/latest/application_messages.md`.
- Dashboard historique: `runs/latest/history_dashboard.md`.
- Weekly digest: `runs/latest/weekly_digest.md`.
- Audit marche/VIE/langues/P0-PN: `runs/latest/audit.md`.
- CSV: `runs/latest/jobs.csv`.
- JSON: `runs/latest/jobs.json`.
- Base SQLite: `runs/latest/jobs.sqlite`.
- Sources: `runs/latest/sources.json`.

## Sources Et Skips

Sources actives du run:

- Sources officielles/publiques: Business France VIE, Forem, Actiris, Bundesagentur Jobsuche, JobTechDev Sweden, NAV Arbeidsplassen Norway, EURAXESS, Doctorat.gouv.fr, AcademicTransfer.
- Remote/RSS publics: Remotive, Arbeitnow, RemoteOK, Jobicy, Himalayas, WeWorkRemotely, SwissDevJobs, GermanTechJobs.
- ATS directs: Databricks, Dataiku, Google DeepMind, Mistral AI, Contentsquare, Intercom, HubSpot, Adyen, Stripe, Anthropic, Scale AI, MongoDB, Celonis, N26, Canonical, GitLab, Elastic, OpenAI, LangChain, Perplexity AI, Cursor, Snowflake, Datadog, Algolia, Qonto, Pigment, Cohere, ElevenLabs, Synthesia, Stability AI, Modal, Poolside, H Company, Dust, Qdrant, Nabla, Doctolib, Delivery Hero.
- APIs avec credentials: France Travail, Jooble.
- Scraper controle: JobSpy Direct sur Indeed uniquement, via `uv run --isolated --no-project --with python-jobspy==1.1.82`.

Skips attendus:

- `adzuna`: credentials absents (`ADZUNA_APP_ID`/`ADZUNA_APP_KEY`).
- `jobspy_api`: service local injoignable sur `http://127.0.0.1:8000`; non bloquant car JobSpy Direct remplace ce besoin.

Sources volontairement hors routine:

- VDAB direct: acces public/partenaire non exploitable ici.
- SerpAPI Google Jobs: quota trop faible.
- Glassdoor via JobSpy: teste, 0 resultat exploitable et erreurs API/location sur marches cibles.
- EURES, JobsIreland, Veolia large, ANRT sans compte: ratio stabilite/signal insuffisant pour la routine.
- ABG, Campus France Doctorat, DAAD/PhDGermany, ETH/EPFL: backlog ponctuel paid PhD/research, pas meilleur que Doctorat.gouv.fr + EURAXESS + AcademicTransfer pour le run quotidien actuel.

## Couverture Marche

- France: **1075**.
- Allemagne: **973**.
- UK: **584**.
- Irlande: **343**.
- Belgique: **325**.
- Remote Europe: **297**.
- Espagne: **290**.
- Singapour: **269**.
- Suede: **263**.
- Pays-Bas: **244**.
- Suisse: **210**.
- Norvege: **133**.
- Pologne: **111**.
- Autriche: **98**.
- Portugal: **89**.
- Danemark: **72**.
- Tchequie: **49**.
- Finlande: **33**.
- Luxembourg: **33**.
- Estonie: **2**.

Verdict restrictivite: **OK**. Le seuil local reste bas (`min_score = 35`), Business France VIE scanne large, `max_per_source = 1200`, et le tri final est fait par priorite LLM + score combine plutot que par hard filters trop agressifs.

Bandes de score:

- 35-45: **1334** offres.
- 45-60: **3301** offres.
- 60-75: **751** offres.
- 75+: **107** offres.

## Shortlist LLM

- Offres jugees: **1200** / 5493.
- Selection: `wide`.
- Priorites: **42** `apply_now`, **299** `shortlist`, **214** `maybe`, **645** `skip`.
- VIE selectionnes: **158** / 509.
- Early-career/graduate/doctoral cible selectionne: **53** / 61.
- Poids de classement final: **40%** score local, **60%** `fit_score` LLM.
- Le rerank est maintenant beaucoup plus large que l'ancien `balanced 200`: il couvre le signal >= 60 puis complete avec VIE, graduate/doctoral et couverture marche.

Top `apply_now` du run:

- Datadog - `AI Research Engineer - Datadog AI Research (DAIR)`, France, score combine 85.76, niveau `stretch`.
- Omnilex - `Data Engineer - Legal Data AI Processing`, Suisse, score combine 84.91, niveau `stretch`.
- MATERA - `GenAI Engineer (H/F)`, France, score combine 84.58, niveau `junior_ok`.
- Capgemini - `Gen AI Engineer`, Finlande, score combine 84.10, niveau `unknown`.
- Qdrant - `Research Engineer, Agentic Retrieval (EMEA)`, Pays-Bas, score combine 83.34, niveau `stretch`.
- Qdrant - `Research Engineer, Agentic Retrieval (EMEA)`, France, score combine 83.07, niveau `stretch`.
- Recare Gmbh - `AI / ML Engineer (m/w/d)`, Allemagne, score combine 82.03, niveau `stretch`.
- Inserm - `INGENIEUR EN DEVELOPPEMENT PYTHON & IA (SIEGE) - H/F`, France, score combine 81.62, niveau `junior_ok`.
- Qdrant - `Research Engineer, Agentic Retrieval (EMEA)`, Allemagne, score combine 81.31, niveau `stretch`.
- Snowflake - `Snowflake Data Engineer`, Pologne, score combine 81.08, niveau `junior_ok`.

## Queue Multi-Run

- Queue dedupee: **300**.
- Statuts: **300** `active`, **0** `stale`, **0** `expired` dans la queue.
- Priorites queue: **42** `apply_now`, **258** `shortlist`.
- VIE dans la queue principale: **17**.
- Lane VIE dediee: **240** items, buckets **2** `apply_now`, **27** `shortlist`, **48** `maybe`, **163** `unjudged_technical`.
- Liens queue: **151** `direct_ok`, **116** `browser_required`, **33** `needs_review`.
- Niveau LLM: **114** `junior_ok`, **162** `stretch`, **24** `unknown`, **0** `too_senior`.
- Experience deterministe dans la queue: **21** `junior_ok`, **22** `stretch`, **257** `unknown`, **0** `too_senior`; **23** items exposent `required_years`.

Checks queue:

- `start_date_check`: 274 `unknown`, 14 `too_soon`, 12 `compatible`.
- Salaire: 141 `meets_or_likely`, 114 `unknown`, 45 `below_min`.
- Remote: 88 `meets`, 207 `weak`, 5 `unknown`.
- Langue: 71 `english_ok`, 26 `french_ok`, 12 `local_language_required`, 191 `unknown`.
- Remote/localisation: 292 `compatible`, 8 `restricted`, 0 `incompatible`.

## Liens

- Liens verifies: **555**.
- `direct_ok`: **306**.
- `browser_required`: **206**.
- `needs_review`: **42**.
- `server_error`: **1**.
- `expired`: **0**.
- `unreachable`: **0**.

Interpretation: les liens `browser_required` ne sont pas des echecs systeme; ce sont surtout des agregateurs/anti-bot/pages protegees a ouvrir dans un navigateur avant candidature. Les `needs_review` et le `server_error` doivent etre confirmes avant candidature.

## Graduate / Early Careers / Doctoral

- Signaux detectes: **374**.
- High/medium: **61**.
- Programmes structures: **24**.
- Doctorats/CIFRE: **217**, dont **6** industriels/CIFRE.
- Dans le judge LLM: **53**.
- Dans la queue: **17**.
- Priorites LLM sur cette couche: **6** `apply_now`, **26** `shortlist`, **16** `maybe`, **5** `skip`.

Verdict: la couche marche et reste correctement secondaire. Elle capture les graduate programmes/new-grad/CIFRE/doctorats industriels pertinents sans transformer le radar en filtre `graduate only`.

## Profil Et Contraintes Integrees

- CV source: `private/main.tex`.
- Profil: Data/AI products end-to-end, RAG/LLM, backend/API, MLOps/DevOps, observabilite, recherche.
- Focus courant: stage recherche Aubay AI Researcher, fev. 2026 a juil. 2026, explicabilite/interpretabilite mecanistique de l'IA.
- Salaire minimum: 45k EUR/an.
- Remote: preference hybride ou remote, minimum vise 2 jours/semaine.
- Demarrage cible: aout/septembre 2026 apres le stage Aubay.
- `start_date_check` reste un signal soft a confirmer avec RH.
- Localisation: pas de blocage pays; preference grandes villes; base actuelle Boulogne-Billancourt/Paris.
- Secteurs exclus: aucun.

## Points Corriges Lors De La Derniere Livraison

- Transport LLM passe en `auto`: OpenAI SDK quand disponible, `base_url` codexlb, fallback REST controle.
- Responses API utilise une sortie JSON Schema stricte avec enum des `stable_id` attendus.
- Les erreurs structurelles LLM sont retentees; le fallback singleton immediat est supprime.
- Quality gate ajoute: un run avec trop de `fallback_default` echoue et supprime les anciennes shortlists au lieu de publier une queue polluee.
- Calibrage codexlb: `JudgeConcurrency 1` est le default prod; `2` est plus lent sur smoke et `5` declenche des risques de `responses session bridge queue full`.
- Calibrage batch: `JudgeBatchSize 10` est le meilleur compromis observe; batch 20 a ete plus lent et a degrade le transport.
- `openai>=2.0.0` ajoute aux dependances et lockfile mis a jour.
- Audit expose maintenant transport/endpoint/fallback/priorites LLM.
- Docs et scripts mis a jour avec `wide 1200`, SDK/codexlb, batch 10, concurrence 1, effort medium.

## P0 A PN

- `P0`: aucun blocage runtime detecte sur le dernier run.
- `P1`: ouvrir manuellement les **206** liens `browser_required` avant candidature.
- `P1`: verifier manuellement les **42** liens `needs_review` et le **1** `server_error` avant candidature.
- `P1`: verifier salaire et remote quand l'offre ou le judge LLM marquent `unknown`/`weak`.
- `P2`: utiliser `start_date_check` comme signal soft et confirmer avec RH les dates `unknown`/`too_soon`; ne pas auto-skipper.
- `P2`: exploiter `vie_priority_queue.md` pour les VIE; la queue principale ne suffit pas a elle seule pour cette voie.
- `P2`: utiliser `deadline`, `language_check`, `remote_location_validity`, `required_years`, `experience_check` et `salary_normalized_annual_eur` comme signaux soft. Les hard filters legitimes restent: remote explicitement incompatible, langue locale obligatoire non compensee par un fit tres fort, ou niveau/experience `too_senior` sans signal junior/all-levels explicite.
- `P2`: garder les candidatures/messages en validation humaine; aucune action LinkedIn automatique de masse.
- `P2`: lancer ponctuellement `scripts/pull_web_state.ps1` pour sauvegarder localement les statuts/notes saisis dans l'interface.
- `P3`: `JudgeConcurrency 2` peut etre reteste si codexlb change, mais le default prod reste 1 tant que les logs montrent des `queue_full` a concurrence elevee.
- `P3`: JobSpy API Docker seulement si tu veux une API locale permanente; le mode uv direct suffit aujourd'hui et est timeout-borne.
- `P3`: WTTJ, DevITJobs-like, Wellfound, ABG, Campus France Doctorat, DAAD/PhDGermany, ETH/EPFL restent des tests ponctuels possibles, pas des manques bloquants du systeme actuel.
- `PN`: VDAB direct, SerpAPI, Glassdoor JobSpy, ANRT sans compte, EURES API, JobsIreland API, Veolia large et LinkedIn automation sont hors scope routine.
