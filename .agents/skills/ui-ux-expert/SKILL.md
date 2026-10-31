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
  2. **Conformité aux recommandations** : Contrôle systématique de complétude et propositions cadrées sur les référentiels scientifiques (ex. TNCD, PNDS).
  3. **Fluidité logistique** : Ordonnancement de la séance selon le degré d'urgence et l'expertise requise.
- **Tone of Voice & Persona Ergonomics ("Sans réfléchir")**:
  - **Rigoureux, sobre, respectueux de l'expertise médicale**, dénué de jargon marketing creux.
  - Every screen must be **instantly readable in 1 second without cognitive effort ("sans réfléchir")** by two primary hospital personas:
    1. **Le Médecin / Spécialiste RCP** (focus: degré d'urgence, orientation pré-RCP, marqueurs cliniques et biologiques clés, évolution longitudinale entre deux RCP, avis par spécialité et références scientifiques).
    2. **La Secrétaire médicale / Coordinateur RCP** (focus: complétude du dossier, pièces manquantes, quorum des spécialités à convoquer en séance, identification patient).

---

## 2. Visual Design System (Typography, Palette, Surfaces & Logotype)

### A. Typography (`sans-serif` & Local-Only Privacy)
- Use clean `sans-serif` typography across all headings, body text, and UI components (`font = "sans-serif"` and `headingFont = "sans-serif"` in `application/.streamlit/config.toml`).
- **Privacy boundary**: Never load external web fonts (e.g., Google Fonts CDN) to guarantee 100% offline/local hospital compliance.

### B. Color Palette (Bleu sombre / Gris ardoise + Sauge / Sarcelle / Rose)
Configured in `application/.streamlit/config.toml` and `apply_card_surface_style()` in `src/ui/patient_mdt/translations.py` (with automatic Light & Dark mode adaptation):

| Semantic Role | Light Mode (Matte Anti-Glare) | Dark Mode | Usage |
| :--- | :--- | :--- | :--- |
| **Sidebar & Brand Slate** | `#2B3748` | `#0B1120` | Softened slate-blue sidebar (`#2B3748` in light mode to avoid harsh contrast), primary logotype (`Data`) |
| **Workspace Canvas** | `#E6ECF0` | `#0F172A` | Soft stone-slate desk background (`backgroundColor`) that eliminates white screen glare |
| **Matte Card Interior** | `#FBFDFF` | `#162032` | Matte off-white paper interior for bordered containers (`div.stApp div[data-testid="stLayoutWrapper"] > div[data-testid="stVerticalBlock"]:not([class*="st-key-clinical_scroll_"])`) and KPI metrics (`[data-testid="stMetric"]`) |
| **Primary — Sarcelle minérale douce (Muted Teal)** | `#467E79` | `#72A8A2` | Primary CTAs, active tabs/controls, focal elements, logotype (`Syntis`) |
| **Success / Conformity — Sauge (Sage)** | `#4D7C6F` (`#E6F1EE` bg) | `#6B9080` | Validated completeness (`Dossier conforme`), standard priority, positive deltas, validation checkmarks |
| **Alert / High Priority / Destructive — Rose** | `#B83B5E` (`#F9E8EC` bg) | `#E11D48` / `#F43F5E` | High priority (`Priorité haute`), critical alerts, AND **all destructive / irreversible actions** (`btn_del_...` and `btn_danger_...`) |
| **Clinical Info Banner (`st.info` / Blue)** | `#3B6E9C` (`#E3EFF8` bg) | `#3B82F6` (`#1E3A5F` bg) | Soft yet clearly visible clinical slate-blue for `st.info` banners (with `#3B6E9C` left accent border) |

### C. Logotype & Application Icon (Anti-Pattern Guardrails)
- Defined in `src/ui/patient_mdt/translations.py` (`get_logo_svg()`, `get_icon_svg()`) and `application/static/icon.svg`:
  - **Wordmark**: Strong `sans-serif` typography pairing `Data` (slate) and `Syntis` (muted mineral teal) with a French domain subtitle (`- Oncologie`, `- Amyotrophie spinale`).
  - **App Icon**: Layered teal dossier sheet (`#72A8A2`) + foreground synthesis card (`#F8FAFC`) with structured horizontal lines + small rose priority dot (`#D94668`) + bottom-right **sage-green** validation badge (`#68A38E` / `#437A68`) with a white checkmark (`#F8FAFC`).
  - **Strict UX Anti-Patterns to Avoid**:
    - Never use 4-arm rotational geometries that could resemble a swastika.
    - Never place a validation checkmark (`✓`) inside a red or rose circle (red/rose is reserved for urgency/danger; validation is always sage-green).

### D. Dark-Mode Portal Safety (`st.popover` & `st.dialog`)
- In Streamlit, `st.popover` and `st.dialog` are mounted via React portals inside `<div id="stFloatingOverlayPortal">` directly under `document.body`, **outside** `<div class="stApp">` (where `color-scheme: dark` is applied).
- Therefore, in `apply_card_surface_style()`:
  - Always scope `light-dark(#FBFDFF, #162032)` card surface rules to `div.stApp ... :not([class*="st-key-clinical_scroll_"])`.
  - Always force `background-color: transparent !important; box-shadow: none !important; border: none !important;` on inner blocks of `div[data-testid="stPopoverBody"]` and `div[role="dialog"]` so popovers (`💭 Réflexion IA`, `🔍 Filtres`, `Options IA`) never turn white in Dark Mode.
  - Note on `st.popover`: never pass an empty label `""` to `st.popover()` (raises `StreamlitAPIException`), and never rely on `with st.container(...) as var:` because `DeltaGenerator.__enter__()` returns `None`.

---

## 3. Iconography & Specialty Naming Rules

1. **Preserve Colorful Icons**: Use expressive colorful emojis and colored Material icons (`:primary[:material/...:]`, `:blue[:material/...:]`, etc.) to aid rapid visual triage.
2. **Clinical Specialty Icons (No Detective Emojis `🕵️`)**:
   - Map agents via `get_agent_icon_and_label()` in `src/ui/patient_mdt/translations.py`:
     - `🧠 Neurologie` (`neurologist expert`)
     - `🧬 Génétique` (`geneticist expert`)
     - `🫁 Pneumologie` (`pulmonologist expert`)
     - `🦿 MPR / Rééducation` (`physiotherapy expert`)
     - `🦴 Orthopédie` (`orthopedist expert`)
     - `🩺 Pancréas` / `🩺 Œsophage` / `🩺 Foie / CHC`
     - `⚖️ Coordinateur RCP` (`MDT Coordinator`)
     - `🗂️ Extraction administrative & clinique` (`Administrative`)
     - `📚 Assistant référentiels` (`Ressource Assistant`)
   - Use the concise specialty noun (`Neurologie`, `Génétique`, `Pneumologie`...) rather than repeating `"Expert ..."` on every badge so multi-specialty lists fit cleanly on a single line.

---

## 4. Clinical Layout & Page Ergonomics

### A. Header, Sidebar Collapse & Architectural Boundary
- **Never import `streamlit` outside `src/ui/` and `app-ui.py`**.
- **Top Header Spacing**: `header[data-testid="stHeader"]` is styled transparent (`pointer-events: none` on the bar, `pointer-events: auto` on buttons) with `padding-top: 2.75rem !important` on `stMainBlockContainer` so top elements are never clipped in production.
- **Permanent Sidebar Collapse/Expand Controls**: `div[data-testid="stSidebarCollapseButton"]` (`«`) and `button[data-testid="stExpandSidebarButton"]` (`»`) are styled with `visibility: visible !important` and a subtle border so clinicians can collapse/expand the left menu at any time (especially on the side-by-side PDF/Dossier view).

### B. RCP Preparation & Triage Dashboard (`src/ui/patient_mdt/cards.py`)
1. **Top KPI Summary Bar**: 4 equal-height bordered metrics (`📁 Dossiers structurés`, `🚨 Priorité haute (RCP)`, `⚠️ Contrôle de complétude`, `🧭 Orientations pré-RCP`).
2. **Full-Width Compact Filter Toolbar**: Search, completeness segmented control, sort order, `Cartes`/`Liste` toggle, and `🔍 Filtres` popover in a single horizontal bar.
3. **Equal-Height 3-Column Card Grid & Bottom-Aligned Buttons**:
   - Use `st.container(border=True, height="stretch")` for cards and place `st.space("stretch")` immediately before the footer (missing items expander + action buttons) so buttons align horizontally across all cards in a row.
4. **Destructive Actions in DataSyntis Rose**:
   - All delete/purge buttons use `key="btn_del_..."` (secondary rose-tinted button) and all irreversible confirmation buttons inside `@st.dialog` use `key="btn_danger_..."` (solid rose primary button + `st.error` warning banner).

### C. Patient Clinical File View (`src/ui/patient_mdt/datas.py`)
1. **Unified Patient & RCP Banner (`render_unified_patient_banner`)**:
   - Displays patient identity, DOB, gender, RCP count, and **cumulative AI execution time** (`:gray-badge[⏱️ Temps cumulé : X min XX s]`, formatted via `_format_duration` in seconds $< 60\text{ s}$ or `M min SS s` $\ge 60\text{ s}$).
   - When a patient has multiple RCPs, displays an enriched chronological timeline (`🔴`/`🟠`/`🟢`/`⚪`/`⏳` + `🧭`/`⚠️`/`✅`) with `◀ Préc.` / `Suiv. ▶` navigation buttons.
2. **3-Row Synoptic Card (`render_clinical_summary_card`) Pinned Above Tabs**:
   - **Row 1 — Statut & Triage RCP (1 line)**: `**🩺 Synthèse synoptique RCP**` + `Priorité` + `Complétude` + `Orientation` (`:red-badge[🧭 Adaptation suggérée]`, appending `proposed_care_type` only if $\le 24$ characters so long sentences never create giant badges). Do not print the long list of missing items at the bottom of the synoptic card (keep it in the tooltip and in `Contrôle de complétude`).
   - **Row 2 — Spécialités requises (for the RCP Secretary)**: `:small[**👥 Spécialités requises (N) :**]` followed by concise violet specialty badges on a single line.
   - **Row 3 — Repères cliniques (for the Physician)**: Multi-column clinical markers with automatic translation of `"Not documented in record"` $\rightarrow$ `"Non renseigné"`, plus longitudinal evolution deltas (`📈 Évolution vs RCP du ...`) when a previous RCP exists.
3. **Separated Tabs & Power-Mode Gating**:
   - Standard mode displays 3 tabs: **`🩺 Dossier clinique`**, **`⚖️ Avis & Décision RCP`**, and **`💬 Assistant IA`**.
   - The 4th tab **`📄 Texte & Chunks`** (and the `📝 Format Markdown` / `🧱 Blocs vectoriels (Chunks)` tabs in `ressources.py`) is **only displayed when `st.session_state.get("power")` is active**.
4. **Collapsed-by-Default Accordions & Individual Expert Accordions**:
   - All sections in both `🩺 Dossier clinique` and `⚖️ Avis & Décision RCP` have `"default_expanded": False` in `SECTION_META` because their key conclusion is already summarized in the accordion header (`_extract_section_header_summary`).
   - In `⚖️ Avis & Décision RCP`, omit redundant `#####` pole headings (`"pole": None`) and list each specialty opinion in `ExpertAnswer` **one by one as its own individual collapsible accordion** (`🧠 Avis — Neurologie — 🚨 Priorité haute · 2 proposition(s)`), sorted by relevance and urgency.
   - Inside each section/expert accordion, place the execution duration (`⏱️ X.X s` / `M min SS s`) in the bottom-right action bar **to the right of the `Relancer cette rubrique` button**.
   - Always wrap `model_cls.model_validate(...)` in `try / except` to gracefully handle `DefaultResponse(value=None)` fallback dicts without raising a Pydantic `ValidationError`.
