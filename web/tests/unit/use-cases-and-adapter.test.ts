import { describe, expect, it, vi } from "vitest";
import { FeedbackUseCase } from "../../src/application/use-cases/feedback.use-case.js";
import { GuidelinesUseCase } from "../../src/application/use-cases/guidelines.use-case.js";
import { IngestUseCase } from "../../src/application/use-cases/ingest.use-case.js";
import { PatientDossierUseCase } from "../../src/application/use-cases/patient-dossier.use-case.js";
import { QueueAdminUseCase } from "../../src/application/use-cases/queue-admin.use-case.js";
import { WorklistUseCase } from "../../src/application/use-cases/worklist.use-case.js";
import { HttpOncoflowApiAdapter } from "../../src/infrastructure/api/http-oncoflow-api.adapter.js";
import { InMemoryOncoflowApiFake } from "../../src/infrastructure/api/in-memory-oncoflow-api.fake.js";

describe("Application Use-Cases with InMemoryOncoflowApiFake", () => {
  it("WorklistUseCase loads oncology and SMA patient/RCP cards and computes 4 KPIs", async () => {
    const api = new InMemoryOncoflowApiFake();
    const useCase = new WorklistUseCase(api);

    const oncoView = await useCase.execute("oncology", { completeness: "all" });
    expect(oncoView.kpis.structuredCount).toBeGreaterThanOrEqual(2);
    expect(oncoView.kpis.highPriorityCount).toBeGreaterThanOrEqual(1);
    expect(oncoView.cards[0]?.priorityLevel).toBe("high");

    const smaView = await useCase.execute("sma", { completeness: "all" });
    expect(smaView.cards.some((c) => c.domain === "sma")).toBe(true);
  });

  it("PatientDossierUseCase loads longitudinal history, updates a section with manual_edits, and preserves manual edits on rerun", async () => {
    const api = new InMemoryOncoflowApiFake();
    const useCase = new PatientDossierUseCase(api);

    const dossier = await useCase.getDossier("A-1042", "oncology", "fr");
    expect(dossier).not.toBeNull();
    expect(dossier?.patientName).toContain("FICTIVE");
    expect(dossier?.timeline.length).toBeGreaterThanOrEqual(2);
    expect(dossier?.opinions.length).toBeGreaterThanOrEqual(1);

    // Inline manual edit of Chemotherapy section
    const updated = await useCase.updateSection(
      dossier!.currentForm.file,
      "Chemotherapy",
      {
        chemotherapy: true,
        chemotherapy_name: "FOLFIRINOX modifié (8 cures)",
        chemotherapy_tolerance: "Neuropathie grade 1",
      },
      "Dr A. Exemple",
      "oncology",
    );
    expect(updated.manualEdits.Chemotherapy).toBeDefined();
    expect(updated.manualEdits.Chemotherapy?.edited_by).toBe("Dr A. Exemple");

    // Rerun another section while preserving manual edits
    const rerunResult = await useCase.rerunSection(
      dossier!.currentForm.file,
      "TumorBiology",
      true,
      "oncology",
    );
    expect(rerunResult.preserveManualEdits).toBe(true);
    const afterRerun = await useCase.getDossier("A-1042", "oncology", "fr");
    expect(afterRerun?.currentForm.manualEdits.Chemotherapy).toBeDefined();
  });

  it("IngestUseCase uploads PDFs with a batch_id and tracks batch status", async () => {
    const api = new InMemoryOncoflowApiFake();
    const useCase = new IngestUseCase(api);

    const result = await useCase.uploadBatch(
      [
        {
          filename: "CR_RCP_Nouveau_2026-11-10.pdf",
          content: Buffer.from("%PDF-1.4 dummy"),
          patientId: "A-1042",
        },
      ],
      "oncology",
    );
    expect(result.batchId).toMatch(/^batch_/);
    const status = await useCase.getBatchStatus(result.batchId, "oncology");
    expect(status.total).toBe(1);
    expect(status.files[0]?.filename).toBe("CR_RCP_Nouveau_2026-11-10.pdf");
  });

  it("GuidelinesUseCase lists TNCD/PNDS resources, specialty agents, and answers RAG chat", async () => {
    const api = new InMemoryOncoflowApiFake();
    const useCase = new GuidelinesUseCase(api);

    const view = await useCase.getOverview("oncology", "fr");
    expect(view.resources.length).toBeGreaterThan(0);
    expect(view.agents.length).toBeGreaterThan(0);

    const reply = await useCase.askGuidelineQuestion(
      "Quel schéma en 2e ligne après FOLFIRINOX ?",
      "oncology",
      "fr",
    );
    expect(reply.answer).toContain("gemcitabine");
    expect(reply.references.length).toBeGreaterThan(0);
  });

  it("FeedbackUseCase creates, filters, and updates bug reports", async () => {
    const api = new InMemoryOncoflowApiFake();
    const useCase = new FeedbackUseCase(api);

    const created = await useCase.createBug({
      title: "Test signalement",
      description: "Détail du signalement",
      category: "extraction",
      severity: "medium",
      domain: "oncology",
      patientOrFile: "#A-1042",
      author: "Dr Test",
    });
    expect(created.id).toBeTruthy();

    await useCase.updateStatus(created.id, "in_progress", "oncology");
    const list = await useCase.listBugs("oncology", { status: "in_progress" });
    expect(list.items.some((b) => b.id === created.id)).toBe(true);
  });

  it("QueueAdminUseCase lists queue stats/jobs, retries failed jobs, cleans queue, and releases GPU locks", async () => {
    const api = new InMemoryOncoflowApiFake();
    const useCase = new QueueAdminUseCase(api);

    const dashboard = await useCase.getDashboard("oncology", true);
    expect(dashboard.stats.total).toBeGreaterThan(0);
    expect(dashboard.jobs.length).toBeGreaterThan(0);

    const failedJob = dashboard.jobs.find((j) => j.status === "FAILED");
    expect(failedJob).toBeDefined();
    await useCase.retryJob(failedJob!.jobId, "oncology");

    const afterRetry = await useCase.getDashboard("oncology", true);
    const retried = afterRetry.jobs.find((j) => j.jobId === failedJob!.jobId);
    expect(retried?.status).toBe("PENDING");

    const released = await useCase.releaseLocks("oncology");
    expect(released.released).toBeGreaterThanOrEqual(0);
  });
});

describe("HttpOncoflowApiAdapter server-side security headers & contract", () => {
  it("injects X-App-Token and X-Oncoflow-Domain server-side and parses API responses", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => [
        {
          file: "case1.pdf",
          patient_id: "P-1",
          first_name: "Jeanne",
          last_name: "Fictive",
          mdt_date: "2026-11-06",
          priority_level: "high",
          is_complete: false,
          missing_count: 2,
          care_adaptation_suggested: true,
          proposed_care_type: "Gemcitabine",
          specialties: ["pancreas expert"],
          processing_status: "COMPLETED",
          processing_step: null,
          processing_progress_pct: 100,
          rcp_count: 3,
        },
      ],
    });

    const adapter = new HttpOncoflowApiAdapter({
      baseUrl: "http://127.0.0.1:8000",
      apiToken: "secret-server-token",
      proxySecret: "proxy-secret-xyz",
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    const cards = await adapter.listPatientCards("oncology");
    expect(cards).toHaveLength(1);
    expect(cards[0]?.patientName).toBe("Fictive Jeanne");
    expect(cards[0]?.priorityLevel).toBe("high");
    expect(cards[0]?.careAdaptationSuggested).toBe(true);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/patientmdtform/patients?domain=oncology");
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer secret-server-token");
    expect(headers["X-API-Key"]).toBe("secret-server-token");
    expect(headers["X-App-Token"]).toBe("secret-server-token");
    expect(headers["X-Oncoflow-Domain"]).toBe("oncology");
  });
});
