# Phase 1: Environment and Runtime Inventory

This inventory is extracted from current source code and is the required input to deployment configuration in later phases.

## Why this exists

Moving to public deployment fails most often due to missing runtime variables, implicit localhost defaults, and hardcoded development behavior. This file makes those explicit.

## Source files reviewed

1. `nethriq/settings.py`
2. `nethriq/views.py`
3. `nethriq/tasks.py`
4. `node/server.js`

## Variables and defaults

| Variable | Used In | Current Default | Production Expectation |
|---|---|---|---|
| `PBVISION_API_KEY` | `node/server.js` | none | required secret |
| `NODE_WEBHOOK_URL` | `node/server.js` | `http://localhost:3000/api/webhook/pbvision` | required public HTTPS URL |
| `NODE_ENDPOINT` | `nethriq/tasks.py` | `http://localhost:3000/api/process-video` | required internal Node URL |
| `DJANGO_BASE_URL` | `nethriq/views.py` | `http://localhost:8000` | required public app base URL |
| `AWS_ACCESS_KEY_ID` | `nethriq/settings.py` | none | required if using S3 in prod |
| `AWS_SECRET_ACCESS_KEY` | `nethriq/settings.py` | none | required if using S3 in prod |
| `AWS_STORAGE_BUCKET_NAME` | `nethriq/settings.py` | none | required if using S3 in prod |
| `AWS_S3_REGION_NAME` | `nethriq/settings.py` | `us-east-1` | set explicitly |
| `CELERY_BROKER_URL` | `nethriq/settings.py` | `redis://localhost:6379/0` | required managed Redis URL |
| `CELERY_RESULT_BACKEND` | `nethriq/settings.py` | `redis://localhost:6379/0` | required managed Redis URL |
| `FILE_UPLOAD_MAX_MEMORY_SIZE` | `nethriq/settings.py` | `104857600` | tune for workload |
| `DATA_UPLOAD_MAX_MEMORY_SIZE` | `nethriq/settings.py` | `104857600` | tune for workload |
| `FILE_UPLOAD_TEMP_DIR` | `nethriq/settings.py` | `/tmp/django_uploads` | ensure writable persistent temp volume |
| `EMAIL_DELIVERY_ENABLED` | `nethriq/settings.py` | true (except tests) | set explicitly |
| `EMAIL_DELIVERY_MAX_ATTACHMENT_BYTES` | `nethriq/settings.py` | `26214400` | set for provider limits |
| `EMAIL_BACKEND` | `nethriq/settings.py` | console backend | SMTP backend required |
| `EMAIL_HOST` | `nethriq/settings.py` | `localhost` | SMTP host required |
| `EMAIL_PORT` | `nethriq/settings.py` | `25` | provider value |
| `EMAIL_HOST_USER` | `nethriq/settings.py` | empty | required for most SMTP providers |
| `EMAIL_HOST_PASSWORD` | `nethriq/settings.py` | empty | required secret |
| `EMAIL_USE_TLS` | `nethriq/settings.py` | false | usually true |
| `EMAIL_USE_SSL` | `nethriq/settings.py` | false | provider dependent |
| `EMAIL_TIMEOUT` | `nethriq/settings.py` | `30` | tune as needed |
| `DEFAULT_FROM_EMAIL` | `nethriq/settings.py` | `no-reply@nethriq.local` | set real sender |
| `CLUB_NAME` | `nethriq/settings.py` | `PB Vision Athletics` | set production branding |
| `CLAIM_LINK_TTL_HOURS` | `nethriq/settings.py` | `24.0` | set policy value |
| `CLAIM_URL_BASE` | `nethriq/settings.py` | empty | required public URL |
| `PRESERVE_SOURCE_VIDEO` | `nethriq/tasks.py` | false | set explicitly |
| `CLEANUP_ON_DELIVERY` | `nethriq/tasks.py` | false | set explicitly |

## Non-env production flags currently hardcoded (must be addressed in Phase 2)

1. `DEBUG = True` in `nethriq/settings.py`.
2. Hardcoded Django `SECRET_KEY` in `nethriq/settings.py`.
3. Static `ALLOWED_HOSTS` list limited to localhost/ngrok in `nethriq/settings.py`.
4. SQLite as default database engine in `nethriq/settings.py`.

## Runtime binaries required but not represented in requirements files

1. `ffmpeg` executable must be available on worker runtime.

## Phase 1 output

This file is the canonical source for deployment variable mapping during Phase 2 and Phase 4 environment setup.
