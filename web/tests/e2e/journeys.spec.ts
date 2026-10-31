import { expect, test } from "@playwright/test";

test.describe("DataSyntis Material Design 3 Web UI — 3 Clinical E2E Journeys", () => {
  test("J1 (Secrétaire RCP): Worklist KPIs, M3 ... menu, double-click open, completeness filter, and PDF batch upload", async ({
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

    // Filter by incomplete records
    await page.goto("/worklist?domain=oncology&completeness=incomplete");
    await expect(page.getByTestId("worklist-table")).toContainText("FICTIVE Jeanne");
    await expect(page.getByTestId("worklist-table")).not.toContainText("MODÈLE Paul");

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

  test("J2 (Médecin Oncologue): Longitudinal dossier, collapsed-by-default sections, preserved manual edits, pre-MDT opinions, and AI chat", async ({
    page,
  }) => {
    await page.goto("/patients/A-1042?domain=oncology");
    await expect(page.getByTestId("synoptic-card")).toContainText("Adaptation suggérée");
    await expect(page.getByTestId("session-timeline")).toContainText("2026-11-06");
    await expect(page.getByTestId("timeline-upcoming")).toContainText("Prochaine séance");

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

    // Switch to Opinions tab and expand specialist opinion
    await page.getByTestId("tab-opinions").click();
    await page.getByTestId("opinion-pancreas expert").locator("summary").first().click();
    await expect(page.getByTestId("opinion-pancreas expert")).toContainText("TNCD Pancréas §4.2");

    // Switch to AI Chat tab and ask a question with specialist agent selector
    await page.getByTestId("tab-chat").click();
    await expect(page.getByTestId("assistant-control-bar")).toBeVisible();
    await page.getByTestId("input-chat-question").fill("Quelle est l'évolution du CA 19-9 ?");
    await page.getByTestId("btn_chat_send").click();
    await expect(page.getByTestId("chat-assistant-reply")).toContainText("412 U/mL");
  });

  test("J3 (Neuropédiatre SMA): Domain switch to SMA, longitudinal motor deltas, and PNDS guidelines RAG", async ({
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

    await page.getByTestId("input-guideline-question").fill("Quel est le rythme de suivi HFMSE ?");
    await page.getByTestId("btn_guideline_chat_send").click();
    await expect(page.getByTestId("chat-assistant-reply")).toContainText("PNDS");

    // Navigate to dedicated Agents page (compact cards expanded on demand)
    await page.getByTestId("nav-agents").click();
    await expect(page.getByTestId("agents-list")).toBeVisible();
    await page.getByTestId("btn_toggle_all_agents").click();
    await expect(page.getByTestId("agent-user-prompts-Administrative")).toBeVisible();
    await expect(page.getByTestId("agent-resources-neurologist expert")).toBeVisible();
    await expect(page.getByTestId("agent-system-prompt-neurologist expert")).toBeVisible();
  });
});
