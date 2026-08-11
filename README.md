# Urban Microclimate Analyzer — Backend

FastAPI service that analyzes street-level images for urban microclimate and walkability indicators using AI vision models.

## Architecture

| Component | Purpose |
|-----------|---------|
| **FastAPI** | REST API + async request handling |
| **Redis** | Job state, sorted-set index, rate limiting, pub/sub |
| **Celery** | Background image-analysis worker pool |
| **Gemini Vision** | Default AI engine (pluggable) |
| **Claude Vision** | Optional AI engine |

## AI Engine Registry

Engines are LEGO-pluggable via `app/services/ai_engines/`. Add a new provider by:

1. Creating `<name>_engine.py` that subclasses `BaseAIEngine` and implements `_call_api()`
2. Adding an entry to `_REGISTRY` in `app/services/ai_engines/__init__.py`

Self-consistency sampling (`ANALYSIS_SAMPLES > 1`) runs N parallel API calls and aggregates results via median (floats) or majority vote (strings), boosting confidence on high-agreement fields.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `GET` | `/api/engines` | List registered AI engines and models |
| `POST` | `/api/analyze` | Synchronous single-image analysis |
| `POST` | `/api/jobs/images` | Submit batch job (async, up to 200 images) |
| `GET` | `/api/jobs` | List all jobs (filterable by status) |
| `GET` | `/api/jobs/{id}` | Poll job status + results |
| `DELETE` | `/api/jobs/{id}` | Cancel + delete job |
| `POST` | `/api/jobs/{id}/retry` | Retry a failed job |
| `GET` | `/api/jobs/{id}/export` | Export results as `?format=json` or `?format=csv` |
| `WS` | `/api/jobs/{id}/ws` | Real-time progress stream |
| `POST` | `/api/prompts` | Create a stored prompt (returns id) |
| `GET` | `/api/prompts` | List stored prompts |
| `GET` | `/api/prompts/{id}` | Get a stored prompt |
| `PUT` | `/api/prompts/{id}` | Update a stored prompt |
| `DELETE` | `/api/prompts/{id}` | Delete a stored prompt |

When at least one key exists under `API_KEY_DIR`, every route above except
`/health*` and `/api/engines` requires a key. HTTP clients send
`Authorization: Bearer <key>`; WebSocket clients pass `?token=<key>` (browsers
can't set headers on the WS handshake). No keys on disk = auth disabled.

### API keys & quota

Keys are files under `API_KEY_DIR` (one JSON file per key, durable on disk —
not Redis), managed with:

```bash
python scripts/manage_api_keys.py create "client-a" --daily-limit 500
python scripts/manage_api_keys.py list
python scripts/manage_api_keys.py revoke <key_id>
```

`create` prints the secret once — it's also saved in the key's JSON file.
Each key has a `daily_limit` on AI calls (`images × samples`, counted at
`/api/analyze` and job submit/retry time); omit `--daily-limit` to fall back
to `DEFAULT_DAILY_AI_CALL_LIMIT`. Usage resets at 00:00 UTC. A request that
would exceed the remaining budget is rejected with `429` before any AI call
is made.

### Prompt library

`/api/analyze` and `/api/jobs/images` accept an optional `prompt_id` form field
to run a **stored** prompt instead of the built-in one. Manage prompts via the
`/api/prompts` CRUD routes; they're persisted as JSON files under `PROMPT_DIR`
(durable on disk — no TTL, not in Redis). A job snapshots the prompt text at
submit time, so editing or deleting a prompt never breaks an in-flight job.

> The downstream CSV export and self-consistency aggregation assume the built-in
> JSON schema (the four analysis categories + `confidence_scores`). A custom
> prompt that returns a different shape still works for JSON output, but those
> two features expect the standard schema.

## Setup

```bash
cp .env.example .env          # fill in API keys
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start services:

```bash
# Terminal 1 — Redis
redis-server

# Terminal 2 — API
uvicorn app.main:app --reload

# Terminal 3 — Worker
celery -A app.worker worker --loglevel=info
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | yes | — | Google Gemini API key |
| `ANTHROPIC_API_KEY` | no | — | Anthropic Claude API key (required to use `engine=claude`) |
| `REDIS_URL` | no | `redis://localhost:6379` | Redis connection URL |
| `API_KEY_DIR` | no | `api_keys/` | Durable on-disk store of issued API keys; manage with `scripts/manage_api_keys.py`. Empty = auth disabled |
| `DEFAULT_DAILY_AI_CALL_LIMIT` | no | `1000` | Fallback daily AI-call quota for keys without their own `daily_limit` |
| `CORS_ORIGINS` | no | `*` | Comma-separated allowed origins. `*` auto-disables credentials |
| `TRUST_PROXY` | no | `false` | Read client IP from `X-Forwarded-For` (enable only behind a trusted proxy) |
| `AI_ENGINE` | no | `gemini` | Default engine (`gemini` or `claude`) |
| `GEMINI_MODEL` | no | `gemini-2.5-flash` | Default Gemini model |
| `ANALYSIS_SAMPLES` | no | `3` | Default self-consistency sample count (1 = disabled). Override per request with the `samples` form field |
| `MAX_ANALYSIS_SAMPLES` | no | `5` | Upper bound a caller may request via `samples` |
| `MAX_JOB_API_CALLS` | no | `1000` | Reject a job whose `images × samples` exceeds this |
| `AI_MAX_CONCURRENT` | no | `10` | Max concurrent AI API calls **per process**. Under Celery prefork the cap is per worker process, so real provider-side concurrency ≈ (workers + 1) × this — size it against your provider's rate limit |
| `AI_CALL_TIMEOUT` | no | `120` | Seconds before a single AI call is aborted + retried |
| `WS_HEARTBEAT_INTERVAL` | no | `30` | WebSocket heartbeat / state re-check interval (s) |
| `STUCK_JOB_TIMEOUT` | no | `600` | Idle seconds before a job is reaped as failed |
| `STUCK_JOB_REAPER_INTERVAL` | no | `60` | How often the reaper scans (s) |
| `IMAGE_DIR` | no | `images/` | Uploaded image storage directory |
| `PROMPT_DIR` | no | `prompt_store/` | Durable on-disk store for the prompt library |
| `MAX_PROMPT_CHARS` | no | `20000` | Max length of a stored prompt's text |
| `MAX_IMAGE_BYTES` | no | `20971520` | Per-image size limit (20 MB) |
| `MAX_JOB_TOTAL_BYTES` | no | `1073741824` | Reject a job whose images' combined size exceeds this (1 GB) |
| `SUBMIT_RATE_LIMIT` | no | `10` | Max job submissions per IP per minute |

## Testing

```bash
pytest
```
