# Sources

## Sans Cle API

| Source | Type | Usage |
|---|---|---|
| Business France VIE | API officielle publique | Missions VIE a l'etranger via Mon Volontariat International; scan pagine large puis tri score/LLM |
| Le Forem Open Data | API open data officielle | Offres Forem/partenaires Wallonie-Bruxelles, avec une partie des offres VDAB traduites en francais |
| Actiris | Endpoint JSON public du site officiel | Offres Bruxelles/Belgique, requetes limitees et filtre local |
| Remotive | API publique | Remote global, attribution requise |
| Arbeitnow | API publique | Europe, surtout Allemagne/remote |
| RemoteOK | API publique | Remote, a filtrer strictement |
| Jobicy | API publique | Remote, variable selon tags |
| Himalayas | API publique | Remote, variable |
| JobSpy Direct | Scraper controle via uv | Indeed par defaut, LinkedIn desactive |
| Greenhouse | ATS direct | Tres fiable si board connu |
| Lever | ATS direct | Tres fiable si company slug connu |
| Ashby | ATS direct | Tres fiable si job board public connu |
| SmartRecruiters | ATS direct | Supporte mais depend du company slug exact |
| Workable/Recruitee/Personio XML | ATS direct | Supporte pour ajouts ponctuels valides |

## Avec Credentials

| Source | Type | Pourquoi |
|---|---|---|
| France Travail | API officielle | Meilleur socle France |
| Jooble | API job search | Bon fallback multi-pays |
| Adzuna | API job search | Optionnel; credentials absents aujourd'hui |

## Mis De Cote

| Source | Motif |
|---|---|
| VDAB direct | Acces public/partenaire bloque; portail OpenServices non self-service exploitable ici |
| SerpAPI Google Jobs | Quota trop faible pour un run quotidien fiable |
| JobSpy API local | Service local non demarre; le mode direct via uv suffit |

## LinkedIn

LinkedIn n'est pas utilise comme moteur d'action automatique. Si un connecteur LinkedIn est ajoute plus tard, il doit rester en lecture/faible volume et produire des drafts avec confirmation humaine.

## Graduate / Early Careers

Les requetes globales incluent maintenant une couche dediee graduate/new-grad/campus/trainee pour data, IA, ML et software engineering. Cette couche sert a ne pas rater les programmes structures, mais elle reste un signal soft:

- pas de filtre `graduate only`;
- les programmes data/AI/software/research sont favorises legerement;
- les programmes business/generalistes et stages/alternances restent penalises;
- les sources avec limite de requetes gardent un quota minimal de requetes early-career sans remplacer les requetes coeur LLM/data engineering.

## Belgique

- Forem est actif sans cle via ODWB/Opendatasoft: `https://www.odwb.be/api/explore/v2.1/catalog/datasets/offres-d-emploi-forem/records`.
- Actiris est actif sans cle via l'endpoint du site: `https://www.actiris.brussels/Umbraco/api/OffersApi/GetAllOffers`.
- VDAB direct est mis de cote: l'API officielle existe mais l'acces exploitable n'est pas public/self-service dans ce contexte. Forem expose deja certaines offres VDAB traduites en francais, donc la couverture belge reste utile sans VDAB.

## Boards ATS Verifies Actifs

- Greenhouse: Databricks, Dataiku, Google DeepMind, Intercom, Adyen, Stripe, Anthropic, Scale AI, MongoDB, Celonis, N26, Canonical, GitLab, Elastic, Datadog, Algolia, Stability AI.
- Lever: Mistral AI, Contentsquare, Qonto, Pigment.
- Ashby: OpenAI, LangChain, Perplexity AI, Cursor, Snowflake, Cohere, ElevenLabs, Synthesia, Modal, Poolside.

OpenAI a un `timeout = 90` dans `config/sources.toml`, car son feed Ashby officiel est volumineux et peut repondre au-dela du timeout HTTP global.

Les gros boards globaux et Business France VIE sont volontairement capes haut dans `scripts/run_daily.ps1` pour ne pas perdre les roles Europe/Irlande/Singapour/VIE apres tri.

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
