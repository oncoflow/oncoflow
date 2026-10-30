---
name: ubiquitous-language-english
description: Enforces 100% English docstrings and comments across the codebase, and strictly enforces the Ubiquitous Language term 'PatientMDTForm' (`patient_mdt_form` / `mdt_form`) instead of French 'RCP' in code identifiers, classes, methods, and docstrings.
---

# Ubiquitous Language & English Documentation Standard (`ubiquitous-language-english`)

This skill enforces strict linguistic and Domain-Driven Design (DDD) Ubiquitous Language conventions across the **Oncoflow / MedDataSyntis** codebase.

---

## 1. Mandatory English Docstrings & Code Comments

- **All docstrings** (module, class, method, and function docstrings) **MUST be written in English**.
- **All inline comments** (`# ...`) **MUST be written in English**.
- French is permitted **only** in user-facing UI strings (`src/ui/`), localized API user messages when explicitly required by the frontend, or clinical prompt templates targeting French records.
- Never write French words (e.g., `Port du domaine`, `Retourne`, `Construit`, `Supprime`, `Agrégat`) inside Python docstrings or comments.

---

## 2. Ubiquitous Language: `PatientMDTForm` Instead of `RCP` & `PatientRecord` Instead of `Dossier`

In the domain, application, and infrastructure layers:
- The French acronym **RCP** (*Réunion de Concertation Pluridisciplinaire*) must **always** be expressed using the Ubiquitous Language term **`PatientMDTForm`** (*Patient Multidisciplinary Team Form*, or `patient_mdt_form` / `mdt_form` in `snake_case`).
- The French term **Dossier** (*Dossier Patient*) must **always** be expressed using the English Ubiquitous Language term **`PatientRecord`** (`patient_record` in `snake_case`).

| Forbidden Legacy/French Identifier | Mandatory Ubiquitous Language Identifier |
| :--- | :--- |
| `RcpFormRepository` | `PatientMDTFormRepository` |
| `InMemoryRcpFormRepository` | `InMemoryPatientMDTFormRepository` |
| `MongoRcpFormRepository` | `MongoPatientMDTFormRepository` |
| `RcpExtractionService` | `PatientMDTFormExtractionService` |
| `RcpQueueJobExecutor` | `PatientMDTFormQueueJobExecutor` |
| `PatientDossierService` | `PatientRecordService` |
| `dossier_service` | `patient_record_service` |
| `resolve_dossier` | `resolve_patient_record` |
| `delete_patient_dossier` | `delete_patient_record` |
| `rcp_repo` | `mdt_form_repo` |
| `verify_is_rcp_form` | `verify_is_patient_mdt_form` |
| `reject_non_rcp_form` | `reject_non_patient_mdt_form` |
| `list_rcp_cards` | `list_patient_mdt_form_cards` |
| `delete_rcp_document` | `delete_patient_mdt_form_document` |
| `rcp_storage_path` | `mdt_form_storage_path` |

### Allowed Exceptions (External/Schema Compatibility Only)
- Existing Pydantic field names inside medical extraction schemas or MongoDB document keys that are part of external data contracts (e.g., `date_rcp`, `rcp_info`, `config.rcp`, `RCPProcessingStatus`, `rcp_count` in API responses) may remain only where required by external schema/configuration contracts, while all new and refactored domain/application/repository classes, methods, parameters, and docstrings MUST use `PatientMDTForm` / `patient_mdt_form` / `mdt_form`.

---

## 3. Automated Verification Checklist

Before completing any code change:
1. Inspect all modified/created `.py` files to ensure every docstring and comment is in English.
2. Verify that all domain ports, repository adapters, application use-case classes, and method names use `PatientMDTForm` / `patient_mdt_form` / `mdt_form` instead of `Rcp` / `rcp`.
3. Run the architectural test suite (`pytest application/tests/test_ddd_architecture.py`) to validate compliance.
