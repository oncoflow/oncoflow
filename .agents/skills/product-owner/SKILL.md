---
name: product-owner
description: "Aligns the technical roadmap, patient dashboard interface, and case prioritization logic with French oncology clinical standards."
---

# Product Owner Skill

This skill defines the requirements, user flows, and case triage rules for Oncoflow, ensuring it perfectly fits the needs of Multidisciplinary Team Meetings (RCP/MDT).

## Domain Workflows

### 1. RCP Dashboard Cards Interface
The clinical user needs a clear and unified representation of patient files. The cards view must convey:
- **Patient Administrative Identity**: First and last name (never display full clinical records without standard authentication).
- **MDT Date**: Planned date for case review.
- **Relevant Experts**: Specialty expert agents determined to be relevant to the case.
- **Completeness Status**: Clearly outline missing elements in the patient file (e.g. missing pathology report, scan, clinical notes).
- **Urgency Priority Level**: Categorize priority to schedule patient order in meetings.

### 2. Case Prioritization Logic
Patients must be sorted dynamically inside the Streamlit dashboard using three severity levels:
- `🚨 Urgent`: Critical cases requiring immediate surgical/therapeutic decision.
- `🟠 Semi-urgent` / `Medium`: Standard diagnostic follow-ups or post-treatment reviews.
- `🟢 Standard` / `Low`: Long-term follow-ups or simple administrative validations.
- `⚪ Indéfini`: Unparsed cases.
