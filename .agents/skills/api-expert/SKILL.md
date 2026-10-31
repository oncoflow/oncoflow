---
name: api-expert
description: "Expert on the Oncoflow / MedDataSyntis Cross-Domain FastAPI architecture (`app-api.py`, `src/routers/`, `src/models/`, `src/application/use_cases/`). Use when auditing, debugging, refactoring, testing, or extending REST and Server-Sent Events (SSE) API endpoints."
---

# Oncoflow API Expert Skill (`api-expert`)

This skill encapsulates full architectural knowledge of the **Oncoflow / MedDataSyntis Cross-Domain FastAPI** (`application/app-api.py`, `src/routers/`, `src/models/`) and defines a concrete roadmap and ruleset for evolving and improving the API.

---

## 1. Current API Architecture Map

### Entrypoint & Lifespan (`application/app-api.py`)
- **App Metadata**: `Oncoflow Cross-Domain API` (`v1.1.0`), OpenAPI schema served at `/api/v1/openapi.json`, interactive docs at `/docs` and `/redoc`.
- **Lifespan Management**:
  1. Boots `InMemoryQueueManager` with `auto_start_workers=True`.
  2. Runs crash recovery from MongoDB (`queue_manager.recover_unfinished_from_mongodb()`).
  3. On shutdown: stops queue workers (`queue_manager.shutdown()`), unloads LLM weights from VRAM (`unload_active_models(app_conf)`), and closes process-wide MongoDB clients (`close_all_mongo_clients()`).
- **Public Healthcheck**: `GET /health` -> `HealthResponse` (status, allowed domains, queue stats).

### Security & Multi-Domain Middleware (`src/routers/dependencies.py`)
- **Authentication (`verify_api_token`)**:
  - Protects all `/api/v1/*` routers via `Authorization: Bearer <token>` or `X-API-Key: <token>`.
  - Uses constant-time `hmac.compare_digest` against `APP_API_TOKEN` (`SecretStr`).
  - Mandatory whenever `APP_DEV_MODE=false` (enforced at startup).
- **Multi-Domain Routing (`AllowedDomainMiddleware` & `DomainConfigDep`)**:
  - Intercepts `/api/*` requests, extracts `?domain=...` or `X-Oncoflow-Domain`, validates against `APP_ALLOWED_DOMAINS` (e.g., `oncology`, `sma`), attaches `request.state.domain_config` via `@lru_cache` `get_domain_scoped_config(domain)`, and echoes `X-Oncoflow-Domain` in response headers.
- **Database Session (`get_db` / `require_db`)**:
  - Yields a domain-scoped `Mongodb(config)` wrapper backed by the shared process-wide `MongoClient` pool.

### Versioned Routers (`/api/v1`)
1. **`/api/v1/patientmdtform`** (`src/routers/patientmdtform.py`, schemas in `src/models/rcp.py`):
   - `GET ""` -> `list[RCPCardResponse]`: Summary cards for all `PatientMDTForm` records in the domain.
   - `GET /patients` -> `list[PatientCardResponse]`: Aggregated patient cards from their latest analyzed `PatientMDTForm`.
   - `GET /patients/{patient_id}` -> `PatientDetailResponse`: Patient identity + chronological history of all `PatientMDTForm` documents.
   - `DELETE /patients/{patient_id}` -> `MessageResponse`: Cascades deletion across `PatientRecord`, `PatientMDTForm` docs, cache, vector store chunks, and PDF files.
   - `POST /patients/{patient_id}/chat` -> `ChatResponse`: Multi-document clinical agent chat across a patient's full history.
   - `GET /{filename}` -> `dict[str, Any]`: Full `PatientMDTForm` document.
   - `DELETE /{filename}` -> `MessageResponse`: Deletes a single `PatientMDTForm` and synchronizes the parent `PatientRecord`.
   - `POST /upload` -> `UploadResponse`: Streams upload in 64 KB chunks (50 MB cap), verifies `%PDF-` magic header, deduplicates by SHA-256 (`resolve_upload`), writes to disk, and enqueues into `PriorityQueue` (or runs synchronously if queue is disabled).
   - `POST /{filename}/process` -> `ProcessResponse`: Reprocesses a single clinical section (`model_name`) or the entire form (`preserve_manual_edits`).
   - `POST /{filename}/chat` -> `ChatResponse`: Single-document agent chat.
   - `GET /{filename}/pdf` -> `FileResponse`: Streams original PDF (`safe_path` traversal protection).
   - `PATCH /{filename}/sections/{section_name}` -> `dict[str, Any]`: Manual clinical override with `manually_edited_sections` tracking and audit metadata (`edited_by`).
   - `PATCH /{filename}/administrative` -> `dict[str, Any]`: Updates patient identity and optionally propagates across all linked forms.
   - `POST /{filename}/link-patient` -> `dict[str, Any]`: Re-links a form to an existing `PatientRecord`.

2. **`/api/v1/queue`** (`src/routers/queue.py`, schemas in `src/models/queue.py`):
   - `GET /domains` -> `QueueDomainsResponse`
   - `GET /stats` -> `QueueStatsResponse`
   - `GET /jobs` -> `list[QueueJobResponse]` (filters: `domain`, `status`, `batch_id`, `filename`, `limit`)
   - `GET /thinking` & `GET /jobs/{job_id}/thinking` -> `QueueThinkingResponse`
   - `GET /thinking/stream` & `GET /jobs/{job_id}/thinking/stream` -> `EventSourceResponse` (`ServerSentEvent` streaming `<think>` deltas, heartbeats, and completion)
   - `POST /enqueue-import` & `POST /rerun` -> `EnqueueResponse`
   - `POST /jobs/{job_id}/retry` -> `QueueJobResponse`
   - `DELETE /jobs/{job_id}` -> `JobDeletedResponse`
   - `POST /clean` -> `QueueCleanResponse` (`completed`, `failed`, `reset_stuck`, `retry_failed`, `pending`, `all`)
   - `GET /locks` -> `list[GpuLeaseResponse]` & `DELETE /locks` -> `ReleaseLocksResponse`

3. **`/api/v1/agents`** (`src/routers/agents.py`, schemas in `src/models/agents.py`):
   - `GET ""` & `GET /{agent_name}` -> `AgentDetailResponse` (system prompt, LLM models, attached clinical reference resources).

4. **`/api/v1/resources`** (`src/routers/resources.py`, schemas in `src/models/resources.py`):
   - `GET ""` -> `list[ResourceIndexResponse]`
   - `POST /{filename}/index` -> `ResourceIndexedResponse`
   - `POST /{filename}/chat` -> `ChatResponse`

---

## 2. High-Priority Improvement Roadmap

When improving or refactoring the API, systematically address these architectural opportunities:

### A. Pure FastAPI Dependency Injection (`Annotated[..., Depends(...)]`)
- **Issue**: In `src/routers/patientmdtform.py`, `_build_record_service` and `_build_extraction_service` are plain helper functions, and `delete_rcp`, `upload_rcp_file`, and `process_rcp` omit `db=Depends(require_db)`, instantiating repositories directly. Furthermore, `get_allowed_domains()` in `src/routers/queue.py` calls `AppConfig()` directly instead of `get_base_config()`.
- **Improvement**:
  - Expose `RecordServiceDep = Annotated[PatientRecordService, Depends(get_record_service)]` and `ExtractionServiceDep = Annotated[PatientMDTFormExtractionService, Depends(get_extraction_service)]` in `src/routers/dependencies.py`.
  - Use `get_base_config()` in `GET /api/v1/queue/domains` to avoid disk/env re-parsing.

### B. Strongly-Typed Pydantic Response Schemas (Zero `dict[str, Any]`)
- **Issue**: `GET /{filename}`, `PATCH /{filename}/sections/{section_name}`, `PATCH /{filename}/administrative`, and `POST /{filename}/link-patient` return `dict[str, Any]` and rely on manual recursive `serialize_mongo_doc`.
- **Improvement**:
  - Introduce `PatientMDTFormDetailResponse`, `AdministrativeUpdateResponse`, and `LinkPatientResponse` in `src/models/` so Pydantic serializes responses in Rust, filters internal fields, and generates rich OpenAPI 3.1 schemas.

### C. Real-Time SSE Streaming for Agent Chat & Async Resource Indexing
- **Issue**: `POST /patientmdtform/{filename}/chat`, `POST /patientmdtform/patients/{patient_id}/chat`, and `POST /resources/{filename}/chat` block until full LLM completion. `POST /resources/{filename}/index` blocks on heavy PDF parsing and vector embedding.
- **Improvement**:
  - Add SSE streaming endpoints (`POST .../chat/stream` with `response_class=EventSourceResponse`) yielding `ServerSentEvent` chunks (`thinking` and `message` events).
  - Allow enqueueing resource indexing jobs into `InMemoryQueueManager` so GPU/CPU embedding work is scheduled alongside MDT form extraction.

### D. Missing Domain Routers (`/api/v1/bug-reports`)
- **Issue**: `BugReport` (`src/domain/bug_report.py`) and `MongoBugReportRepository` (`src/infrastructure/documents/repositories.py`) exist, but Streamlit (`src/ui/reports/bugs.py`) accesses MongoDB directly instead of going through an API router.
- **Improvement**:
  - Add `src/routers/bug_reports.py` (`/api/v1/bug-reports`) with `GET`, `POST`, `PATCH /{report_id}`, and `DELETE /{report_id}`.

### E. RFC 7807 / Standardized Error Responses & Ubiquitous Language
- Map domain exceptions (`NonPatientMDTFormError`, `UnsafePathError`, `ValueError`, `KeyError`) via centralized FastAPI `@app.exception_handler(...)` handlers instead of repetitive `try ... except HTTPException: raise except Exception:` blocks in every endpoint.
- Migrate legacy `rcp` identifiers and French docstrings in `src/routers/` and `src/models/rcp.py` to `PatientMDTForm` and 100% English docstrings (`ubiquitous-language-english` skill).

---

## 3. Testing & Verification Workflow (Strict TDD)

Always run from `/home/guillaume/git/oncoflow/application`:

1. **Write Failing Contract / Integration Tests First (`Red`)**:
   - Add tests in `application/tests/test_api_*.py` using `fastapi.testclient.TestClient(app)` without starting background workers (do not enter lifespan context unless testing lifespan).
   - Verify OpenAPI contract compliance with `pytest tests/test_api_openapi.py tests/test_api_auth.py`.
2. **Implement & Pass (`Green`)**:
   - Keep routers thin; place orchestration in `src/application/use_cases/`.
3. **Lint & Format (`Refactor`)**:
   - `uv run ruff check src/ tests/ app-api.py`
   - `uv run ruff format --check src/ tests/ app-api.py`
   - `uv run pytest tests/`
