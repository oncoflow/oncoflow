---
name: ui-ux-expert
description: "Enforces DataSyntis UI/UX design system, brand identity, clinical ergonomics, color palette (slate/teal/sage/rose), elevated white card surfaces, and colorful iconography across all Streamlit views (`src/ui/` and `app-ui.py`)."
---

# DataSyntis UI & UX Expert Skill (`ui-ux-expert`)

This skill defines the brand identity, visual design system, clinical UX patterns, and Streamlit ergonomic rules for **DataSyntis**. Activate this skill whenever creating, modifying, auditing, or styling any Streamlit page in `application/app-ui.py` or `application/src/ui/`.

---

## 1. Brand Identity & Positioning (`DataSyntis`)

- **Application Name**: **DataSyntis** (never use the legacy name `MedDataSyntis` in user-facing UI, logos, or titles).
- **Mission**:
  > *"Libérer du temps médical utile en transformant le chaos documentaire en dossiers directement exploitables pour la décision RCP."*
- **Positioning**:
  > *"L'outil d'analyse des dossiers qui prépare le terrain pour faciliter / optimiser la décision médicale."*
- **Three Core Product Promises**:
  1. **Exhaustivité documentaire** : Ingestion multi-PDF agnostique et consolidation chronologique par patient.
  2. **Conformité aux recommandations** : Contrôle systématique de complétude et propositions cadrées sur les référentiels scientifiques (ex. TNCD).
  3. **Fluidité logistique** : Ordonnancement de la séance selon le degré d'urgence et l'expertise requise.
- **Tone of Voice**:
  - **Rigoureux, sobre, respectueux de l'expertise médicale**, dénué de jargon marketing creux ou d'effets d'annonce techno-béats.
  - Prefer precise clinical and operational terms (*"Préparation & ordonnancement RCP"*, *"Contrôle de complétude"*, *"Dossier conforme"*, *"Intégration documentaire"*, *"Modules d'expertise"*) over casual or flashy phrasing.

---

## 2. Visual Design System (Typography, Palette, Surfaces & Logotype)

### A. Typography (`sans-serif` & Local-Only Privacy)
- Use clean `sans-serif` typography across all headings, body text, and UI components (`font = "sans-serif"` and `headingFont = "sans-serif"` in `application/.streamlit/config.toml`).
- **Privacy boundary**: Never load external web fonts (e.g., Google Fonts CDN) to guarantee 100% offline/local hospital compliance.

### B. Color Palette (Bleu sombre / Gris ardoise + Sauge / Sarcelle / Rose)
Configured in `application/.streamlit/config.toml` (with automatic Light & Dark mode adaptation):

| Semantic Role | Light Mode (Matte Anti-Glare) | Dark Mode | Usage |
| :--- | :--- | :--- | :--- |
| **Sidebar & Brand Slate** | `#2B3748` | `#0B1120` | Softened slate-blue sidebar (`#2B3748` in light mode to avoid harsh contrast), primary logotype (`Data`) |
| **Workspace Canvas** | `#E6ECF0` | `#0F172A` | Soft stone-slate desk background (`backgroundColor`) that eliminates white screen glare |
| **Matte Card Interior (Option 1)** | `#FBFDFF` | `#162032` | Matte off-white paper interior for bordered containers (`div[data-testid="stLayoutWrapper"] > div[data-testid="stVerticalBlock"]`) and KPI metrics (`[data-testid="stMetric"]`) via `apply_card_surface_style()` |
| **Primary — Sarcelle minérale douce (Muted Teal)** | `#467E79` | `#72A8A2` | Primary CTAs, active tabs/controls, focal elements, logotype (`Syntis`) — soft mineral celadon/teal |
| **Success / Conformity — Sauge (Sage)** | `#4D7C6F` (`#E6F1EE` bg) | `#6B9080` | Validated completeness (`Dossier conforme`), standard priority, positive deltas |
| **Alert / High Priority — Rose** | `#B83B5E` (`#F9E8EC` bg) | `#F43F5E` | Muted raspberry-rose for high priority (`Priorité haute`), critical alerts, focal point of the app icon (`#D94668`) |
| **Clinical Info Banner (`st.info` / Blue)** | `#3B6E9C` (`#E3EFF8` bg) | `#3B82F6` (`#1E3A5F` bg) | Soft yet clearly visible clinical slate-blue for `st.info` banners (with `#3B6E9C` left accent border) |

### C. Logotype & Application Icon
- Defined in `src/ui/patient_mdt/translations.py` (`get_logo_svg()`, `get_icon_svg()`) and `application/static/icon.svg`:
  - **Wordmark**: Strong `sans-serif` typography pairing `Data` (slate) and `Syntis` (teal) with an uppercase domain subtitle (`ONCOLOGIE`, `AMYOTROPHIE SPINALE (SMA)`, etc.).
  - **App Icon / Favicon / Desktop Shortcut**: Rounded dark-slate square (`#1E293B`) featuring 4 converging teal/sage document beams (`#14B8A6`, `#6B9080`) that cross and assemble around a central rose focal point (`#E11D48`), evoking **document crossing, ordered assembly, and clinical focalization**.

---

## 3. Iconography Rules (Keep Icons in Color)

- **Always preserve colorful icons across the interface** to aid rapid visual scanning during high-tempo RCP meetings:
  1. **Sidebar Navigation (`st.Page`)**: Because `st.Page(..., icon=...)` does not support `:color[:material/...:]` syntax, use expressive **colorful emojis** (`📇`, `👤`, `📥`, `🩺`, `📚`, `📋`, `⚙️`).
  2. **KPIs, Badges & Section Headers**: Use colorful emojis (`📁`, `🚨`, `⚠️`, `💉`, `✅`, `❌`, `⏳`, `🔄`, `🟠`, `🟢`, `⚪`, `🗂️`, `📅`, `📄`, `👁️`, `🗑️`, `💭`, `📌`) and/or colored Material icons (`:primary[:material/...:]`, `:blue[:material/...:]`, `:green[:material/...:]`, `:red[:material/...:]`, `:orange[:material/...:]`, `:violet[:material/...:]`).
  3. Never flatten all interface icons into monochrome gray Material icons.

---

## 4. Clinical UX & Ergonomic Patterns

### A. Architectural Boundary & Compact Top Spacing (CRITICAL)
- **Never import `streamlit` outside `src/ui/` and `app-ui.py`**. All business logic, database queries, and queue operations must go through `src/application/` Use Cases and `src/domain/` entities.
- **Compact Top Page Margin**: Streamlit applies a large `6rem` top padding by default on `div[data-testid="stMainBlockContainer"]`. `apply_card_surface_style()` in `src/ui/patient_mdt/translations.py` overrides `padding-top: 1.5rem !important` on `stMainBlockContainer` and zeroes `padding-top` / `margin-top` on `h1` so page titles sit high on the screen and maximize vertical clinical workspace.

### B. RCP Preparation & Triage Dashboard (`src/ui/patient_mdt/cards.py`)
1. **Top KPI Summary Bar**:
   - Display 4 equal-height bordered metrics (`st.metric(..., border=True, height="stretch")`) at the top:
     - `📁 Dossiers structurés`
     - `🚨 Priorité haute (RCP)`
     - `⚠️ Contrôle de complétude`
     - `💉 Actes / Interventions`
2. **Full-Width Compact Filter Toolbar**:
   - Never push the main dashboard into a narrow column using a permanent `[3, 1]` side filter column.
   - Place search (`st.text_input`), completeness (`st.segmented_control`), sorting (`st.selectbox`), view toggle (`Cartes` / `Liste`), and advanced filters (`🔍 Filtres` inside `st.popover`) in a single horizontal bordered toolbar (`st.container(border=True)`).
3. **Equal-Height 3-Column Card Grid**:
   - Render cards in rows of 3 (`st.columns(3)`) with `st.container(border=True, height="stretch")` so every card in a row has the exact same height.
   - Separate **consolidated patient dossiers** (`📁 Dossiers patients consolidés`) and **chronological RCP forms** (`📄 Flux documentaire RCP`) into `st.tabs` rather than stacking both grids vertically.
4. **Safe Destructive Actions**:
   - Delete buttons (`🗑️`) on cards and list rows must use `type="secondary"` (never `type="primary"`) and always open a confirmation `@st.dialog`.

### C. Patient Clinical File View (`src/ui/patient_mdt/datas.py`)
1. **Unified Hospital-Grade Patient & RCP Banner (`render_unified_patient_banner`)**:
   - Combine the Back button (`◀️ Dossiers`), patient full name (`### 👤 {patient.full_name}`), inline administrative badges (`🎂 {dob}`, `⚧️ {gender}`, `🗂️ {count} RCP`), active RCP document metadata, document action buttons (`⏬ Télécharger PDF`, `🔄 Relancer l'analyse`, `Options IA`), and the chronological RCP timeline selector (`st.segmented_control` when $\le 4$ forms, `st.selectbox` when $> 4$) inside a **single unified bordered header card** (`st.container(border=True)`).
   - Follow immediately with a **single** `[1, 1]` split view: `pdf_viewer` on the left (`height=800`) and `st.tabs(["📋 Données cliniques", "💬 Assistant IA", "📄 Texte & Chunks"])` on the right.
2. **Synoptic Clinical Summary Banner (`render_clinical_summary_card`) & Independent Scroll**:
   - Wrap the right-hand clinical data panel in a scrollable container (`st.container(height=760, border=False)`) so clinicians can scroll through extracted sections while keeping the PDF fixed on the left.
   - Display `🩺 Synthèse synoptique RCP` at the top with Priority, Completeness, Intervention, and Specialty badges on the first row, followed by a multi-column mini-grid of key extracted clinical markers (Organ, OMS, MSI/MSS, Treatments in Oncology; SMA Type, SMN2 copies, Ventilation, Feeding in SMA).
3. **Clinical Pole Grouping & Inline Expander Header Summaries (`SECTION_META`)**:
   - Order and group clinical sections by medical reasoning poles (`🎯 Aide à la décision & Conformité RCP`, `🩺 Caractérisation clinique & biologique`, `🔬 Bilan paraclinique & Historique thérapeutique`, `👤 Données administratives extraites`) instead of Python alphabetical class order.
   - Display the extracted key value directly inside the expander header (`_extract_section_header_summary`, e.g., `🎯 Localisation de la tumeur primitive — Pancréas · ⏱️ 1.2s`) and keep single-value atomic sections or `PatientAdministrative` collapsed by default (`expanded=False`) so decision-critical sections stay front and center.
4. **Dedicated Clinical Renderers & Prioritized Expert Tabs**:
   - Render `RadiologicalExamination`, `ChemotherapyData`, `ExpertSuggestion`, `Reference`, and `MTDComplete` with dedicated clinical cards and badges (never raw Python `BaseModel` string dumps), and format both `date` and `datetime` values as `DD/MM/YYYY`.
   - In `ExpertAnswer`, sort specialist tabs so relevant experts (`expert_relevant=True`) appear first with explicit icons (`🚨` urgent, `✅` relevant, `⚪` non-relevant) and show a concise 1-line notice for non-relevant specialties.
5. **Discreet Execution Time & Single-Line Section Footer**:
   - **Execution time (`execution_times`) is secondary metadata**: never give it a dedicated row or `st.caption` inside the card body. Display it discreetly in the expander header (`:small[:gray[· ⏱️ {exec_time:.1f}s]]`) and in the retry button's `help` tooltip.
   - **Same-row AI Reflection & Retry**: Place the AI reasoning popover (`💭 :small[Réflexion IA]`, `type="tertiary"`) and the section retry button (`:blue[:material/refresh:] :small[Relancer cette rubrique]`, `type="tertiary"`) **on the same horizontal line** inside `st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center")`.

### D. Unified AI Assistant & Guidelines (`ressources.py`, `agents.py`)
- In `datas.py`, provide a single `💬 Assistant IA` tab with a `st.segmented_control` selector for scope (`Dossier patient complet` vs `Fiche RCP active uniquement`).
- In `ressources.py`, avoid duplicate welcome messages when initializing the RAG chat session (`messages_res` already contains the initial greeting).
- In `agents.py`, display specialty modules in an equal-height 3-column grid (`st.container(border=True, height="stretch")`) with clear indexing status (`✅` vs `⚠️`).
