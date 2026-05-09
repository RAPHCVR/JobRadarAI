# Etat Courant

Derniere validation: **2026-05-09 16:43 Europe/Paris**, full run large manuel `20260509-160240` apres audit, nettoyage, durcissement JobSpy Direct et extension sources/geographies.

Commande utilisee pour la base large:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/run_daily.ps1 `
  -ProjectRoot C:\Users\Raphael\Documents\JobRadarAI `
  -MaxPerSource 1200 `
  -Judge -JudgeRequired -JudgeLimit 200 -JudgeBatchSize 5 `
  -JudgeSelectionMode balanced -JudgeEffort medium `
  -JudgeTimeoutSeconds 360 -JudgeMaxAttempts 3 -JudgeRetrySeconds 30 `
  -LinkCheckLimit 240 -LinkCheckTimeoutSeconds 10 -LinkCheckWorkers 12 `
  -HistoryRecheckStaleLimit 80
```

## Resultat

- Offres retenues: **4815**.
- Sources OK: **58**.
- Sources ignorees attendues: **2**.
- Erreurs source: **0**.
- Remote/hybride detecte: **2057** offres, soit **42.7%**.
- Salaire publie hors VIE: **507** offres, dont **452** >= 45k EUR/an.
- Deadlines publiees: **891**.
- Salaires normalises EUR/an: **502**.
- Annees d'experience extraites: **1261**.
- VIE Business France retenus: **532**.
- Judge LLM: **200** offres jugees en mode `balanced`, effort `medium`, batchs de 5.
- Verification liens: **236** liens verifies.
- Queue multi-run: **176** items dedupes.
- Snapshot final: `runs/history/20260509-160240`.
- Registre multi-run: `runs/history/job_history.sqlite`.
- Logs: `runs/logs/`.
- Tache Windows: `JobRadarAI-Daily` **desactivee**. Aucun run automatique ne doit partir tant que la tache reste `Disabled`.

Exports principaux:

- Dashboard: `runs/latest/dashboard.html`.
- Rapport: `runs/latest/report.md`.
- Shortlist LLM: `runs/latest/llm_shortlist.md`.
- Digest graduate/early-career/doctoral: `runs/latest/graduate_programs.md`.
- Verification liens: `runs/latest/link_checks.md`.
- Queue multi-run: `runs/latest/application_queue.md`.
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

- France: **822**.
- Allemagne: **655**.
- UK: **579**.
- Irlande: **345**.
- Belgique: **303**.
- Remote Europe: **297**.
- Espagne: **292**.
- Singapour: **260**.
- Pays-Bas: **229**.
- Suede: **218**.
- Suisse: **207**.
- Pologne: **111**.
- Norvege: **105**.
- Portugal: **104**.
- Autriche: **100**.
- Danemark: **72**.
- Tchequie: **50**.
- Finlande: **32**.
- Luxembourg: **32**.
- Estonie: **2**.

Verdict restrictivite: **OK**. Le seuil local reste bas (`min_score = 35`), Business France VIE scanne large, `max_per_source = 1200`, et le tri final est fait par score + LLM plutot que par hard filters trop agressifs.

Bandes de score:

- 35-45: **1209** offres.
- 45-60: **2817** offres.
- 60-75: **690** offres.
- 75+: **99** offres.

## Shortlist LLM

- Offres jugees: **200** / 4815.
- Selection: `balanced`.
- Priorites: **9** `apply_now`, **75** `shortlist`, **39** `maybe`, **77** `skip`.
- VIE selectionnes: **53** / 532.
- Early-career/graduate/doctoral cible selectionne: **22** / 52.

Top `apply_now` du run:

- Datadog - `AI Research Engineer - Datadog AI Research (DAIR)`, France, score combine 86.47, niveau `stretch`.
- Resmed - `Data Platform Engineer`, Irlande, score combine 83.24, niveau `junior_ok`.
- Cohere - `Applied AI Engineer - Agentic Workflows`, UK, score combine 82.08, niveau `stretch`.
- Databricks - `AI Engineer - FDE (Forward Deployed Engineer)`, UK, score combine 80.98, niveau `junior_ok`.
- Omnilex - `Data Engineer - Legal Data AI Processing`, Suisse, score combine 79.90, niveau `stretch`.
- Qdrant - `Research Engineer, Agentic Retrieval (EMEA)`, Pays-Bas, score combine 78.49, niveau `stretch`.
- HMS Analytical Software GmbH - `Data Engineer (mwd) - Data Platforms & Data Pipelines`, Allemagne, score combine 77.39, niveau `junior_ok`.
- NN GROUP - `Junior Data Engineer`, Tchequie, score combine 76.36, niveau `junior_ok`.
- Symrise - `Data Science / Machine Learning graduate`, Espagne, score combine 61.16, niveau `junior_ok`.

## Queue Multi-Run

- Queue dedupee: **176**.
- Statuts: **169** `active`, **7** `stale`, **0** `expired` dans la queue.
- Priorites queue: **13** `apply_now`, **103** `shortlist`, **4** `high_score`, **56** `maybe`.
- Historique global: **4815** offres actives, **671** offres `stale`, **0** `expired`.
- Deltas vs run precedent `20260508-204629-expanded`: **2233** nouvelles offres, **3** revenus, **671** absentes ce run.

Checks queue:

- `start_date_check`: 119 `unknown`, 46 `too_soon`, 11 `compatible`.
- Salaire: 102 `meets_or_likely`, 44 `unknown`, 30 `below_min`.
- Remote: 58 `meets`, 115 `weak`, 3 `unknown`.
- Langue: 26 `english_ok`, 12 `french_ok`, 2 `local_language_required`, 136 `unknown`.
- Remote/localisation: 174 `compatible`, 1 `restricted`, 1 `unknown`.
- Niveau: 85 `junior_ok`, 80 `stretch`, 8 `unknown`; les `too_senior` LLM ou deterministes ne restent pas dans la queue actionnable.

## Liens

- Liens verifies: **236**.
- `direct_ok`: **132**.
- `browser_required`: **89**.
- `needs_review`: **15**.
- `expired`: **0**.
- `unreachable`: **0**.
- `server_error`: **0**.

Interpretation: les liens `browser_required` ne sont pas des echecs systeme; ce sont surtout des agregateurs/anti-bot/pages protegees a ouvrir dans un navigateur avant candidature. Les `needs_review` doivent etre confirmes manuellement avant de candidater.

## Graduate / Early Careers / Doctoral

- Signaux detectes: **316**.
- High/medium: **52**.
- Programmes structures: **22**.
- Doctorats/CIFRE: **184**, dont **6** industriels/CIFRE.
- Dans le judge LLM: **22**.
- Dans la queue: **24**.
- Priorites LLM sur cette couche: **2** `apply_now`, **14** `shortlist`, **5** `maybe`, **1** `skip`.

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

- Bug Windows JobSpy Direct corrige: un process enfant pouvait garder les pipes stdout/stderr ouverts et bloquer `jobradai run` apres timeout. La commande optionnelle utilise maintenant des fichiers temporaires et tue le process tree au timeout.
- Tests ajoutes pour verifier que `_run_text_command` capture bien stdout/stderr et rend la main apres timeout.
- Full run large relance et termine sans erreur source.
- Documentation vivante remise a jour sur le run `20260509-160240`.
- Garde-fou ajoute: une offre avec `experience_check=too_senior` deterministe sort de la queue actionnable sauf override LLM `junior_ok`; les cas `stretch` 2-4 ans restent visibles.
- Queue et audit regeneres apres ce garde-fou: **176** items, **0** `experience_check=too_senior` dans la queue.
- Workspace nettoye puis pousse sur GitHub.

## P0 A PN

- `P0`: aucun blocage runtime detecte sur le dernier run.
- `P1`: ouvrir manuellement les **89** liens `browser_required` avant candidature.
- `P1`: verifier manuellement les **15** liens `needs_review` avant candidature.
- `P1`: verifier salaire et remote quand l'offre ou le judge LLM marquent `unknown`/`weak`.
- `P2`: utiliser `start_date_check` comme signal soft et confirmer avec RH les dates `unknown`/`too_soon`; ne pas auto-skipper.
- `P2`: utiliser `deadline`, `language_check`, `remote_location_validity`, `required_years`, `experience_check` et `salary_normalized_annual_eur` comme signaux soft. Les hard filters legitimes restent: remote explicitement incompatible, langue locale obligatoire non compensee par un fit tres fort, ou niveau/experience `too_senior` sans signal junior/all-levels explicite.
- `P2`: garder les candidatures/messages en validation humaine; aucune action LinkedIn automatique de masse.
- `P3`: JobSpy API Docker seulement si tu veux une API locale permanente; le mode uv direct suffit aujourd'hui et est timeout-borne.
- `P3`: WTTJ, DevITJobs-like, Wellfound, ABG, Campus France Doctorat, DAAD/PhDGermany, ETH/EPFL restent des tests ponctuels possibles, pas des manques bloquants du systeme actuel.
- `PN`: VDAB direct, SerpAPI, Glassdoor JobSpy, ANRT sans compte, EURES API, JobsIreland API, Veolia large et LinkedIn automation sont hors scope routine.
