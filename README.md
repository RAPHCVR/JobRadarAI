# JobRadarAI

Radar local pour trouver, filtrer et classer des offres **data / IA / LLM orchestration / recherche appliquee** sur France, Europe, Irlande, Suisse, Belgique et Singapour.

L'objectif est pragmatique:

- utiliser d'abord des sources propres: APIs publiques, ATS directs, sources officielles;
- garder les scrapers et LinkedIn en fallback controle, jamais en auto-apply massif;
- scorer les offres selon le fit technique, la praticite marche, la langue, le visa, le salaire, le remote et les missions **VIE**;
- traiter les roles **graduate / new-grad / early-careers** comme un signal soft dedie quand ils restent data/IA/software, sans filtrer le corpus principal sur ce critere;
- produire des exports exploitables sans dependance lourde: HTML, Markdown, CSV, JSON, SQLite;
- garder un historique date des runs pour comparer les resultats dans le temps.

## Etat Actuel

Dernier run valide: **2026-05-08 21:34 Europe/Paris**, lance manuellement en mode complet apres elargissement prudent des requetes France Travail/Jooble/JobSpy/Forem/Actiris et durcissement du timeout LLM: collecte, exports, judge LLM elargi, verification liens priority-aware, registre multi-run, audit et snapshot. Les exports valides sont dans `runs/latest`; le snapshot final est `runs/history/final-20260508-expanded-github-ready-v3`.

La tache Windows `JobRadarAI-Daily` est actuellement **desactivee**. Aucun run automatique ne doit partir tant qu'elle n'est pas reactivee manuellement.

Resultat runtime du dernier run:

- 2895 offres retenues.
- 43 sources OK, 2 sources ignorees attendues, 0 erreur.
- 364 missions VIE Business France retenues.
- 1319 offres avec signal remote/hybride, soit 45.6%.
- 107 offres hors VIE avec salaire publie, dont 81 >= 45000 EUR/an.
- 200 offres jugees par le LLM en selection `balanced`: 12 `apply_now`, 57 `shortlist`, 32 `maybe`, 99 `skip`; les 7 offres graduate/early-career high/medium du corpus sont incluses.
- 62 signaux graduate/early-career detectes, dont 7 high/medium; les 7 sont juges par le LLM et remontent dans la queue.
- 166 liens verifies en mode priority-aware: 112 `direct_ok`, 43 `browser_required`, 11 `needs_review`, 0 `unreachable`.
- 144 items dans la queue multi-run dedupee `runs/latest/application_queue.md`.
- 302 nouvelles offres et 358 offres disparues marquees `stale` dans le ledger; 0 lien expire dans l'historique courant.
- Checks queue: start `{'unknown': 142, 'too_soon': 1, 'compatible': 1}`, salaire `{'below_min': 28, 'unknown': 42, 'meets_or_likely': 74}`, remote `{'meets': 43, 'weak': 101}`.

Le scoring integre `private/main.tex`, le stage Aubay AI Researcher fev. 2026 - juil. 2026, et les contraintes courantes: profil junior/new-grad, minimum 45k EUR/an, preference hybride/remote avec au moins 2 jours de teletravail vises, demarrage cible a partir d'aout/septembre 2026 comme signal soft a confirmer avec RH, preference grandes villes et focus recherche IA/explicabilite mecanistique.

## Sources Actives

Fonctionne sans cle API:

- Business France VIE, source officielle Mon Volontariat International.
- Le Forem Open Data, via ODWB/Opendatasoft.
- Actiris, via endpoint JSON du site officiel.
- Remotive.
- Arbeitnow.
- RemoteOK.
- Jobicy.
- Himalayas.
- ATS directs verifies: Databricks, Dataiku, Google DeepMind, Mistral AI, Contentsquare, Intercom, Adyen, Stripe, Anthropic, Scale AI, MongoDB, Celonis, N26, Canonical, GitLab, Elastic, OpenAI, LangChain, Perplexity AI, Cursor, Snowflake, Datadog, Algolia, Qonto, Pigment, Cohere, ElevenLabs, Synthesia, Stability AI, Modal, Poolside.
- JobSpy Direct via `uv`, sur Indeed par defaut, sans LinkedIn.

Actif avec credentials locaux:

- France Travail.
- Jooble.

Ignorees attendues sur le dernier run:

- Adzuna: credentials absents.
- JobSpy API local: service `http://127.0.0.1:8000` injoignable, remplace par JobSpy Direct.

Mis de cote volontairement:

- VDAB direct: bloque cote acces public/partenaire; le portail OpenServices n'offre pas d'onboarding self-service exploitable ici. On ne le traite plus comme un P restant.
- SerpAPI Google Jobs: desactive a cause du quota trop faible; a ne pas utiliser en routine.

## Lancer

Depuis PowerShell:

```powershell
cd C:\Users\Raphael\Documents\JobRadarAI
$env:PYTHONPATH = "src"
uv run --no-project --with-editable . -- python -m jobradai run --max-per-source 1200
```

Run complet conseille quand tu veux une shortlist finale exploitable:

```powershell
.\scripts\run_daily.ps1 -Judge -JudgeRequired -JudgeLimit 120 -JudgeBatchSize 5 -JudgeSelectionMode balanced -JudgeEffort high
```

Run large ponctuel avant une grosse session candidature:

```powershell
.\scripts\run_daily.ps1 -Judge -JudgeRequired -JudgeLimit 200 -JudgeBatchSize 5 -JudgeSelectionMode balanced -JudgeEffort medium -JudgeTimeoutSeconds 360
```

Ce script fait maintenant, par defaut:

1. collecte + exports;
2. judge LLM si `-Judge` est passe;
3. verification de liens;
4. synchronisation du registre multi-run;
5. audit P0/P1/P2;
6. snapshot dans `runs/history/<timestamp>`.

JobSpy est lance via `uv run --isolated --no-project --with python-jobspy==1.1.82`; il n'a pas besoin d'une installation globale et ne cree pas d'environnement projet persistant. La version est pinnee pour eviter une resolution PyPI dynamique non controlee dans la tache quotidienne.

## Exports

- `runs/latest/dashboard.html`
- `runs/latest/report.md`
- `runs/latest/jobs.csv`
- `runs/latest/jobs.json`
- `runs/latest/jobs.sqlite`
- `runs/latest/sources.json`
- `runs/latest/graduate_programs.md`
- `runs/latest/graduate_programs.json`
- `runs/latest/llm_shortlist.md`
- `runs/latest/llm_shortlist.json`
- `runs/latest/link_checks.md`
- `runs/latest/link_checks.json`
- `runs/latest/application_queue.md`
- `runs/latest/application_queue.json`
- `runs/latest/application_messages.md`
- `runs/latest/application_messages.json`
- `runs/latest/history_dashboard.md`
- `runs/latest/history_dashboard.json`
- `runs/latest/weekly_digest.md`
- `runs/latest/weekly_digest.json`
- `runs/latest/audit.md`
- `runs/latest/audit.json`
- `runs/history/latest.txt`
- `runs/history/job_history.sqlite`
- `runs/history/<timestamp>/snapshot.json`

## Tests

```powershell
cd C:\Users\Raphael\Documents\JobRadarAI
$env:PYTHONPATH = "src"
uv run --no-project --with-editable . -- python -m unittest discover -s tests
```

## Configuration

- `config/profile.toml`: profil cible, mots-cles forts/faibles, titres pertinents.
- `config/markets.toml`: scoring marche, praticite, langue, visa, salaire.
- `config/sources.toml`: sources, requetes, ATS directs.
- `config/secrets.example.env`: modele de credentials. Copier en `config/.env` si tu veux activer des APIs a cle.

Credentials et secrets restent dans `config/.env` ou variables d'environnement, jamais dans le code.

## Philosophie De Scoring

Le score final combine:

- fit technique: data engineering, LLM, RAG, MLOps/LLMOps, orchestration, recherche, cloud;
- role: seniorite et proximite du titre;
- marche/praticite: Irlande, Suisse, Belgique, Singapour, France, Pays-Bas, Luxembourg, UK, Allemagne, Remote Europe;
- source: ATS/direct/officiel mieux note que scraper;
- fraicheur;
- signal salaire;
- VIE Business France: indemnite mensuelle traitee a part, car elle n'est pas comparable a un brut annuel CDI;
- graduate/new-grad/early-careers: bonus faible et explicite si le role est data/IA/software/research; penalite neutralisee pour le label seul, mais les stages/alternances et programmes business restent penalises.

Le dashboard et les exports gardent les raisons explicites pour eviter une boite noire.

## Garde-Fous LinkedIn

Ce projet ne fait pas de bulk connect, bulk message ou auto-apply LinkedIn. Le mode recommande reste:

- 10 a 20 candidatures tres ciblees par semaine;
- CV adapte;
- message recruteur prepare mais valide manuellement;
- sources ATS/officielles pour les donnees.

## Ajouter Des ATS

Ajouter dans `config/sources.toml`:

```toml
[[ats_feeds]]
name = "Example"
type = "greenhouse"
url = "https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true"
markets = ["ireland", "france", "remote_europe"]
```

Types supportes:

- `greenhouse`
- `lever`
- `ashby`
- `smartrecruiters`
- `workable`
- `recruitee`
- `personio_xml`

Les feeds ATS peuvent definir `timeout = 90` ou `retries = 3` si un board officiel est volumineux. OpenAI utilise cet override car son feed Ashby pese environ 10.7 MB et peut repondre en plus d'une minute.

## Commandes Utiles

Verification liens seule:

```powershell
.\scripts\run_link_check.ps1
```

Le link-check verifie les items LLM actionnables `apply_now`/`shortlist`/`maybe`, puis ajoute le top local jusqu'a la limite configuree en ignorant les items deja marques `skip` par le judge courant. Sans shortlist LLM fraiche, il retombe sur le top local.

Audit seul:

```powershell
.\scripts\run_audit.ps1
```

Snapshot seul:

```powershell
.\scripts\snapshot_latest.ps1
```

Synchronisation historique seule:

```powershell
.\scripts\sync_history.ps1
```

Digest graduate/early-careers seul, depuis le `jobs.json` courant:

```powershell
$env:PYTHONPATH = "src"
uv run --no-project --with-editable . -- python -m jobradai graduate-digest
```

Judge seul:

```powershell
.\scripts\run_judge.ps1 -Limit 120 -BatchSize 5 -SelectionMode balanced -Effort high
```

Judge large ponctuel:

```powershell
.\scripts\run_judge.ps1 -Limit 200 -BatchSize 5 -SelectionMode balanced -Effort medium -TimeoutSeconds 360
```

Le judge ne remplace pas le score local: il sert a corriger les faux positifs de niveau, notamment les offres trop senior/lead/VP, a trier les VIE larges, a garder une couverture graduate/early-careers technique quand elle existe, et a produire un angle de candidature par offre. Le mode `balanced` garde du top global mais force aussi une couverture VIE, early-career et marches cibles.
