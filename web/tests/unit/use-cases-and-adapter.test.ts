import { describe, expect, it, vi } from "vitest";
import { FeedbackUseCase } from "../../src/application/use-cases/feedback.use-case.js";
import { GuidelinesUseCase } from "../../src/application/use-cases/guidelines.use-case.js";
import { IngestUseCase } from "../../src/application/use-cases/ingest.use-case.js";
import { PatientDossierUseCase } from "../../src/application/use-cases/patient-dossier.use-case.js";
import { QueueAdminUseCase } from "../../src/application/use-cases/queue-admin.use-case.js";
import { WorklistUseCase } from "../../src/application/use-cases/worklist.use-case.js";
import {
  bffRequestContext,
  HttpOncoflowApiAdapter,
} from "../../src/infrastructure/api/http-oncoflow-api.adapter.js";
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

  it("waits for chat responses with extended chatTimeoutMs and preserves HTTP 500 statusCode after backend retries fail", async () => {
    const timeoutSpy = vi.spyOn(AbortSignal, "timeout");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ response: "Réponse après retry backend" }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          detail: "Erreur interne lors de la communication avec l'agent.",
        }),
      });

    const adapter = new HttpOncoflowApiAdapter({
      baseUrl: "http://127.0.0.1:8000",
      timeoutMs: 30_000,
      chatTimeoutMs: 300_000,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    const reply = await adapter.askDossierQuestion(
      { patientId: "A-1042" },
      "test",
      "sma",
      "fr",
      "neurologist expert",
    );
    expect(reply.answer).toBe("Réponse après retry backend");
    expect(timeoutSpy).toHaveBeenCalledWith(300_000);

    await expect(
      adapter.askDossierQuestion(
        { patientId: "A-1042" },
        "test",
        "sma",
        "fr",
        "neurologist expert",
      ),
    ).rejects.toMatchObject({
      message: expect.stringContaining("HTTP 500"),
      statusCode: 500,
    });

    timeoutSpy.mockRestore();
  });

  it("returns null from getDossier (for 404 page) when a patient ID does not exist in FastAPI", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ detail: "Le dossier patient 'toto' n'existe pas." }),
    });

    const adapter = new HttpOncoflowApiAdapter({
      baseUrl: "http://127.0.0.1:8000",
      fetchImpl: fetchMock as unknown as typeof fetch,
    });
    const dossierUseCase = new PatientDossierUseCase(adapter);

    const dossier = await dossierUseCase.getDossier("toto", "sma", "fr");
    expect(dossier).toBeNull();
  });

  it("covers all HttpOncoflowApiAdapter endpoints (forms, patients, sections, resources, bugs, queue, agenda)", async () => {
    const fetchMock = vi.fn(async (urlStr: string, init?: RequestInit) => {
      const url = String(urlStr);
      const method = (init?.method ?? "GET").toUpperCase();

      if (url.includes("/api/v1/patientmdtform/schema")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            domain: "oncology",
            sections: [{ name: "PatientAdministrative", schema: { properties: {} } }],
            enums: { priority: ["low", "medium", "high"] },
          }),
        };
      }
      if (url.includes("/api/v1/patientmdtform/resolve")) {
        const isPdf = url.includes("file=doc.pdf") && !url.includes("patient_id=");
        return {
          ok: true,
          status: 200,
          json: async () =>
            isPdf
              ? { resolved_type: "rcp", selected_file: "doc.pdf" }
              : { patient: { patient_id: "P-1" }, latest_file: "doc.pdf" },
        };
      }
      if (url.includes("/api/v1/patientmdtform/patients/P-1/chat")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ answer: "Synthèse patient", references: [{ name: "doc.pdf" }] }),
        };
      }
      if (url.includes("/api/v1/patientmdtform/patients/P-1") && method === "GET") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            patient: { patient_id: "P-1" },
            enriched_rcps: [
              {
                file: "doc.pdf",
                mdt_date: "2026-11-06",
                processing_status: "COMPLETED",
                PatientAdministrative: { first_name: "Jeanne", last_name: "Fictive" },
                MTDCompleted: { mtd_complete: { is_mtd_complete: false, what_missing: ["IRM"] } },
                CareOrientationProposal: {
                  care_adaptation_suggested: true,
                  proposed_care_type: "Chirurgie",
                  suggested_priority: "medium",
                },
                ExpertAnswer: {
                  "pancreas expert": { expert_relevant: true, patient_priority: "high" },
                },
                manual_edits: {
                  PatientAdministrative: { is_manual: true, edited_by: "Dr Test" },
                },
                markdown_text: "# Compte rendu",
                chunks: [{ id: "c1", text: "chunk" }],
              },
            ],
          }),
        };
      }
      if (url.includes("/api/v1/patientmdtform/patients?") && method === "GET") {
        return {
          ok: true,
          status: 200,
          json: async () => [
            {
              patient_id: "P-1",
              first_name: "Jeanne",
              last_name: "Fictive",
              born_name: "Martin",
              date_birth: "1960-05-14",
              gender: "F",
              rcp_count: 2,
            },
          ],
        };
      }
      if (url.includes("/api/v1/patientmdtform?") && method === "GET") {
        return {
          ok: true,
          status: 200,
          json: async () => [
            {
              file: "doc.pdf",
              patient_id: "P-1",
              patient: "Fictive Jeanne",
              missing: ["IRM"],
              experts: ["pancreas expert"],
              processing_status: "COMPLETED",
            },
          ],
        };
      }
      if (url.includes("/pdf?")) {
        return {
          ok: true,
          status: 200,
          arrayBuffer: async () => new Uint8Array([37, 80, 68, 70]).buffer,
        };
      }
      if (url.includes("/api/v1/patientmdtform/batches/")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            batch_id: "b1",
            files: [{ filename: "doc.pdf", status: "COMPLETED", progress_pct: 100 }],
          }),
        };
      }
      if (
        url.includes("/api/v1/patientmdtform/") &&
        (method === "GET" || url.includes("/rollback") || url.includes("/missing-items"))
      ) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            file: "doc.pdf",
            patient_id: "P-1",
            sections: {
              PatientAdministrative: { first_name: "Jeanne", last_name: "Fictive" },
              MTDCompleted: { is_mtd_complete: true, what_missing: [] },
            },
            hidden_missing_items: ["Bilan"],
            hide_missing_items: false,
            processing_status: "COMPLETED",
          }),
        };
      }
      if (url.includes("/api/v1/queue/rerun")) {
        return { ok: true, status: 200, json: async () => ({ job_id: "job-rerun-1" }) };
      }
      if (url.includes("/process?")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ jobs: [{ job_id: "job-full-1" }] }),
        };
      }
      if (url.includes("/api/v1/resources?") && method === "GET") {
        return {
          ok: true,
          status: 200,
          json: async () => [
            {
              filename: "PNDS_SMA.pdf",
              size_bytes: 1024,
              is_indexed: true,
              chunk_count: 12,
              updated_at: "2026-11-01",
            },
          ],
        };
      }
      if (url.includes("/api/v1/resources/") && url.includes("/file?")) {
        if (url.includes("missing-citation")) {
          return { ok: false, status: 404 };
        }
        return {
          ok: true,
          status: 200,
          arrayBuffer: async () => new Uint8Array([37, 80, 68, 70]).buffer,
        };
      }
      if (url.includes("/api/v1/resources/") && url.includes("/chat?")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ answer: "Réponse référentiel" }),
        };
      }
      if (url.includes("/api/v1/agents?")) {
        return {
          ok: true,
          status: 200,
          json: async () => [
            {
              name: "pancreas expert",
              role: "Expert pancréas",
              resources: ["TNCD.pdf"],
              models: ["mistral"],
              system_prompt: "Tu es expert",
            },
          ],
        };
      }
      if (url.includes("/api/v1/bug-reports") && method === "GET") {
        return {
          ok: true,
          status: 200,
          json: async () => [
            {
              bug_id: "BUG-1",
              title: "Bug 1",
              description: "Desc",
              category: "ui",
              severity: "low",
              status: "resolved",
              domain: "oncology",
              patient_id: "P-1",
              reporter: "Dr X",
              created_at: "2026-11-04",
            },
          ],
        };
      }
      if (url.includes("/api/v1/bug-reports") && method === "POST") {
        return {
          ok: true,
          status: 201,
          json: async () => ({ bug_id: "BUG-1", status: "open", created_at: "2026-11-04" }),
        };
      }
      if (url.includes("/api/v1/queue/stats")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            pending: 1,
            processing: 1,
            completed: 5,
            failed: 0,
            cancelled: 0,
            active_locks: 1,
          }),
        };
      }
      if (url.includes("/api/v1/queue/thinking")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            is_thinking: true,
            filename: "doc.pdf",
            step: "Extraction",
            content: "Analyse en cours...",
          }),
        };
      }
      if (url.includes("/api/v1/queue/jobs?")) {
        return {
          ok: true,
          status: 200,
          json: async () => [
            {
              job_id: "J-1",
              job_type: "FULL_EXTRACTION",
              status: "PENDING",
              priority: 1,
              domain: "oncology",
              filename: "doc.pdf",
              model_name: "TumorBiology",
              progress_pct: 50,
              current_step: "LLM",
              preserve_manual_edits: true,
            },
          ],
        };
      }
      if (url.includes("/api/v1/queue/clean")) {
        return { ok: true, status: 200, json: async () => ({ affected_jobs: 3 }) };
      }
      if (url.includes("/api/v1/queue/locks")) {
        return { ok: true, status: 200, json: async () => ({ released_locks: 1 }) };
      }
      if (url.includes("/api/v1/mdt-agenda")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            agenda_id: "next_mdt_oncology",
            domain: "oncology",
            session_date: "2026-11-12",
            sort_strategy: "urgency_first",
            defer_incomplete_files: true,
            available_experts: ["pancreas expert"],
            attending_experts: ["pancreas expert"],
            items: [
              {
                position: 1,
                patient_id: "P-1",
                filename: "doc.pdf",
                patient_name: "Fictive Jeanne",
                urgency: "high",
                urgency_score: 90,
                is_complete: true,
                required_experts: ["pancreas expert"],
                present_required_experts: ["pancreas expert"],
                absent_required_experts: [],
              },
            ],
            expert_windows: [
              {
                expert_name: "pancreas expert",
                is_attending: true,
                case_count: 1,
                urgent_case_count: 1,
                first_position: 1,
                last_position: 1,
                is_contiguous: true,
                patient_ids: ["P-1"],
              },
            ],
            candidates: [
              {
                patient_id: "P-2",
                filename: "doc2.pdf",
                patient_name: "Autre Patient",
                urgency: "low",
              },
            ],
          }),
        };
      }

      return { ok: true, status: 200, json: async () => ({}) };
    });

    const adapter = new HttpOncoflowApiAdapter({
      baseUrl: "http://127.0.0.1:8000/",
      apiToken: "tok",
      proxySecret: "sec",
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect((await adapter.listRcpCards("oncology")).length).toBe(1);
    expect((await adapter.listPatients("oncology", true)).length).toBe(1);
    await adapter.deletePatient("P-1", "oncology");
    await adapter.deleteForm("doc.pdf", "oncology");

    const schema1 = await adapter.getDomainSchema("oncology");
    const schema2 = await adapter.getDomainSchema("oncology");
    expect(schema1).toBe(schema2);

    expect((await adapter.resolveTarget("doc.pdf", "oncology")).kind).toBe("form");
    expect((await adapter.resolveTarget("P-1", "oncology")).kind).toBe("patient");

    const forms = await adapter.getPatientForms("P-1", "oncology");
    expect(forms).toHaveLength(1);
    expect(forms[0]?.metrics.priority_level).toBe("high");

    const updated = await adapter.updateFormSection(
      "doc.pdf",
      "PatientAdministrative",
      { first_name: "Jeanne" },
      "Dr Test",
      "oncology",
    );
    expect(updated.file).toBe("doc.pdf");

    expect(
      (await adapter.rollbackSection("doc.pdf", "PatientAdministrative", "oncology")).file,
    ).toBe("doc.pdf");
    expect(
      (
        await adapter.updateMissingItems(
          "doc.pdf",
          { hideMissingItems: true, editedBy: "Dr Test" },
          "oncology",
        )
      ).file,
    ).toBe("doc.pdf");

    expect((await adapter.rerunSection("doc.pdf", "TumorBiology", true, "oncology")).jobId).toBe(
      "job-rerun-1",
    );
    expect((await adapter.processFullForm("doc.pdf", true, "oncology")).jobId).toBe("job-full-1");
    await adapter.linkFormToPatient("doc.pdf", "P-1", "oncology");

    const pdfBuf = await adapter.getFormPdfBuffer("doc.pdf", "oncology", "bbox");
    expect(pdfBuf).toBeInstanceOf(Buffer);

    const chatReply = await adapter.askDossierQuestion(
      { patientId: "P-1" },
      "Question ?",
      "oncology",
      "en",
    );
    expect(chatReply.answer).toBe("Synthèse patient");

    const uploadRes = await adapter.uploadForms(
      [{ filename: "doc.pdf", content: Buffer.from("pdf"), patientId: "P-1" }],
      "b1",
      "oncology",
    );
    expect(uploadRes.filenames).toEqual(["doc.pdf"]);
    expect((await adapter.getBatchStatus("b1", "oncology")).completed).toBe(1);

    expect((await adapter.listResources("oncology")).length).toBe(1);
    expect((await adapter.uploadResource("new.pdf", Buffer.from("pdf"), "oncology")).filename).toBe(
      "new.pdf",
    );
    await adapter.reindexResource("new.pdf", "oncology");
    await adapter.deleteResource("new.pdf", "oncology");
    expect(
      await adapter.getResourcePdfBuffer("PNDS_SMA.pdf", "oncology", "doc.pdf"),
    ).toBeInstanceOf(Buffer);
    // Fallback resolution when citation title doesn't match directly
    expect(await adapter.getResourcePdfBuffer("missing-citation pnds", "oncology")).toBeInstanceOf(
      Buffer,
    );

    expect((await adapter.listAgents("oncology", "fr")).length).toBe(1);
    expect((await adapter.askGuidelineQuestion("Question ?", "oncology", "fr")).answer).toBe(
      "Réponse référentiel",
    );

    const createdBug = await adapter.createBug({
      title: "Bug 1",
      description: "Desc",
      category: "ui",
      severity: "low",
      domain: "oncology",
      patientOrFile: "P-1",
      author: "Dr X",
    });
    expect(createdBug.id).toBe("BUG-1");
    expect((await adapter.updateBugStatus("BUG-1", "resolved", "oncology")).status).toBe(
      "resolved",
    );
    await adapter.deleteBug("BUG-1", "oncology");

    const qStats = await adapter.getQueueStats("oncology");
    expect(qStats.activeFormFile).toBe("doc.pdf");
    expect(qStats.thinkingPreview).toBe("Analyse en cours...");
    expect((await adapter.listQueueJobs("oncology")).length).toBe(1);
    await adapter.retryQueueJob("J-1", "oncology");
    await adapter.cancelOrDeleteQueueJob("J-1", "oncology");
    expect(await adapter.cleanQueue("completed", "oncology")).toBe(3);
    expect((await adapter.releaseGpuLocks("oncology")).released).toBe(1);

    const agenda = await adapter.getMdtAgenda("oncology");
    expect(agenda.sortStrategy).toBe("urgency_first");
    expect(agenda.items).toHaveLength(1);
    await adapter.updateMdtAgenda(
      {
        sessionDate: "2026-11-15",
        sortStrategy: "hybrid",
        deferIncompleteFiles: false,
        attendingExperts: ["pancreas expert"],
        toggleExpert: "pancreas expert",
        patientIds: ["P-1"],
        resetEnrolledPatients: false,
      },
      "oncology",
    );
    await adapter.addPatientsToMdtAgenda({ patientIds: ["P-2"] }, "oncology");
    await adapter.removePatientFromMdtAgenda("P-1", "oncology");
    await adapter.clearMdtAgenda("oncology");
    await adapter.movePatientInMdtAgenda("P-1", { direction: "up" }, "oncology");
  });

  it("delegates to fallbackPort when HTTP requests fail", async () => {
    const failingFetch = vi.fn().mockRejectedValue(new Error("Network error"));
    const fallback = new InMemoryOncoflowApiFake();
    const adapter = new HttpOncoflowApiAdapter({
      baseUrl: "http://127.0.0.1:8000",
      fetchImpl: failingFetch as unknown as typeof fetch,
      fallbackPort: fallback,
    });

    expect((await adapter.listPatientCards("oncology")).length).toBeGreaterThan(0);
    expect((await adapter.listRcpCards("oncology")).length).toBeGreaterThan(0);
    expect((await adapter.listPatients("oncology")).length).toBeGreaterThan(0);
    expect((await adapter.getDomainSchema("oncology")).sections.length).toBeGreaterThan(0);
    expect((await adapter.resolveTarget("A-1042", "oncology")).kind).toBe("patient");
    expect((await adapter.getPatientForms("A-1042", "oncology")).length).toBeGreaterThan(0);
    expect((await adapter.listResources("oncology")).length).toBeGreaterThan(0);
    expect((await adapter.listAgents("oncology", "fr")).length).toBeGreaterThan(0);
    expect((await adapter.listBugs("oncology")).length).toBeGreaterThan(0);
    expect((await adapter.getQueueStats("oncology")).total).toBeGreaterThan(0);
    expect((await adapter.listQueueJobs("oncology")).length).toBeGreaterThan(0);
    expect((await adapter.getMdtAgenda("oncology")).agendaId).toBeTruthy();

    // Also exercise write/action methods through fallbackPort
    const cards = await adapter.listPatientCards("oncology");
    const sampleFile = cards[0]!.file;
    const samplePid = cards[0]!.patientId!;
    await adapter.updateFormSection(
      sampleFile,
      "PatientAdministrative",
      { first_name: "Jeanne" },
      "Dr Test",
      "oncology",
    );
    await adapter.rollbackSection(sampleFile, "PatientAdministrative", "oncology");
    await adapter.updateMissingItems(sampleFile, { hideMissingItems: false }, "oncology");
    await adapter.rerunSection(sampleFile, "TumorBiology", true, "oncology");
    await adapter.processFullForm(sampleFile, true, "oncology");
    await adapter.linkFormToPatient(sampleFile, samplePid, "oncology");
    expect(await adapter.getFormPdfBuffer(sampleFile, "oncology")).not.toBeNull();
    expect(await adapter.getFormDetail(sampleFile, "oncology")).not.toBeNull();
    expect(
      (await adapter.askDossierQuestion({ filename: sampleFile }, "Q?", "oncology", "fr")).answer,
    ).toBeTruthy();
    const batch = await adapter.uploadForms(
      [{ filename: "f.pdf", content: Buffer.from("%PDF") }],
      "b-fb",
      "oncology",
    );
    expect((await adapter.getBatchStatus(batch.batchId, "oncology")).total).toBe(1);
    await adapter.uploadResource("r.pdf", Buffer.from("%PDF"), "oncology");
    await adapter.reindexResource("r.pdf", "oncology");
    expect(await adapter.getResourcePdfBuffer("r.pdf", "oncology")).not.toBeNull();
    await adapter.deleteResource("r.pdf", "oncology");
    expect((await adapter.askGuidelineQuestion("Q?", "oncology", "fr")).answer).toBeTruthy();
    const bug = await adapter.createBug({
      title: "T",
      description: "D",
      category: "ui",
      severity: "low",
      domain: "oncology",
      patientOrFile: null,
      author: "A",
    });
    await adapter.updateBugStatus(bug.id, "resolved", "oncology");
    await adapter.deleteBug(bug.id, "oncology");
    const jobs = await adapter.listQueueJobs("oncology");
    if (jobs[0]) {
      await adapter.retryQueueJob(jobs[0].jobId, "oncology");
      await adapter.cancelOrDeleteQueueJob(jobs[0].jobId, "oncology");
    }
    await adapter.cleanQueue("completed", "oncology");
    await adapter.releaseGpuLocks("oncology");
    await adapter.updateMdtAgenda({ sortStrategy: "manual" }, "oncology");
    await adapter.addPatientsToMdtAgenda({ patientIds: [samplePid] }, "oncology");
    await adapter.movePatientInMdtAgenda(samplePid, { direction: "up" }, "oncology");
    await adapter.removePatientFromMdtAgenda(samplePid, "oncology");
    await adapter.clearMdtAgenda("oncology");
    await adapter.deleteForm(sampleFile, "oncology");
    await adapter.deletePatient(samplePid, "oncology");
  });

  it("propagates X-Forwarded-For / X-Oncoflow-User via bffRequestContext and caches short-TTL calls with invalidation on write", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => [
        {
          patient_id: "P-1",
          first_name: "Jeanne",
          last_name: "Fictive",
          rcp_count: 2,
        },
      ],
    }));

    const adapter = new HttpOncoflowApiAdapter({
      baseUrl: "http://127.0.0.1:8000",
      fetchImpl: fetchMock as unknown as typeof fetch,
      cacheTtlMs: 15_000,
    });

    await bffRequestContext.run(
      {
        clientIp: "10.20.30.40",
        userId: "dr.martin",
        userName: "Dr Martin",
        requestId: "req-123",
      },
      async () => {
        const p1 = await adapter.listPatients("oncology", false);
        const p2 = await adapter.listPatients("oncology", false);
        expect(p1).toEqual(p2);
        // Second call within TTL must hit the in-memory cache
        expect(fetchMock).toHaveBeenCalledTimes(1);

        const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        const headers = init.headers as Record<string, string>;
        expect(headers["X-Forwarded-For"]).toBe("10.20.30.40");
        expect(headers["X-Real-IP"]).toBe("10.20.30.40");
        expect(headers["X-Oncoflow-User"]).toBe("dr.martin");
        expect(headers["X-Oncoflow-User-Name"]).toBe("Dr Martin");
        expect(headers["X-Request-ID"]).toBe("req-123");

        // Any write invalidates the dossier caches
        await adapter.deleteForm("doc.pdf", "oncology");
        await adapter.listPatients("oncology", false);
        expect(fetchMock).toHaveBeenCalledTimes(3);
      },
    );
  });

  it("maps getPatientDashboard and triggerPatientSummary responses, caches non-active dashboard, and falls back gracefully", async () => {
    const dashboardPayload = {
      patient: {
        patient_id: "P-DASH",
        first_name: "Paul",
        last_name: "Durand",
      },
      latest_file: "durand_2026_05.pdf",
      rcp_count: 2,
      metrics: [
        {
          metric_key: "TumorBiology.ca19_9",
          section: "TumorBiology",
          field: "ca19_9",
          label: "CA 19-9",
          unit: "U/mL",
          scale_min: 0,
          scale_max: 5000,
          polarity: "lower_is_better",
          value_type: "numeric_or_mixed",
          points: [
            {
              form_id: "durand_2026_01.pdf",
              form_date: "2026-01-10",
              form_date_label: "2026-01-10",
              days_since_first_rcp: 0,
              x_ratio: 0,
              raw_value: 850,
              display_value: "850",
              numeric_value: 850,
              sub_values: { D: 850 },
              is_annotative_only: false,
              is_manual: true,
              edited_by: "Dr. Durand",
              edited_at: "2026-01-11T09:00:00Z",
              delta_numeric: -200,
              delta_display: "-200",
            },
          ],
        },
      ],
      summary: {
        has_summary: true,
        generated_at: "2026-05-15T10:00:00Z",
        covered_form_ids: ["durand_2026_01.pdf", "durand_2026_05.pdf"],
        latest_form_id_at_generation: "durand_2026_05.pdf",
        latest_form_date_at_generation: "2026-05-15",
        model_used: "mistral-nemo",
        is_obsolete: false,
        obsolete_reasons: [],
        new_forms_since_summary: [],
        removed_forms_since_summary: [],
        modified_forms_since_summary: [],
        content: {
          clinical_trajectory_overview: "Réponse biologique favorable sous FOLFIRINOX.",
          disease_and_treatment_evolution: "Diminution CA 19-9.",
          notable_metric_changes: ["CA 19-9: 850 → 120 U/mL"],
          unresolved_vigilance_points: ["Scanner thoracique à programmer"],
          mdt_decisions_recap: ["Poursuite chimiothérapie"],
          sources_used: ["durand_2026_01.pdf"],
        },
        active_job: null,
      },
    };

    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes("/summary")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            queued: true,
            already_queued: false,
            job: { job_id: "JOB-SUM-1", status: "PENDING" },
            summary: {
              ...dashboardPayload.summary,
              active_job: { job_id: "JOB-SUM-1", status: "PENDING" },
            },
          }),
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => dashboardPayload,
      };
    });

    const adapter = new HttpOncoflowApiAdapter({
      baseUrl: "http://127.0.0.1:8000",
      fetchImpl: fetchMock as unknown as typeof fetch,
      cacheTtlMs: 15_000,
    });
    const useCase = new PatientDossierUseCase(adapter);

    const dash1 = await useCase.getPatientDashboard("P-DASH", "oncology");
    const dash2 = await useCase.getPatientDashboard("P-DASH", "oncology");
    expect(dash1?.patientName).toBe("Durand Paul");
    expect(dash1?.metrics[0]?.points[0]?.numericValue).toBe(850);
    expect(dash1?.metrics[0]?.points[0]?.subValues).toEqual({ D: 850 });
    expect(dash1?.summary.content?.clinicalTrajectoryOverview).toContain("FOLFIRINOX");
    expect(dash2).toEqual(dash1);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const trig = await useCase.triggerPatientSummary("P-DASH", "oncology", true);
    expect(trig.queued).toBe(true);
    expect(trig.jobId).toBe("JOB-SUM-1");
    expect(trig.summary?.activeJob).toEqual({ job_id: "JOB-SUM-1", status: "PENDING" });

    // Fallback when HTTP fails and no InMemory fallback is attached (computes from getPatientForms)
    const failingAdapter = new HttpOncoflowApiAdapter({
      baseUrl: "http://127.0.0.1:8000",
      fetchImpl: (async (url: string) => {
        if (url.includes("/dashboard")) {
          throw new Error("dashboard endpoint down");
        }
        return {
          ok: true,
          status: 200,
          json: async () => [
            {
              file: "f1.pdf",
              patient_id: "P-FALL",
              PatientAdministrative: {
                first_name: "Claire",
                last_name: "Moreau",
                date_rcp: "2026-03-01",
              },
              CancerDescription: {
                type_of_cancer: "Pancreas",
                tnm_status: "cT2N0M0",
                recist_response: "PR",
                target_lesion_size_mm: 24,
              },
              TumorBiology: {
                msi_state: false,
                ca19_9: 310,
                ace: 3.2,
                dpd_uracilemia: 8.1,
              },
              HepaticStatus: {
                child_pugh_score: "A5",
                bclc_stage: "A",
                bilirubin_umol_l: 12,
              },
              NutritionalStatus: {
                weight_kg: 64,
                weight_loss_percent: 4,
                bmi: 21.5,
              },
              SurgicalStatus: {
                resectability_status: "Resectable",
                resection_margin: "R0",
              },
            },
          ],
        };
      }) as unknown as typeof fetch,
    });

    const fallbackDash = await failingAdapter.getPatientDashboard("P-FALL", "oncology");
    expect(fallbackDash?.patientName).toBe("Moreau Claire");
    expect(fallbackDash?.metrics.length).toBeGreaterThan(0);

    // Also verify PatientDossierUseCase summary pills for CancerDescription, TumorBiology, HepaticStatus, NutritionalStatus, SurgicalStatus
    const failingUseCase = new PatientDossierUseCase(failingAdapter);
    const richDossier = await failingUseCase.getDossier("P-FALL", "oncology", "fr");
    const sectionTitles = new Map(richDossier?.sections.map((s) => [s.name, s.summaryText]) ?? []);
    expect(sectionTitles.get("CancerDescription")).toContain("cT2N0M0");
    expect(sectionTitles.get("TumorBiology")).toContain("CA 19-9: 310 U/mL");
    expect(sectionTitles.get("HepaticStatus")).toContain("Child-Pugh A5");
    expect(sectionTitles.get("NutritionalStatus")).toContain("64 kg");
    expect(sectionTitles.get("SurgicalStatus")).toContain("R0");
  });
});
