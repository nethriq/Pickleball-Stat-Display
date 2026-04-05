# Phase 1: Localhost Baseline Capture (Deployment Parity Gate)

This document implements Phase 1 by defining exactly what must pass on localhost before any PaaS deployment work proceeds.

## Why this exists

Phase 1 freezes a known-good behavior baseline so production rollout can be verified against real evidence, not assumptions.

## Scope

Baseline flow to verify end-to-end:

1. User auth path is functional.
2. Video upload creates a `VideoJob`.
3. PB Vision webhook handoff reaches Django internal save endpoint.
4. Job transitions to player selection and then processing.
5. Pipeline finishes and deliverables are created.
6. Delivery email logic runs and job reaches `COMPLETED`.

## Ground truth from code

Primary lifecycle touchpoints:

1. `nethriq/views.py` creates upload jobs in `PENDING`.
2. `nethriq/views.py` webhook paths set `AWAITING_PLAYER_SELECTION`.
3. `nethriq/views.py` player selection sets `PROCESSING`.
4. `nethriq/tasks.py` terminal status is `COMPLETED` or `FAILED`.

## Prerequisites

1. Python env activated:

```bash
pyenv activate project-venv
```

2. Services available locally:

- Django app
- Redis
- Celery worker
- Node gateway
- FFmpeg executable on PATH

3. Local env file populated (`.env` or `.env.local`) with at least:

- `PBVISION_API_KEY`
- `NODE_WEBHOOK_URL`
- `NODE_ENDPOINT` (if non-default)
- Email values if testing real SMTP delivery

## Baseline execution order

1. Start Django API.
2. Start Node gateway.
3. Start Celery worker.
4. Confirm health endpoint:

```bash
curl -sS http://localhost:8000/api/health/
```

5. Run one complete job through the UI/API.
6. Select player index once webhook data is saved.
7. Wait for task chain completion.

## Evidence to capture (required)

Create one timestamped folder and store proof artifacts:

```text
artifacts/phase1/<YYYYMMDD-HHMMSS>/
```

Required files:

1. `health.json`: output of `/api/health/`.
2. `job_status_timeline.txt`: status snapshots from upload to completion.
3. `django.log`: relevant request/task events.
4. `node.log`: webhook receipt and Django handoff lines.
5. `celery.log`: task chain and completion lines.
6. `deliverables_tree.txt`: listing of `data/job_<id>/deliveries`.
7. `runtime_versions.txt`: Python/Node/FFmpeg versions.

## Phase 1 acceptance criteria (must all pass)

1. Job status progression observed:

`PENDING -> AWAITING_PLAYER_SELECTION -> PROCESSING -> COMPLETED`

2. No unhandled exceptions in Django/Node/Celery logs for the selected job.
3. At least one ZIP deliverable exists under the job `deliveries` directory.
4. `result_json` exists for the completed `VideoJob`.
5. If email delivery is enabled, email dispatch result is present in delivery metadata.

## Fail-fast blockers

Stop and fix before moving to Phase 2+ if any occurs:

1. FFmpeg command not found.
2. Webhook hits Node but fails to save in Django internal endpoint.
3. Job stuck in `PROCESSING` for a test-size video without progress logs.
4. Celery worker cannot connect to Redis.
5. Job reaches `FAILED` for baseline input.

## Sign-off template

```text
Phase 1 Sign-off
Date:
Operator:
Job ID:
Outcome: PASS | FAIL
Notes:
Artifact folder:
```
