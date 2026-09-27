---
name: python-developer
description: "Develops, modifies, and debugs Python services, LangChain chains, Vector Store connectors, and Streamlit dashboards within the Oncoflow application."
---

# Python Developer Skill

This skill provides comprehensive rules, code patterns, and reference architectures for managing Python development on the Oncoflow platform.

## Key Technologies
- **Python `>=3.13`** (Check and strictly follow typing and typing extension patterns).
- **Streamlit**: Single-page and multi-page configurations using `st.Page` and state synchronization via `st.session_state`.
- **LangChain**: Modern LangChain chains, custom agent wrappers, `ToolRetryMiddleware`, `ModelRetryMiddleware`, and Pydantic validation.
- **Milvus / Chroma**: MMR retrieval using `max_marginal_relevance_search` parameters (`k`, `fetch_k`, `expr`).

## Rules & Patterns

### 1. LangChain Agent Integration
When modifying or instantiating an agent, always refer to the base template in [agent.py](file:///home/guillaume/git/oncoflow/application/src/application/agent/agent.py). Utilize structured response structures based on Pydantic `BaseModel`:

```python
from pydantic import BaseModel, Field

class CustomResponse(BaseModel):
    clinical_summary: str = Field(description="Structured clinical description in French")
    is_complete: bool = Field(description="True if record is complete")
```

### 2. Streamlit Dashboard Best Practices
- Never use heavy processes inside standard Streamlit loops without catching exceptions or using spinners (`st.spinner()`).
- Keep date formatting robust and avoid comparing naive and aware datetimes. Use the utility:
```python
def to_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(pytz.timezone("Europe/Paris")).replace(tzinfo=None)
    return dt
```

### 3. Vector Database Connection Rules
- Do not build separate DB clients inside local search operations.
- Always retrieve context from standard readers passed through the LangChain runtime context:
```python
reader: DocumentReader = runtime.context["reader"]
retrieved_docs = reader.vecdb.clientdb.max_marginal_relevance_search(
    query, k=k, fetch_k=20, **kwargs
)
```
