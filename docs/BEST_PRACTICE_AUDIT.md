# Audit Best Practice

Derniere mise a jour: **2026-05-10**.

## Verdict

Le bon design pour ce besoin est un radar local multi-sources avec priorite aux sources propres:

1. APIs officielles et ATS publics.
2. Agregateurs a cle seulement quand ils couvrent vraiment les marches cibles.
3. Scrapers controles en fallback.
4. LinkedIn en lecture prudente ou brouillons humains, jamais en actions automatiques de masse.

Le projet suit ce modele. Il est utilisable en routine manuelle ou quotidienne desactivee/reactivable, avec exports HTML/Markdown/CSV/JSON/SQLite, logs, audit marche/VIE/langues, judge LLM, verification liens, registre multi-run et snapshots historiques.

Une interface web privee est aussi deployee sous `https://jobs.raphcvr.me` pour piloter la queue depuis desktop/mobile: image GHCR, pod Kubernetes non-root, PVC Longhorn pour `runs/`, auth par cookie signe et aucun secret ou run bake dans l'image.

## Etat Runtime Valide

Dernier full run complet valide documente: **2026-05-10 19:26 Europe/Paris**. Queue/history/audit regeneres apres correctif VIE le **2026-05-10 20:00 Europe/Paris**.

- 5493 offres retenues.
- 58 sources OK.
- 2 skips attendus: Adzuna sans credentials, JobSpy API local injoignable.
- 0 erreur source.
- 509 VIE retenus.
- 1200 offres jugees par le LLM en `wide`, effort `medium`, batch 10, concurrence 1.
- Qualite LLM: 0 `fallback_default` / 1200, transport `auto` via OpenAI SDK + `base_url` codexlb, fallback REST controle.
- 555 liens verifies en mode priority-aware.
- Snapshot: `runs/history/20260510-173933-vie-fix`.
- Registre multi-run: `runs/history/job_history.sqlite`.
- Queue dedupee: `runs/latest/application_queue.md`, 300 items actifs apres rebaseline fresh, triee par priorite LLM puis `COALESCE(last_combined_score, score)`.
- Lane VIE dediee: `runs/latest/vie_priority_queue.md`, 240 missions priorisees dont 77 deja jugees LLM et 163 VIE techniques non jugees.
- Historique: 5493 offres courantes, 5493 connues, 0 absente/stale/expired dans le ledger fresh.
- Audit dedupe 2026-05-09: le gros ecart apparent venait surtout du cumul `stale` et d'un churn Jooble cause par des parametres d'URL volatils; les IDs stables canonisent maintenant les liens Jooble.
- Audit sources 2026-05-10: les autres sources a delta ou zero count ont ete verifiees. Aucun autre faux-churn d'ID detecte; Jobicy avait seulement une strategie tag trop stricte et utilise maintenant un fallback global filtre localement. GermanTechJobs n'etait pas casse, mais le cap RSS `400` etait trop bas pour un flux live >2000 items; il passe a `1200`. France Travail pagine maintenant `3 x 50` resultats par requete et inclut `data scientist`/France data/MDM; smoke live apres correctif: **1231** IDs uniques, **10/10** anciennes absentes retrouvees, **189** offres >= 60 de score.
- P0: aucun blocage runtime detecte.
- Plateforme web: `jobradarai-web` Running 1/1 sur Kubernetes, image `ghcr.io/raphcvr/jobradarai-web:sha-0014aed`, ingress `jobs.raphcvr.me`, HTTPS `/api/health` OK, PVC synchronise avec `run_name=20260510-173933`, `queue_count=300`, `llm_count=1200`.

## Repos Et Systemes Audites

- `speedyapply/JobSpy`: meilleure brique open-source pratique pour Indeed et quelques boards generalistes; utilisee en mode direct via `uv`, sans `.venv` projet. Glassdoor a ete teste puis mis hors scope, LinkedIn reste desactive par defaut.
- `rainmanjam/jobspy-api`: option Docker/FastAPI si on veut un service local permanent avec API key, cache, rate limiting et proxy. Pas necessaire ici tant que le mode direct uv suffit.
- `stickerdaniel/linkedin-mcp-server`: MCP LinkedIn mature pour profils, jobs et messages, mais avec risque ToS et absence de rate limit fort. Non integre volontairement.
- `ChanMeng666/server-google-jobs`: MCP Google Jobs via SerpAPI. Mis de cote ici car le quota SerpAPI est trop faible pour la routine.
- `A-tavv/phd_position_tracker` et `Yukiinoa/foryourseek_v1.0`: utiles pour confirmer le pattern AcademicTransfer public `__NUXT_DATA__` + `api.academictransfer.com/vacancies/`. Integre localement sous forme minimale, sans reprendre leur crawler complet.
- Petits scrapers ATS publics Greenhouse/Lever/Ashby: aucun projet public trouve ne justifie de remplacer le code local. La bonne approche reste de garder des parsers simples et d'ajouter des boards verifies.

## Sources Officielles Et ATS

- France Travail: actif et revalide en live, meilleur socle France.
- Business France VIE: actif sans cle via l'API officielle Mon Volontariat International.
- Le Forem Open Data: actif sans cle via ODWB/Opendatasoft; apporte Wallonie-Bruxelles et une couverture partielle VDAB traduite; requetes elargies a `Data Analyst`/`Data Quality Analyst` apres audit des absentes live.
- Actiris: actif sans cle via endpoint JSON du site officiel; requetes elargies a `Data Analyst`/`Data Quality Analyst`.
- Bundesagentur Jobsuche: actif sans cle, source officielle Allemagne + Autriche, filtree par pays pour eviter de melanger `Deutschland` et `Österreich`.
- JobTechDev Sweden: actif sans cle, source officielle Suede.
- NAV Arbeidsplassen Norway: actif sans cle via endpoint public de recherche; le feed NAV tokenise n'est pas necessaire pour la decouverte.
- EURAXESS: actif sans cle comme source verticale research/AI institutions, avec filtre strict sur AI/data/ML.
- Doctorat.gouv.fr: actif sans cle via API officielle publique des propositions de theses; les sujets deja attribues sont ignores par defaut et les CIFRE/doctorats AI/data/software sont traites comme opportunistes.
- AcademicTransfer: actif sans cle durable; token public extrait de Nuxt, endpoint JSON, filtre strict PhD/doctoral + AI/data/software et salaires mensuels normalisables.
- WeWorkRemotely, SwissDevJobs, GermanTechJobs: actifs via RSS public; gardes parce qu'ils ajoutent un signal different et testable, pas seulement du volume generaliste.
- Jooble: actif, bon complement multi-pays.
- Greenhouse, Lever, Ashby: actifs via endpoints publics, meilleur ratio fiabilite/volume pour entreprises tech/IA.
- SmartRecruiters: support durci avec queries, pagination, detail fetch, URLs humaines, skip offres inactives/internes, dedupe et filtres optionnels de titres.
- Workable, Recruitee, Personio XML: supportes par le code pour ajouts ponctuels.
- HubSpot, Cohere, ElevenLabs, Synthesia, Stability AI, Modal, Poolside, H Company, Dust, Qdrant, Nabla, Doctolib et Delivery Hero: ajoutes apres verification endpoint live ou smoke cible.
- OpenAI Ashby: actif avec timeout specifique a 90 s, car le feed officiel est volumineux.
- SerpAPI Google Jobs: desactive volontairement; quota trop faible.
- VDAB: desactive volontairement; acces public/partenaire bloque, pas une action restante.
- Adzuna: configure en option multi-pays, mais inactif sans credentials. A activer seulement si les cles sont disponibles et si le ratio signal/bruit est bon au smoke.
- LLM judge OpenAI-compatible: implemente avec `gpt-5.4-mini`; le mode valide est `wide` + `JudgeLimit 1200` + batch 10 + concurrence 1 + effort `medium` + transport `auto`. Le chemin prod utilise l'OpenAI Python SDK avec `base_url` codexlb quand disponible, sortie JSON Schema stricte, fallback REST controle et quality gate. Le score final est LLM-majoritaire (`40%` local, `60%` LLM) pour laisser le judge dominer le reranking tout en gardant un garde-fou explicable.

## Garde-Fous Mis En Place

- Credentials uniquement dans `config/.env`, ignore par git.
- Pas de `.venv` projet; JobSpy tourne via `uv run --isolated --no-project`.
- JobSpy Direct est borne par `timeout_seconds = 240` et le process tree est tue au timeout; c'est un fallback Indeed, pas un blocage du pipeline.
- Dedupe soft/loose avec priorite aux sources officielles/ATS.
- Filtrage marche: France, Irlande, Suisse, Belgique, Singapour, Pays-Bas, Luxembourg, UK, Allemagne, Autriche, Suede, Danemark, Norvege, Finlande, Espagne, Portugal, Estonie, Pologne, Tchequie, Remote Europe.
- Correction de geographie pour eviter les faux positifs type `US-CA-Dublin`, `gent` dans `agentic` ou `uk` dans `Ukraine`.
- Penalites titre pour roles non coeur: product/program manager, account, business development, customer success, marketing, recruiting, solution/support engineering.
- Penalites de niveau pour profil junior/new-grad: senior, lead, principal, architect, VP, et exigences 3+/5+ ans.
- Requetes sources FR/EN: `Ingénieur IA`, `Ingénieur Data`, `Machine Learning Engineer`, `ML Engineer`, `AI Research Engineer`, `LLM Application Engineer`, `Data Scientist`.
- Veille niche ajoutee sans durcir le tri: `Analytics Engineer`, `Applied Scientist`, `Interpretability Engineer`, `Explainability Engineer`, `AI Safety Engineer`, `Knowledge Graph Engineer`, `Semantic Web Engineer`; ces termes restent sous garde-fous niveau/experience/salaire/langue.
- JobSpy Direct ne supprime plus les roles junior/graduate; seulement les stages/alternances non cibles.
- Business France VIE scanne largement l'API officielle paginee; le tri metier se fait par score combine LLM-majoritaire et lane VIE separee.
- Forem et Actiris appliquent un filtre local minimal apres recherche source pour garder les signaux data/IA/LLM/research.
- Tokenisation scoring multi-mots: `distributed systems`, `data quality`, `GitHub Actions`, `Azure DevOps`, etc.
- Seuil local a 35 pour garder un corpus de revue large; shortlist finale par judge LLM et priorites explicites.
- Jobicy rate-limit 429 traite en best-effort.
- JobSpy Direct est execute avec stdout/stderr vers fichiers temporaires et timeout process-tree sur Windows; cela evite qu'un enfant garde un pipe ouvert et bloque le run.
- `runs/latest/audit.md` verifie P0/P1/P2, langues, VIE, visa, salaire, remote et liens.
- L'audit remonte explicitement un P0/P1 si le corpus est vide, si `sources.json` est absent/illisible, si la shortlist est stale, ou si le link-check manque.
- Les timeouts socket du judge LLM sont convertis en erreur controlee pour permettre fallbacks endpoint et retries.
- Le script quotidien retente le judge, verifie les liens, regenere l'audit et snapshotte le resultat.
- Le script quotidien synchronise un ledger multi-run dedupe entre les liens et l'audit.
- `runs/latest/jobs.sqlite` reste un snapshot du run courant; les offres pertinentes anciennes sont conservees dans `runs/history/job_history.sqlite` avec `first_seen`, `last_seen`, `seen_count`, `absent_count`, `presence_status`, dernier statut lien et derniere priorite LLM.
- La queue expose `start_date_check = compatible | too_soon | unknown` comme signal soft, plus `vie_priority_queue.md`, `application_messages.md`, `history_dashboard.md` et `weekly_digest.md`.
- La queue, le judge, l'audit, les exports et SQLite exposent aussi `deadline`, `language_check`, `remote_location_validity` et `salary_normalized_annual_eur`.
- Le judge recoit aussi `required_years`, `experience_check` et `experience_evidence`; les `too_senior` LLM ou deterministes sont retires de la queue actionnable sauf override LLM `junior_ok`, tandis que les cas `stretch` restent visibles.
- Le scoring expose `doctoral_scope`: bonus leger pour CIFRE/industrial PhD, penalite explicite pour doctorat academique sans salaire/entreprise clair. Cela garde les PhD utiles visibles sans les laisser depasser les jobs/VIE/graduate mieux alignes.
- Les salaires non EUR sont normalises en estimation annuelle EUR pour le tri, sans masquer la devise d'origine.
- Les remote US-only/localisation incompatible sont penalises; les cas `restricted` restent en verification humaine.
- Le judge LLM logge la progression par batch et `run_daily.ps1` expose `-JudgeTimeoutSeconds`/`-JudgeConcurrency`/`-JudgeTransport`/`-JudgeMaxFallbackRatio`. Le calibrage codexlb actuel montre que concurrence 1 est le default prod; concurrence 2 est plus lente au smoke et concurrence 5 peut saturer la file `responses session bridge`. Batch 10 est le compromis valide; batch 20 a ete plus lent et a degrade le transport.
- Le judge supprime les anciennes shortlists avant execution et echoue si le taux de `fallback_default` depasse le seuil configure; le rebaseline 2026-05-10 a ete lance avec seuil strict 0 et a termine a 0/1200.
- Les exports CSV neutralisent les formules Excel et le dashboard n'accepte que des liens HTTP(S).
- Les erreurs HTTP redigent secrets en query/path/body.
- LinkedIn non automatise en masse.
- Plateforme web protegee par `JOBRADAR_WEB_PASSWORD`, cookie `HttpOnly`/`SameSite=Lax`/`Secure`, session signee, rate-limit login, garde `Origin` sur mutations API, secret Kubernetes, root filesystem read-only, service account token desactive.
- L'image Docker exclut `runs/`, `private/` et `config/.env`; les donnees live sont synchronisees vers le PVC par `scripts/sync_web_data.ps1`.
- `scripts/pull_web_state.ps1` permet de rapatrier les statuts/notes du PVC vers un fichier local ignore par Git.

## Reste A Faire

- `P0`: aucun blocage runtime detecte sur le dernier run complet.
- `P1`: verifier manuellement les 206 liens `browser_required` avant candidature, surtout Indeed/JobSpy et pages protegees/anti-bot.
- `P1`: verifier manuellement les 42 liens `needs_review` et le 1 `server_error` avant candidature.
- `P1`: verifier manuellement salaire et remote quand l'offre ne publie pas l'information ou quand le LLM marque `unknown`/`weak`.
- `P2`: confirmer avec RH les dates de demarrage `unknown`/`too_soon`; ne pas filtrer automatiquement sur ce signal.
- `P2`: exploiter `vie_priority_queue.md` pour les arbitrages VIE; la queue principale ne doit plus etre le seul filtre de decision sur cette voie.
- `P2`: traiter `deadline`, `language_check`, `remote_location_validity`, `required_years`, `experience_check` et `salary_normalized_annual_eur` comme signaux de tri et de verification; `too_senior` doit rester hors queue actionnable sauf override LLM junior/all-levels explicite.
- `P2/P3`: surveiller sur les prochains runs le bruit apporte par `Analytics Engineer` et `Applied Scientist`; le premier full run post-extension est correct, mais ces titres doivent rester sous garde-fous niveau/experience.
- `P2`: garder les candidatures/messages en validation humaine; aucune action LinkedIn automatique de masse.
- `P2`: apres chaque gros run local, synchroniser la plateforme web avec `scripts/sync_web_data.ps1`; ne copier `runs/state/application_state.json` qu'en migration explicite.
- `P2`: sauvegarder regulierement l'etat web avec `scripts/pull_web_state.ps1` si l'interface devient la source principale des statuts de candidature.
- `P3`: demarrer `rainmanjam/jobspy-api` en Docker seulement si tu veux une API JobSpy permanente au lieu du mode uv direct; le mode direct est maintenant timeout-borne.
- `P3`: DevITJobs-like/Wellfound/ABG/Campus France Doctorat/DAAD restent des tests ponctuels possibles, mais ne sont pas prioritaires apres l'ajout EURAXESS + Doctorat.gouv.fr + AcademicTransfer + RSS tech.
- `PN`: VDAB direct, SerpAPI, Glassdoor JobSpy, ANRT sans compte, EURES API, JobsIreland API et Veolia large ne sont plus des pistes actives. On les garde hors scope tant que l'acces/ratio signal-bruit ne change pas.
