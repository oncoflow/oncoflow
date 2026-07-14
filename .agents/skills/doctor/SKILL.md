---
name: doctor
description: "Checks medical data validity, oncology guidelines compliance (TNCD), and verifies patient record grounding to ensure clinical safety."
---

# Doctor (Clinical Expert) Skill

This skill ensures medical safety, compliance with French national digest-cancer guidelines (TNCD), and validation of clinical agent extractions.

## Clinical Safety Principles

### 1. Guideline Compliance (TNCD)
Clinical decisions and scientific evidence suggested by expert agents must align with the **Thésaurus National de Cancérologie Digestive (TNCD)**.
- For pancreatic diseases: Ground all evidence on `TNCDPANCREAS.pdf`.
- For esophageal diseases: Ground all evidence on `TNCDOESOPHAGE.pdf`.
- For hepatocellular carcinoma: Ground all evidence on `TNCDCHC.pdf`.

### 2. Patient Record Grounding
- **Strict Adherence**: The patient record (MTD) is the absolute source of truth.
- **No Interpretation**: Administrative and initial diagnostic extractions must not assume missing details or infer unlisted clinical symptoms.
- **Missing Data Flagging**: If standard clinical indicators (e.g. TNM staging, WHO performance status, histological type) are missing, the agent must systematically record them under `what_missing`.
- **Expert Relevance**: Expert agents must explicitly verify if the patient's case belongs to their cancer specialty (e.g. `expert_relevant: True`).
