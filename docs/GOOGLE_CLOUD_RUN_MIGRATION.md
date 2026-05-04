# Google Cloud Run Migration

This guide moves the current Render deployment to Google Cloud Run while preserving the same runtime shape:

- `restailor-api`: FastAPI HTTP service
- `restailor-worker`: on-demand Cloud Run Job that runs `arq --burst`
- `restailor-frontend`: Next.js HTTP service
- PostgreSQL: Cloud SQL for PostgreSQL
- Redis: Memorystore for Redis
- Secrets: Doppler at runtime, with only `DOPPLER_TOKEN` stored in Google Secret Manager

Cloud Run services must listen on the injected `PORT` value. The API and frontend Docker images in this repo are now compatible with that contract. The ARQ worker does not serve HTTP, so deploy it as a Cloud Run Job and trigger it after enqueue. The job uses ARQ burst mode and exits once no queued work remains, which avoids paying for an always-polling worker when nobody is using the app.

## One-Time GCP Setup

Use the same region for Cloud Run, Artifact Registry, Cloud SQL, Memorystore, and VPC resources. `us-east5` is a close match for the existing Render `ohio` region.

```bash
export PROJECT_ID=your-gcp-project
export REGION=us-east5
export REPOSITORY=restailor

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  vpcaccess.googleapis.com \
  compute.googleapis.com

gcloud artifacts repositories create "$REPOSITORY" \
  --repository-format=docker \
  --location="$REGION"
```

## Database And Redis

Create Cloud SQL for PostgreSQL 18 to match the current Render Postgres major version, and enable `pgcrypto` in the `restailor` database before running migrations. Do not import the Render Postgres 18 dump into an older Cloud SQL major version.

For Redis, create Memorystore in the same region. Cloud Run needs private network access to reach Memorystore. Prefer Direct VPC egress with `NETWORK` and `SUBNET` because it works for services and jobs. A Serverless VPC Access connector can still be used through `VPC_CONNECTOR`.

Recommended secret values:

```bash
DATABASE_URL=postgresql://USER:PASSWORD@PRIVATE_SQL_IP:5432/restailor
REDIS_URL=redis://:PASSWORD@PRIVATE_REDIS_IP:6379/0
```

If you prefer Cloud SQL Unix sockets, attach the Cloud SQL instance in deploy and set:

```bash
DATABASE_URL=postgresql://USER:PASSWORD@/restailor?host=/cloudsql/PROJECT:REGION:INSTANCE
```

## Secrets

Keep sensitive application values in Doppler under the `restailor` project and `prd` config. In Google Secret Manager, store only a Doppler service token for that config:

```bash
gcloud secrets create restailor-doppler-token --replication-policy=automatic
printf '%s' 'dp.st.prd.xxxx' | gcloud secrets versions add restailor-doppler-token --data-file=-

source deploy/cloudrun/secrets.env
```

`deploy/cloudrun/secrets.env` should define:

```bash
DOPPLER_SECRETS=DOPPLER_TOKEN=restailor-doppler-token:latest
```

The Cloud Run runtime service account also needs access to read that secret. The API service account needs permission to execute the worker job after enqueuing Redis work:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:SERVICE_ACCOUNT_EMAIL" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:SERVICE_ACCOUNT_EMAIL" \
  --role="roles/run.jobsExecutor"
```

The non-secret production defaults live in:

- `deploy/cloudrun/api.env.yaml`
- `deploy/cloudrun/worker.env.yaml`
- `deploy/cloudrun/frontend.env.yaml`

Review the domain, email, analytics, and captcha values before deploying.

## Build And Deploy

Set the public frontend values at build time because `NEXT_PUBLIC_*` variables are baked into the Next.js client bundle.

```bash
export PROJECT_ID=your-gcp-project
export REGION=us-east5
export NEXT_PUBLIC_API_BASE_URL=https://api.restailor.com
export NEXT_PUBLIC_API_URL=https://api.restailor.com
export NEXT_PUBLIC_SITE_URL=https://restailor.com
export NEXT_PUBLIC_TURNSTILE_SITE_KEY=your-public-site-key

# Optional, preferred for private IP Redis/SQL:
export NETWORK=default
export SUBNET=default
export VPC_EGRESS=private-ranges-only

# Optional for services/jobs only when using a Serverless VPC Access connector:
# export VPC_CONNECTOR=restailor-connector

# Optional, when using Cloud SQL attachment:
export CLOUD_SQL_INSTANCE=PROJECT:REGION:INSTANCE

# Required if using Secret Manager mappings:
source deploy/cloudrun/secrets.env

./scripts/deploy_to_cloud_run.sh
```

The script builds the API, worker, and frontend images through Cloud Build, deploys a migration job, waits for `alembic upgrade head`, then deploys the API service, on-demand worker job, and frontend service.

The deployed API is configured with `CLOUD_RUN_WORKER_JOB`, `CLOUD_RUN_WORKER_REGION`, and `CLOUD_RUN_WORKER_PROJECT`. After the API successfully enqueues ARQ work in Redis, it makes a best-effort call to the Cloud Run Jobs API to execute `restailor-worker`.

Do the first deployment manually from this script before connecting GitHub automation. Once Cloud Run, migrations, Doppler, Redis, SQL, and the first real background job are proven, connect the GitHub repo to Cloud Build or GitHub Actions for repeat deploys.

If you later choose a Cloud Run worker pool instead, set it to the smallest fixed instance count you can tolerate. A worker pool is a continuous polling process and is billed while instances are running, even when the Redis queue is empty.

## Edge Protection

The API and frontend deploy with `--min-instances 0` and `--ingress internal-and-cloud-load-balancing` by default. Public traffic should enter through the global HTTPS load balancer, not the direct `*.run.app` service URLs. This keeps direct Cloud Run scanner traffic from waking idle service instances. For a first bootstrap before the load balancer exists, temporarily run the deploy with `CLOUD_RUN_INGRESS=all`, then switch back before DNS cutover.

After the load balancer backend services exist, attach the Cloud Armor policy:

```bash
export PROJECT_ID=your-gcp-project
./scripts/configure_cloudrun_edge_protection.sh
```

The policy blocks obvious low-value scanner user agents and common exploit scan paths before they reach Cloud Run. Keep the rule list conservative; use load balancer logs to add only noisy patterns that are clearly not real users.

## Cutover Checklist

- Deploy Cloud Run services without changing DNS.
- Confirm the migration job exits successfully.
- Check API health through the load balancer: `https://api.restailor.com/health`.
- Check frontend SSR pages load through the load balancer and API proxy calls reach the API.
- Run a small authenticated tailor and judge flow so Redis queueing, SSE, worker processing, billing, and database writes are all exercised.
- In regions where Cloud Run domain mappings are unavailable, put a global external HTTPS load balancer in front of the services with serverless NEGs:
  - `api.restailor.com` routes to `restailor-api`.
  - `restailor.com` and `www.restailor.com` route to `restailor-frontend`.
  - DNS points all three names at the load balancer IP with DNS-only records while the Google-managed certificate provisions.
- Attach Cloud Armor with `./scripts/configure_cloudrun_edge_protection.sh`.
- Keep Render live until Cloud Run has processed real traffic and logs look clean.
- Disable Render auto-deploy first, then decommission the old services after the rollback window.

## Rollback

Leave Render untouched during the first cutover. If Cloud Run has an incident, point DNS back to Render, pause Cloud Run traffic if needed, and inspect:

```bash
gcloud run services logs read restailor-api --region "$REGION"
gcloud run services logs read restailor-frontend --region "$REGION"
gcloud run jobs executions list --job restailor-worker --region "$REGION"
```
