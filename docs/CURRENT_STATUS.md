# Etat Courant

Derniere validation run: **2026-05-11 17:58 Europe/Paris**, full rebaseline manuel `20260510-173933` conserve, puis onze augments LLM cibles, correction France Travail HTTP 409 en `browser_required`, verification liens, queue/history et audit regeneres sous `20260511-170036-hard-audit-residual7-final`.

Derniere validation plateforme web: **2026-05-11 17:58 Europe/Paris**, image `ghcr.io/raphcvr/jobradarai-web:sha-5ca3919` deployee, `runs/latest` resynchronise puis audit final recopie sur Kubernetes sous `https://jobs.raphcvr.me`.

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
- Judge LLM base: **1200** offres jugees en mode `wide`, effort `medium`, batch 10, concurrence 1.
- Augments LLM cibles: **1533** offres jugees en plus, dont **430** watch/VIE techniques, **303** rescue non-VIE titre/source et **800** residuels manuels/entreprises/doctorats a risque de faux negatif.
- Total LLM exploite par la queue et les exports: **2733** jugements uniques.
- Transport LLM: `auto` via OpenAI SDK quand possible, `base_url=https://codex.raphcvr.me/v1`.
- Qualite LLM: **0 fallback_default / 2733**, quality gate stricte `-JudgeMaxFallbackRatio 0`.
- Endpoints LLM base: **117** batchs `responses_sdk`, **4** batchs fallback REST `responses`, aucun fallback de jugement. Les augments cibles ont aussi termine a **0 fallback**; residual7 a ete force en `raw`/effort `low` apres blocage SDK et a traite 120/120 offres.
- Verification liens: **1318** liens verifies, **732** `direct_ok`, **570** `browser_required`, **0** `needs_review`, **13** `expired`, **2** `unreachable`, **1** `server_error`.
- Queue multi-run: **300** items dedupes, tous `active`, triee par priorite LLM puis `COALESCE(last_combined_score, score)`.
- Lane VIE dediee: **170** missions priorisees, toutes jugees LLM, buckets **2** `apply_now`, **50** `shortlist`, **118** `maybe`.
- Lane watch non jugee: **0** offre restante; les **79** offres techniques/IA/data reperees ont ete traitees par augment LLM cible.
- Rescue non-VIE + passes manuelles residuelles: **1103** offres reperees par audit titre/source/entreprise/doctorat jugees; **43** `apply_now`, **260** `shortlist`, **303** `maybe`, **497** `skip`; residuel VIE-like non juge: **0**; buckets residuels actionnables A/B: **0** apres residual7.
- Snapshot final: `runs/history/20260511-170036-hard-audit-residual7-final-consistent`.
- Registre multi-run: `runs/history/job_history.sqlite`, fresh rebaseline, **5493** offres connues, **0** missing, **52** returned jobs au dernier sync, dernier sync `20260511-170036-hard-audit-residual7-final`.
- Tache Windows: `JobRadarAI-Daily` **desactivee**.
- Plateforme web: pod `jobradarai-web` **Running 1/1**, image `sha-5ca3919`, HTTPS `/api/health` OK, PVC synchronise avec `queue_count=300`, `queue_priority_counts={'apply_now': 86, 'shortlist': 214}`, `vie_queue_count=170`, `unjudged_watch_count=0`, `llm_augment_count=1533`, `link_checked_count=1318`.

Exports principaux:

- Dashboard: `runs/latest/dashboard.html`.
- Rapport: `runs/latest/report.md`.
- Shortlist LLM: `runs/latest/llm_shortlist.md`.
- Digest graduate/early-career/doctoral: `runs/latest/graduate_programs.md`.
- Verification liens: `runs/latest/link_checks.md`.
- Queue multi-run: `runs/latest/application_queue.md`.
- Lane VIE dediee: `runs/latest/vie_priority_queue.md`.
- Lane watch non jugee: `runs/latest/unjudged_watch_queue.md`.
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

- Offres jugees base: **1200** / 5493.
- Selection: `wide`.
- Priorites: **42** `apply_now`, **299** `shortlist`, **214** `maybe`, **645** `skip`.
- Augments cibles: **1533** jugements additionnels, priorites **44** `apply_now`, **311** `shortlist`, **408** `maybe`, **770** `skip`.
- Total exploite par la queue et les exports: **2733** jugements uniques, **0** fallback.
- VIE juges: **509** / 509.
- Early-career/graduate/doctoral cible selectionne: **53** / 61.
- Poids de classement final: **40%** score local, **60%** `fit_score` LLM.
- Le rerank est maintenant beaucoup plus large que l'ancien `balanced 200`: il couvre le signal >= 60 puis complete avec VIE, graduate/doctoral et couverture marche.
- Augment notable: Mistral AI `Applied AI, Fullstack Software Engineer, Critical and Sovereign Institutions, Paris` est maintenant `apply_now`; Mistral `Software Engineer, Enterprise Agents` est `shortlist`.

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
- Priorites queue: **86** `apply_now`, **214** `shortlist`.
- VIE dans la queue principale: **11**.
- Lane VIE dediee: **170** items, buckets **2** `apply_now`, **50** `shortlist`, **118** `maybe`, **0** non juge.
- Lane watch non jugee: **0** item.
- Augments LLM cibles integres: **1533** jugements, priorites **44** `apply_now`, **311** `shortlist`, **408** `maybe`, **770** `skip`.
- Liens queue: **136** `direct_ok`, **164** `browser_required`, **0** `needs_review`.
- Niveau LLM: **124** `junior_ok`, **159** `stretch`, **17** `unknown`, **0** `too_senior`.
- Experience deterministe dans la queue: **22** `junior_ok`, **18** `stretch`, **258** `unknown`, **2** `too_senior` a verifier manuellement; **21** items exposent `required_years`.

Checks queue:

- `start_date_check`: 256 `unknown`, 35 `compatible`, 9 `too_soon`.
- Salaire: 140 `meets_or_likely`, 110 `unknown`, 50 `below_min`.
- Remote: 87 `meets`, 205 `weak`, 8 `unknown`.
- Langue: 66 `english_ok`, 41 `french_ok`, 6 `local_language_required`, 187 `unknown`.
- Remote/localisation: 291 `compatible`, 9 `restricted`, 0 `incompatible`.

## Liens

- Liens verifies: **1318**.
- `direct_ok`: **732**.
- `browser_required`: **570**.
- `needs_review`: **0**.
- `server_error`: **1**.
- `expired`: **13**.
- `unreachable`: **2**.

Interpretation: les liens `browser_required` ne sont pas des echecs systeme; ce sont surtout des agregateurs/anti-bot/pages protegees a ouvrir dans un navigateur avant candidature. Les anciens France Travail HTTP 409 sont maintenant classes dans ce bucket, ce qui evite de polluer `needs_review`. Les `expired`, `unreachable` et `server_error` restants sont hors queue actionnable, mais restent a confirmer si tu tombes dessus.

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
- History/link-check lisent maintenant aussi `runs/latest/llm_augments/*.json`; les runs cibles ne creent donc plus d'angle mort lien ou queue.
- France Travail HTTP 409 est classe `browser_required` plutot que `needs_review`: c'est un blocage navigateur/anti-bot attendu sur `candidat.francetravail.fr`, pas une offre a retraiter automatiquement.
- Augments cibles executes: 242 offres watch/VIE techniques puis 188 VIE restants, tous a 0 fallback. Resultat: lane VIE entierement jugee et `unjudged_watch_queue` vide.
- Audit rescue execute sur deux poches non-VIE au titre/source: 140 puis 163 offres, tous a 0 fallback. Resultat: **16** nouveaux `apply_now`, **70** `shortlist`.
- Audit manuel/residuel ajoute ensuite 120 + 120 + 120 + 80 + 160 + 80 + 120 offres sur les borderlines, doctorats/LLM, entreprises sensibles, exceptions et residuels stricts: **27** `apply_now`, **190** `shortlist`, **220** `maybe`, **363** `skip`, 0 fallback.
- Dernieres passes residual6/residual7: residual6 a prouve que l'ancien libelle `2856 bruits` etait trop fort (**4** `apply_now`, **11** `shortlist` sur 80); residual7 a juge 120 autres suspects et n'a trouve que **14** `shortlist`, **0** `apply_now`. Resultat: **0** VIE-like non juge restant et **0** bucket A/B actionnable parmi les **2760** non juges restants; il reste **271** weak-signal C et **2489** low-signal/noise.

## P0 A PN

- `P0`: aucun blocage runtime detecte sur le dernier run.
- `P1`: ouvrir manuellement les **570** liens `browser_required` avant candidature, surtout Indeed/JobSpy, France Travail HTTP 409 et pages protegees/anti-bot.
- `P1`: verifier manuellement les **13** liens `expired`, les **2** `unreachable` et le **1** `server_error` si tu veux recuperer des offres hors queue. Il reste **0** `needs_review`.
- `P1`: verifier salaire et remote quand l'offre ou le judge LLM marquent `unknown`/`weak`.
- `P2`: utiliser `start_date_check` comme signal soft et confirmer avec RH les dates `unknown`/`too_soon`; ne pas auto-skipper.
- `P2`: exploiter `vie_priority_queue.md` pour les VIE; la queue principale ne suffit pas a elle seule pour cette voie.
- `P2`: garder `unjudged_watch_queue.md` comme garde-fou de futurs runs; sur l'etat courant elle est vide, car Mistral Enterprise Agents/Applied AI, LangChain LangSmith, Poolside, DeepMind, Canonical Junior Observability, Cohere internship et les autres signaux detectes ont ete juges par l'augment cible.
- `P2`: utiliser `deadline`, `language_check`, `remote_location_validity`, `required_years`, `experience_check` et `salary_normalized_annual_eur` comme signaux soft. Les hard filters legitimes restent: remote explicitement incompatible, langue locale obligatoire non compensee par un fit tres fort, ou niveau/experience `too_senior` sans override LLM `junior_ok`/`stretch` explicite.
- `P2`: garder les candidatures/messages en validation humaine; aucune action LinkedIn automatique de masse.
- `P2`: lancer ponctuellement `scripts/pull_web_state.ps1` pour sauvegarder localement les statuts/notes saisis dans l'interface.
- `P3`: `JudgeConcurrency 2` peut etre reteste si codexlb change, mais le default prod reste 1 tant que les logs montrent des `queue_full` a concurrence elevee.
- `P3`: JobSpy API Docker seulement si tu veux une API locale permanente; le mode uv direct suffit aujourd'hui et est timeout-borne.
- `P3`: WTTJ, DevITJobs-like, Wellfound, ABG, Campus France Doctorat, DAAD/PhDGermany, ETH/EPFL restent des tests ponctuels possibles, pas des manques bloquants du systeme actuel.
- `PN`: VDAB direct, SerpAPI, Glassdoor JobSpy, ANRT sans compte, EURES API, JobsIreland API, Veolia large et LinkedIn automation sont hors scope routine.
