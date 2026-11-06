## 🔗 Linked Issue (Story / Feature / Bug)

- **Closes / Fixes / Part of**: #<!-- issue number -->
- **Parent Story / Milestone**: <!-- Milestone name or Story #XX -->
- **Type**: `[ ] Feature` · `[ ] Bugfix` · `[ ] Refactor / Chore`

---

## 🎯 Summary of Changes

<!-- Concisely describe what this PR implements or fixes and why -->

---

## ✅ Definition of Done (DoD) Checklist

- [ ] **Issue Acceptance Criteria**: All DoD checkboxes from the linked GitHub issue are satisfied.
- [ ] **DDD & Architectural Boundaries**:
  - Zero I/O in `application/src/domain/` (`test_ddd_architecture.py` passes).
  - Zero `streamlit` imports outside `application/src/ui/`.
  - 100% local execution preserved (no external cloud LLM/API calls).
- [ ] **Ubiquitous Language & English Documentation**:
  - 100% English docstrings and inline comments.
  - Strict usage of `PatientMDTForm` (`patient_mdt_form` / `mdt_form`) and `PatientRecord`.
- [ ] **Quality & Automated Tests (TDD: Red -> Green -> Refactor)**:
  - [ ] `ruff check` & `ruff format --check` pass.
  - [ ] `pytest` passes with zero regressions.
  - [ ] `npm --prefix web run lint` (WCAG 2.2 AA) & `npm --prefix web run test` (Vitest) pass (if `web/` or API contracts changed).
  - [ ] `prek run` passes cleanly.
