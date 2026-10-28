# DataDrift — Dataset Version & Schema Quality Monitor

DataDrift is a small data registry for ML teams. Every time a training dataset is refreshed, the new
snapshot is registered with its version tag, record count, missing-value percentage and a **drift score**
(0.0 – 1.0) that measures how far it has moved from the last verified baseline. Send a column profile and the
backend computes the score itself (Jensen-Shannon distance per column, see
[How drift is scored](#how-drift-is-scored)); send a score and it is used as given. Snapshots at or above the
drift threshold (0.30) are flagged `DRIFT_DETECTED` and blocked from training until someone reviews them.
Flagging drift raises a Prometheus alert that shows up in Grafana.

The application is deliberately small. The point of the project is the path it takes from a laptop to a
monitored Kubernetes cluster: tests → containers → CI/CD → security scan → registry → Terraform →
Kubernetes/Helm → GitOps with Argo CD → Prometheus/Grafana.

> **Presentation and video:** everything for the review is in [`demo/`](demo/): the slide deck
> ([`DataDrift-Capstone-Presentation.pptx`](demo/DataDrift-Capstone-Presentation.pptx), also as
> [PDF](demo/DataDrift-Capstone-Presentation.pdf)) and the video walkthrough
> ([`DataDrift-Demo.mp4`](demo/DataDrift-Demo.mp4), 86 MB; or **watch it online on
> [Loom](https://www.loom.com/share/e653b00a16604e28bbdb0d13955c33af)** without downloading). Screenshots of the
> running project are in
> [`screenshots/`](screenshots/) (see [Screenshots](#screenshots)).

```text
 Developer ── git push ──► GitHub ──► GitHub Actions
                                       ├─ ruff + pytest (backend)
                                       ├─ npm build (frontend)
                                       ├─ terraform validate + helm lint
                                       ├─ docker build ─► Trivy scan (fail on HIGH/CRITICAL)
                                       ├─ push to GHCR, tagged with the commit SHA
                                       └─ commit the new tag to helm/datadrift/values-gitops.yaml
                                                    │
                     Terraform: AWS VPC + EKS        │   (local demo: kind cluster)
                                                    ▼
                          Argo CD (in the cluster) watches Git and syncs helm/datadrift
                     ┌──────────────── Ingress (nginx) ─────────────────┐
                     │  /            → frontend  (React + Nginx, 2 pods) │
                     │  /api, /docs  → backend   (FastAPI, 2–5 pods, HPA)│
                     └───────────────────────────┬──────────────────────┘
                                                 ▼
                                      PostgreSQL (StatefulSet + PVC)
                 Prometheus ◄── /metrics (ServiceMonitor) ── backend
                     │  PrometheusRule: DatasetDriftDetected
                     ▼
                  Grafana dashboard "DataDrift — Registry & API Overview"
```

## Tech stack

| Layer | Tools |
|-------|-------|
| Frontend | React 19, Vite, plain CSS, served by unprivileged Nginx |
| Backend | FastAPI, SQLAlchemy 2, Alembic, Pydantic, prometheus-fastapi-instrumentator |
| Database | PostgreSQL 16 |
| Testing / quality | pytest (SQLite test DB), ruff |
| Containers | Docker (multi-stage frontend, non-root images), Docker Compose |
| CI/CD | GitHub Actions, GitHub Container Registry (GHCR) |
| Security | Trivy image scanning |
| Infrastructure as Code | Terraform (AWS VPC, subnets, NAT, IAM, EKS, managed node group) |
| Orchestration | Kubernetes (kind locally, EKS in AWS), Helm, ingress-nginx, HPA, metrics-server |
| GitOps | Argo CD (automated sync with prune and self-heal), image tags written back by CI |
| Observability | kube-prometheus-stack: Prometheus, Alertmanager, Grafana |

## Repository layout

```text
datadrift-capstone/
├── backend/                 FastAPI app, Alembic migrations, pytest suite, Dockerfile
│   ├── app/                 main.py (routes), models.py, schemas.py, db.py, config.py, metrics.py
│   ├── alembic/versions/    0001_create_datasets.py, 0002_add_drift_profiles.py
│   └── tests/               conftest.py (SQLite test DB), test_api.py (14), test_drift.py (15)
├── frontend/                React dashboard, Nginx template, multi-stage Dockerfile
├── docker-compose.yml       postgres + backend + frontend
├── .github/workflows/       ci-cd.yml
├── terraform/               AWS VPC + EKS
├── k8s/                     namespace, kind cluster config, ingress-nginx / metrics-server values
├── helm/datadrift/          Helm chart (deployments, services, ingress, HPA, Postgres,
│                            ServiceMonitor, PrometheusRule, Grafana dashboard);
│                            values-gitops.yaml holds the image tags Argo CD deploys
├── argocd/                  Argo CD install values + the DataDrift Application manifest
├── monitoring/              kube-prometheus-stack values (Prometheus + Grafana)
├── scripts/                 seed, cluster-up, argocd-up, deploy-local, load-test
├── demo/                    presentation deck (PPTX + PDF) and video walkthrough
└── screenshots/             screenshots of the running project
```

## The application

### Data model — `datasets` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer | primary key |
| `dataset_name` | varchar(120) | e.g. `customer-churn` |
| `version_tag` | varchar(60) | e.g. `v1.2-cleaned`; unique per dataset |
| `record_count` | integer | rows in the snapshot |
| `missing_pct` | float | % of missing values |
| `drift_score` | float | 0.0 – 1.0, enforced by a check constraint |
| `status` | varchar(20) | `VERIFIED`, `DRIFT_DETECTED` or `ARCHIVED` |
| `drift_method` | varchar(20) | `provided`, `computed`, `baseline` or `unscored` |
| `profile` | json | column → histogram (bucket → count), optional |
| `column_drift` | json | per-column drift when the score was computed |
| `baseline_id` | integer | the snapshot it was compared with (foreign key, `SET NULL` on purge) |
| `created_at`, `updated_at` | timestamptz | |

The table is created by the Alembic migration `0001_create_datasets.py`; `0002_add_drift_profiles.py` adds the
drift columns. The backend
container runs `alembic upgrade head` before starting. A Postgres advisory lock stops several replicas from
migrating at the same time.

### API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | liveness: the process is up |
| GET | `/ready` | readiness: the database answers |
| GET | `/metrics` | Prometheus metrics |
| GET | `/api/datasets` | list snapshots (optional `?status=DRIFT_DETECTED`) |
| GET | `/api/datasets/summary` | counts per status and the average drift score |
| GET | `/api/datasets/{id}` | one snapshot |
| POST | `/api/datasets` | register a snapshot; drift is computed from its profile (or taken as given), status follows |
| PUT | `/api/datasets/{id}` | update drift score / status (the UI's **Flag drift** button) |
| DELETE | `/api/datasets/{id}` | archive; `?purge=true` deletes permanently |

### How drift is scored

`backend/app/drift.py`. A snapshot can carry a `profile`: for each column, a histogram of counts per bucket or
category, for example `{"plan": {"basic": 600, "pro": 300, "team": 100}}`.

1. **Baseline.** The newest `VERIFIED` snapshot of the same dataset that has a profile. Flagged snapshots never
   become the baseline, so a drifted release can't quietly reset the reference.
2. **Per column.** Both histograms are normalised and compared with the Jensen-Shannon distance (base 2):
   symmetric, 0.0 for identical distributions, 1.0 for no overlap. A column that appears in only one of the two
   profiles is a schema change and scores 1.0.
3. **Snapshot score.** The worst column. It is stored with the per-column scores and the baseline's id.

| Request | `drift_method` | `drift_score` |
|---------|----------------|---------------|
| `drift_score` given (with or without a profile) | `provided` | as given |
| profile, no earlier verified profile for this dataset | `baseline` | 0.0 |
| profile, baseline found | `computed` | worst column's distance |
| neither | `unscored` | 0.0 |

A `PUT` with a new `drift_score` sets `drift_method` back to `provided`.

Interactive Swagger docs: `http://localhost:8000/docs` (Compose) or `http://datadrift.localtest.me/docs` (Kubernetes).

### Custom metrics

| Metric | Type | Meaning |
|--------|------|---------|
| `datadrift_datasets{status}` | gauge | snapshots per status |
| `datadrift_avg_drift_score` | gauge | average drift of non-archived snapshots |
| `datadrift_drift_score{dataset_name,version_tag,status}` | gauge | drift score of each snapshot |
| `datadrift_drift_flags_total{dataset_name}` | counter | times a snapshot entered `DRIFT_DETECTED` |
| `datadrift_snapshots_registered_total` | counter | snapshots registered |
| `http_requests_total`, `http_request_duration_seconds` | counter / histogram | request rate, errors, latency |

## Prerequisites

| Tool | Needed for |
|------|-----------|
| Docker (with Compose v2) | everything: Compose stack, image builds, and the kind cluster's nodes |
| Python 3.12 | backend tests and lint |
| Node 22 | frontend build outside Docker (optional) |
| kind, kubectl, Helm 3+ | Kubernetes, Helm and monitoring sections |
| Terraform ≥ 1.6 | infrastructure code (an AWS account is optional, see below) |
| curl, jq | `seed.sh`, `load-test.sh` and the API examples below |

Which scripts need a **running kind cluster** (create it once with `./scripts/cluster-up.sh`):

| Script / command | Needs the kind cluster? |
|------------------|-------------------------|
| `scripts/seed.sh` (default URL) | no, it targets the Compose stack on `localhost:3000` |
| `scripts/seed.sh http://datadrift.localtest.me` | yes |
| `scripts/cluster-up.sh` | no, it creates the cluster |
| `scripts/argocd-up.sh` | yes |
| `scripts/deploy-local.sh` | yes |
| `scripts/load-test.sh` | yes, it targets the Ingress and drives the HPA |
| Prometheus / Grafana port-forwards | yes |

The cluster runs inside the Docker container `datadrift-control-plane`. After a Docker or machine restart,
bring it back with `docker start datadrift-control-plane` (data on the Postgres volume is kept), and restart
any port-forwards.

## Run and test the full project

Every command below runs from the repository root unless a step says otherwise. Steps 1–6 work without a
cluster; steps 7–11 need the kind cluster (see [Prerequisites](#prerequisites)).

### 1. Clone and start the stack with Docker Compose

```bash
git clone https://github.com/KavyaDhyani/datadrift-capstone.git
cd datadrift-capstone
docker compose up --build -d --wait     # postgres, backend (runs the migration first), frontend
docker compose ps                       # all three services Up; backend and postgres (healthy)
./scripts/seed.sh                       # registers nine sample snapshots, three of them scored from profiles
```

| URL | What |
|-----|------|
| http://localhost:3000 | DataDrift UI |
| http://localhost:8000/docs | Swagger UI for the API |
| http://localhost:8000/health | liveness, returns `{"status":"UP"}` |
| http://localhost:8000/metrics | Prometheus metrics |

### 2. Test the REST API (GET, POST, PUT, DELETE)

```bash
API=http://localhost:8000
curl -s $API/health
curl -s $API/ready                                         # checks the database connection
curl -s $API/api/datasets | jq                              # list all snapshots
curl -s "$API/api/datasets?status=VERIFIED" | jq length     # filter by status
curl -s $API/api/datasets/summary | jq                      # counts and average drift

# POST: register a snapshot; drift >= 0.30 is flagged automatically
ID=$(curl -s -X POST $API/api/datasets -H 'Content-Type: application/json' \
  -d '{"dataset_name":"demo-set","version_tag":"v1","record_count":5000,"missing_pct":1.2,"drift_score":0.42}' \
  | jq .id)
curl -s $API/api/datasets/$ID | jq '{dataset_name, status}'  # DRIFT_DETECTED

# POST with a profile and no score: the backend computes drift against the last verified baseline
P='{"plan":{"basic":600,"pro":300,"team":100}}'
curl -s -X POST $API/api/datasets -H 'Content-Type: application/json' \
  -d "{\"dataset_name\":\"profiled\",\"version_tag\":\"v1\",\"record_count\":1000,\"profile\":$P}" | jq .drift_method   # "baseline"
P='{"plan":{"basic":100,"pro":300,"team":600}}'
curl -s -X POST $API/api/datasets -H 'Content-Type: application/json' \
  -d "{\"dataset_name\":\"profiled\",\"version_tag\":\"v2\",\"record_count\":1000,\"profile\":$P}" \
  | jq '{drift_score, status, column_drift}'                                  # 0.5346, DRIFT_DETECTED

# PUT: mark it verified (what the UI's "Mark verified" button does)
curl -s -X PUT $API/api/datasets/$ID -H 'Content-Type: application/json' -d '{"status":"VERIFIED"}' | jq .status

# Validation and conflicts
curl -s -o /dev/null -w '%{http_code}\n' -X POST $API/api/datasets -H 'Content-Type: application/json' \
  -d '{"dataset_name":"demo-set","version_tag":"v1","record_count":1}'       # 409 duplicate version
curl -s -o /dev/null -w '%{http_code}\n' -X POST $API/api/datasets -H 'Content-Type: application/json' \
  -d '{"dataset_name":"bad","version_tag":"v1","record_count":1,"drift_score":1.5}'  # 422 out of range
curl -s -o /dev/null -w '%{http_code}\n' $API/api/datasets/999999            # 404

# DELETE: archive by default, ?purge=true removes the row
curl -s -X DELETE $API/api/datasets/$ID | jq .status                          # ARCHIVED
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE "$API/api/datasets/$ID?purge=true"   # 204
```

In the UI, **Flag drift** sends `PUT {"status":"DRIFT_DETECTED"}` and the badge turns red;
**Mark verified** sends it back to `VERIFIED`.

### 3. Check the database and the Alembic migration

```bash
docker compose exec postgres psql -U datadrift -d datadrift -c "\d datasets"
docker compose exec postgres psql -U datadrift -d datadrift -c "SELECT * FROM alembic_version;"   # 0001_create_datasets
docker compose exec postgres psql -U datadrift -d datadrift \
  -c "SELECT id, dataset_name, version_tag, drift_score, status FROM datasets ORDER BY id;"
```

### 4. Run the tests and the linter

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
pytest -v                     # 14 passed
deactivate && cd ..
```

`tests/conftest.py` sets `DATABASE_URL` to a throwaway SQLite file before the app is imported and recreates
the tables for every test, so the suite never touches Postgres. The 29 tests cover every endpoint, including
validation errors, duplicate versions (409), automatic drift flagging, archive vs purge, and the metrics output,
plus the drift scoring: the distance itself, baseline choice, schema changes and which method wins.

### 5. Check the containers: non-root users and the Trivy scan

```bash
docker compose exec backend id          # uid=10001(appuser)
docker compose exec frontend id         # uid=101(nginx)

for img in datadrift-backend:local datadrift-frontend:local; do
  docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.75.0 \
    image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 "$img"
  echo "$img -> trivy exit code $?"     # 0 = no fixable HIGH/CRITICAL CVEs
done
```

### 6. Validate and plan the Terraform code

```bash
cd terraform
terraform init
terraform fmt -check && terraform validate
# No AWS account needed: offline plan with dummy keys (creates nothing)
AWS_ACCESS_KEY_ID=demo AWS_SECRET_ACCESS_KEY=demo terraform plan -var offline_plan=true   # Plan: 25 to add
cd ..
```

With a real AWS account, use `terraform plan`, `terraform apply` and `terraform destroy` instead
(see [Terraform](#terraform--aws-vpc--eks)).

### 7. Deploy to Kubernetes with Argo CD (kind)

```bash
./scripts/cluster-up.sh       # kind cluster + ingress-nginx + metrics-server + kube-prometheus-stack (~3 min)
./scripts/argocd-up.sh        # Argo CD + the DataDrift Application; waits for Synced/Healthy, prints the password
./scripts/seed.sh http://datadrift.localtest.me

kubectl get application datadrift -n argocd   # SYNC STATUS Synced, HEALTH STATUS Healthy
kubectl get pods -n datadrift                 # 2 backend, 2 frontend, 1 postgres, all Running
kubectl get svc,ingress,hpa -n datadrift      # ClusterIP services, ingress host, HPA 2-5 @ 60% CPU
curl -s http://datadrift.localtest.me/api/datasets/summary | jq
```

- App: http://datadrift.localtest.me. `*.localtest.me` resolves to 127.0.0.1, so no hosts-file edit is needed.
- Argo CD: http://argocd.localtest.me, user `admin`. Print the password again with
  `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo`

Without Argo CD, `./scripts/deploy-local.sh` installs the same chart directly with `helm upgrade --install`
(from locally built images, or `--ghcr <sha>` for CI's images) and `helm list -n datadrift` shows the release.
Use one or the other: the script refuses to run while Argo CD manages the app.

### 8. Open Prometheus and Grafana

Run each port-forward in its own terminal and leave it running:

```bash
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
kubectl port-forward -n monitoring svc/monitoring-grafana 3001:80
```

- Prometheus targets: http://localhost:9090/targets (search `datadrift`: 2/2 backend pods UP)
- Prometheus alert rules: http://localhost:9090/alerts
- Grafana: http://localhost:3001, login `admin` / `datadrift-admin`, then
  **Dashboards → DataDrift — Registry & API Overview** (http://localhost:3001/d/datadrift-overview)

```bash
kubectl port-forward -n datadrift svc/datadrift-backend 8001:8000 &   # 8001, because Compose uses 8000
curl -s localhost:8001/metrics | grep -E "^datadrift_|^http_requests_total"
```

### 9. Trigger the drift alert

Click **Flag drift** on any snapshot at http://datadrift.localtest.me, or use the API:

```bash
K8S=http://datadrift.localtest.me
ID=$(curl -s "$K8S/api/datasets?status=VERIFIED" | jq '.[0].id')
curl -s -X PUT $K8S/api/datasets/$ID -H 'Content-Type: application/json' -d '{"status":"DRIFT_DETECTED"}' | jq .status

# about 30 s later the alert is firing:
curl -s --get localhost:9090/api/v1/query \
  --data-urlencode 'query=ALERTS{alertname="DatasetDriftDetected",alertstate="firing"}' | jq '.data.result[].metric'
```

The Grafana **Drift alert** panel turns red and shows FIRING. Clear it again:

```bash
curl -s -X PUT $K8S/api/datasets/$ID -H 'Content-Type: application/json' -d '{"status":"VERIFIED"}' | jq .status
```

### 10. Watch the autoscaler

```bash
kubectl get hpa -n datadrift -w                                  # terminal 1
./scripts/load-test.sh http://datadrift.localtest.me 180 20      # terminal 2: 3 minutes of traffic
```

Replicas go from 2 up to 4 within about a minute once CPU passes 60%. After the load stops, the HPA waits
for its 5-minute scale-down stabilization window and then returns to 2. The Grafana panels for requests,
latency, errors, CPU and replicas fill in during the test.

### 11. Ship a change through the pipeline (GitOps)

```bash
git pull                                   # CI adds a commit after every push; start from the latest main
sed -i -E "s/const UI_VERSION = '[0-9.]+'/const UI_VERSION = '1.2.0'/" frontend/src/App.jsx
git commit -am "Bump dashboard version badge to 1.2.0" && git push
```

1. https://github.com/KavyaDhyani/datadrift-capstone/actions runs tests, build, Trivy and the GHCR push.
2. Its last job commits `Deploy <sha> to the cluster via Argo CD [skip ci]`, which writes the new SHA into
   `helm/datadrift/values-gitops.yaml`.
3. Argo CD checks Git every minute, goes OutOfSync, then syncs and rolls out the new pods.

```bash
kubectl get application datadrift -n argocd -w          # OutOfSync -> Synced (Ctrl+C to stop)
kubectl get deploy -n datadrift -o custom-columns=NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image
git pull && git log --oneline -3                        # shows the tag commit CI made
```

Refresh http://datadrift.localtest.me: the header badge shows the new version. To roll back, revert the change
in Git (`git revert <commit> && git push`) and Argo CD deploys the reverted state.

### Reset the data

```bash
# Compose
docker compose exec postgres psql -U datadrift -d datadrift -c "TRUNCATE datasets RESTART IDENTITY;"
./scripts/seed.sh
# kind
kubectl exec -n datadrift statefulset/datadrift-postgres -- \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "TRUNCATE datasets RESTART IDENTITY;"'
./scripts/seed.sh http://datadrift.localtest.me
```

### Clean up

```bash
pkill -f "kubectl port-forward"
kind delete cluster --name datadrift     # removes the local cluster
docker compose down -v                   # removes the Compose stack and its database volume
```

## CI/CD pipeline — `.github/workflows/ci-cd.yml`

Runs on every push and pull request to `main`:

1. **Backend lint + tests**: ruff, then `pytest -v`. A failing test stops the pipeline.
2. **Frontend build**: `npm ci && npm run build`.
3. **Validate Terraform + Helm**: `terraform fmt -check`, `terraform validate`, `helm lint`.
4. **Build, scan & push** (backend and frontend in parallel): Docker build → Trivy scan that fails on
   fixable HIGH/CRITICAL CVEs → push to `ghcr.io/<owner>/datadrift-<service>:<commit-sha>`.
   Pull requests build and scan but never push.
5. **GitOps hand-off** (pushes to `main` only): writes the new SHA into `helm/datadrift/values-gitops.yaml` and
   commits it as the person who pushed, marked `[skip ci]`. Argo CD deploys it (see
   [GitOps](#gitops--argo-cd)). The pipeline never holds cluster credentials. If `main` has moved on in the
   meantime, the job skips and the newer run writes its own tag.

Every image tag is the full Git commit SHA, never `latest`, so any running pod can be traced back to the
commit that built it.

## Security scanning with Trivy

Trivy scans each image's OS packages and Python/Node dependencies against public CVE databases.
The first scan of this project found real problems that are now fixed:

- **Frontend**: 43 HIGH CVEs in the Alpine packages of the `nginx-unprivileged` base image (for example
  CVE-2026-33630 in `c-ares` and several `curl` CVEs). Fixed by `apk upgrade --no-cache` in the runtime stage.
- **Backend**: HIGH CVEs in libraries vendored inside `pip` (`urllib3` CVE-2026-97687, `msgpack`) and in
  `setuptools` (CVE-2025-47273, path traversal). The app never uses pip at runtime, so the Dockerfile
  uninstalls pip/setuptools/wheel after installing dependencies.

Both images now scan clean (0 HIGH/CRITICAL). `--ignore-unfixed` means the gate only fails on problems
that have a fix available.

## Terraform — AWS VPC + EKS

`terraform/` uses plain `aws_*` resources so every piece is visible: VPC, 2 public + 2 private subnets in two
AZs, internet gateway, NAT gateway, route tables, IAM roles, EKS cluster and a managed node group
(2–4 × t3.medium). See [terraform/README.md](terraform/README.md).

```bash
cd terraform
terraform init && terraform validate
# with an AWS account:
terraform plan && terraform apply
aws eks update-kubeconfig --region ap-south-1 --name datadrift-eks
terraform destroy
# without one (offline plan, nothing is created):
AWS_ACCESS_KEY_ID=demo AWS_SECRET_ACCESS_KEY=demo terraform plan -var offline_plan=true
```

No credentials are committed. `*.tfvars` and state files are git-ignored, and `terraform.tfvars.example`
documents the inputs.

## Kubernetes + Helm

Locally the chart runs on a kind cluster. The same chart deploys to EKS with `values-prod.yaml`.
Everything in this section and the next needs the kind cluster running (see [Prerequisites](#prerequisites)).

```bash
./scripts/cluster-up.sh       # kind cluster + ingress-nginx + metrics-server + kube-prometheus-stack
./scripts/argocd-up.sh        # Argo CD deploys the chart from Git (GitOps)
./scripts/seed.sh http://datadrift.localtest.me
```

Open http://datadrift.localtest.me (`*.localtest.me` resolves to 127.0.0.1, so no hosts-file edit is needed).

What the chart creates in namespace `datadrift`:

| Resource | Details |
|----------|---------|
| Deployment `datadrift-backend` | 2–5 replicas (HPA on 60% CPU), `/ready` + `/health` probes, waits for Postgres, non-root, read-only root FS |
| Deployment `datadrift-frontend` | 2 replicas, Nginx on 8080 as uid 101 |
| StatefulSet `datadrift-postgres` | PostgreSQL 16 with a 1 Gi PVC, credentials from a Secret |
| Services | ClusterIP for backend (8000), frontend (80), postgres (5432) |
| Ingress | `/api`, `/docs` → backend, `/` → frontend |
| HPA | backend, CPU based |
| ServiceMonitor, PrometheusRule, dashboard ConfigMap | monitoring hooks (see below) |

Plain Helm instead of Argo CD: `./scripts/deploy-local.sh` (or `--ghcr <commit-sha>` for CI's images).

## GitOps — Argo CD

Argo CD runs inside the cluster and keeps it in sync with this repository, so Git is the single source of
truth for what is deployed.

| File | Purpose |
|------|---------|
| `argocd/argocd-values.yaml` | Argo CD Helm values (chart `argo/argo-cd` 10.9.5): UI at `argocd.localtest.me` behind ingress-nginx, Git checked every 60 s, Dex, notifications and the ApplicationSet controller turned off to save memory |
| `argocd/datadrift-application.yaml` | the `datadrift` Application: chart `helm/datadrift` from `main` with `values-gitops.yaml`, namespace `datadrift`, automated sync with `prune` and `selfHeal` |
| `helm/datadrift/values-gitops.yaml` | GHCR image repositories and the current tag; CI rewrites the tag after each build |
| `scripts/argocd-up.sh` | installs Argo CD, hands over an existing Helm release (the Postgres volume is kept), applies the Application |

Flow: `git push` → CI tests, scans and pushes `image:<sha>` → CI commits the tag → Argo CD sees the commit
(OutOfSync) → syncs → rolling update with `maxUnavailable: 0`.

```bash
kubectl get applications -n argocd                       # datadrift  Synced  Healthy
kubectl annotate application datadrift -n argocd argocd.argoproj.io/refresh=normal --overwrite   # check Git now
kubectl get application datadrift -n argocd -o jsonpath='{range .status.history[*]}{.revision}{"\n"}{end}'
```

`selfHeal` in action: `kubectl scale deploy/datadrift-frontend -n datadrift --replicas=1` is undone within
seconds, because Git says 2.

## Observability — Prometheus + Grafana

- The **ServiceMonitor** makes Prometheus scrape `/metrics` on every backend pod every 15 s.
- The **PrometheusRule** defines `DatasetDriftDetected` (one alert per drifted snapshot, labelled with the
  dataset and version), `DataDriftBackendDown` and `DataDriftHighErrorRate`.
- The **Grafana dashboard** "DataDrift — Registry & API Overview" is loaded automatically by the Grafana
  sidecar. It shows the drift alert state, snapshots in drift, the average drift gauge, drift score per
  snapshot, drift flags over time, request rate, p95 latency, error rate, backend CPU and HPA replicas.

```bash
kubectl port-forward -n monitoring svc/monitoring-grafana 3001:80                     # admin / datadrift-admin
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
```

Clicking **Flag drift** in the UI sends `PUT /api/datasets/{id}`. The badge turns red, the next scrape exports
the snapshot with `status="DRIFT_DETECTED"`, and within about 30 seconds the `DatasetDriftDetected` alert
fires in Prometheus and the dashboard's "Drift alert" panel turns red.

## Known issues and limitations

- **No AWS account was used.** Terraform is validated and planned offline with dummy credentials, so there is
  no AWS Console screenshot and no real `terraform apply`/`destroy`. Everything runs on a local kind cluster.
- **EKS deployment is described, not exercised.** `values-prod.yaml` and the Terraform outputs cover EKS, but
  only the kind cluster has been deployed to.
- **CI commits to `main`.** The GitOps job adds a `[skip ci]` tag commit after every push, so run `git pull`
  before your next commit.
- **Demo credentials are in Git.** The local Postgres password (`datadrift-local`) and the Grafana admin
  password are committed for the local demo only. A real cluster would use Kubernetes Secrets managed outside
  Git (for example Sealed Secrets or External Secrets), and Argo CD's generated admin password should be rotated.
- **Postgres is a single pod.** The StatefulSet has a persistent volume but no replication or backups; in AWS it
  would move to Amazon RDS.
- **Drift is computed from client-side profiles, not raw data.** The client sends per-column histograms; DataDrift
  does not read the dataset files. Numeric columns must be bucketed the same way in every snapshot, and a client
  can still send its own `drift_score`, which is used as given.
- **Alerts stay in Prometheus and Grafana.** Alertmanager has no receiver (Slack or email) configured.
- **Single-node cluster.** kind shows autoscaling and rolling updates, but not node failure.

## Screenshots

All screenshots were taken from the running project. They follow the order of the
[run-and-test guide](#run-and-test-the-full-project).

### Application — Docker Compose

**`docker compose up --build`**: both images build, and Postgres, backend and frontend start. Postgres and the
backend report `Healthy`.

![docker compose up --build](screenshots/01-compose-up-build.png)

**`docker compose ps`**: the three services are up, with ports 3000 (UI) and 8000 (API) published.

![docker compose ps](screenshots/02-compose-ps.png)

**Dashboard at http://localhost:3000**: KPI cards, the snapshot registry with drift bars, and the training gate.
All six seeded snapshots are verified.

![DataDrift dashboard](screenshots/03-ui-dashboard.png)

**Register a snapshot**: the form shows whether the drift score is below or above the 0.30 threshold before it
is submitted.

![Register snapshot form](screenshots/04-ui-register-snapshot.png)

**Drift detected**: a snapshot registered with drift 0.31 is flagged automatically, gets a red badge and is
listed as blocked in the training gate.

![Snapshot flagged as drift detected](screenshots/05-ui-drift-detected.png)

### API, metrics and database

**Swagger UI at `/docs`**: GET, POST, PUT and DELETE on `/api/datasets`, plus `/health`, `/ready` and the summary.

![Swagger UI](screenshots/06-api-swagger-docs.png)

**`/health`** returns `{"status":"UP"}`.

![Health endpoint](screenshots/07-api-health.png)

**`/metrics`** in Prometheus format: Python process metrics, the custom `datadrift_*` gauges and counters, and
`http_requests_total`.

![Metrics endpoint](screenshots/08-api-metrics.png)

**PostgreSQL**: the `datasets` table with its unique and check constraints, the Alembic version
`0001_create_datasets`, and the seeded rows.

![Postgres table and Alembic version](screenshots/09-postgres-schema-alembic.png)

### Docker — non-root images

The backend runs as `uid=10001(appuser)` and the frontend as `uid=101(nginx)`. The image list shows tags
for the commit SHA, and the Dockerfiles show the multi-stage frontend build (`node:22-alpine AS build` →
`nginx-unprivileged`).

![Non-root containers](screenshots/10-docker-non-root.png)

### Testing — ruff and pytest

`ruff check` and `ruff format --check` pass, and `pytest -v` runs 14 tests, all passing.

![ruff and pytest](screenshots/11-ruff-pytest.png)

### Git and GitHub

The commit history: one descriptive commit per step, all by the project author.

![Commit history](screenshots/12-git-log.png)

### CI/CD — GitHub Actions

A green pipeline run: lint + tests, frontend build and Terraform/Helm validation run in parallel, then the
build → Trivy scan → GHCR push matrix for both images, then the Helm deploy job. The summary shows the
pushed image `ghcr.io/kavyadhyani/datadrift-backend:<commit-sha>`, "built, scanned clean, pushed".

![GitHub Actions run](screenshots/13-github-actions-run.png)

**Pushing to GHCR**: inside the *Build, scan & push (backend)* job, the image is built and scanned, then the
job logs in to `ghcr.io` with the workflow's `GITHUB_TOKEN` ("Login Succeeded") and pushes the image. No
personal credentials are stored in the repository.

![GHCR login and push steps](screenshots/35-actions-ghcr-login-push.png)

**GHCR packages**: both images are public on the GitHub Container Registry. Every version is tagged with the
full commit SHA that built it (for example `269dc33615f4de7173754d9368e8040c13cf8c42`), never `latest`. The
"Latest" badge is only GitHub's label for the newest version.

![GHCR backend package with SHA tags](screenshots/36-ghcr-backend-package.png)

![GHCR frontend package with SHA tags](screenshots/37-ghcr-frontend-package.png)

### DevSecOps — Trivy in the pipeline

The *Trivy scan (fails on fixable HIGH/CRITICAL CVEs)* step runs `aquasec/trivy:0.75.0` against the freshly
built image. It downloads the latest vulnerability database, checks the Debian OS packages and Python
libraries, and also scans for secrets. The step passed, so the image had no fixable HIGH or CRITICAL CVEs
and the job went on to push it. A finding would have stopped the job before the push.

![Trivy scan step in GitHub Actions](screenshots/34-actions-trivy-scan.png)

### Terraform — AWS VPC + EKS

**`terraform init`, `fmt -check` and `validate`**: the configuration is valid.

![terraform init and validate](screenshots/14-terraform-init-validate.png)

**`terraform plan`** (offline, dummy credentials): `Plan: 25 to add, 0 to change, 0 to destroy`, with the
outputs for the EKS cluster.

![terraform plan](screenshots/15-terraform-plan.png)

**The key resources in the plan**: VPC, two public and two private subnets, NAT gateway, EKS cluster,
managed node group, and the EBS CSI and metrics-server add-ons.

![Terraform resources](screenshots/16-terraform-resources.png)

**`terraform plan -destroy`**: nothing was applied, so there is nothing left to destroy and no AWS cost.

![terraform destroy plan](screenshots/17-terraform-destroy-plan.png)

### Kubernetes + Helm (kind)

**`./scripts/cluster-up.sh`**: installs ingress-nginx, metrics-server and kube-prometheus-stack with Helm.

![cluster-up: ingress-nginx](screenshots/18-cluster-up-ingress.png)

![cluster-up: metrics-server and kube-prometheus-stack](screenshots/19-cluster-up-monitoring.png)

**`./scripts/deploy-local.sh`**: builds images tagged with the commit SHA, loads them into kind and runs
`helm upgrade --install`. The pods roll over to the new version.

![Helm deploy](screenshots/20-helm-deploy-seed.png)

**`kubectl get pods,svc,ingress,hpa` and `helm list`**: all pods Running, ClusterIP services for backend, frontend
and Postgres, the Ingress host `datadrift.localtest.me`, the HPA (2–5 replicas at 60% CPU) and the release
`datadrift` in status `deployed`.

![kubectl and helm list](screenshots/21-kubectl-pods-svc-helm.png)

**The app through the Ingress** at http://datadrift.localtest.me.

![UI through the Ingress](screenshots/22-ui-via-ingress.png)

### GitOps — Argo CD

**Applications page** at http://argocd.localtest.me: the `datadrift` Application is **Healthy** and
**Synced**, tracking `helm/datadrift` on `main` of this repository.

![Argo CD applications](screenshots/38-argocd-applications.png)

**Resource tree**: everything the chart creates (deployments with their ReplicaSets and pods, the Postgres
StatefulSet and its volume, services, ingress, HPA, ServiceMonitor, PrometheusRule and dashboard ConfigMap),
all green. The header shows that the last sync came from CI's commit `Deploy 7cd971a to the cluster via Argo CD`.

![Argo CD resource tree](screenshots/39-argocd-resource-tree.png)

**History and rollback**: each push to `main` is a separate automated sync, one per commit, initiated by the
automated sync policy. Any revision can be rolled back from here or by reverting it in Git.

![Argo CD sync history](screenshots/40-argocd-sync-history.png)

**From the terminal**: the Application is `Synced` / `Healthy`, and the latest commit on `main` is the tag
commit CI made after the previous push.

![Argo CD status and the CI tag commit](screenshots/41-argocd-cli-synced.png)

### Observability — Prometheus + Grafana

**`curl /metrics` on the backend Service in the cluster**.

![Metrics in Kubernetes](screenshots/23-k8s-metrics-endpoint.png)

**Prometheus targets**: the ServiceMonitor `datadrift/datadrift-backend` is scraping both backend pods, 2/2 UP.

![Prometheus targets](screenshots/24-prometheus-targets.png)

**Alert rules** from the Helm chart's PrometheusRule: `DatasetDriftDetected`, `DataDriftBackendDown` and
`DataDriftHighErrorRate`, all inactive.

![Prometheus alert rules](screenshots/25-prometheus-alert-rules.png)

**Grafana dashboard "DataDrift — Registry & API Overview"**, loaded automatically: drift alert OK, snapshots in
drift, verified count, the average drift gauge, backend pods up, drift score per snapshot and snapshots by
status.

![Grafana dashboard](screenshots/26-grafana-dashboard.png)

**API panels**: request rate, p95 latency, error responses, backend CPU per pod and HPA replicas.

![Grafana API panels](screenshots/27-grafana-api-panels.png)

### The drift alert, live

After **Flag drift** is clicked on `clinic-readmission@v0.9-beta`, `DatasetDriftDetected` fires within about
30 seconds, labelled with the dataset and version.

![Prometheus alert firing](screenshots/28-prometheus-alert-firing.png)

The Grafana **Drift alert** panel turns red with **FIRING**, "Snapshots in drift" shows 1, and the status chart
steps up.

![Grafana alert firing](screenshots/29-grafana-alert-firing.png)

### Autoscaling — HPA

Under `./scripts/load-test.sh`, CPU rises to 98% of the request and the HPA scales the backend from 2 to 4
pods. After the load stops, it waits out the 5-minute stabilization window and scales back to 2.

![HPA scaling](screenshots/30-hpa-scaling.png)

The same three load tests in Grafana: request rate, 4xx responses from the deliberate 404 calls, CPU per pod,
and replicas moving between 2 and 4.

![Grafana during load tests](screenshots/31-grafana-load-test.png)

### Live change: commit → pipeline → deployment

After the version badge was bumped to 1.1.0 and pushed, the pipeline built and pushed new images (captured
before Argo CD was added; Argo CD now performs the deploy step automatically).
`deploy-local.sh --ghcr <sha>` deployed those exact GHCR images, the rollout finished, both Deployments run
the image tagged with the new commit SHA, and `helm history` lists the revision.

![Deploy GHCR images](screenshots/32-deploy-ghcr-images.png)

The UI through the Ingress now shows **UI v1.1.0**.

![UI version 1.1.0](screenshots/33-ui-version-1-1-0.png)
