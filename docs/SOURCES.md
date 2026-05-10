# Sources

## Sans Cle API

| Source | Type | Usage |
|---|---|---|
| Business France VIE | API officielle publique | Missions VIE a l'etranger via Mon Volontariat International; scan pagine large puis tri score/LLM |
| Le Forem Open Data | API open data officielle | Offres Forem/partenaires Wallonie-Bruxelles, avec une partie des offres VDAB traduites en francais; 24 termes dont data analyst/data quality |
| Actiris | Endpoint JSON public du site officiel | Offres Bruxelles/Belgique, requetes limitees et filtre local; 24 termes dont data analyst/data quality |
| Bundesagentur Jobsuche | API publique officielle | Allemagne + Autriche data/AI/LLM, filtree par pays pour distinguer `Deutschland` et `Österreich` |
| JobTechDev Sweden | API publique officielle | Suede via JobSearch API, bon signal Stockholm/tech/data sans scraper |
| NAV Arbeidsplassen | Endpoint public officiel | Norvege via recherche publique Arbeidsplassen, bon signal data/AI mais langue norvegienne a verifier |
| EURAXESS | Portail officiel UE | Research/AI institutions, universites et organismes publics; filtre local strict AI/data/ML, plus MSCA/Doctoral Network/Industrial Doctorate seulement quand un signal technique est present |
| Doctorat.gouv.fr | API officielle publique | Propositions de theses/CIFRE en France; ignore par defaut les sujets deja attribues et filtre localement AI/data/software/recherche appliquee |
| AcademicTransfer | API publique avec token public Nuxt | PhD/doctoral jobs Pays-Bas avec salaires et deadlines; filtre strict titre PhD + AI/data/software |
| Remotive | API publique | Remote global, attribution requise |
| Arbeitnow | API publique | Europe, surtout Allemagne/remote |
| RemoteOK | API publique | Remote, a filtrer strictement |
| Jobicy | API publique | Remote global; fallback global filtre localement car les tags API sont parfois trop specifiques |
| Himalayas | API publique | Remote, variable |
| WeWorkRemotely | RSS public | Remote programming/devops; filtre local fort car le flux est global et parfois US-centric |
| SwissDevJobs | RSS public | Suisse tech avec salaires souvent publics, tres utile pour data/AI/backend |
| GermanTechJobs | RSS public | Allemagne/Autriche remote/hybride avec salaires souvent publics; scan cappe haut et borne car le RSS live depasse 2000 items et un cap trop bas provoque du churn artificiel |
| JobSpy Direct | Scraper controle via uv | Indeed par defaut, LinkedIn desactive, timeout borne pour rester un fallback non bloquant |
| Greenhouse | ATS direct | Tres fiable si board connu |
| Lever | ATS direct | Tres fiable si company slug connu |
| Ashby | ATS direct | Tres fiable si job board public connu |
| SmartRecruiters | ATS direct | Supporte queries, pagination, detail fetch, URLs humaines, skip inactif/interne et filtres de titres |
| Workable/Recruitee/Personio XML | ATS direct | Supporte pour ajouts ponctuels valides |

## Avec Credentials

| Source | Type | Pourquoi |
|---|---|---|
| France Travail | API officielle | Meilleur socle France; pagination `3 x 50` par requete, dedupe par ID et termes France data/science/MDM pour eviter de perdre les offres live hors premiere page |
| Jooble | API job search | Bon fallback multi-pays |
| Adzuna | API job search | Optionnel; configure multi-pays mais inactif sans `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` |

## Mis De Cote

| Source | Motif |
|---|---|
| VDAB direct | Acces public/partenaire bloque; portail OpenServices non self-service exploitable ici |
| SerpAPI Google Jobs | Quota trop faible pour un run quotidien fiable |
| JobSpy API local | Service local non demarre; le mode direct via uv suffit |

## LinkedIn

LinkedIn n'est pas utilise comme moteur d'action automatique. Si un connecteur LinkedIn est ajoute plus tard, il doit rester en lecture/faible volume et produire des drafts avec confirmation humaine.

## Graduate / Early Careers / Doctoral

Les requetes globales incluent maintenant une couche dediee graduate/new-grad/campus/trainee et doctorat industriel/CIFRE pour data, IA, ML, software engineering et recherche appliquee. Cette couche sert a ne pas rater les programmes structures, mais elle reste un signal soft:

- pas de filtre `graduate only`;
- les programmes data/AI/software/research sont favorises legerement;
- les CIFRE, industrial PhD et doctoral researcher data/AI/R&D sont detectes opportunistiquement;
- Doctorat.gouv.fr et AcademicTransfer apportent maintenant une couche directe sur les sujets doctoraux publics pertinents, sans remplacer le coeur jobs data/AI;
- Doctorat.gouv.fr et AcademicTransfer ont des requetes explicites interpretabilite/explicabilite/AI safety/knowledge graph/semantic web pour couvrir les niches recherche alignees avec le stage Aubay, avec filtres metier stricts;
- les PhD purement academiques sans entreprise, statut/salaire ou sujet technique clair restent a verifier et ne doivent pas noyer la queue;
- les programmes business/generalistes et stages/alternances restent penalises;
- les sources avec limite de requetes gardent un quota minimal de requetes early-career sans remplacer les requetes coeur LLM/data engineering.

## Belgique

- Forem est actif sans cle via ODWB/Opendatasoft: `https://www.odwb.be/api/explore/v2.1/catalog/datasets/offres-d-emploi-forem/records`.
- Actiris est actif sans cle via l'endpoint du site: `https://www.actiris.brussels/Umbraco/api/OffersApi/GetAllOffers`.
- VDAB direct est mis de cote: l'API officielle existe mais l'acces exploitable n'est pas public/self-service dans ce contexte. Forem expose deja certaines offres VDAB traduites en francais, donc la couverture belge reste utile sans VDAB.

## Extension Geographique Active

Extension ajoutee en P3 devenu pertinent, avec scoring prudent:

- Autriche: active via Bundesagentur/AMS, Jooble et JobSpy; bon levier Vienne/scaleups mais allemand souvent a verifier.
- Suede: active via JobTechDev Sweden, Jooble et JobSpy; bon marche anglophone tech autour de Stockholm.
- Norvege: active via NAV Arbeidsplassen, Jooble et JobSpy; tres bon salaire, anglais parfois present, norvegien a verifier.
- Danemark: actif via Jooble et JobSpy; Copenhagen est pertinent, mais pas de nouvelle API officielle simple ajoutee.
- Finlande: active via Jooble et JobSpy; Helsinki/Espoo opportunistes, volume plus limite.
- Espagne: active via Jooble et JobSpy; surtout Barcelona/Madrid, a garder seulement quand salaire/fit sont solides.
- Portugal: active via Jooble et JobSpy; surtout Lisbon/Porto, opportuniste car salaire local souvent sous cible.
- Estonie: active en wide via Jooble/JobSpy; Tallinn/Tartu utiles pour startups anglophones, volume attendu faible.
- Pologne: active en wide via Jooble/JobSpy; Warsaw/Krakow/Wroclaw/Gdansk, bon volume mais salaire/langue a verifier.
- Tchequie: active en wide via Jooble/JobSpy; Prague/Brno, opportuniste surtout si anglais et salaire compatibles.

Ces pays sont dans `target_markets`, mais Espagne/Portugal/Estonie/Pologne/Tchequie ont un scoring prudent pour eviter qu'un volume bon marche ou trop local-language noie les meilleures offres.

## Donnees Structurees

Le pipeline enrichit maintenant les offres avec des champs de decision lisibles par le scoring, le judge, la queue et les exports:

- `deadline`: date limite extraite quand la source la publie, notamment VIE, JobTechDev, NAV et EURAXESS.
- `salary_currency`, `salary_period`, `salary_min_annual_eur`, `salary_max_annual_eur`, `salary_normalized_annual_eur`: normalisation indicative des salaires EUR/CHF/GBP/USD/SEK/NOK/DKK/PLN/CZK.
- `language_check = english_ok | french_ok | local_language_required | unknown`: signal soft pour ne pas jeter une offre avant lecture humaine.
- `remote_location_validity = compatible | restricted | incompatible | unknown`: detecte surtout les remote US-only ou les contraintes de residence; `restricted` reste a verifier.
- `required_years`, `experience_check = junior_ok | stretch | too_senior | unknown`, `experience_evidence`: extraction explicite des annees et du risque seniorite pour que le judge LLM ne doive pas retrouver seul une phrase noyee dans une longue description.

## Boards ATS Verifies Actifs

- Greenhouse: Databricks, Dataiku, Google DeepMind, Intercom, HubSpot, Adyen, Stripe, Anthropic, Scale AI, MongoDB, Celonis, N26, Canonical, GitLab, Elastic, Datadog, Algolia, Stability AI.
- Lever: Mistral AI, Contentsquare, Qonto, Pigment.
- Ashby: OpenAI, LangChain, Perplexity AI, Cursor, Snowflake, Cohere, ElevenLabs, Synthesia, Modal, Poolside, H Company, Dust, Qdrant, Nabla.
- Greenhouse additionnel: Doctolib.
- SmartRecruiters: Delivery Hero, avec queries limitees, detail fetch pour URLs humaines et filtres de titres; Veolia a ete teste mais laisse hors scope actif car le signal courant est trop bruite pour le profil.

OpenAI a un `timeout = 90` dans `config/sources.toml`, car son feed Ashby officiel est volumineux et peut repondre au-dela du timeout HTTP global.

Les gros boards globaux et Business France VIE sont volontairement capes haut dans `scripts/run_daily.ps1` pour ne pas perdre les roles Europe/Irlande/Singapour/VIE apres tri.

## Extensions Candidates

Ces sources ne sont pas actives dans la routine. Elles sont gardees comme backlog source, avec une condition claire d'integration.

| Source | Priorite | Decision |
|---|---|---|
| Welcome to the Jungle | P2 | Pertinent surtout France/startups/scaleups. A integrer seulement via sitemaps publics `job-listings.*.xml.gz` + JSON-LD `JobPosting`, avec cap strict et filtres locaux. Ne pas crawler la recherche interne `jobs?query=*`. |
| ABG | P3 | Portail doctoral/recherche utile mais endpoint Prototype/AJAX HTML observe trop large/bruite, meme avec filtres. A garder pour smoke ponctuel ou si un endpoint JSON propre est identifie. |
| Campus France / Recherche en France | P3 | Public avec endpoint DataTables `doctorat.campusfrance.org/phd/offers/ajax_dtlist`, mais redondant ADUM/Doctorat.gouv, plus lent et melange doctorats/stages/post-docs. Fallback decouverte, pas routine. |
| ANRT CIFRE | PN | Source officielle CIFRE tres pertinente humainement, mais offres/candidatures derriere compte. A traiter manuel si acces disponible, pas automatisation publique. |
| DAAD / PhDGermany | P3 | Potentiel Allemagne doctorale, portail public avec indices API `api.daad.de`, mais pas encore superieur au mix EURAXESS + AcademicTransfer + moteurs existants pour ce profil. A tester ponctuellement si on pousse l'axe paid PhD Allemagne. |
| ETH / EPFL | P3 | Pages officielles publiques utiles en decouverte ponctuelle (`jobs.ethz.ch`, page Working at EPFL), mais pas de source API/RSS stable ajoutee; a integrer seulement si un endpoint exploitable et filtrable est identifie. |
| DevITJobs-like | P3 | Non actif aujourd'hui: moins differenciant que SwissDevJobs/GermanTechJobs pour le profil, a tester seulement si on veut encore plus de volume global/remote. |
| Glassdoor via JobSpy | PN | Teste le 2026-05-09 avec `python-jobspy==1.1.82`: 0 resultat sur Paris/Dublin/Berlin/London/remote, erreurs Glassdoor `location not parsed` / `Error encountered in API response`, alors qu'Indeed repond dans le meme smoke. Mis de cote definitivement pour ce radar. |
| StepStone / jobs.de / boards DE/BE prives | P3 | Gros volume, mais scraping souvent fragile ou bruite. Bundesagentur + ATS directs sont prioritaires. |
| Wellfound / YC Work at a Startup | P3 | Potentiellement utile startup/AI, mais souvent login/US-heavy; a garder en recherche ponctuelle. |
| Monster / Talent.com / SimplyHired-like | PN | Trop de doublons, SEO pages et bruit pour la valeur attendue aujourd'hui. |

## Systemes Existants Regardes

- `speedyapply/JobSpy` reste la bonne brique locale legere pour Indeed et autres boards supportes; dans ce radar on garde Indeed seulement en routine. Glassdoor a ete teste et mis hors scope, LinkedIn reste desactive.
- `ever-co/ever-jobs` est interessant si on veut une plateforme serveur/MCP multi-sources lourde. Pas integre ici: cela ferait basculer le radar local vers un produit serveur a maintenir.
- `A-tavv/phd_position_tracker` et `Yukiinoa/foryourseek_v1.0` ont confirme la bonne approche AcademicTransfer: extraire le token public Nuxt `__NUXT_DATA__`, puis appeler `api.academictransfer.com/vacancies/` en JSON. Le code local integre seulement ce pattern minimal, avec filtres metier plus stricts.
- Les petits scrapers WTTJ trouves sont surtout Selenium/one-off et ne justifient pas une dependance. Si WTTJ est ajoute, l'approche propre reste sitemap public + JSON-LD.
- `navikt/pam-stilling-feed` existe pour la Norvege mais fonctionne par consommateurs/tokens; le radar utilise donc l'endpoint public de recherche Arbeidsplassen, suffisant pour la decouverte.
- Recherches GitHub ciblees `doctorat.gouv.fr/api/propositions-these`, `doctorat.campusfrance.org/phd/offers/ajax_dtlist` et `abg.asso.fr/fr/candidatOffres/recherche`: aucun projet public reutilisable propre trouve. Pas de crawler tiers a integrer pour ces trois sources.

## Pistes Testees Et Non Retenues

- EURES: pas d'endpoint public stable/pratique valide au smoke; trop fragile pour le chemin quotidien.
- JobsIreland: portail public visible, mais aucun endpoint API simple valide au smoke.
- Glassdoor via JobSpy: non retenu definitivement. Le smoke compare a Indeed prouve que le wrapper fonctionne, mais Glassdoor renvoie 0 resultat et des erreurs API/location sur les marches cibles; l'ajouter ne ferait qu'ajouter de l'instabilite sans signal utile.
- ABG: endpoint AJAX public observe (`/fr/candidatOffres/recherche`, formulaire `criteria[...]`), mais il retourne un volume trop large meme avec filtres; pas assez propre pour la routine actuelle.
- Campus France / Recherche en France: endpoint DataTables public observe (`/phd/offers/ajax_dtlist`) mais le smoke AJAX a ete lent et la source duplique largement Doctorat.gouv/ADUM; pas prioritaire en routine.
- DAAD / PhDGermany: portail public observe, mais garde en P3 paid PhD Allemagne tant que l'axe doctorat n'est pas prioritaire.
- ETH / EPFL: pages publiques observees, anciennes URLs directes 404; garder en decouverte ponctuelle plutot que parser fragile.
- Veolia SmartRecruiters large: contient ponctuellement des programmes graduate interessants, mais le flux courant remonte surtout des offres hors cible, alternance/stage ou business; a garder comme recherche manuelle ponctuelle, pas source active.

## Ajouter Une Source ATS

Verifier l'endpoint en PowerShell:

```powershell
$ProgressPreference = 'SilentlyContinue'
(Invoke-WebRequest -UseBasicParsing -Uri 'https://boards-api.greenhouse.io/v1/boards/COMPANY/jobs?content=true' -TimeoutSec 15).StatusCode
```

Puis ajouter dans `config/sources.toml`:

```toml
[[ats_feeds]]
name = "Example"
type = "greenhouse"
url = "https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true"
markets = ["france", "ireland", "remote_europe"]
```

Pour un feed officiel volumineux:

```toml
timeout = 90
retries = 2
```

Pour un SmartRecruiters bruite, ajouter des filtres de titres:

```toml
queries = ["data engineer", "machine learning", "AI Engineer", "AI Research Engineer"]
include_title_keywords = ["data engineer", "machine learning engineer", "ml engineer", "ai engineer", "ai research engineer"]
exclude_title_keywords = ["senior", "staff", "intern", "manager"]
```

## Verification Liens

Le link-check verifie les liens de la shortlist plus les meilleurs scores:

```powershell
.\scripts\run_link_check.ps1
```

Statuts:

- `direct_ok`: lien serveur directement exploitable.
- `browser_required`: agregateur, anti-bot ou verification humaine; ouvrir manuellement.
- `needs_review`: HTTP non bloquant mais a verifier.
- `server_error`: erreur temporaire probable cote site.
- `expired`: offre probablement retiree.
- `unreachable`: lien injoignable.
