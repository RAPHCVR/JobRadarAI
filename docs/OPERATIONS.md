# Operations

## Run Quotidien Manuel

```powershell
cd C:\Users\Raphael\Documents\JobRadarAI
$env:PYTHONPATH = "src"
uv run --no-project --with-editable . -- python -m jobradai run --max-per-source 1200
```

Run complet conseille quand tu veux une shortlist finale:

```powershell
.\scripts\run_daily.ps1 -Judge -JudgeRequired -JudgeLimit 120 -JudgeBatchSize 5 -JudgeSelectionMode balanced -JudgeEffort high
```

Run large ponctuel avant candidature:

```powershell
.\scripts\run_daily.ps1 -Judge -JudgeRequired -JudgeLimit 200 -JudgeBatchSize 5 -JudgeSelectionMode balanced -JudgeEffort medium -JudgeTimeoutSeconds 360
```

Ce run genere:

- `runs/latest/dashboard.html`
- `runs/latest/report.md`
- `runs/latest/jobs.csv`
- `runs/latest/jobs.json`
- `runs/latest/jobs.sqlite`
- `runs/latest/sources.json`
- `runs/latest/graduate_programs.md` et `.json`
- `runs/latest/llm_shortlist.md` et `.json` si `-Judge` est actif
- `runs/latest/link_checks.md` et `.json`
- `runs/latest/application_queue.md` et `.json`
- `runs/latest/application_messages.md` et `.json`
- `runs/latest/history_dashboard.md` et `.json`
- `runs/latest/weekly_digest.md` et `.json`
- `runs/latest/audit.md` et `.json`
- `runs/history/<timestamp>/snapshot.json`
- `runs/history/job_history.sqlite`

Le judge LLM est retente par defaut 3 fois avec 30 secondes d'attente (`-JudgeMaxAttempts`, `-JudgeRetrySeconds`). Si le judge echoue, le script regenere quand meme l'audit pour ne pas laisser `runs/latest` sans rapport frais. Avec `-JudgeRequired`, le script sort en erreur apres audit/snapshot si la shortlist LLM n'est pas produite.
`-JudgeTimeoutSeconds` controle le timeout LLM par appel batch. Le defaut est 360 secondes pour eviter de perdre un run large sur un batch lent; le script logge la progression `judge_batch_start/done` par batch et retente le judge complet si besoin.

Le link-check est actif par defaut dans `run_daily.ps1`:

- `-SkipLinkCheck` pour le desactiver.
- `-LinkCheckLimit 160` par defaut, plus les items LLM actionnables `apply_now`/`shortlist`/`maybe`.
- Les items LLM `skip` ne sont pas reverifies sauf s'ils reviennent par un futur run non juge; le top local ajoute reste filtre pour ne pas reprendre les `skip` deja connus.
- `-LinkCheckTimeoutSeconds 10`.
- `-LinkCheckWorkers 12`.

Le snapshot est actif par defaut:

- `-NoSnapshot` pour le desactiver.
- `runs/history/latest.txt` pointe vers le dernier snapshot.

Le registre multi-run est actif par defaut:

- `-SkipHistorySync` pour le desactiver.
- `-HistoryRecheckStaleLimit 40` reverifie les anciennes offres pertinentes absentes du run courant.
- `runs/latest/jobs.sqlite` reste le snapshot courant strict.
- `runs/history/job_history.sqlite` conserve l'historique dedupe avec `active`, `stale` et `expired`.
- `runs/latest/application_queue.md` concatene les offres pertinentes anciennes et nouvelles, dedupees.
- `runs/latest/application_messages.md` prepare des messages RH brouillons pour candidature manuelle.
- `runs/latest/history_dashboard.md` et `weekly_digest.md` comparent le run courant au precedent: nouvelles, revenues, disparues, stale et expirees.

## Commandes Directes

Verification:

```powershell
$env:PYTHONPATH = "src"
uv run --no-project --with-editable . -- python -m unittest discover -s tests
```

Link-check seul:

```powershell
.\scripts\run_link_check.ps1
```

Audit seul:

```powershell
.\scripts\run_audit.ps1
```

Snapshot seul:

```powershell
.\scripts\snapshot_latest.ps1
```

Historique multi-run seul:

```powershell
.\scripts\sync_history.ps1
```

Judge large seul:

```powershell
.\scripts\run_judge.ps1 -Limit 200 -BatchSize 5 -SelectionMode balanced -Effort medium -TimeoutSeconds 360
```

Sources configurees:

```powershell
$env:PYTHONPATH = "src"
uv run --no-project --with-editable . -- python -m jobradai sources
```

Digest graduate/early-careers/doctorats seul:

```powershell
$env:PYTHONPATH = "src"
uv run --no-project --with-editable . -- python -m jobradai graduate-digest
```

JobSpy Direct est un fallback Indeed controle. Il est borne par `jobspy_direct.timeout_seconds` dans `config/sources.toml`; si ce timeout est atteint, le run continue avec une source en erreur/skip au lieu de rester bloque.

## Lire Les Resultats

1. Ouvrir `runs/latest/dashboard.html`.
2. Lire `runs/latest/llm_shortlist.md` pour la shortlist finale.
3. Lire `runs/latest/graduate_programs.md` si tu veux verifier les graduate programmes/new-grad/CIFRE sans en faire le filtre principal.
4. Lire `runs/latest/application_queue.md` pour la queue dedupee multi-run.
5. Lire `runs/latest/application_messages.md` pour les brouillons RH a valider manuellement.
6. Lire `runs/latest/link_checks.md` avant de candidater.
7. Lire `runs/latest/history_dashboard.md` ou `weekly_digest.md` pour comparer au run precedent.
8. Lire `runs/latest/audit.md` pour marche/langues/VIE/remote/salaire et P0/P1/P2.
9. Importer `runs/latest/jobs.csv` dans Excel si besoin.
10. Utiliser `runs/latest/jobs.sqlite` pour le run courant, ou `runs/history/job_history.sqlite` pour l'historique.

## Exemple SQL

```sql
SELECT score, market, company, title, location, url
FROM jobs
WHERE score >= 70
ORDER BY score DESC;
```

## Planification Windows

Etat actuel verifie: `JobRadarAI-Daily` existe mais est **desactivee**. Aucun run automatique ne doit partir tant que la tache reste `Disabled`.

Le script `scripts/run_daily.ps1` ecrit ses logs dans `runs/logs` et supprime les logs plus vieux que `-LogRetentionDays` jours, 45 par defaut.

Tache planifiee simple:

```powershell
schtasks /Create /F /SC DAILY /ST 08:30 /TN "JobRadarAI-Daily" /TR "pwsh -NoProfile -ExecutionPolicy Bypass -File C:\Users\Raphael\Documents\JobRadarAI\scripts\run_daily.ps1"
```

Tache planifiee avec shortlist finale:

```powershell
schtasks /Create /F /SC DAILY /ST 08:30 /TN "JobRadarAI-Daily" /TR "pwsh -NoProfile -ExecutionPolicy Bypass -File C:\Users\Raphael\Documents\JobRadarAI\scripts\run_daily.ps1 -Judge -JudgeRequired -JudgeLimit 120 -JudgeBatchSize 5 -JudgeSelectionMode balanced -JudgeEffort high"
```

Desactiver la tache conservee:

```powershell
Disable-ScheduledTask -TaskName "JobRadarAI-Daily"
```

La reactiver plus tard:

```powershell
Enable-ScheduledTask -TaskName "JobRadarAI-Daily"
```

## LLM Judge

Configuration dans `config/.env`:

```env
JOBRADAR_LLM_BASE_URL=https://codex.raphcvr.me/v1
JOBRADAR_LLM_API_KEY=...
JOBRADAR_LLM_MODEL=gpt-5.4-mini
JOBRADAR_LLM_REASONING_EFFORT=high
JOBRADAR_LLM_TIMEOUT_SECONDS=360
```

Commande directe:

```powershell
.\scripts\run_judge.ps1 -Limit 120 -BatchSize 5 -SelectionMode balanced -Effort high
```

Modes de selection:

- `balanced`: recommande; mix top global, VIE, graduate/early-career/doctorat industriel technique et couverture marches.
- `top`: top local pur.
- `vie`: uniquement VIE, trie par fit technique/role.
- `all`: tout le corpus exporte; utile pour une passe exhaustive mais lent.

## Audit Et P0-PN

```powershell
.\scripts\run_audit.ps1
```

L'audit lit les exports existants et ecrit `runs/latest/audit.md` + `runs/latest/audit.json`. Il considere stale une shortlist ou un link-check dont le fingerprint ne correspond plus a `jobs.json`.

Interpretation:

- `P0`: blocage runtime ou donnees invalides.
- `P1`: action manuelle necessaire avant candidature.
- `P2`: durcissement ou validation utile.
- `P3+`: optimisation.
- `PN`: piste volontairement hors scope.
