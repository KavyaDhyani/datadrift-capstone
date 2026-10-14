# DataDrift — Dataset Version & Schema Quality Monitor

DataDrift is a small data registry for ML teams. Every time a training dataset is refreshed, the new
snapshot is registered with its version tag, record count, missing-value percentage and a **drift score**
(0.0 – 1.0) that measures how far it has moved from the last verified baseline. Snapshots at or above the
drift threshold (0.30) are flagged `DRIFT_DETECTED` and blocked from training until someone reviews them.
Flagging drift raises a Prometheus alert that shows up in Grafana.

The application is deliberately small. The point of the project is the path it takes from a laptop to a
monitored Kubernetes cluster: tests → containers → CI/CD → security scan → registry → Terraform →
Kubernetes/Helm → Prometheus/Grafana.

```text
 Developer ── git push ──► GitHub ──► GitHub Actions
                                       ├─ ruff + pytest (backend)
                                       ├─ npm build (frontend)
                                       ├─ terraform validate + helm lint
                                       ├─ docker build ─► Trivy scan (fail on HIGH/CRITICAL)
                                       └─ push to GHCR, tagged with the commit SHA
                                                    │
                     Terraform: AWS VPC + EKS        │   (local demo: kind cluster)
                                                    ▼
                                       helm upgrade --install datadrift
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
| Observability | kube-prometheus-stack: Prometheus, Alertmanager, Grafana |

## Repository layout

```text
datadrift-capstone/
├── backend/                 FastAPI app, Alembic migrations, pytest suite, Dockerfile
│   ├── app/                 main.py (routes), models.py, schemas.py, db.py, config.py, metrics.py
│   ├── alembic/versions/    0001_create_datasets.py
│   └── tests/               conftest.py (SQLite test DB) + test_api.py (14 tests)
├── frontend/                React dashboard, Nginx template, multi-stage Dockerfile
├── docker-compose.yml       postgres + backend + frontend
├── .github/workflows/       ci-cd.yml
├── terraform/               AWS VPC + EKS
├── k8s/                     namespace, kind cluster config, ingress-nginx / metrics-server values
├── helm/datadrift/          Helm chart (deployments, services, ingress, HPA, Postgres,
│                            ServiceMonitor, PrometheusRule, Grafana dashboard)
├── monitoring/              kube-prometheus-stack values (Prometheus + Grafana)
├── troubleshooting/         deliberately broken manifests for the debugging lab
├── scripts/                 seed, cluster-up, deploy-local, load-test
└── docs/                    demo guide and video script
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
| `created_at`, `updated_at` | timestamptz | |

The table is created by the Alembic migration `backend/alembic/versions/0001_create_datasets.py`. The backend
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
| POST | `/api/datasets` | register a snapshot; status is set from the drift score |
| PUT | `/api/datasets/{id}` | update drift score / status (the UI's **Flag drift** button) |
| DELETE | `/api/datasets/{id}` | archive; `?purge=true` deletes permanently |

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

## Run it locally with Docker Compose

```bash
docker compose up --build -d
./scripts/seed.sh                   # registers six sample snapshots through the API
```

- UI: http://localhost:3000
- API docs: http://localhost:8000/docs
- Metrics: http://localhost:8000/metrics

Stop with `docker compose down` (add `-v` to delete the database volume).

## Tests and code quality

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
pytest -v
```

`tests/conftest.py` sets `DATABASE_URL` to a throwaway SQLite file before the app is imported and recreates
the tables for every test, so the suite never touches Postgres. The 14 tests cover every endpoint, including
validation errors, duplicate versions (409), automatic drift flagging, archive vs purge, and the metrics output.

## CI/CD pipeline — `.github/workflows/ci-cd.yml`

Runs on every push and pull request to `main`:

1. **Backend lint + tests**: ruff, then `pytest -v`. A failing test stops the pipeline.
2. **Frontend build**: `npm ci && npm run build`.
3. **Validate Terraform + Helm**: `terraform fmt -check`, `terraform validate`, `helm lint`.
4. **Build, scan & push** (backend and frontend in parallel): Docker build → Trivy scan that fails on
   fixable HIGH/CRITICAL CVEs → push to `ghcr.io/<owner>/datadrift-<service>:<commit-sha>`.
   Pull requests build and scan but never push.
5. **Deploy**: `helm upgrade --install` with the new SHA tags when a `KUBE_CONFIG_DATA` secret is configured
   (for example an EKS kubeconfig). Without it the job prints the command to deploy the same images locally.

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

```bash
./scripts/cluster-up.sh       # kind cluster + ingress-nginx + metrics-server + kube-prometheus-stack
./scripts/deploy-local.sh     # build images tagged with the commit SHA, load into kind, helm upgrade --install
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

To deploy the exact images CI pushed for a commit: `./scripts/deploy-local.sh --ghcr <commit-sha>`.

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

## Troubleshooting lab

```bash
kubectl apply -f troubleshooting/broken-image.yaml     # ImagePullBackOff → kubectl describe pod
kubectl apply -f troubleshooting/broken-service.yaml   # Service with no endpoints → check labels
```

Each file explains the symptom, how to diagnose it and how to fix it.

## Demo material

- [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md): every command for the live demo and the screenshot checklist
- [docs/VIDEO_SCRIPT.md](docs/VIDEO_SCRIPT.md): narration for the recorded walkthrough
