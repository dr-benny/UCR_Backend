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

When `API_KEY` is set, every route above except `/health*` and `/api/engines`
requires the key. HTTP clients send `Authorization: Bearer <key>`; WebSocket
clients pass `?token=<key>` (browsers can't set headers on the WS handshake).

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
| `API_KEY` | no | — | When set, `/api/analyze` + `/api/jobs` require it (`Authorization: Bearer <key>`, or `?token=` for WebSocket). Unset = auth disabled |
| `CORS_ORIGINS` | no | `*` | Comma-separated allowed origins. `*` auto-disables credentials |
| `TRUST_PROXY` | no | `false` | Read client IP from `X-Forwarded-For` (enable only behind a trusted proxy) |
| `AI_ENGINE` | no | `gemini` | Default engine (`gemini` or `claude`) |
| `GEMINI_MODEL` | no | `gemini-2.5-flash` | Default Gemini model |
| `ANALYSIS_SAMPLES` | no | `3` | Self-consistency sample count (1 = disabled) |
| `AI_MAX_CONCURRENT` | no | `10` | Max concurrent AI API calls |
| `IMAGE_DIR` | no | `images/` | Uploaded image storage directory |
| `MAX_IMAGE_BYTES` | no | `20971520` | Per-image size limit (20 MB) |
| `SUBMIT_RATE_LIMIT` | no | `10` | Max job submissions per IP per minute |

## Testing

```bash
pytest
```
