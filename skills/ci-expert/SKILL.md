---
name: ci-expert
description: "Manages continuous integration configurations, Ruff lint/formatting runs, local automated Pytest suites, and dependency alignments."
---

# CI Expert Skill

This skill governs testing pipelines, syntax style validations, and environment checks for the Oncoflow project.

## Verification & Pipelines

### 1. Style & Linting Suite
All additions or modifications to Python code must be checked against Ruff rules to maintain high quality:
- **Linting check**: `ruff check src/`
- **Formatting check**: `ruff format src/`

### 2. Automated Testing (Pytest)
Test suites for both core business models and agent tools must be run before merging changes:
- Run all tests: `pytest src/application/agent/tests/`
- Ensure all test assertions avoid external web API mockups, enforcing fully local execution boundaries.

### 3. Dependency Validation
- Any package update must be added through `pyproject.toml` and locked via `uv`.
- Runtime checks must verify compatibility with Python `>=3.13`.
