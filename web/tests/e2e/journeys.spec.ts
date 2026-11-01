import { expect, test } from "@playwright/test";

test.describe("DataSyntis Material Design 3 Web UI — End-to-End Clinical & Ergonomic Journeys", () => {
  test("J1 (Secrétaire RCP): Worklist KPIs, M3 ... menu, double-click open, completeness filter, cards view, and PDF batch upload", async ({
    page,
  }) => {
    await page.goto("/worklist?domain=oncology");
    await expect(page.getByTestId("kpi-structured")).toBeVisible();
    await expect(page.getByTestId("kpi-priority-high")).toContainText("1");
    await expect(page.getByTestId("worklist-table")).toContainText("FICTIVE Jeanne");
    await expect(page.getByTestId("rail-fab-ingest")).toBeVisible();

    // Open M3 ... contextual menu on worklist row
    const menuTrigger = page.getByTestId("menu-patient-A-1042").locator("summary");
    await expect(menuTrigger).toBeVisible();
    await menuTrigger.click();
    await expect(page.getByTestId("menu-patient-A-1042").locator(".ds-menu__panel")).toBeVisible();
    await page.keyboard.press("Escape");

    // Double-click on a dossier row to open the dossier
    await page.getByTestId("worklist-row-A-1042").locator("td").first().dblclick();
    await expect(page).toHaveURL(/\/patients\/A-1042/);

    // Filter by incomplete records and verify cards display mode
    await page.goto("/worklist?domain=oncology&completeness=incomplete");
    await expect(page.getByTestId("worklist-table")).toContainText("FICTIVE Jeanne");
    await expect(page.getByTestId("worklist-table")).not.toContainText("MODÈLE Paul");

    await page.goto("/worklist?domain=oncology&display=cards");
    await expect(page.locator(".ds-patient-grid")).toBeVisible();

    // Navigate to Ingest via the M3 Navigation Rail + Importer PDF FAB and upload a PDF
    await page.getByTestId("rail-fab-ingest").click();
    await expect(page).toHaveURL(/\/ingest/);

    await page.getByTestId("input-ingest-files").setInputFiles({
      name: "CR_Scanner_Test_E2E.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4 mock e2e pdf"),
    });
    await page.getByTestId("btn_ingest_submit").click();

    await expect(page.getByTestId("batch-tracker")).toBeVisible();
    await expect(page.getByTestId("batch-tracker")).toContainText("CR_Scanner_Test_E2E.pdf");
  });

  test("J2 (Médecin Oncologue): Longitudinal dossier, missing items checklist, PDF expand, preserved manual edits, pre-MDT opinions, and AI Co-Pilot", async ({
    page,
  }) => {
    await page.goto("/patients/A-1042?domain=oncology");
    await expect(page.getByTestId("synoptic-card")).toContainText("Adaptation suggérée");
    await expect(page.getByTestId("session-timeline")).toContainText("06/11/2026");
    await expect(page.getByTestId("timeline-upcoming")).toContainText("Prochaine séance");

    // Toggle PDF split-view expansion
    await page.getByTestId("btn_pdf_expand").click();
    await expect(page.getByTestId("split-view")).toHaveClass(/ds-split--pdf-expanded/);
    await page.getByTestId("btn_pdf_expand").click();
    await expect(page.getByTestId("split-view")).not.toHaveClass(/ds-split--pdf-expanded/);

    // Expand clinical sections (collapsed by default)
    await page.getByTestId("btn_toggle_all_sections").click();
    await expect(page.getByTestId("reasoning-TumorLocation")).toBeVisible();

    // Edit Chemotherapy section inline
    await page.getByTestId("btn_edit_section_Chemotherapy").click();
    const chemoInput = page.locator("#inp-Chemotherapy-chemotherapy_name");
    await expect(chemoInput).toBeVisible();
    await chemoInput.fill("FOLFIRINOX modifié (8 cures validées RCP)");
    await page.getByTestId("btn_save_section_Chemotherapy").click();

    await expect(page.getByTestId("section-Chemotherapy")).toContainText("Modifié manuellement");
    await expect(page.getByTestId("section-Chemotherapy")).toContainText(
      "FOLFIRINOX modifié (8 cures validées RCP)",
    );

    // Rerun TumorBiology and verify Chemotherapy manual edit is preserved
    await page.getByTestId("btn_rerun_section_TumorBiology").click();
    await expect(page.getByTestId("section-Chemotherapy")).toContainText("Modifié manuellement");

    // Switch to Opinions tab, inspect missing items checklist, and expand specialist opinion
    await page.getByTestId("tab-opinions").click();
    await page.getByTestId("section-MTDCompleted").locator("summary").first().click();
    await expect(page.getByTestId("missing-items-panel")).toBeVisible();
    await expect(page.getByTestId("missing-items-list")).toBeVisible();
    await page.getByTestId("opinion-pancreas expert").locator("summary").first().click();
    await expect(page.getByTestId("opinion-pancreas expert")).toContainText("TNCD Pancréas §4.2");

    // Open M3 AI Co-Pilot Side Sheet via the Floating Extended FAB, test quick prompt menu & ask a question
    await page.getByTestId("btn_fab_ai_chat").click();
    await expect(page.getByTestId("ai-chat-drawer")).toBeVisible();
    await expect(page.getByTestId("assistant-control-bar")).toBeVisible();
    await expect(page.locator(".ds-m3-select").first()).toBeVisible();

    const quickPromptsSplit = page.getByTestId("quick-prompt-chips");
    await quickPromptsSplit.locator("[data-split-prompt-toggle]").click();
    await quickPromptsSplit.locator("[data-quick-prompt]").first().click();
    await expect(page.getByTestId("input-chat-question")).not.toHaveValue("");

    await page.getByTestId("input-chat-question").fill("Quelle est l'évolution du CA 19-9 ?");
    await page.getByTestId("btn_chat_send").click();
    await expect(page.getByTestId("chat-assistant-reply")).toContainText("412 U/mL");
  });

  test("J3 (Neuropédiatre SMA): Domain switch to SMA, longitudinal motor deltas, PNDS guidelines RAG, and AI Experts catalog", async ({
    page,
  }) => {
    await page.goto("/worklist?domain=sma");
    await expect(page.getByTestId("worklist-table")).toContainText("EXEMPLE Léo");

    await page.getByTestId("btn_open_S-0007").click();
    await expect(page.getByTestId("synoptic-card")).toContainText("42/66");
    await expect(page.getByTestId("synoptic-card")).toContainText("+2 vs 2026-05-18");

    // Navigate to Guidelines & Agents for SMA
    await page.getByTestId("nav-guidelines").click();
    await expect(page.getByTestId("guideline-control-bar")).toBeVisible();
    await expect(
      page.getByTestId("resource-item-PNDS_Amyotrophie_Spinale_SMA_2025.pdf"),
    ).toBeVisible();

    await page.getByTestId("btn_fab_ai_chat").click();
    await expect(page.getByTestId("ai-chat-drawer")).toBeVisible();
    await page.getByTestId("input-guideline-question").fill("Quel est le rythme de suivi HFMSE ?");
    await page.getByTestId("btn_guideline_chat_send").click();
    await expect(page.getByTestId("chat-assistant-reply")).toContainText("PNDS");
    await page.getByTestId("btn_close_ai_chat").click();

    // Navigate to dedicated Agents page (compact cards expanded on demand)
    await page.getByTestId("nav-agents").click();
    await expect(page.getByTestId("agents-list")).toBeVisible();
    await page.getByTestId("btn_toggle_all_agents").click();
    await expect(page.getByTestId("agent-user-prompts-Administrative")).toBeVisible();
    await expect(page.getByTestId("agent-resources-neurologist expert")).toBeVisible();
    await expect(page.getByTestId("agent-system-prompt-neurologist expert")).toBeVisible();
  });

  test("J4 (Coordination Séance RCP): Agenda KPIs, live specialty focus highlighting, inter-dossier navigation, and new meeting onboarding modal", async ({
    page,
  }) => {
    await page.goto("/agenda?domain=oncology");
    await expect(page.getByTestId("kpi-agenda-enrolled")).toBeVisible();
    await expect(page.getByTestId("kpi-agenda-urgent")).toBeVisible();
    await expect(page.getByTestId("kpi-agenda-quorum")).toBeVisible();
    await expect(page.getByTestId("kpi-agenda-incomplete")).toBeVisible();
    await expect(page.getByTestId("agenda-item-A-1042")).toBeVisible();
    await expect(page.getByTestId("agenda-item-A-1037")).toBeVisible();

    // Live client-side specialty focus highlighting via select dropdown
    const focusSelect = page.getByTestId("select-focus-specialty");
    await focusSelect.selectOption("pancreas expert");
    await expect(page.getByTestId("agenda-item-A-1042")).toHaveClass(/ds-agenda-item--focused/);
    await expect(page.getByTestId("agenda-item-A-1037")).toHaveClass(/ds-agenda-item--dimmed/);
    await focusSelect.selectOption("");
    await expect(page.getByTestId("agenda-item-A-1042")).not.toHaveClass(/ds-agenda-item--focused/);

    // Start the RCP session on #1 dossier and navigate to next/prev dossier
    await page.getByTestId("btn_start_session").click();
    await expect(page).toHaveURL(/\/patients\/A-1042.*from=agenda/);
    await expect(page.getByTestId("agenda-dossier-nav")).toBeVisible();
    await expect(page.getByTestId("agenda-dossier-position")).toContainText("#1/2");

    await page.getByTestId("btn_agenda_next_dossier").click();
    await expect(page).toHaveURL(/\/patients\/A-1037.*from=agenda/);
    await expect(page.getByTestId("agenda-dossier-position")).toContainText("#2/2");

    await page.getByTestId("btn_back_to_agenda").click();
    await expect(page).toHaveURL(/\/agenda/);

    // Open "Programmer une nouvelle réunion" onboarding modal and submit
    await page.getByTestId("btn_schedule_new_meeting").first().click();
    await expect(page.getByTestId("schedule-meeting-dialog")).toBeVisible();
    await page.getByTestId("input-onboarding-date").fill("2026-12-15");
    await page.getByTestId("btn_confirm_schedule_meeting").click();
    await expect(page.locator("#heading-ordered-agenda")).toContainText("2026-12-15");
  });

  test("J5 (Supervision Qualité, File GPU & Préférences M3): Theme selector, Rail collapse, Queue Side Sheet, Feedback bug report, and GPU Queue Admin", async ({
    page,
  }) => {
    await page.goto("/worklist?domain=oncology");

    // Topbar contextual menu: switch theme to Dark then back to Light
    await page.getByTestId("menu-topbar-actions").locator("summary").click();
    await page.getByTestId("btn_theme_dark").click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

    await page.getByTestId("menu-topbar-actions").locator("summary").click();
    await page.getByTestId("btn_theme_light").click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

    // Collapse and expand the M3 Navigation Rail
    await page.getByTestId("btn_sidebar_toggle").click();
    await expect(page.locator("body")).toHaveClass(/ds-shell--sidebar-collapsed/);
    await page.getByTestId("btn_sidebar_toggle").click();
    await expect(page.locator("body")).not.toHaveClass(/ds-shell--sidebar-collapsed/);

    // Open Queue Side Sheet from bottom banner
    await page.getByTestId("btn_queue_open").click();
    await expect(page.getByTestId("queue-drawer")).toBeVisible();
    await page.keyboard.press("Escape");

    // Feedback page: create a bug report
    await page.getByTestId("nav-feedback").click();
    await expect(page.getByTestId("bugs-table")).toContainText("BUG-101");
    await page.getByTestId("input-bug-title").fill("Test E2E — Alignement badge RCP");
    await page
      .getByTestId("input-bug-desc")
      .fill("Vérification automatisée du formulaire de signalement.");
    await page.getByTestId("btn_bug_submit").click();
    await expect(page.getByTestId("bugs-table")).toContainText("Test E2E — Alignement badge RCP");

    // Admin Queue page: retry failed job and release GPU locks
    await page.getByTestId("nav-queue").click();
    await expect(page.getByTestId("queue-jobs-table")).toContainText("job-failed-1039");
    await page.getByTestId("btn_retry_job-failed-1039").click();
    await page.getByTestId("btn_release_locks").click();
    await expect(page.getByTestId("queue-jobs-table")).toBeVisible();
  });

  test("J6 (Ergonomie Mobile Responsive 390x844): Off-canvas navigation drawer, auto-collapsed mobile filters, and AI chat keyboard viewport sync", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/worklist?domain=oncology");

    // Bottom navigation bar is visible on mobile
    await expect(page.getByTestId("bottom-nav")).toBeVisible();

    // Filter card with data-mobile-collapsible="true" auto-collapses on mobile when no filter is active
    const filterDetails = page.locator("details[data-mobile-collapsible='true']").first();
    await expect(filterDetails).not.toHaveAttribute("open", "");

    // Open and close off-canvas mobile navigation drawer
    await page.getByTestId("btn_mobile_nav_toggle").click();
    await expect(page.locator("body")).toHaveClass(/ds-shell--mobile-nav-open/);
    await page.keyboard.press("Escape");
    await expect(page.locator("body")).not.toHaveClass(/ds-shell--mobile-nav-open/);

    // Navigate to patient dossier on mobile and verify AI Co-Pilot drawer keyboard class sync
    await page.goto("/patients/A-1042?domain=oncology");
    await page.getByTestId("btn_fab_ai_chat").click();
    const chatDrawer = page.getByTestId("ai-chat-drawer");
    await expect(chatDrawer).toBeVisible();

    const chatInput = page.getByTestId("input-chat-question");
    await chatInput.focus();
    await expect(chatDrawer).toHaveClass(/is-keyboard-open/);
  });
});
