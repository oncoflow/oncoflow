---
name: product-owner
description: "Aligns the technical roadmap, functional specifications, patient dashboard interface, longitudinal multi-RCP workflows, and case prioritization logic with French hospital RCP/MDT standards (Oncology & Rare Diseases / SMA)."
---

# DataSyntis Product Owner Skill (`product-owner`)

This skill defines the product vision, functional requirements, hospital user personas, case triage rules, and medico-legal boundaries for **DataSyntis**, ensuring every feature serves Multidisciplinary Team Meetings (**RCP / MDT**) in French hospitals.

---

## 1. Product Vision, Positioning & Three Core Promises

- **Brand Name**: **DataSyntis**
- **Mission**:
  > *"Libérer du temps médical utile en transformant le chaos documentaire en dossiers directement exploitables pour la décision RCP."*
- **Positioning**:
  > *"L'outil d'analyse des dossiers qui prépare le terrain pour faciliter et optimiser la décision médicale collégiale."*
- **Three Product Promises**:
  1. **Exhaustivité documentaire** : Ingestion multi-PDF agnostique, réconciliation d'identité et consolidation chronologique multi-RCP par patient.
  2. **Conformité aux recommandations** : Contrôle systématique de complétude du dossier et propositions d'experts cadrées sur les référentiels scientifiques (ex. TNCD en oncologie digestive, PNDS dans l'amyotrophie spinale / SMA).
  3. **Fluidité logistique** : Ordonnancement intelligent de la séance RCP selon le degré d'urgence, l'état de complétude et le quorum de spécialités requis.

---

## 2. Hospital Personas & Zero-Friction Workflows

Every feature must be evaluated against the concrete operational needs of two primary hospital users:

### A. La Secrétaire médicale / Coordinateur RCP (Préparation & Logistique de séance)
- **Key questions answered in < 2 seconds**:
  1. *Le dossier est-il complet pour passer en RCP ?* $\rightarrow$ Badge `:orange-badge[⚠️ À compléter (N)]` ou `:green-badge[✅ Dossier conforme]` + liste structurée des pièces manquantes (`MTDCompleted`).
  2. *Quels spécialistes dois-je convoquer pour le quorum ?* $\rightarrow$ Ligne dédiée `👥 Spécialités requises (N) : 🧠 Neurologie · 🧬 Génétique · 🫁 Pneumologie...`
  3. *Dans quel ordre programmer les dossiers de la séance ?* $\rightarrow$ Tri par urgence (`Urgent` > `Semi-urgent` > `Standard`) et filtrage par complétude ou spécialité.
  4. *Que faire si l'extraction d'identité échoue sur un PDF scanné ?* $\rightarrow$ Bandeau d'alerte proactif permettant de saisir l'état civil manuellement ou de rattacher la fiche à un patient existant.

### B. Le Médecin / Spécialiste RCP (Analyse clinique & Concertation collégiale)
- **Key questions answered in < 2 seconds**:
  1. *Quelle est la situation actuelle et l'orientation proposée ?* $\rightarrow$ Carte épinglée `🩺 Synthèse synoptique RCP` (Priorité, Complétude, Orientation `🧭 Adaptation suggérée` vs `Suivi habituel`, Spécialités requises, et repères cliniques clés).
  2. *Qu'est-ce qui a changé depuis la dernière RCP de ce patient ?* $\rightarrow$ Navigation chronologique multi-RCP (`◀ Préc.` / `Suiv. ▶` + frise enrichie) et badges `📈 Évolution vs RCP du DD/MM/YYYY` (delta d'urgence, d'orientation, de score OMS, nouvelles imageries ou lignes de traitement).
  3. *Quels sont les éléments du bilan clinique et paraclinique ?* $\rightarrow$ Onglet `🩺 Dossier clinique` avec synthèse directement dans l'en-tête de chaque accordéon (replié par défaut pour éviter toute surcharge visuelle).
  4. *Quels sont les avis motivés par spécialité et les preuves issues des référentiels ?* $\rightarrow$ Onglet `⚖️ Avis & Décision RCP` listant chaque avis de spécialité un à un avec ses propositions (`ExpertSuggestion`) et ses citations exactes (`Reference`).

---

## 3. Case Prioritization & Medico-Legal Semantics

### A. Triage Severity Levels
Patients and RCP forms are dynamically prioritized using four levels:
- `🚨 Priorité haute` (`Urgent`) : Cas critiques nécessitant une discussion et une adaptation thérapeutique ou chirurgicale prioritaire.
- `🟠 Semi-urgent` (`Medium`) : Réévaluations diagnostiques ou bilans intermédiaires à traiter rapidement.
- `🟢 Standard` (`Low`) : Surveillance régulière, suivi au long cours ou validation de conformité.
- `⚪ Non qualifié` (`Indéfini`) : Fiche en attente ou non encore qualifiée.

### B. Non-Prescriptive Medico-Legal Wording (`CareOrientationProposal`)
- DataSyntis is a **pre-RCP preparation and decision-support tool**, never an autonomous prescriber.
- Always use `CareOrientationProposal` (`care_adaptation_suggested`, `proposed_care_type`, *"Proposition d'orientation pré-RCP"*, *"Adaptation suggérée"*, *"Suivi habituel"*) rather than prescriptive terms like *"Intervention requise"*.

### C. Human-in-the-Loop Sovereignty (`manual_edits`)
- Any field edited manually by a clinician or medical secretary is flagged in `manual_edits`.
- Standard AI re-extractions (`Relancer l'IA`) must preserve manual edits by default (`preserve_manual_edits=True`); overwriting manual edits is restricted to explicit opt-in via Power Mode (`Options IA`).

---

## 4. Ubiquitous Language & Acceptance Criteria Checklist

When writing specifications or reviewing implementations:
1. **Ubiquitous Language in Code**: Enforce `PatientMDTForm` (`patient_mdt_form`, `mdt_form`) in Python classes, methods, and docstrings (see [`.agents/skills/ubiquitous-language-english/SKILL.md`](../ubiquitous-language-english/SKILL.md)), while keeping the French clinical UI terminology (`RCP`) for end users.
2. **Multi-Domain Extensibility**: Ensure features work seamlessly across both **Digestive Oncology (`oncology`)** and **Spinal Muscular Atrophy (`sma`)** without hardcoding single-domain assumptions in shared components.
3. **Patient Data Privacy**: Strictly local execution (local LLM via LiteLLM/llama.cpp/Ollama, local Milvus, local MongoDB).
