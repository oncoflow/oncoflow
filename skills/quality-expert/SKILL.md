---
name: quality-expert
description: "Ensures test coverage metrics, logging context formats (text/json), exception safety, and performance constraints."
---

# Quality Expert Skill

This skill ensures exceptional code reliability, rigorous logging formats, performance benchmarking, and strict exception boundaries.

## Rules & Standards

### 1. Robust Application Logging
- Logging must support both human-readable `text` formats and machine-parsable `json` structures depending on the environmental `APP_LOGS_LEVEL` settings.
- Always initialize handlers using `AppConfig.set_logger()`. Include necessary context keys (`model`, `output_format`, `page`):
```python
logger = app_conf.set_logger("ui", default_context={"page": "cards"})
```

### 2. Exception Safety & Spinner UX
- All database, vector search, or parsing failures must be caught cleanly before crashing the web application.
- User UI flows must show localized toasts or warning boxes rather than raw Python tracebacks:
```python
try:
    rag.read_document()
except Exception as e:
    st.error(f"Erreur lors de l'indexation : {e}")
```

### 3. Tool Execution Benchmark
- Search queries in `search_on_mtd` and `search_on_ressources` must have configurable execution timeouts.
- Set a baseline limit for retrieval count (`k=4`) to prevent context window bloat and latency spikes.
