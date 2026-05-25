# Changelog

All notable changes to this project will be documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [0.5.0] — 2026-05-14

### Added — Async Job Queue

- `models/job.py` — `Job` model (UUID hex pk, status, request/result JSONB,
  progress_current/total, error, timestamps, route_id FK)
- `dao/job_dao.py` — `JobDAO` CRUD: `create_job`, `get_by_id`, `list_jobs`,
  `mark_started`, `increment_progress`, `mark_done`, `mark_failed`
- `schemas/job.py` — `JobPoint`, `RouteJobCreate` (1–200 points, concurrency 1–10),
  `JobProgress`, `JobResponse`
- `services/job_service.py` — `process_route_job()` background runner:
  - Opens its own `SessionLocal()` (request session is closed by then)
  - Creates `SurveyRoute` → marks job `processing` with `route_id`
  - Runs points through `analyze_from_streetview` in parallel (per-job Semaphore
    + global `AI_MAX_CONCURRENT` cap from [0.4.0])
  - Individual point failures (LookupError, AI errors) are caught and counted —
    don't crash the whole job
  - Whole-job crashes → `mark_failed(error=...)` so rows never stuck in
    'processing' forever
- `api/v1/jobs.py` — 3 endpoints under `/api/jobs`:
  - `POST /route` → 202 + job id (fire-and-forget via `asyncio.create_task`)
  - `GET /{id}` → poll status, progress, result/error
  - `GET /` → list jobs with optional `?status=` filter

### Why

Long routes (50+ points) take ~5–10 min to analyse. Blocking HTTP request
times out at client side. New flow:
```
client  ──POST /api/jobs/route──▶  API returns job_id in <100ms
                                   ↳ asyncio.create_task fires runner
client  ──GET  /api/jobs/{id}──▶   {"status":"processing","progress":{"current":3,"total":10}}
                                   ...
client  ──GET  /api/jobs/{id}──▶   {"status":"done","result":{"route_id":42,"analysis_ids":[...]}}
```

Trade-off accepted: if the API process crashes mid-job, the row stays in
`processing`. Acceptable for now; recoverable later with a startup sweep
that flips orphaned `processing` rows to `failed`.

### Tests

- `tests/test_dao_job.py` — 12 tests covering all DAO methods
- `tests/test_api_jobs.py` — 13 tests: 202 response, validation (empty points,
  concurrency 1–10, missing lat), GET found/missing, status=done/failed responses
- `tests/test_service_job.py` — 6 tests: happy path, partial failure, route-creation
  crash → mark_failed, empty points, session always closed on success/failure

Total: **182 tests passing** (was 151).

---

## [0.4.0] — 2026-05-14

### Added — Global AI Rate Limiter

- `config.py` — `AI_MAX_CONCURRENT: int = 10` — hard cap concurrent Gemini calls ทั้ง app
- `base.py` — `_guarded_call()` — wrapper รอบ `_call_api` ที่ acquire global semaphore ก่อนเสมอ
- `base.py` — `_get_semaphore()` — lazy-init semaphore (สร้างใน event loop แรกที่ใช้)  
  ทุก call ผ่านจุดนี้จุดเดียว ไม่ว่าจะมาจาก batch หรือ self-consistency sampling

### Why

เดิม: batch=5 images × samples=3 = **15 Gemini calls พร้อมกัน** → rate limit  
ตอนนี้: เกิน `AI_MAX_CONCURRENT` → queue อัตโนมัติ ไม่ error

### Changed

- `analyze_image_bytes` ใน `base.py` — เปลี่ยนจากเรียก `_call_api` โดยตรง → เรียก `_guarded_call` แทน
- Tests — เพิ่ม 3 cases ใน `TestGlobalSemaphore`:
  - `test_guarded_call_invokes_call_api` — ตรวจว่า semaphore ถูก acquire/release
  - `test_semaphore_limits_concurrency` — วัด peak concurrent calls ≤ limit จริง
  - `test_semaphore_releases_on_exception` — exception ต้อง release semaphore (ไม่ deadlock)

---

## [0.3.0] — 2026-05-14

### Added — Parallel Batch Processing

- `GET /api/analyze/batch` — เพิ่ม `?concurrency=N` param (1–10, default 5)  
  จากเดิม sequential for loop → ใช้ `asyncio.gather` + `asyncio.Semaphore`  
  ผล: 10 points จาก ~30s → ~6s
- `POST /api/analyze/upload/batch` — เพิ่ม `concurrency` form field เช่นกัน  
  อ่านไฟล์ทั้งหมดพร้อมกันก่อน (`asyncio.gather`) แล้วค่อย analyze คุมด้วย Semaphore
- Helper `_read_upload()` แยก logic อ่าน UploadFile + validate mime ออกมา
- Tests เพิ่ม 4 cases: concurrency param, out-of-range 422, all-fail returns [], order preserved

### Changed

- `analyze.py` — import `asyncio`, batch handler refactor เป็น `_analyze_one()` inner coroutine
- `upload.py` — import `asyncio`, split read phase / analyze phase ออกจากกัน

---

## [0.2.0] — 2026-05-14

### Added — Self-Consistency Sampling (Wang et al., 2022)

- `config.py` — `ANALYSIS_SAMPLES: int = 3` ตั้งค่าจำนวน samples (1 = ปิด)
- `base.py` — multi-sample path ใน `analyze_image_bytes`:  
  เรียก `_call_api` N ครั้งพร้อมกัน (`asyncio.gather`) ด้วย temperature=0.7  
  aggregate ผล: float→median, string→majority vote, list→union
- `base.py` — `_aggregate_samples(samples)` — recursive merge dict/list/scalar
- `base.py` — `_aggregate_value(values)` — median (numeric) / majority vote (string)
- `base.py` — `_agreement_score(values)` — CV-based score สำหรับ numeric, fraction สำหรับ string  
  ผล blend เป็น confidence_scores ใหม่: `min(1.0, mean_conf × (0.4 + 0.6 × agreement))`
- `gemini_engine.py` — รับ `temperature` param, wrap sync SDK call ด้วย `asyncio.to_thread`  
  ทำให้ concurrent samples วิ่งจริงโดยไม่ block event loop
- `tests/test_service_consistency.py` — 40 tests ครอบ aggregation ทุก edge case

---

## [0.1.0] — 2026-05-14

### Added — Test Suite (from zero)

- `tests/conftest.py` — patch `MetaData.create_all` ก่อน import app, mock DB session factory,  
  fixtures: `db`, `mock_route`, `mock_analysis`, `client` (TestClient)
- `tests/test_model_properties.py` — 20 tests computed properties ของ `StreetAnalysis`
- `tests/test_dao_route.py` — 8 tests RouteDAO CRUD
- `tests/test_dao_analysis.py` — 14 tests AnalysisDAO (รวม auto-increment logic)
- `tests/test_service_ai_base.py` — 9 tests `_extract_json` (direct, markdown, embedded, fallback)
- `tests/test_service_analysis.py` — 15 tests pipeline: validate_mime, save_upload, _build_dao_data
- `tests/test_api_routes.py` — 16 tests routes endpoints
- `tests/test_api_analyze.py` — 25 tests analyze/upload endpoints
- `pytest.ini` — `asyncio_mode = auto`
- `requirements-dev.txt` — pytest, pytest-asyncio, httpx

### Fixed

- `models/analysis.py` — bug `walkway_width_m`: `"wide" in "very_wide"` เป็น True  
  แก้โดยเรียงเช็ค `"very_wide"` และ `"very_narrow"` ก่อน `"wide"` และ `"narrow"`

### Changed — AI Prompt (prompts.py)

- บรรทัดแรก: `OUTPUT ONLY VALID JSON. Do not include any text...`
- เพิ่ม 8-step Chain-of-Thought reasoning section
- เพิ่มตาราง Bangkok street typology calibration (ตรอก 1–2m → ถนนใหญ่ 16–30m)
- เพิ่มตาราง reference object sizes (คน, มอเตอร์ไซค์, รถยนต์, ประตู, ฯลฯ)
- Perspective Correction section พร้อม triangulation rules
- Type annotations ต่อ field + confidence score rubric (0.9–1.0 / 0.7–0.9 / ...)
- แก้ JSON closing bracket ที่หายไป

---

## [0.0.1] — ก่อนหน้านี้ (initial state)

### Added (existing before this session)

- FastAPI app + SQLAlchemy + GeoAlchemy2/PostGIS
- Google Street View Static API integration
- Gemini Vision AI engine (single-sample)
- RouteDAO, AnalysisDAO CRUD
- KML export endpoint
- Upload-based analysis endpoints (single + batch sequential)
- `export_service.py`, `storage.py` (S3, inactive)
