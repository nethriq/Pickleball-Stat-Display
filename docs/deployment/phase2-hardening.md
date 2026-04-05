# Phase 2: Environment-Driven Hardening

**Objective**: Remove all hardcoded secrets and environment-specific values from application code. Code now reads configuration from environment variables, enabling deployment across different environments (localhost → staging → production) without code changes.

## Changes Made

### 1. Django Hardening (`settings.py`)
- **SECRET_KEY**: Changed from hardcoded string to `os.environ.get('SECRET_KEY', fallback)`
  - Local fallback: Uses Django's insecure default for development
  - Production: Must be set by PaaS environment variable
- **DEBUG**: Changed from hardcoded `True` to `_env_bool('DEBUG', False)`
  - Local: Set to `True` in `.env` for development
  - Production: Set to `False` automatically
- **ALLOWED_HOSTS**: Changed from hardcoded list to environment-driven split: `os.environ.get('ALLOWED_HOSTS', '...').split(',')`
  - Local: `localhost,127.0.0.1,.ngrok-free.dev`
  - Production: Will be set to your deployed domain(s)

### 2. Node.js Hardening (`server.js`)
- **DJANGO_BASE_URL**: Changed from hardcoded `http://localhost:8000` to `process.env.DJANGO_BASE_URL`
  - Local: `http://localhost:8000`
  - Production: Will be set to your deployed Django app URL

### 3. Environment File (`.env`)
- Already exists and protected in `.gitignore`
- Contains all local development values:
  - Django security: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`
  - Service URLs: `DJANGO_BASE_URL`, `NODE_WEBHOOK_URL`
  - Integrations: `PBVISION_API_KEY`, email credentials
  - Infrastructure: Redis broker/backend URLs
  - AWS S3 (commented out for local dev)

## Verification Checklist

✅ **Code changes applied**:
- `settings.py`: SECRET_KEY, DEBUG, ALLOWED_HOSTS now environment-driven
- `server.js`: DJANGO_BASE_URL now environment-driven
- `.env`: Secured in `.gitignore` (pre-existing)
- `.gitignore`: Already includes `.env` and `.env.local`

✅ **Local development setup**:
- All local values in `.env`
- Running with `pyenv activate project-venv` reads `.env` automatically via Django's loader
- Node gateway reads `.env` via dotenv package

✅ **Deployment ready**:
- No hardcoded secrets in code
- All configuration externalizable
- Environment variables follow 12-factor app principles

## Phase 2 Validation

The baseline test validates:
1. Django still reads environment variables correctly
2. Node gateway can forward to environment-driven Django URL
3. All services (Celery, Redis, email) still work with env config
4. End-to-end flow (upload → process → deliverables) succeeds

**Success Criteria**: Phase 1 baseline test passes identically with environment-driven configuration.

## Production Deployment (Phase 3+)

For PaaS deployment, platform will inject:
```bash
SECRET_KEY=<strong-random-key>
DEBUG=False
ALLOWED_HOSTS=your-app.example.com,www.your-app.example.com
DJANGO_BASE_URL=https://your-app.example.com
NODE_WEBHOOK_URL=https://your-app.example.com/api/webhook/pbvision
PBVISION_API_KEY=<from-pbvision>
CELERY_BROKER_URL=<redis-url-from-platform>
CELERY_RESULT_BACKEND=<redis-url-from-platform>
AWS_ACCESS_KEY_ID=<from-platform>
AWS_SECRET_ACCESS_KEY=<from-platform>
AWS_STORAGE_BUCKET_NAME=<from-platform>
EMAIL_HOST=<smtp-host>
EMAIL_HOST_USER=<smtp-user>
EMAIL_HOST_PASSWORD=<smtp-pass>
```

No code changes needed—configuration injection only.
