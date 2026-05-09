# Etat Courant

Derniere validation run: **2026-05-09 19:59 Europe/Paris**, full run large manuel `20260509-192018` apres audit, nettoyage, durcissement JobSpy Direct, extension sources/geographies, extension titres et garde-fous experience.

Derniere validation plateforme web: **2026-05-09 23:40 Europe/Paris**, interface UI/UX amelioree, deployee sur Kubernetes sous `https://jobs.raphcvr.me`.

Commande utilisee pour la base large:

```powershell
.\scripts\run_daily.ps1 `
  -Judge -JudgeRequired -JudgeLimit 200 -JudgeBatchSize 5 `
  -JudgeSelectionMode balanced -JudgeEffort medium `
  -JudgeTimeoutSeconds 360 -JudgeMaxAttempts 3 -JudgeRetrySeconds 30 `
  -LinkCheckLimit 240 -LinkCheckTimeoutSeconds 10 -LinkCheckWorkers 12 `
  -HistoryRecheckStaleLimit 80
```

## Resultat

- Offres retenues: **4976**.
- Sources OK: **58**.
- Sources ignorees attendues: **2**.
- Erreurs source: **0**.
- Remote/hybride detecte: **2089** offres, soit **42.0%**.
- Salaire publie hors VIE: **521** offres, dont **466** >= 45k EUR/an.
- Deadlines publiees: **987**.
- Salaires normalises EUR/an: **515**.
- Annees d'experience extraites: **1277**.
- VIE Business France retenus: **532**.
- Judge LLM: **200** offres jugees en mode `balanced`, effort `medium`, batchs de 5.
- Verification liens: **236** liens verifies.
- Queue multi-run: **181** items dedupes.
- Snapshot final: `runs/history/20260509-192018`.
- Registre multi-run: `runs/history/job_history.sqlite`.
- Logs: `runs/logs/`.
- Tache Windows: `JobRadarAI-Daily` **desactivee**. Aucun run automatique ne doit partir tant que la tache reste `Disabled`.
- Plateforme web: pod `jobradarai-web` **Running 1/1**, image `ghcr.io/raphcvr/jobradarai-web:sha-e7ad16a`, ingress `jobs.raphcvr.me`, PVC Longhorn `jobradarai-data` 5Gi, auth active.
- Smoke web HTTPS: `/api/health` OK, login OK, `run_name=20260509-192018`, `queue_count=181`, CV PDF disponible, rendu desktop/mobile OK sans overflow horizontal.

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

- France: **847**.
- Allemagne: **706**.
- UK: **586**.
- Irlande: **345**.
- Remote Europe: **295**.
- Espagne: **291**.
- Belgique: **291**.
- Singapour: **264**.
- Suede: **260**.
- Pays-Bas: **246**.
- Suisse: **207**.
- Norvege: **135**.
- Pologne: **112**.
- Portugal: **104**.
- Autriche: **100**.
- Danemark: **71**.
- Tchequie: **50**.
- Finlande: **32**.
- Luxembourg: **32**.
- Estonie: **2**.

Verdict restrictivite: **OK**. Le seuil local reste bas (`min_score = 35`), Business France VIE scanne large, `max_per_source = 1200`, et le tri final est fait par score + LLM plutot que par hard filters trop agressifs.

Bandes de score:

- 35-45: **1257** offres.
- 45-60: **2905** offres.
- 60-75: **710** offres.
- 75+: **104** offres.

## Shortlist LLM

- Offres jugees: **200** / 4976.
- Selection: `balanced`.
- Priorites: **13** `apply_now`, **72** `shortlist`, **40** `maybe`, **75** `skip`.
- VIE selectionnes: **52** / 532.
- Early-career/graduate/doctoral cible selectionne: **22** / 55.

Top `apply_now` du run:

- Datadog - `AI Research Engineer - Datadog AI Research (DAIR)`, France, score combine 86.17, niveau `stretch`.
- Capgemini - `Gen AI Engineer`, Finlande, score combine 85.97, niveau `stretch`.
- Databricks - `AI Engineer - FDE (Forward Deployed Engineer)`, UK, score combine 80.38, niveau `junior_ok`.
- Omnilex - `Data Engineer - Legal Data AI Processing`, Suisse, score combine 79.60, niveau `stretch`.
- Qdrant - `Research Engineer, Agentic Retrieval (EMEA)`, France, score combine 79.07, niveau `junior_ok`.
- Experience IT Solutions - `IA / MLOps Engineer. Remoto`, Espagne, score combine 78.18, niveau `stretch`.
- Qdrant - `Research Engineer, Agentic Retrieval (EMEA)`, Pays-Bas, score combine 77.59, niveau `stretch`.
- Symrise - `Data Engineering graduate`, Espagne, score combine 66.98, niveau `junior_ok`.
- Datadog - `Software Engineer - Early Career`, Portugal, score combine 66.75, niveau `junior_ok`.
- Databricks - `Software Engineer - New Grad (2026 Start) - Aarhus`, Danemark, score combine 65.72, niveau `junior_ok`.

## Queue Multi-Run

- Queue dedupee: **181**.
- Statuts: **174** `active`, **7** `stale`, **0** `expired` dans la queue.
- Priorites queue: **17** `apply_now`, **103** `shortlist`, **2** `high_score`, **59** `maybe`.
- Historique global: **4976** offres actives, **1184** offres `stale`, **0** `expired`.
- Deltas vs run precedent `20260509-160240`: **674** nouvelles offres, **1** revenue, **1184** absentes ce run.

Checks queue:

- `start_date_check`: 123 `unknown`, 47 `too_soon`, 11 `compatible`.
- Salaire: 106 `meets_or_likely`, 43 `unknown`, 32 `below_min`.
- Remote: 62 `meets`, 117 `weak`, 2 `unknown`.
- Langue: 45 `english_ok`, 15 `french_ok`, 7 `local_language_required`, 114 `unknown`.
- Remote/localisation: 179 `compatible`, 1 `restricted`, 1 `unknown`.
- Niveau: 77 `junior_ok`, 92 `stretch`, 12 `unknown`; les `too_senior` LLM ou deterministes ne restent pas dans la queue actionnable.
- Experience: 18 `junior_ok`, 22 `stretch`, 141 `unknown`, 0 `too_senior`; 23 offres de queue exposent `required_years`.

## Liens

- Liens verifies: **236**.
- `direct_ok`: **130**.
- `browser_required`: **91**.
- `needs_review`: **15**.
- `expired`: **0**.
- `unreachable`: **0**.
- `server_error`: **0**.

Interpretation: les liens `browser_required` ne sont pas des echecs systeme; ce sont surtout des agregateurs/anti-bot/pages protegees a ouvrir dans un navigateur avant candidature. Les `needs_review` doivent etre confirmes manuellement avant de candidater.

## Graduate / Early Careers / Doctoral

- Signaux detectes: **346**.
- High/medium: **55**.
- Programmes structures: **23**.
- Doctorats/CIFRE: **214**, dont **6** industriels/CIFRE.
- Dans le judge LLM: **22**.
- Dans la queue: **24**.
- Priorites LLM sur cette couche: **6** `apply_now`, **9** `shortlist`, **6** `maybe`, **1** `skip`.

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
- Documentation vivante remise a jour sur le run `20260509-192018`.
- Garde-fou ajoute: une offre avec `experience_check=too_senior` deterministe sort de la queue actionnable sauf override LLM `junior_ok`; les cas `stretch` 2-4 ans restent visibles.
- Queue et audit regeneres apres ce garde-fou: **181** items, **0** `experience_check=too_senior` dans la queue.
- Extension des titres/requetes: `ML Engineer`, `AI/ML Engineer`, `ML Ops Engineer`, `AI Research Engineer`, `LLM Research Engineer`, `LLM Application Engineer`, `Analytics Engineer` et veille niche `Applied Scientist`/interpretability/explainability/AI safety/knowledge graph/semantic web. Le run `20260509-192018` confirme un signal utile sans explosion de bruit.
- Workspace nettoye puis pousse sur GitHub.
- Interface web React/Vite + shadcn-style ajoutee, dockerisee, publiee via GHCR, deployee sur Kubernetes et synchronisee avec `runs/latest`.
- Durcissement web ajoute: rate-limit login, garde `Origin` sur mutations API, headers HSTS/permissions/COOP.
- Passe UI/UX web ajoutee: grille responsive lisible desktop/mobile, etats vides, tri radar/score/dernieres notes, feedback sauvegarde/copie, champs URL candidature/contact, dernier contact et variante CV.
- CV PDF genere localement apres installation des paquets TinyTeX manquants (`babel-french`, `fontawesome5`) puis monte dans le PVC web.
- Secret web initial cree dans Kubernetes; copie locale ignoree par Git dans `runs/state/web_initial_credentials.txt`.

## P0 A PN

- `P0`: aucun blocage runtime detecte sur le dernier run.
- `P0`: plateforme web deployee et smoke HTTPS OK.
- `P1`: ouvrir manuellement les **91** liens `browser_required` avant candidature.
- `P1`: verifier manuellement les **15** liens `needs_review` avant candidature.
- `P1`: verifier salaire et remote quand l'offre ou le judge LLM marquent `unknown`/`weak`.
- `P2`: utiliser `start_date_check` comme signal soft et confirmer avec RH les dates `unknown`/`too_soon`; ne pas auto-skipper.
- `P2`: utiliser `deadline`, `language_check`, `remote_location_validity`, `required_years`, `experience_check` et `salary_normalized_annual_eur` comme signaux soft. Les hard filters legitimes restent: remote explicitement incompatible, langue locale obligatoire non compensee par un fit tres fort, ou niveau/experience `too_senior` sans signal junior/all-levels explicite.
- `P2/P3`: verifier le bruit des nouveaux titres au prochain run, surtout `Analytics Engineer` et `Applied Scientist`; conserver si le score et le judge remontent bien des roles data/AI/platform/research, pas BI reporting ou research senior hors cible.
- `P2`: garder les candidatures/messages en validation humaine; aucune action LinkedIn automatique de masse.
- `P2`: quand un nouveau run est genere localement, lancer `scripts/sync_web_data.ps1` pour rafraichir la plateforme; ne pas copier `runs/state` sauf migration volontaire des statuts.
- `P2`: lancer ponctuellement `scripts/pull_web_state.ps1` pour sauvegarder localement les statuts/notes saisis dans l'interface.
- `P3`: JobSpy API Docker seulement si tu veux une API locale permanente; le mode uv direct suffit aujourd'hui et est timeout-borne.
- `P3`: WTTJ, DevITJobs-like, Wellfound, ABG, Campus France Doctorat, DAAD/PhDGermany, ETH/EPFL restent des tests ponctuels possibles, pas des manques bloquants du systeme actuel.
- `PN`: VDAB direct, SerpAPI, Glassdoor JobSpy, ANRT sans compte, EURES API, JobsIreland API, Veolia large et LinkedIn automation sont hors scope routine.
