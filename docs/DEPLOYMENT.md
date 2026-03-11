# Deployment Guide

**Last Updated:** October 3, 2025

Complete guide for deploying Resume Tailor to production environments.

## Pre-Deployment Checklist

### Required Infrastructure

- [ ] PostgreSQL 16+ with pgcrypto extension enabled
- [ ] Redis 7+ (managed service recommended)
- [ ] Container runtime (Docker, Kubernetes, or platform PaaS)
- [ ] Secrets manager (Doppler, AWS Secrets Manager, etc.)
- [ ] Domain with SSL/TLS certificate
- [ ] Email service (SMTP or transactional email API)

### Required Secrets

Set these in your secrets manager:

```bash
# Core Authentication
AUTH_SECRET_KEY=<256-bit-random-string>
VERIFY_SECRET_KEY=<256-bit-random-string>
RESET_SECRET_KEY=<256-bit-random-string>

# Encryption
PII_ENCRYPTION_KEY=<256-bit-random-string>
TOTP_FERNET_KEY=<base64-encoded-fernet-key>
SECURITY_REMEMBER_SIGNER_SECRET=<256-bit-random-string>

# Database (or use DATABASE_URL)
DB_USER=<username>
DB_PASSWORD=<secure-password>
DB_HOST=<host>
DB_PORT=5432
DB_NAME=restailor

# Redis (or use REDIS_URL)
REDIS_HOST=<host>
REDIS_PORT=6379
REDIS_PASSWORD=<password>

# AI Providers (at least one required)
OPENAI_API_KEY=sk-...
CLAUDE_API_KEY=sk-ant-...
GEMINI_API_KEY=...
GROK_API_KEY=...

# Email
MAIL_SERVER=<smtp-host>
MAIL_PORT=587
MAIL_USERNAME=<username>
MAIL_PASSWORD=<password>
MAIL_FROM=noreply@yourdomain.com
MAIL_STARTTLS=1

# WebAuthn
WEBAUTHN_RP_ID=yourdomain.com
WEBAUTHN_RP_NAME=Resume Tailor
WEBAUTHN_ORIGIN=https://yourdomain.com

# Production Flags
STRICT_SECRETS=1
COOKIE_SECURE=1
```

### Generate Secrets

```bash
# Random 256-bit keys (Linux/Mac)
openssl rand -base64 32

# Fernet key (Python)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Build Production Images

### API Service

```bash
docker build -f docker/api.Dockerfile --target prod -t restailor-api:latest .
```

### Worker Service

```bash
docker build -f docker/arq.Dockerfile --target prod -t restailor-worker:latest .
```

### Frontend Service

```bash
docker build -f docker/next.Dockerfile --target prod -t restailor-frontend:latest ./frontend
```

## Database Setup

### 1. Create Database

```sql
CREATE DATABASE restailor;
CREATE USER resume_app WITH PASSWORD 'secure-password';
GRANT ALL PRIVILEGES ON DATABASE restailor TO resume_app;
```

### 2. Enable pgcrypto Extension

```sql
\c restailor
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

### 3. Run Migrations

```bash
# Set DATABASE_URL or DB_* environment variables
export DATABASE_URL="postgresql://resume_app:password@host:5432/restailor"

# Run migrations
poetry run alembic upgrade head
```

### 4. Verify Migration Status

```bash
poetry run alembic current
# Should show latest migration ID
```

## Deployment Platforms

### Render.com

**1. Create Services:**

**API Service (Web Service):**
- Build Command: `pip install poetry && poetry install --no-dev`
- Start Command: `poetry run uvicorn main:app --host 0.0.0.0 --port $PORT`
- Environment: Python 3.13
- Health Check: `/healthz`

**Worker Service (Background Worker):**
- Build Command: `pip install poetry && poetry install --no-dev`
- Start Command: `poetry run arq worker.WorkerSettings`
- Environment: Python 3.13

**Frontend (Static Site or Web Service):**
- Build Command: `npm install && npm run build`
- Start Command: `npm start`
- Environment: Node 20
- Auto-Deploy: Yes

**2. Add Add-ons:**
- PostgreSQL 16
- Redis 7

**3. Environment Variables:**
Set all required secrets in Render dashboard for each service.

**4. Deploy:**
- Connect GitHub repository
- Enable auto-deploy on push to main branch
- Monitor deploy logs

### Docker Compose (Self-Hosted)

**1. Create `docker-compose.prod.yml`:**

```yaml
version: "3.9"
name: restailor-prod

services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:7
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    restart: unless-stopped

  api:
    image: restailor-api:latest
    environment:
      DATABASE_URL: postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/${DB_NAME}
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      STRICT_SECRETS: "1"
      # All other secrets from env file
    env_file:
      - .env.prod
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    restart: unless-stopped

  worker:
    image: restailor-worker:latest
    environment:
      DATABASE_URL: postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/${DB_NAME}
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      STRICT_SECRETS: "1"
    env_file:
      - .env.prod
    depends_on:
      - postgres
      - redis
    restart: unless-stopped

  frontend:
    image: restailor-frontend:latest
    environment:
      NEXT_PUBLIC_API_URL: https://api.yourdomain.com
    ports:
      - "3000:3000"
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

**2. Deploy:**

```bash
# Pull latest images
docker-compose -f docker-compose.prod.yml pull

# Run migrations
docker-compose -f docker-compose.prod.yml run --rm api poetry run alembic upgrade head

# Start services
docker-compose -f docker-compose.prod.yml up -d

# Check logs
docker-compose -f docker-compose.prod.yml logs -f
```

### Kubernetes

**1. Create ConfigMap:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: restailor-config
data:
  STRICT_SECRETS: "1"
  COOKIE_SECURE: "1"
  DB_PORT: "5432"
  REDIS_PORT: "6379"
  WEBAUTHN_RP_ID: "yourdomain.com"
  WEBAUTHN_RP_NAME: "Resume Tailor"
  WEBAUTHN_ORIGIN: "https://yourdomain.com"
```

**2. Create Secrets:**

```bash
kubectl create secret generic restailor-secrets \
  --from-literal=AUTH_SECRET_KEY=... \
  --from-literal=PII_ENCRYPTION_KEY=... \
  --from-literal=DB_PASSWORD=... \
  --from-literal=REDIS_PASSWORD=... \
  --from-literal=OPENAI_API_KEY=...
```

**3. Create Deployments:**

See `k8s/` directory for complete manifests (create if needed).

## Post-Deployment Tasks

### 1. Verify Services

```bash
# Check API health
curl https://api.yourdomain.com/healthz

# Should return:
# {"ok": true, "db": "ok", "redis": "ok"}

# Check frontend
curl https://yourdomain.com

# Check time endpoint
curl https://api.yourdomain.com/time
```

### 2. Create Admin User

```bash
# Connect to API container
docker exec -it restailor-api bash

# Run Python shell
poetry run python

# Create admin
from restailor.db import SessionLocal
from restailor.models import User
from restailor.security import get_password_hash

db = SessionLocal()
admin = User(
    username="admin@yourdomain.com",
    hashed_password=get_password_hash("secure-password"),
    role="admin",
    is_verified=True,
    is_email_verified=True
)
db.add(admin)
db.commit()
print(f"Admin created with ID: {admin.id}")
```

### 3. Test Key Workflows

1. **Sign up** - Create test user
2. **Login** - Get JWT token
3. **Submit job** - Test AI integration
4. **Check balance** - Verify pricing
5. **Admin login** - Test admin panel

### 4. Configure Monitoring

Set up monitoring for:
- Application errors (Sentry, Rollbar, etc.)
- Performance monitoring (Datadog, New Relic, etc.)
- Uptime monitoring (UptimeRobot, Pingdom, etc.)
- Log aggregation (CloudWatch, Loggly, etc.)

### 5. Set Up Backups

**Database:**
```bash
# Automated daily backups
pg_dump -h $DB_HOST -U $DB_USER -d restailor > backup-$(date +%Y%m%d).sql

# Restore
psql -h $DB_HOST -U $DB_USER -d restailor < backup-20251003.sql
```

**Redis:**
```bash
# Enable AOF persistence
redis-cli CONFIG SET appendonly yes

# Or use RDB snapshots
redis-cli BGSAVE
```

## Rolling Updates

### Zero-Downtime Deployment

**1. Prepare:**
```bash
# Build new image
docker build -f docker/api.Dockerfile --target prod -t restailor-api:v2 .

# Test locally
docker run --rm -e DATABASE_URL=... restailor-api:v2 poetry run alembic upgrade head
```

**2. Run Migrations:**
```bash
# Migrations should be backward compatible
# Run before deploying new code
kubectl run migration --image=restailor-api:v2 \
  --restart=Never \
  --command -- poetry run alembic upgrade head

# Wait for completion
kubectl wait --for=condition=complete job/migration
```

**3. Update API:**
```bash
# Update deployment image
kubectl set image deployment/restailor-api api=restailor-api:v2

# Watch rollout
kubectl rollout status deployment/restailor-api
```

**4. Update Worker:**
```bash
kubectl set image deployment/restailor-worker worker=restailor-worker:v2
kubectl rollout status deployment/restailor-worker
```

**5. Update Frontend:**
```bash
kubectl set image deployment/restailor-frontend frontend=restailor-frontend:v2
kubectl rollout status deployment/restailor-frontend
```

**6. Verify:**
```bash
curl https://api.yourdomain.com/healthz
# Smoke test key endpoints
```

## Rollback Procedures

### Immediate Rollback

```bash
# Kubernetes
kubectl rollout undo deployment/restailor-api

# Docker Compose
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d --scale api=0
# Deploy previous image
docker-compose -f docker-compose.prod.yml up -d
```

### Database Rollback

```bash
# Downgrade one migration
poetry run alembic downgrade -1

# Downgrade to specific revision
poetry run alembic downgrade abc123

# Check current
poetry run alembic current
```

### Full Disaster Recovery

**1. Stop Services:**
```bash
docker-compose -f docker-compose.prod.yml down
```

**2. Restore Database:**
```bash
psql -h $DB_HOST -U $DB_USER -d restailor < backup-20251003.sql
```

**3. Verify Data:**
```bash
psql -h $DB_HOST -U $DB_USER -d restailor -c "SELECT COUNT(*) FROM users;"
```

**4. Restart Services:**
```bash
docker-compose -f docker-compose.prod.yml up -d
```

**5. Monitor Logs:**
```bash
docker-compose -f docker-compose.prod.yml logs -f
```

## Performance Tuning

### Database

```sql
-- Add indexes for common queries
CREATE INDEX CONCURRENTLY idx_applications_user_active 
  ON applications (user_id) WHERE is_test = false;

CREATE INDEX CONCURRENTLY idx_jobs_status_created 
  ON jobs (status, created_at DESC);

-- Analyze tables
ANALYZE applications;
ANALYZE jobs;
ANALYZE charges;

-- Vacuum
VACUUM ANALYZE;
```

### Redis

```bash
# Increase memory limit
redis-cli CONFIG SET maxmemory 2gb
redis-cli CONFIG SET maxmemory-policy allkeys-lru

# Monitor
redis-cli INFO memory
```

### Application

```bash
# Increase worker concurrency
# Set in worker environment
ARQ_MAX_JOBS=20

# API workers
uvicorn main:app --workers 4 --host 0.0.0.0 --port 8000
```

## Monitoring & Alerts

### Health Checks

**API:**
```bash
# Shallow
curl https://api.yourdomain.com/health

# Deep (checks DB and Redis)
curl https://api.yourdomain.com/healthz
```

**Database:**
```sql
-- Check connections
SELECT count(*) FROM pg_stat_activity WHERE datname = 'restailor';

-- Check slow queries
SELECT pid, now() - query_start as duration, query 
FROM pg_stat_activity 
WHERE state = 'active' AND query NOT LIKE '%pg_stat_activity%'
ORDER BY duration DESC;
```

**Redis:**
```bash
redis-cli PING
redis-cli INFO stats
```

### Log Monitoring

Key log patterns to alert on:

```bash
# Errors
grep -i "error\|exception\|failed" /var/log/restailor/*.log

# Authentication failures
grep "401\|403\|login failed" /var/log/restailor/*.log

# Database errors
grep "database\|postgres\|connection" /var/log/restailor/*.log

# Rate limit hits
grep "rate limit exceeded" /var/log/restailor/*.log
```

### Metrics to Track

- Request rate (requests/sec)
- Response time (p50, p95, p99)
- Error rate (errors/min)
- Active jobs
- Queue depth (Redis)
- Database connections
- Memory usage
- CPU usage
- Disk I/O

## Security Hardening

### SSL/TLS

```nginx
# Nginx reverse proxy config
server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Firewall

```bash
# Allow only necessary ports
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw enable
```

### Database

```sql
-- Restrict network access
-- Edit postgresql.conf
listen_addresses = 'localhost'

-- Edit pg_hba.conf
host    restailor    resume_app    10.0.0.0/8    scram-sha-256
```

## Troubleshooting Production Issues

### High CPU Usage

```bash
# Check which process
top -o %CPU

# Check Python profiling
poetry run py-spy top --pid <pid>

# Check slow queries
psql -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"
```

### Memory Leaks

```bash
# Monitor memory over time
watch -n 5 'docker stats --no-stream | grep restailor'

# Check Python objects
poetry run python -m memory_profiler main.py
```

### Database Connection Pool Exhausted

```sql
-- Check active connections
SELECT count(*), state FROM pg_stat_activity GROUP BY state;

-- Kill idle connections
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE datname = 'restailor' 
  AND state = 'idle' 
  AND query_start < now() - interval '5 minutes';
```

### Worker Queue Backed Up

```bash
# Check Redis queue length
redis-cli LLEN arq:queue:default

# Check failed jobs
redis-cli KEYS "arq:job:*" | wc -l

# Clear queue (DANGER)
redis-cli FLUSHDB
```

---

---

## Appendix A: Stripe Payment Setup

### Quick Start

1. **Get Stripe keys** from https://dashboard.stripe.com/apikeys (test or live)
2. **Add to secrets manager:**
   ```bash
   STRIPE_SECRET_KEY=sk_test_...  # or sk_live_ for production
   STRIPE_PUBLISHABLE_KEY=pk_test_...  # or pk_live_ for production
   STRIPE_ENABLED=true
   ```

3. **Create webhook endpoint:**
   ```bash
   stripe webhook_endpoints create \
     --url=https://api.yourdomain.com/webhooks/stripe \
     --enabled-events=checkout.session.completed,payment_intent.succeeded \
     --api-key=sk_test_YOUR_KEY
   ```

4. **Save webhook secret:**
   ```bash
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```

5. **Restart services** and test at `/billing`

### Production Checklist

- [ ] Switch to **live** Stripe keys (sk_live_, pk_live_)
- [ ] Create production webhook endpoint
- [ ] Update `STRIPE_WEBHOOK_SECRET` with production value
- [ ] Verify webhook endpoint is enabled in Stripe Dashboard
- [ ] Test end-to-end payment flow
- [ ] Monitor webhook logs for errors

**See archived `docs/archive/setup/STRIPE_SETUP.md` for detailed troubleshooting.**

---

## Appendix B: Cloudflare Configuration

### DNS Setup

1. **Add DNS records** in Cloudflare dashboard:
   - A record: `yourdomain.com` → your server IP (proxied)
   - CNAME: `api.yourdomain.com` → your API host (proxied)
   - CNAME: `www.yourdomain.com` → `yourdomain.com` (proxied)

2. **Configure SSL/TLS:**
   - SSL/TLS encryption mode: **Full (strict)**
   - Enable "Always Use HTTPS"
   - Enable "Automatic HTTPS Rewrites"

### Domain Redirects

To redirect alternate domains to primary domain:

1. Go to **Rules > Redirect Rules**
2. Click **"Create rule"**
3. Configure:
   - **When:** Hostname equals `alternate-domain.com`
   - **Then:** Dynamic redirect to `https://yourdomain.com${uri.path}`
   - **Status:** 301 (Permanent)
   - **Preserve query string:** Yes

### Email Routing (Optional)

1. Enable **Email Routing** in Cloudflare
2. Add destination address
3. Create routing rules:
   - `noreply@yourdomain.com` → your email
   - `support@yourdomain.com` → your email

**See archived `docs/archive/setup/CLOUDFLARE_*.md` files for detailed guides.**

---

## Appendix C: Render.com Deployment

### Quick Deploy

1. **Create Render account** at https://render.com
2. **Create PostgreSQL database:**
   - Plan: Professional (recommended for production)
   - Region: Choose closest to users

3. **Create Redis instance:**
   - Plan: Standard (recommended)
   - Region: Same as PostgreSQL

4. **Create Web Service (API):**
   - Build Command: `pip install poetry && poetry install --only main`
   - Start Command: `poetry run uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Instance Type: Standard Plus or Pro
   - Auto-Deploy: Yes
   - Health Check Path: `/healthz`
   - Environment: Copy all secrets from template

5. **Create Background Worker:**
   - Build Command: `pip install poetry && poetry install --only main`
   - Start Command: `poetry run arq worker.WorkerSettings`
   - Instance Type: Standard
   - Environment: Same as API service

6. **Create Static Site (Frontend):**
   - Build Command: `cd frontend && npm install && npm run build`
   - Publish Directory: `frontend/out`
   - Auto-Deploy: Yes

7. **Configure environment variables** for each service from `.env.example`

8. **Trigger first deployment** and monitor logs

**See archived `docs/archive/setup/RENDER_SETUP.md` for detailed Render CLI commands.**

---

**For development setup, see [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md).**  
**For database details, see [DB.md](DB.md).**  
**For archived detailed setup guides, see `docs/archive/` directory.**
