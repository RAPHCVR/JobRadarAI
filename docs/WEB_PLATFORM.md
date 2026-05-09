# Plateforme Web Hebergee

Interface privee pour exploiter `runs/latest` depuis mobile ou desktop, sans automatiser les candidatures.

## URL

Host cible Kubernetes: `https://jobs.raphcvr.me`.

L'interface expose:

- dashboard pipeline par statut candidature;
- queue filtrable par bucket, marche, statut lien, statut utilisateur et recherche texte;
- detail offre avec signaux `start_date_check`, `deadline`, `language_check`, `remote_location_validity`, `required_years`, `experience_check`, salaire normalise quand disponible;
- edition de `application_status`, `fit_status`, priorite, notes, prochaine action, contact;
- timeline manuelle par offre;
- bouton d'ouverture du lien de candidature et copie du message RH;
- visualisation du CV PDF si `runs/cv/main.pdf` est monte, sinon source TeX.

## Securite

- Auth obligatoire en prod via `JOBRADAR_WEB_PASSWORD`.
- Cookie de session signe par `JOBRADAR_WEB_SESSION_SECRET`, `HttpOnly`, `SameSite=Lax`, `Secure` en Kubernetes.
- `JOBRADAR_WEB_API_TOKEN` optionnel pour appels API en `Authorization: Bearer`.
- Image Docker sans `runs/`, sans `private/`, sans `config/.env`.
- Donnees montees dans le PVC `jobradarai-data`.
- Pod non-root, token service account desactive, root filesystem read-only.
- Pas d'action LinkedIn, auto-apply ou bulk messaging.

## Local

Frontend:

```powershell
cd C:\Users\Raphael\Documents\JobRadarAI\web
npm install
npm run build
```

Backend sans auth locale:

```powershell
cd C:\Users\Raphael\Documents\JobRadarAI
.\scripts\run_web.ps1
```

Backend avec auth locale:

```powershell
$env:JOBRADAR_WEB_PASSWORD = "..."
$env:JOBRADAR_WEB_SESSION_SECRET = "au-moins-32-caracteres-aleatoires"
$env:JOBRADAR_WEB_COOKIE_SECURE = "false"
.\scripts\run_web.ps1
```

## Docker

```powershell
docker build -t ghcr.io/raphcvr/jobradarai-web:latest .
docker push ghcr.io/raphcvr/jobradarai-web:latest
```

Le workflow GitHub Actions `.github/workflows/web-image.yml` build et push aussi l'image GHCR sur `main` quand `Dockerfile`, `src/`, `config/` ou `web/` changent.

## Kubernetes

Manifests: `deploy/k8s/jobradarai-web`.

Deploiement:

```powershell
.\scripts\deploy_web_k8s.ps1
```

Le script:

- applique le namespace;
- copie `ghcr-secret` depuis `motus` si absent dans `jobradarai`;
- cree `jobradarai-web-secret` avec mot de passe fort si absent;
- ecrit le mot de passe initial dans `runs/state/web_initial_credentials.txt`, ignore par Git;
- applique le kustomize;
- attend le rollout.

Synchroniser le dernier run local vers le PVC:

```powershell
.\scripts\sync_web_data.ps1
```

Ce script copie `runs/latest` et, si presents, `private/main.tex` et `private/main.pdf` vers `/app/runs/cv` dans le PVC. Il ne copie pas `runs/state/application_state.json` par defaut pour eviter d'ecraser les statuts saisis dans l'interface.

## Rotation Secret

```powershell
$password = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(24)).TrimEnd("=")
$session = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(48)).TrimEnd("=")
kubectl create secret generic jobradarai-web-secret -n jobradarai `
  --from-literal=JOBRADAR_WEB_PASSWORD=$password `
  --from-literal=JOBRADAR_WEB_SESSION_SECRET=$session `
  --from-literal=JOBRADAR_WEB_API_TOKEN="" `
  --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deployment/jobradarai-web -n jobradarai
```

## Limites

- Une seule replica: c'est volontaire, car `application_state.json` est un fichier sur PVC.
- La plateforme exploite les exports courants; elle ne lance pas de candidature et ne modifie pas les sources.
- Pour rafraichir la base, lancer le pipeline normal puis `scripts/sync_web_data.ps1`.
