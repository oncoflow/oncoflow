---
name: ddd-tdd-architect
description: "Enforces Domain-Driven Design (DDD), Hexagonal/Clean Architecture boundaries, and strict Test-Driven Development (TDD: Red -> Green -> Refactor) across the Oncoflow / MedDataSyntis codebase."
---

# DDD & TDD Architect Skill (`ddd-tdd-architect`)

This skill defines the architectural rules, tactical patterns, and strict Test-Driven Development (TDD) workflow for designing, refactoring, and implementing features in **Oncoflow / MedDataSyntis**.

---

## 1. Strict TDD Workflow (Red → Green → Refactor)

Every feature or architectural refactoring **MUST** follow the 3-step TDD cycle:

1. **🔴 RED (Write Failing Tests First)**:
   - Before writing or modifying any production code in `src/domain/`, `src/application/`, `src/infrastructure/`, or `src/routers/`, write unit/integration tests in `application/tests/` that specify the target domain invariants, repository contracts, and application use cases.
   - Domain and Application Use Case tests MUST run **in-memory without real I/O** (using pure domain objects and in-memory/fake repositories implementing the domain `Protocol` ports).
   - Run `pytest` to verify the new tests fail for the expected reason.

2. **🟢 GREEN (Implement Minimum Clean Code to Pass)**:
   - Implement the domain entities, value objects, repository protocols/adapters, and application use cases required to make the tests pass.
   - Ensure zero functional regression across existing user journeys (FastAPI routes, Streamlit views, Queue workers, AI extraction).

3. **🔵 REFACTOR (Enforce Clean Boundaries & Linting)**:
   - Eliminate duplication between FastAPI (`src/routers/`) and Streamlit (`src/ui/`) by routing both through Application Use Cases.
   - Run `ruff check src/ tests/` and `ruff format src/ tests/`.
   - Re-run the full `pytest` suite to confirm 100% green status.

---

## 2. Strategic & Tactical DDD Rules

### A. Dependency Rule (Hexagonal / Clean Architecture)
Dependencies MUST point **inward** toward the Domain:

```
src/ui/ & src/routers/  ──►  src/application/  ──►  src/domain/  ◄──  src/infrastructure/
```

- **`src/domain/` (Pure Core — ZERO I/O)**:
  - Contains **Entities**, **Aggregate Roots**, **Value Objects**, **Domain Events / Exceptions**, **Domain Services**, and **Repository Ports (`typing.Protocol`)**.
  - **FORBIDDEN in `src/domain/`**:
    - Importing `src.infrastructure.*` (no `Mongodb`, no `QueueBroker`, no `pymongo`, no `httpx`).
    - Importing `src.application.reader.DocumentReader` or `src.application.agent.*` for execution.
    - File system mutations (`os.remove`, `open`, `os.makedirs`).
    - UI presentation details (no `streamlit`, no hardcoded URLs like `"datas?patient_id=..."`).
    - Module-level singletons that freeze the medical domain at import time.

- **`src/application/` (Use Cases & Orchestration)**:
  - Contains **Application Services / Use Cases** that coordinate Domain Aggregates, Repository Ports, Document Readers, AI Agents, and the Job Queue.
  - Shared by **both** FastAPI (`src/routers/`) and Streamlit (`src/ui/`).

- **`src/infrastructure/` (Adapters & Technical Drivers)**:
  - Implements the Ports defined in `src/domain/` or `src/application/`:
    - Persistence adapters (`MongoPatientRepository`, `MongoPatientMDTFormRepository`, `MongoBugReportRepository`, `MongoDocumentCacheRepository`).
    - Queue & concurrency engine (`InMemoryQueueManager`, `QueueBroker`), delegating business job execution to an injected Application `QueueJobExecutor`.
    - Document parsers & Vector Stores (`Docling`, `Milvus`, `Chroma`, `Ollama`).

- **`src/ui/` & `src/routers/` (Primary Adapters / Presentation)**:
  - Thin controllers/views that validate user input, invoke Application Use Cases, and format responses/views (building UI links, HTTP status codes, Streamlit widgets).

- **Ubiquitous Language & English Documentation (see `ubiquitous-language-english` skill)**:
  - All docstrings and code comments MUST be written in English.
  - Always use `PatientMDTForm` (`patient_mdt_form` / `mdt_form`) instead of French `RCP` in class names, method names, and repository ports (`PatientMDTFormRepository`, `PatientMDTFormExtractionService`, `PatientMDTFormQueueJobExecutor`).

---

## 3. Tactical Building Blocks

1. **Value Objects (`frozen=True` Pydantic models or dataclasses)**:
   - Use immutable Value Objects for concepts defined by their attributes rather than an ID (e.g., `PatientIdentity`, `CardMetrics`, clinical extraction schemas in `oncology/` and `sma/`).
2. **Entities & Aggregate Roots**:
   - **No I/O in `__init__`**: Instantiating an entity (`Patient`, `PatientMDTForm`) must be a pure, fast, in-memory operation.
   - Business state transitions and invariant checks belong on the Aggregate Root (`patient.attach_file(...)`, `form.compute_card_metrics()`, `form.select_latest_analyzed(...)`).
3. **Repositories (`typing.Protocol`)**:
   - Accept and return **Domain Entities / Value Objects**, not raw MongoDB dicts with `_id`.
   - Encapsulate all collection names (`patients`, `rcp_info`, `bug_reports`, `document_cache`) inside `src/infrastructure/documents/`.
