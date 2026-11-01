import { describe, expect, it } from "vitest";
import { loadConfig } from "../../src/config.js";
import { HttpOncoflowApiAdapter } from "../../src/infrastructure/api/http-oncoflow-api.adapter.js";
import { InMemoryOncoflowApiFake } from "../../src/infrastructure/api/in-memory-oncoflow-api.fake.js";
import { buildServer } from "../../src/ui/server.js";

describe("Next RCP / MDT Session Agenda Builder (/agenda)", () => {
  it("renders the agenda builder page with enrolled patients, attending experts, and passage windows", async () => {
    const api = new InMemoryOncoflowApiFake();
    const config = loadConfig({ APP_DEV_MODE: "true" });
    const app = await buildServer({ config, api });

    const res = await app.inject({
      method: "GET",
      url: "/agenda?domain=oncology",
    });

    expect(res.statusCode).toBe(200);
    expect(res.body).toContain("Ordre du jour RCP");
    expect(res.body).toContain("Programmer une nouvelle réunion");
    expect(res.body).toContain("Paramétrage de la réunion RCP");
    expect(res.body).toContain('data-testid="agenda-config-card"');
    expect(res.body).toContain("FICTIVE Jeanne");
    expect(res.body).toContain("MODÈLE Paul");
    expect(res.body).toContain('data-testid="agenda-expert-chips"');
    expect(res.body).toContain('data-testid="btn_schedule_new_meeting"');
    expect(res.body).not.toContain("Reléguer les dossiers incomplets");
  });

  it("hides settings when no meeting is scheduled and renders Dossier précédent / Dossier suivant when opening a dossier from the agenda", async () => {
    const api = new InMemoryOncoflowApiFake();
    const config = loadConfig({ APP_DEV_MODE: "true" });
    const app = await buildServer({ config, api });

    // 1. Opening a patient dossier from the agenda (?from=agenda) renders prev/next dossier navigation
    const dossierFromAgenda = await app.inject({
      method: "GET",
      url: "/patients/A-1042?domain=oncology&from=agenda",
    });
    expect(dossierFromAgenda.statusCode).toBe(200);
    expect(dossierFromAgenda.body).toContain('data-testid="agenda-dossier-nav"');
    expect(dossierFromAgenda.body).toContain('data-testid="btn_agenda_prev_dossier"');
    expect(dossierFromAgenda.body).toContain('data-testid="btn_agenda_next_dossier"');
    expect(dossierFromAgenda.body).toContain("Dossier précédent");
    expect(dossierFromAgenda.body).toContain("Dossier suivant");
    expect(dossierFromAgenda.body).toContain("/patients/A-1037?domain=oncology&from=agenda");

    // 2. Clear the agenda -> no active meeting -> settings card is hidden
    await app.inject({
      method: "POST",
      url: "/agenda/patients/clear?domain=oncology",
    });
    const emptyAgendaRes = await app.inject({
      method: "GET",
      url: "/agenda?domain=oncology",
    });
    expect(emptyAgendaRes.statusCode).toBe(200);
    expect(emptyAgendaRes.body).not.toContain('data-testid="agenda-config-card"');
    expect(emptyAgendaRes.body).toContain("Aucune réunion RCP programmée");
  });

  it("supports direct onboarding via POST /agenda/schedule ('Programmer une nouvelle réunion')", async () => {
    const api = new InMemoryOncoflowApiFake();
    const config = loadConfig({ APP_DEV_MODE: "true" });
    const app = await buildServer({ config, api });

    const scheduleRes = await app.inject({
      method: "POST",
      url: "/agenda/schedule?domain=oncology",
      payload: {
        sessionDate: "2026-12-10",
        sortStrategy: "urgency_first",
        attendingExpertsPresent: "true",
        attendingExperts: ["pancreas expert", "oesophagus expert"],
        patientIdsPresent: "true",
        patientIds: ["A-1042"],
      },
    });
    expect(scheduleRes.statusCode).toBe(302);

    const view = await api.getMdtAgenda("oncology");
    expect(view.sessionDate).toBe("2026-12-10");
    expect(view.sortStrategy).toBe("urgency_first");
    expect(view.attendingExperts).toEqual(["pancreas expert", "oesophagus expert"]);
    expect(view.items.map((i) => i.patientId)).toEqual(["A-1042"]);
    expect(view.candidates.map((c) => c.patientId)).toContain("A-1037");
  });

  it("toggles expert attendance, updates sort strategy and sessionDate, moves/pins patients, and removes/enrolls patients", async () => {
    const api = new InMemoryOncoflowApiFake();
    const config = loadConfig({ APP_DEV_MODE: "true" });
    const app = await buildServer({ config, api });

    // 1. Toggle pancreas expert off -> triggers quorum warning on Jeanne FICTIVE (#A-1042)
    const toggleRes = await app.inject({
      method: "POST",
      url: "/agenda/options?domain=oncology",
      payload: {
        toggleExpert: "pancreas expert",
        sessionDate: "2026-12-01",
        sortStrategy: "expert_grouping",
      },
    });
    expect(toggleRes.statusCode).toBe(302);

    const agendaAfterToggle = await api.getMdtAgenda("oncology");
    expect(agendaAfterToggle.attendingExperts).not.toContain("pancreas expert");
    expect(agendaAfterToggle.sessionDate).toBe("2026-12-01");
    expect(agendaAfterToggle.sortStrategy).toBe("expert_grouping");
    expect(agendaAfterToggle.quorumWarningCount).toBeGreaterThanOrEqual(1);

    // 2. Move Jeanne FICTIVE (#A-1042, currently #2 because pancreas expert is absent) up to #1 and pin
    await app.inject({
      method: "POST",
      url: "/agenda/patients/A-1042/move?domain=oncology",
      payload: { direction: "up", pinned: "true" },
    });
    const agendaAfterMove = await api.getMdtAgenda("oncology");
    expect(agendaAfterMove.items[0]?.patientId).toBe("A-1042");
    expect(agendaAfterMove.items[0]?.pinned).toBe(true);

    // 3. Remove A-1037 -> moves to candidates pool
    await app.inject({
      method: "POST",
      url: "/agenda/patients/A-1037/remove?domain=oncology",
    });
    const agendaAfterRemove = await api.getMdtAgenda("oncology");
    expect(agendaAfterRemove.items.map((i) => i.patientId)).not.toContain("A-1037");
    expect(agendaAfterRemove.candidates.map((c) => c.patientId)).toContain("A-1037");

    // 4. Re-enroll A-1037 from candidate pool
    await app.inject({
      method: "POST",
      url: "/agenda/patients?domain=oncology",
      payload: { patientId: "A-1037" },
    });
    const agendaAfterEnroll = await api.getMdtAgenda("oncology");
    expect(agendaAfterEnroll.items.map((i) => i.patientId)).toContain("A-1037");

    // 5. Clear agenda and batch enroll all candidates
    await app.inject({
      method: "POST",
      url: "/agenda/patients/clear?domain=oncology",
    });
    const cleared = await api.getMdtAgenda("oncology");
    expect(cleared.items).toHaveLength(0);

    await app.inject({
      method: "POST",
      url: "/agenda/patients?domain=oncology",
      payload: { enrollAllCandidates: "true", filterMode: "all" },
    });
    const enrolledAll = await api.getMdtAgenda("oncology");
    expect(enrolledAll.items.length).toBeGreaterThanOrEqual(2);
  });

  it("maps FastAPI snake_case payload in HttpOncoflowApiAdapter", async () => {
    const mockFetch: typeof fetch = async () =>
      new Response(
        JSON.stringify({
          agenda_id: "next_mdt_oncology",
          domain: "oncology",
          session_date: "2026-11-20",
          sort_strategy: "urgency_first",
          defer_incomplete_files: true,
          available_experts: ["pancreas expert"],
          attending_experts: ["pancreas expert"],
          total_enrolled: 1,
          urgent_count: 1,
          incomplete_count: 0,
          quorum_warning_count: 0,
          items: [
            {
              position: 1,
              patient_id: "A-1042",
              filename: "jeanne.pdf",
              patient_name: "FICTIVE Jeanne",
              first_name: "Jeanne",
              last_name: "FICTIVE",
              date_birth: "1958-03-02",
              urgency: "Urgent",
              urgency_score: 2,
              priority_level: "high",
              is_complete: true,
              missing_count: 0,
              missing_items: [],
              care_adaptation_suggested: true,
              proposed_care_type: "Chirurgie",
              required_experts: ["pancreas expert"],
              present_required_experts: ["pancreas expert"],
              absent_required_experts: [],
              quorum_met: true,
              expert_coverage_ratio: 1,
              cluster_key: "pancreas expert",
              pinned: false,
              rank_reason: "Priorité haute (Urgent)",
              mdt_date: "2026-11-06",
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
              patient_ids: ["A-1042"],
            },
          ],
          candidates: [],
          updated_at: "2026-11-01T18:00:00Z",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );

    const adapter = new HttpOncoflowApiAdapter({
      baseUrl: "http://127.0.0.1:8000",
      apiToken: "test-token",
      fetchImpl: mockFetch,
    });

    const view = await adapter.getMdtAgenda("oncology");
    expect(view.agendaId).toBe("next_mdt_oncology");
    expect(view.sortStrategy).toBe("urgency_first");
    expect(view.items).toHaveLength(1);
    expect(view.items[0]?.patientId).toBe("A-1042");
    expect(view.expertWindows[0]?.firstPosition).toBe(1);
  });
});
