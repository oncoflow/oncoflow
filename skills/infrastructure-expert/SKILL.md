---
name: infrastructure-expert
description: "Manages local docker compose services (Milvus, Mongo), hardware VRAM allocations, GPU configurations, and network isolation."
---

# Infrastructure Expert Skill

This skill outlines operational rules for local hosting environments, Docker orchestration, database persistence, and system resources.

## System Orchestration

### 1. Database Subnet Isolation (Milvus & MongoDB)
- Databases are deployed using standard Docker Compose configurations.
- Main vector database: Milvus standalone instance defined in `docker/compose/milvus-standalone-docker-compose.yml`.
- MongoDB handles storage of metadata, RAG cache, and dashboard patient cards. Keep credentials securely defined inside local environment variables.

### 2. Hardware Resource Constraints
- Running local LLMs (Mistral Nemo, Granite vision models) and embedding pipelines requires significant VRAM resources.
- **Minimum Requirement**: 12GB NVIDIA VRAM.
- Agents must fail fast if GPU access is blocked or out-of-memory exceptions occur, rather than hanging indefinitely.

### 3. Local Privacy Isolation
- Strictly deny any outbound calls or internet requests that transmit patient files, medical terms, or logs.
- Network operations must only communicate over standard local bindings (`localhost`, `127.0.0.1`) on standard ports (`19530` for Milvus, `27017` for MongoDB, `11434` for Ollama).
