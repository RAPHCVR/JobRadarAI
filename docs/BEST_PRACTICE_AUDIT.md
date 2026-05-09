# Audit Best Practice

Derniere mise a jour: **2026-05-09**.

## Verdict

Le bon design pour ce besoin est un radar local multi-sources avec priorite aux sources propres:

1. APIs officielles et ATS publics.
2. Agregateurs a cle seulement quand ils couvrent vraiment les marches cibles.
3. Scrapers controles en fallback.
4. LinkedIn en lecture prudente ou brouillons humains, jamais en actions automatiques de masse.

Le projet suit ce modele. Il est utilisable en routine manuelle ou quotidienne desactivee/reactivable, avec exports HTML/Markdown/CSV/JSON/SQLite, logs, audit marche/VIE/langues, judge LLM, verification liens, registre multi-run et snapshots historiques.

## Etat Runtime Valide

Dernier full run complet valide documente: **2026-05-08 21:34 Europe/Paris**.

Note post-audit du **2026-05-08/09**: Bundesagentur Jobsuche, Delivery Hero SmartRecruiters filtre, correction du matching pays, JobTechDev Sweden, NAV Arbeidsplassen Norway, EURAXESS, Doctorat.gouv.fr, AcademicTransfer, WeWorkRemotely RSS, SwissDevJobs, GermanTechJobs, champs structures P2 dont `required_years`/`experience_check`, et extension Autriche/Nordics/Espagne/Portugal/Estonie/Pologne/Tchequie ont ete ajoutes et valides par tests/smoke cibles apres ce full run. Les compteurs ci-dessous restent ceux du run complet indique.

- 2895 offres retenues.
- 43 sources OK.
- 2 skips attendus: Adzuna sans credentials, JobSpy API local injoignable.
- 0 erreur source.
- 364 VIE retenus.
- 200 offres jugees par le LLM en `balanced`.
- 166 liens verifies en mode priority-aware.
- Snapshot: `runs/history/final-20260508-expanded-github-ready-v3`.
- Registre multi-run: `runs/history/job_history.sqlite`.
- Queue dedupee: `runs/latest/application_queue.md`, 108 items sur le dernier run apres durcissement `too_senior`/signaux structures.
- Historique: 302 nouvelles offres, 358 disparues marquees `stale`, 0 `expired`.
- P0: aucun blocage runtime detecte.

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
- Le Forem Open Data: actif sans cle via ODWB/Opendatasoft; apporte Wallonie-Bruxelles et une couverture partielle VDAB traduite.
- Actiris: actif sans cle via endpoint JSON du site officiel.
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
- LLM judge OpenAI-compatible: implemente avec `gpt-5.4-mini`, effort `high`, batchs de 5 pour eviter les timeouts proxy.

## Garde-Fous Mis En Place

- Credentials uniquement dans `config/.env`, ignore par git.
- Pas de `.venv` projet; JobSpy tourne via `uv run --isolated --no-project`.
- JobSpy Direct est borne par `timeout_seconds = 240` et le process tree est tue au timeout; c'est un fallback Indeed, pas un blocage du pipeline.
- Dedupe soft/loose avec priorite aux sources officielles/ATS.
- Filtrage marche: France, Irlande, Suisse, Belgique, Singapour, Pays-Bas, Luxembourg, UK, Allemagne, Autriche, Suede, Danemark, Norvege, Finlande, Espagne, Portugal, Estonie, Pologne, Tchequie, Remote Europe.
- Correction de geographie pour eviter les faux positifs type `US-CA-Dublin`, `gent` dans `agentic` ou `uk` dans `Ukraine`.
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
- La queue, le judge, l'audit, les exports et SQLite exposent aussi `deadline`, `language_check`, `remote_location_validity` et `salary_normalized_annual_eur`.
- Le judge recoit aussi `required_years`, `experience_check` et `experience_evidence`; les `too_senior`/`too_junior` sont retires de la queue actionnable.
- Le scoring expose `doctoral_scope`: bonus leger pour CIFRE/industrial PhD, penalite explicite pour doctorat academique sans salaire/entreprise clair. Cela garde les PhD utiles visibles sans les laisser depasser les jobs/VIE/graduate mieux alignes.
- Les salaires non EUR sont normalises en estimation annuelle EUR pour le tri, sans masquer la devise d'origine.
- Les remote US-only/localisation incompatible sont penalises; les cas `restricted` restent en verification humaine.
- Le judge LLM logge la progression par batch et `run_daily.ps1` expose `-JudgeTimeoutSeconds`; pour un run ponctuel large, `JudgeLimit 200` + `JudgeEffort medium` est plus stable que `high` sur le gateway actuel.
- Les exports CSV neutralisent les formules Excel et le dashboard n'accepte que des liens HTTP(S).
- Les erreurs HTTP redigent secrets en query/path/body.
- LinkedIn non automatise en masse.

## Reste A Faire

- `P0`: aucun blocage runtime detecte sur le dernier run complet.
- `P1`: verifier manuellement les 43 liens `browser_required` avant candidature, surtout Indeed/JobSpy et pages protegees Ashby.
- `P1`: verifier manuellement les 11 liens `needs_review/server_error` avant candidature.
- `P1`: verifier manuellement salaire et remote quand l'offre ne publie pas l'information ou quand le LLM marque `unknown`/`weak`.
- `P2`: confirmer avec RH les dates de demarrage `unknown`/`too_soon`; ne pas filtrer automatiquement sur ce signal.
- `P2`: traiter `deadline`, `language_check`, `remote_location_validity`, `required_years`, `experience_check` et `salary_normalized_annual_eur` comme signaux de tri et de verification; `too_senior` doit rester hors queue actionnable sauf signal junior/all-levels explicite.
- `P2`: garder les candidatures/messages en validation humaine; aucune action LinkedIn automatique de masse.
- `P3`: demarrer `rainmanjam/jobspy-api` en Docker seulement si tu veux une API JobSpy permanente au lieu du mode uv direct; le mode direct est maintenant timeout-borne.
- `P3`: DevITJobs-like/Wellfound/ABG/Campus France Doctorat/DAAD restent des tests ponctuels possibles, mais ne sont pas prioritaires apres l'ajout EURAXESS + Doctorat.gouv.fr + AcademicTransfer + RSS tech.
- `PN`: VDAB direct, SerpAPI, Glassdoor JobSpy, ANRT sans compte, EURES API, JobsIreland API et Veolia large ne sont plus des pistes actives. On les garde hors scope tant que l'acces/ratio signal-bruit ne change pas.
