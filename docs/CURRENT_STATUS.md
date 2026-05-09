# Etat Courant

Derniere validation: **2026-05-08 21:34 Europe/Paris**, run manuel complet apres elargissement prudent des requetes France Travail/Jooble/JobSpy/Forem/Actiris, judge LLM 200, verification liens priority-aware, registre multi-run, audit et snapshot.

Extensions post-run ajoutees le **2026-05-08/09**: source officielle Bundesagentur Jobsuche, support SmartRecruiters durci, Delivery Hero filtre par titres utiles, correction du matching pays par alias bornes, JobTechDev Sweden, NAV Arbeidsplassen Norway, EURAXESS, Doctorat.gouv.fr, AcademicTransfer, WeWorkRemotely RSS, SwissDevJobs, GermanTechJobs, champs structures `deadline`/`language_check`/`remote_location_validity`/`required_years`/`experience_check`/salaire annualise EUR, extension graduate/early-career/doctorat industriel-CIFRE, et ouverture prudente Autriche/Nordics/Espagne/Portugal/Estonie/Pologne/Tchequie via scoring marche + Jooble/JobSpy. Ces changements sont valides par tests et smoke live cibles, mais les volumes ci-dessous restent ceux du dernier full run.

## Resultat

- Offres retenues: 2895.
- Score local maximum visible dans les exports: voir `runs/latest/report.md` et `runs/latest/dashboard.html`.
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
- Snapshot final: `runs/history/final-20260508-expanded-github-ready-v3`.
- Registre multi-run: `runs/history/job_history.sqlite`.
- Logs: `runs/logs/`.
- Tache Windows: `JobRadarAI-Daily` **desactivee**. Aucun run automatique ne doit partir tant que la tache reste `Disabled`.

Sources du dernier run:

- 43 OK.
- 2 ignorees attendues: `adzuna` sans credentials, `jobspy_api` local injoignable.
- 0 erreur.
- VDAB et SerpAPI sont desactives volontairement et ne polluent plus l'audit actif.

Judge LLM dernier run:

- Mode: `balanced`.
- Modele: `gpt-5.4-mini`.
- Effort: `medium`.
- 200 offres jugees, 40 batchs.
- Priorites: 12 `apply_now`, 57 `shortlist`, 32 `maybe`, 99 `skip`.
- VIE inclus dans la selection: 51 / 364.
- Graduate/early-career inclus dans la selection: 7 / 7 high/medium.

Graduate/early-career/doctoral:

- Signaux detectes dans le corpus: 62.
- High/medium: 7, tous juges par le LLM et presents dans la queue.
- Priorites LLM: 1 `apply_now`, 2 `shortlist`, 4 `maybe`.
- Le signal reste soft: pas de filtre `graduate only`; les doctorats academiques sans entreprise/statut/salaire clair restent a verifier; les stages/alternances et roles business/generalistes restent low.

Verification liens dernier run:

- 166 liens verifies en mode priority-aware: items LLM `apply_now`/`shortlist`/`maybe` + top local non marque `skip`.
- 112 `direct_ok`.
- 43 `browser_required`: agregateurs ou pages protegees/anti-bot a ouvrir dans un navigateur avant candidature.
- 11 `needs_review`: a verifier manuellement avant candidature.
- 0 `unreachable`.
- Queue multi-run: 108 items dedupes, alimentes par les offres actives et les anciennes offres pertinentes non expirees.
- Ledger: 2895 offres actives, 358 offres `stale`, 0 `expired`; 302 nouvelles offres vs le run precedent, 358 disparues.
- Queue checks: start 106 `unknown`, 1 `too_soon`, 1 `compatible`; salaire 61 `meets_or_likely`, 28 `unknown`, 19 `below_min`; remote 30 `meets`, 78 `weak`; langue 9 `english_ok`, 2 `french_ok`, 1 `local_language_required`, 96 `unknown`; remote/localisation 107 `compatible`, 1 `unknown`.

## Profil Et Contraintes Integrees

- CV source: `private/main.tex`.
- Profil: Data/AI products end-to-end, RAG/LLM, backend/API, MLOps/DevOps, observabilite, recherche.
- Focus courant: stage recherche Aubay AI Researcher, fev. 2026 a juil. 2026, sur explicabilite/interpretabilite mecanistique de l'IA.
- Salaire minimum: 45k EUR/an.
- Remote: preference hybride ou remote, minimum vise 2 jours/semaine.
- Demarrage cible: aout/septembre 2026 apres le stage Aubay; `start_date_check` reste un signal soft a confirmer avec RH.
- Dates limites, langue, validite remote/localisation, annees d'experience requises et salaires devises sont maintenant exposes en champs structures pour aider le scoring, le judge et la queue sans hard-filter automatique.
- Localisation: pas de blocage pays, preference grandes villes; base actuelle Boulogne-Billancourt/Paris.
- Secteurs exclus: aucun.

## Sources Actives

- ATS directs: Databricks, Dataiku, Google DeepMind, Mistral AI, Contentsquare, Intercom, HubSpot, Adyen, Stripe, Anthropic, Scale AI, MongoDB, Celonis, N26, Canonical, GitLab, Elastic, OpenAI, LangChain, Perplexity AI, Cursor, Snowflake, Datadog, Algolia, Qonto, Pigment, Cohere, ElevenLabs, Synthesia, Stability AI, Modal, Poolside, H Company, Dust, Qdrant, Nabla, Doctolib, Delivery Hero.
- APIs publiques/officielles sans cle: Business France VIE, Le Forem Open Data, Actiris, Bundesagentur Jobsuche, JobTechDev Sweden, NAV Arbeidsplassen Norway, EURAXESS, Doctorat.gouv.fr, AcademicTransfer, Remotive, Arbeitnow, RemoteOK, Jobicy, Himalayas, WeWorkRemotely RSS, SwissDevJobs, GermanTechJobs.
- APIs avec credentials: France Travail, Jooble.
- Scraper controle: JobSpy Direct via `uv run --isolated --no-project --with python-jobspy==1.1.82`, avec Indeed par defaut, LinkedIn desactive et timeout configurable `jobspy_direct.timeout_seconds = 240`.
- LLM judge: endpoint compatible OpenAI via `JOBRADAR_LLM_BASE_URL`, modele `gpt-5.4-mini`, batchs de 5.

## Sources Non Actives Ou Bloquees

- VDAB: mis de cote. L'acces public exploitable n'est pas disponible ici; le portail OpenServices indique un onboarding self-service bloque. Forem et Actiris couvrent deja une partie utile de la Belgique sans cle.
- SerpAPI Google Jobs: mis de cote. Quota trop faible pour un run quotidien fiable.
- Adzuna: configure en option multi-pays, mais credentials absents; non bloquant.
- JobSpy API HTTP: service local injoignable; le mode direct via uv remplace ce besoin.
- Glassdoor via JobSpy: teste le 2026-05-09, 0 resultat exploitable et erreurs API/location sur les marches cibles; mis hors scope definitivement pour ce radar.
- EURES et JobsIreland: testes comme extensions P3, non retenus faute d'endpoint public stable/pratique valide.
- ABG et Campus France Doctorat: publics mais non actifs. ABG est trop bruite au smoke AJAX; Campus France est moins direct et redondant avec Doctorat.gouv.fr.
- ANRT CIFRE: pertinent mais derriere compte/offres-candidatures; pas exploitable comme source publique automatique.
- Veolia SmartRecruiters large: teste, non retenu en source active car le flux courant est trop bruite pour le profil.

## Couverture Dernier Run

- UK: 570.
- France: 462.
- Allemagne: 352.
- Irlande: 343.
- Belgique: 333.
- Remote Europe: 293.
- Singapour: 254.
- Pays-Bas: 200.
- Suisse: 55.
- Luxembourg: 33.

## VIE, Langues, Remote Et Salaire

- Remote/hybride detecte: 1319 offres, soit 45.6%.
- Salaire publie hors VIE: 107 offres, dont 81 >= 45k EUR/an.
- VIE: 364 missions Business France retenues, toutes avec indemnite mensuelle indiquee.
- Indemnite VIE observee: 2607 a 4427 EUR/mois.
- Les nouveaux champs post-run exposent maintenant `deadline`, `language_check`, `remote_location_validity`, `required_years`, `experience_check`, `salary_currency` et `salary_normalized_annual_eur` dans les exports, le SQLite, le judge, l'audit et la queue.
- Restrictivite: OK. Seuil local 35, Business France VIE scanne large, 2895 offres gardees, 636 offres dans la bande 35-45, 51 VIE juges par le LLM.
- France: meilleur fit langue/visa/proximite, salaire a verifier plus souvent.
- Irlande: meilleure cible anglophone UE, forte priorite mais volume junior coherent a filtrer.
- Suisse: excellente remuneration, volume plus faible, permis a verifier.
- Belgique/Luxembourg: bon compromis francais/anglais/UE, sources officielles maintenant solides sans VDAB direct.
- UK/Singapour: marche AI/data fort, mais visa/relocation a traiter comme risque.
- Allemagne/Pays-Bas: bons volumes, anglais souvent possible, langue locale a verifier offre par offre.

## Points Corriges Lors Du Dernier Audit

- SerpAPI desactive et retire du chemin actif, car le quota est trop faible.
- VDAB desactive et retire du P actif, car l'acces public/partenaire est bloque.
- Nouveaux ATS IA/data verifies et ajoutes: Cohere, ElevenLabs, Synthesia, Stability AI, Modal, Poolside.
- Les sources optionnelles desactivees ne sont plus remontees comme `skipped` par defaut, pour garder l'audit centre sur l'actionnable.
- Verification liens ajoutee: `python -m jobradai verify-links`, scripts PowerShell, exports Markdown/JSON et integration audit.
- Snapshot historique ajoute: `python -m jobradai snapshot`, script PowerShell, copie datee dans `runs/history`.
- Registre multi-run ajoute: `python -m jobradai sync-history`, `runs/history/job_history.sqlite`, `runs/latest/application_queue.md`.
- Queue enrichie: `start_date_check`, `application_messages.md`, `history_dashboard.md` et `weekly_digest.md`.
- Judge LLM rendu observable avec logs `judge_batch_start/done` et `-JudgeTimeoutSeconds`.
- `runs/latest/jobs.sqlite` est maintenant un snapshot strict du run courant; l'historique multi-run vit dans `runs/history/job_history.sqlite`.
- Script quotidien etendu: run, judge, link-check, history sync, audit, snapshot.
- OpenAI Ashby durci avec timeout ATS specifique a 90 s. Cause racine: feed officiel volumineux, environ 10.7 MB, reponse observee autour de 62 s.
- Audit enrichi: il remonte les liens proteges/agregateurs, les liens expires, et l'absence de link-check.
- Tests ajoutes pour verifier link-check, snapshots et optional sources desactivees.
- Couche graduate/early-career/doctorat industriel ajoutee: requetes dediees, quota minimal dans les sources limitees, signal de scoring, digest dedie, coverage LLM balanced et section dans la queue.
- Garde-fou doctorat ajoute: `doctoral_scope` favorise CIFRE/industrial PhD et rabaisse les doctorats academiques sans salaire/entreprise clair pour qu'ils restent opportunistes.
- Bug d'idempotence `sync-history` corrige: relancer le meme `run_name` pour rafraichir les exports preserve `new_jobs` et `returned_jobs`.
- Couverture requetes elargie sans sur-filtrage: France Travail garde maintenant les termes francais supplementaires, Jooble couvre aussi UK/DE/NL/LU, et JobSpy/Forem/Actiris interrogent plus de termes tout en gardant LinkedIn desactive.
- Robustesse run/judge durcie: timeout LLM par defaut a 360 s et logs natifs PowerShell captures sans interrompre la logique de retry.
- Hygiene GitHub ajoutee: `.gitignore` protege `private/`, `config/.env`, `runs/`, bases SQLite et logs; workflow CI Windows ajoute pour lancer les tests unitaires.
- Bundesagentur Jobsuche ajoutee comme source officielle Allemagne, avec filtre pays `Deutschland` pour eviter d'integrer les offres AMS/Autriche comme si elles etaient allemandes.
- SmartRecruiters durci: requetes dediees, pagination, detail fetch, URLs humaines, skip offres inactives/internes, dedupe detail/list, et filtres optionnels de titres.
- Delivery Hero ajoute en SmartRecruiters filtre: le smoke live retient 2 offres ciblees au lieu de 50 resultats bruites.
- Matching marche corrige: les alias pays/villes sont maintenant bornes, pour eviter les faux positifs du type `gent` dans `agentic` ou `uk` dans `Ukraine`.
- Extension geographique prudente ajoutee: Autriche, Suede, Danemark, Norvege, Finlande, Espagne et Portugal. Nordics/Autriche ont un score marche viable; Espagne/Portugal restent opportunistes avec score salaire plus bas.
- JobTechDev Sweden et NAV Arbeidsplassen Norway ajoutes comme sources officielles sans cle; Jooble et JobSpy couvrent les autres extensions sans creer de scraper fragile supplementaire.
- Smoke live cible 2026-05-09 sur les nouvelles sources officielles: Bundesagentur 145 offres dont 120 Allemagne et 25 Autriche; JobTechDev Sweden 95 offres; NAV Arbeidsplassen 83 offres dont 81 Norvege, 1 Suisse et 1 Danemark.
- Champs structures P2 ajoutes bout en bout: `deadline`, `language_check`, `remote_location_validity`, `required_years`, `experience_check`, normalisation devise/salaire annuel EUR, stockage SQLite, exports CSV/JSON/HTML/Markdown, audit, queue multi-run et payload LLM judge.
- Garde-fou niveau ajoute: les formulations `at least/minimum X years ... experience` sont extraites explicitement et les offres `too_senior` ne restent plus en queue actionnable.
- EURAXESS ajoute comme source verticale research/AI institutions, avec filtre local strict AI/data/ML pour eviter les offres recherche generalistes.
- WeWorkRemotely, SwissDevJobs et GermanTechJobs ajoutes via RSS public, apres smoke live et filtrage strict. Smoke cible: EURAXESS 9 offres brutes dont 8 gardees, WeWorkRemotely 45, SwissDevJobs 186, GermanTechJobs 186; pipeline smoke des nouvelles sources: 387 offres exportees sans erreur.
- Doctorat.gouv.fr et AcademicTransfer ajoutes comme sources doctorales opportunistes: API officielle theses/CIFRE France avec skip des sujets attribues, et API AcademicTransfer validee via token public Nuxt d'apres smoke live + repos publics GitHub. Smoke cible 2026-05-09: Doctorat.gouv.fr `CIFRE/LLM` reduit a 5 offres techniques apres filtre, AcademicTransfer `phd machine learning` a 3 offres pertinentes avec salaire/deadline.
- Extension wide ajoutee pour Estonie/Pologne/Tchequie via Jooble/JobSpy et scoring prudent; c'est un elargissement opportuniste, pas une nouvelle priorite qui doit noyer Irlande/Suisse/France/Belgique.
- Adzuna est pret cote configuration multi-pays si credentials disponibles, mais reste hors chemin actif sans cle.

## P0 A PN

- `P0`: aucun blocage runtime detecte sur le dernier run.
- `P1`: ouvrir manuellement les 43 liens `browser_required` avant candidature.
- `P1`: verifier manuellement les 11 liens `needs_review/server_error` avant candidature.
- `P1`: verifier salaire et remote quand l'offre ou le judge LLM marquent `unknown`/`weak`.
- `P2`: utiliser `start_date_check` comme signal soft et confirmer avec RH les dates `unknown`/`too_soon`; ne pas auto-skipper.
- `P2`: utiliser aussi `deadline`, `language_check`, `remote_location_validity`, `required_years`, `experience_check` et `salary_normalized_annual_eur` comme signaux soft. Les seuls cas vraiment durs sont les remote explicitement incompatibles type US-only, une langue locale obligatoire non compensee par un fit tres fort, ou un niveau `too_senior` sans signal junior/all-levels explicite.
- `P2`: tester les candidatures/messages manuellement; aucune action LinkedIn automatique de masse.
- `P3`: JobSpy API Docker seulement si tu veux une API locale permanente; le mode uv direct suffit aujourd'hui et est timeout-borne.
- `P3`: DevITJobs-like, Wellfound, ABG, Campus France Doctorat et DAAD/PhDGermany restent des tests ponctuels possibles, mais pas meilleurs que les sources ajoutees pour la routine actuelle.
- `PN`: VDAB direct, SerpAPI, Glassdoor JobSpy, ANRT sans compte, EURES API, JobsIreland API et Veolia large sont mis de cote, pas des actions ouvertes.
