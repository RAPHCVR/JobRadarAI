# Live Audit 2026-05-07

Audit historique conserve pour trace. L'etat courant est `docs/LIVE_AUDIT_2026-05-08.md`; depuis le 2026-05-08, VDAB direct et SerpAPI sont mis hors scope actif.

Audit realise le 2026-05-07, Europe/Paris. La tache Windows `JobRadarAI-Daily` a ete desactivee apres le run planifie de 08:30, puis un run manuel complet a ete relance et valide a 16:36 apres durcissement scoring/audit/judge.

## Verdict

- Etat runtime: OK pour le crawl quotidien et les exports.
- Etat LLM: OK. `gpt-5.4-mini` a juge 120 offres en `balanced`, effort `high`, via l'endpoint compatible OpenAI configure.
- Restrictivite: OK. Le seuil local reste bas (`min_score=35`), Business France VIE scanne large, JobSpy a ete elargi a 12 requetes et le tri dur est confie au judge LLM.
- LinkedIn: ne pas activer en quotidien. JobSpy et Ever Jobs documentent LinkedIn comme restrictif/rate-limite; le bon usage reste lecture faible volume ou brouillons manuels.

## Run Frais

- Offres retenues: 2597.
- Sources OK: 37.
- Sources ignorees: 4 (`adzuna`, `serpapi_google_jobs`, `jobspy_api`, `vdab_generic`).
- Erreurs runtime: 0.
- Remote/hybride detecte: 1123 offres, 43.2%.
- Salaire publie hors VIE: 74 offres, dont 58 >= 45000 EUR.
- Business France VIE brut: 902 offres VIE depuis l'API.
- Business France VIE retenus: 369, toutes avec indemnite mensuelle.
- Indemnites VIE observees: 2607 a 4427 EUR/mois.
- Shortlist LLM `balanced`: 120 offres jugees, 24 batchs, 11 `apply_now`, 34 `shortlist`, 12 `maybe`, 63 `skip`; 31 VIE inclus, couverture marches: Belgique 23, France 23, UK 14, Pays-Bas 13, Allemagne 12, Luxembourg 10, Irlande 8, Singapour 7, Remote Europe 5, Suisse 5.

## Couverture Marche

- UK: 423.
- France: 421.
- Irlande: 345.
- Allemagne: 319.
- Belgique: 309.
- Remote Europe: 259.
- Singapour: 239.
- Pays-Bas: 187.
- Suisse: 64.
- Luxembourg: 31.

## Sources Critiques

- Business France VIE: OK, API officielle `https://civiweb-api-prd.azurewebsites.net/api/Offers/search`, POST smoke `200`.
- France Travail: OK, OAuth + recherche Offres d'emploi v2, 270 offres brutes.
- Jooble: OK via cle locale; liens publics souvent proteges par Cloudflare en fetch serveur, donc a traiter comme source de decouverte.
- JobSpy Direct: OK via `uv run --isolated --no-project --with python-jobspy==1.1.82`.
- ATS directs: OK, Greenhouse/Ashby/Lever/Workable/etc. restent les sources les plus fiables pour candidater.
- Le Forem Open Data: OK dans le run manuel via ODWB/Opendatasoft, 20 offres data/IA/research apres filtre local.
- Actiris: OK dans le run manuel via endpoint JSON du site officiel, 53 offres data/IA/research apres filtre local; sitemap public disponible en fallback.

## Verification Liens

Echantillon verifie apres le run:

- Business France VIE top 3: HTTP 200 sur `mon-vie-via.businessfrance.fr`.
- ATS top Dataiku/Datadog/Anthropic: HTTP 200 sur Greenhouse ou pages carrieres.
- France Travail top 2: HTTP 200 sur France Travail ou URL recruteur.
- JobSpy/Indeed top 3: HTTP 403 `Security Check` en fetch serveur. Ce n'est pas un echec du crawl JobSpy, mais ces liens doivent etre ouverts/verifies dans un navigateur avant candidature.
- Jooble top 3: HTTP 403 Cloudflare en fetch serveur. Source utile pour decouverte, moins fiable pour apply final direct.

## JobSpy Et Alternatives

- `speedyapply/JobSpy` reste le meilleur fallback Python leger: installe via `uv`, pas de service persistant, supporte Indeed/LinkedIn/Glassdoor/Google/ZipRecruiter/Bayt/Naukri/BDJobs selon le README.
- Le README JobSpy indique aussi qu'Indeed est actuellement le plus fiable et que LinkedIn est le plus restrictif, souvent rate-limite, avec proxies quasi necessaires pour gros volume.
- `rainmanjam/jobspy-api` est utile seulement si tu veux un service Docker/FastAPI avec cache, rate limit et auth; le mode direct actuel suffit et evite un daemon local.
- `ever-co/ever-jobs` est plus ambitieux: NestJS, API, CLI, MCP, 160+ sources, nombreux ATS. Interessant en P2/P3 si tu veux une plateforme plus lourde, mais pas necessaire pour ce radar quotidien deja fonctionnel.
- Les petits ports/wrappers publics trouves (`alpharomercoma/ts-jobspy`, `Liohtml/RUSTJobSpy`, wrappers JobSpy divers) ne remplacent pas JobSpy aujourd'hui pour ce besoin.

## Changements Appliques

- `config/sources.toml`: JobSpy Direct passe a `max_queries=12`, `results_wanted=12`, `sites=["indeed"]`, LinkedIn toujours desactive.
- `src/jobradai/sources/optional.py`: JobSpy API respecte maintenant la meme config que JobSpy Direct et ne reactive pas LinkedIn par defaut.
- `src/jobradai/llm_judge.py`: un batch LLM incomplet echoue explicitement au lieu de remplir des jugements par defaut.
- `src/jobradai/llm_judge.py`: les timeouts socket/OS sont convertis en erreur LLM controlee pour permettre les fallbacks endpoint et les retries du script quotidien.
- `src/jobradai/audit.py`: une shortlist LLM plus vieille que `jobs.json` est ignoree pour eviter les selections stale.
- `src/jobradai/audit.py`: corpus vide ou `sources.json` absent/illisible remonte en P0/P1 au lieu d'un faux OK.
- `src/jobradai/scoring.py`: les signaux multi-mots du profil sont tokenises (`distributed systems`, `data quality`, `GitHub Actions`, `Azure DevOps`, etc.).
- `src/jobradai/pipeline.py`: les sources optionnelles distinguent maintenant vrais skips attendus et erreurs inattendues.
- `src/jobradai/http.py` + `src/jobradai/redaction.py`: les erreurs HTTP redigent les secrets en query/path/body avant export/log.
- `src/jobradai/exporters.py`: les exports CSV neutralisent les formules Excel et le dashboard n'accepte que des liens HTTP(S).
- `src/jobradai/llm_judge.py` + `src/jobradai/fingerprint.py`: la shortlist LLM porte un fingerprint du corpus pour eviter les audits stale.
- `scripts/run_daily.ps1`: le judge LLM est retry; si `-JudgeRequired` echoue, l'audit est quand meme regenere puis la tache sort en erreur.
- `scripts/*.ps1`: les executions Python passent par `uv run --no-project --with-editable . -- python`, pour eviter un `.venv` projet persistant.
- `src/jobradai/sources/public.py` + `config/sources.toml`: ajout Forem Open Data et Actiris avec filtre local minimal contre les faux positifs `engineer`.
- Scheduler Windows `JobRadarAI-Daily`: configuration conservee mais tache desactivee; aucun run automatique tant qu'elle reste `Disabled`.
- `README.md`, `docs/CURRENT_STATUS.md`, `docs/BEST_PRACTICE_AUDIT.md` et `docs/OPERATIONS.md`: etat mis a jour avec le run manuel 2026-05-07 15:53/16:36, Forem/Actiris inclus, tache toujours desactivee.

## P0 A PN

- P0: aucun blocage crawl/export/LLM sur le dernier run.
- P1: garder LinkedIn hors automatisation quotidienne; usage manuel/faible volume seulement.
- PN: SerpAPI est maintenant hors scope actif vu le quota trop limite.
- P2: envisager Ever Jobs uniquement si tu veux une plateforme serveur/MCP plus lourde que le radar actuel.
- PN: VDAB direct est maintenant hors scope actif car l'acces public/partenaire n'est pas exploitable ici.
- P3: passer la tache Windows en compte non interactif seulement si tu veux une execution meme session fermee; il faudra valider un mode de credential Windows.
