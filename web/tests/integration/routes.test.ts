import { describe, expect, it } from "vitest";
import { loadConfig } from "../../src/config.js";
import { InMemoryOncoflowApiFake } from "../../src/infrastructure/api/in-memory-oncoflow-api.fake.js";
import {
  buildServer,
  isSafeFilename,
  sanitizeLocalRedirect,
  verifyProxySecret,
} from "../../src/ui/server.js";

async function createTestApp() {
  const api = new InMemoryOncoflowApiFake();
  const config = loadConfig({
    PORT_WEB: "0",
    APP_DOMAIN: "oncology",
    APP_ALLOWED_DOMAINS: "oncology,sma",
  });
  const app = await buildServer({ config, api });
  return { app, api };
}

describe("Fastify BFF Routes & Material Design 3 HTML Views (Integration)", () => {
  it("GET / redirects to /worklist and sets strict self-hosted CSP header", async () => {
    const { app } = await createTestApp();
    const resRedirect = await app.inject({ method: "GET", url: "/" });
    expect(resRedirect.statusCode).toBe(302);
    expect(resRedirect.headers.location).toBe("/worklist");

    const res = await app.inject({ method: "GET", url: "/worklist" });
    expect(res.statusCode).toBe(200);
    expect(res.headers["content-security-policy"]).toContain("default-src 'self'");
    expect(res.body).toContain('data-testid="sidebar"');
    expect(res.body).toContain('data-testid="queue-banner"');
    expect(res.body).toContain('data-testid="theme-selector"');
    expect(res.body).toContain('data-testid="kpi-structured"');
    expect(res.body).toContain('data-testid="kpi-priority-high"');
    expect(res.body).toContain('data-testid="worklist-table"');
    expect(res.body).toContain("FICTIVE Jeanne");
    // Medico-legal check: never use "Intervention requise"
    expect(res.body).toContain("Adaptation suggérée");
    expect(res.body).not.toContain("Intervention requise");
    // Fixed domain per instance: no manual domain selector in sidebar
    expect(res.body).not.toContain('data-testid="domain-select"');
    // Material Design 3 Navigation Rail & Contextual Menus (...)
    expect(res.body).toContain("ds-nav-rail");
    expect(res.body).toContain('data-testid="rail-fab-ingest"');
    expect(res.body).toContain("ds-nav__indicator");
    expect(res.body).toContain('data-testid="menu-topbar-actions"');
    expect(res.body).toContain('data-testid="menu-patient-A-1042"');
    // Styleguide link hidden unless expertMode is enabled
    expect(res.body).not.toContain('data-testid="nav-styleguide"');

    const expertRes = await app.inject({ method: "GET", url: "/worklist?expert=true" });
    expect(expertRes.body).toContain('data-testid="nav-styleguide"');

    const cardsRes = await app.inject({ method: "GET", url: "/worklist?display=cards" });
    expect(cardsRes.statusCode).toBe(200);
    expect(cardsRes.body).toContain("ds-patient-grid");
    await app.close();
  });

  it("GET /styleguide serves the Material Design 3 styleguide with the SVG icon catalog", async () => {
    const { app } = await createTestApp();
    const res = await app.inject({ method: "GET", url: "/styleguide" });
    expect(res.statusCode).toBe(200);
    expect(res.body).toContain("Catalogue d'icônes Material Design 3");
    expect(res.body).toContain('id="ic-compass"');
    await app.close();
  });

  it("GET /worklist filters by domain (sma) and completeness (incomplete)", async () => {
    const { app } = await createTestApp();
    const smaRes = await app.inject({
      method: "GET",
      url: "/worklist?domain=sma",
    });
    expect(smaRes.statusCode).toBe(200);
    expect(smaRes.body).toContain("EXEMPLE Léo");

    const incRes = await app.inject({
      method: "GET",
      url: "/worklist?domain=oncology&completeness=incomplete",
    });
    expect(incRes.statusCode).toBe(200);
    expect(incRes.body).toContain("FICTIVE Jeanne");
    expect(incRes.body).not.toContain("MODÈLE Paul");
    await app.close();
  });

  it("GET /patients/:patientId renders longitudinal timeline, synoptic card, sections, opinions, and saves manual edits", async () => {
    const { app } = await createTestApp();
    const res = await app.inject({
      method: "GET",
      url: "/patients/A-1042",
    });
    expect(res.statusCode).toBe(200);
    expect(res.body).toContain('data-testid="synoptic-card"');
    expect(res.body).toContain('data-testid="session-timeline"');
    expect(res.body).toContain('data-testid="split-view"');
    expect(res.body).toContain("jeanne_fictive_2026_11_06.pdf");
    expect(res.body).toContain("TNCD Pancréas §4.2");
    // Timeline upcoming node & readable PDF iframe hash
    expect(res.body).toContain('data-testid="timeline-upcoming"');
    expect(res.body).toContain("Prochaine séance");
    expect(res.body).toContain("#navpanes=0&amp;pagemode=none&amp;view=FitH&amp;toolbar=1");
    expect(res.body).toContain('data-testid="btn_pdf_expand"');
    // AI reasoning (reasoning_thinking) & quick prompt chips
    expect(res.body).toContain('data-testid="reasoning-TumorLocation"');
    expect(res.body).toContain('data-testid="quick-prompt-chips"');
    // Zero raw JSON blocks for MTDCompleted or RadiologicalExams
    expect(res.body).not.toContain('{"is_mtd_complete"');

    // Save a manual edit on Chemotherapy section
    const editRes = await app.inject({
      method: "POST",
      url: "/forms/jeanne_fictive_2026_11_06.pdf/sections/Chemotherapy",
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        "hx-request": "true",
      },
      payload:
        "chemotherapy_name=FOLFIRINOX+modifi%C3%A9+7+cures&chemotherapy_tolerance=Neuropathie+grade+1",
    });
    expect(editRes.statusCode).toBe(200);
    expect(editRes.body).toContain("Modifié manuellement");
    expect(editRes.body).toContain("FOLFIRINOX modifié 7 cures");

    // Rerun TumorBiology while preserving manual edits on Chemotherapy
    const rerunRes = await app.inject({
      method: "POST",
      url: "/forms/jeanne_fictive_2026_11_06.pdf/sections/TumorBiology/rerun",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      payload: "preserve_manual_edits=true",
    });
    expect([200, 302]).toContain(rerunRes.statusCode);

    const checkRes = await app.inject({
      method: "GET",
      url: "/patients/A-1042?expert=true",
    });
    expect(checkRes.body).toContain("Modifié manuellement");
    expect(checkRes.body).toContain("FOLFIRINOX modifié 7 cures");
    // Expert mode shows user prompt, AI vs Human trace, and Chunks
    expect(checkRes.body).toContain('data-testid="prompt-TumorLocation"');
    expect(checkRes.body).toContain('data-testid="trace-Chemotherapy"');
    expect(checkRes.body).toContain("Chunk #1");
    await app.close();
  });

  it("POST /patients/:patientId/chat answers clinical questions with citations", async () => {
    const { app } = await createTestApp();
    const chatRes = await app.inject({
      method: "POST",
      url: "/patients/A-1042/chat",
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        "hx-request": "true",
      },
      payload: "question=Evolution+du+CA+19-9",
    });
    expect(chatRes.statusCode).toBe(200);
    expect(chatRes.body).toContain("412 U/mL");
    expect(chatRes.body).toContain("TNCD Pancréas §4.2");
    await app.close();
  });

  it("GET /guidelines, GET /agents, and POST /guidelines/chat display TNCD/PNDS resources, dedicated agents page with prompts, and RAG answers", async () => {
    const { app } = await createTestApp();
    const res = await app.inject({ method: "GET", url: "/guidelines" });
    expect(res.statusCode).toBe(200);
    expect(res.body).toContain("TNCD_Pancreas_2026.pdf");
    expect(res.body).toContain('data-testid="btn_goto_agents"');

    const agentsRes = await app.inject({ method: "GET", url: "/agents" });
    expect(agentsRes.statusCode).toBe(200);
    expect(agentsRes.body).toContain('data-testid="agents-list"');
    expect(agentsRes.body).toContain("Prompts utilisateurs d'extraction");
    expect(agentsRes.body).toContain("Instructions système de l'agent");

    const chatRes = await app.inject({
      method: "POST",
      url: "/guidelines/chat",
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        "hx-request": "true",
      },
      payload: "question=2e+ligne+apr%C3%A8s+FOLFIRINOX",
    });
    expect(chatRes.statusCode).toBe(200);
    expect(chatRes.body).toContain("gemcitabine");
    expect(chatRes.body).toContain("TNCD_Pancreas_2026.pdf");
    await app.close();
  });

  it("GET /feedback and POST /feedback manage bug reports", async () => {
    const { app } = await createTestApp();
    const getRes = await app.inject({ method: "GET", url: "/feedback" });
    expect(getRes.statusCode).toBe(200);
    expect(getRes.body).toContain("BUG-101");

    const postRes = await app.inject({
      method: "POST",
      url: "/feedback",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      payload:
        "title=Anomalie+affichage+date&description=La+date+RCP+est+vide&category=ui&severity=low&patientOrFile=%23A-1042",
    });
    expect([200, 302]).toContain(postRes.statusCode);

    const afterRes = await app.inject({ method: "GET", url: "/feedback" });
    expect(afterRes.body).toContain("Anomalie affichage date");
    await app.close();
  });

  it("GET /admin/queue and POST /admin/queue/* supervise jobs and locks", async () => {
    const { app } = await createTestApp();
    const res = await app.inject({ method: "GET", url: "/admin/queue" });
    expect(res.statusCode).toBe(200);
    expect(res.body).toContain("job-running-1042");
    expect(res.body).toContain("job-failed-1039");

    const retryRes = await app.inject({
      method: "POST",
      url: "/admin/queue/jobs/job-failed-1039/retry",
    });
    expect([200, 302]).toContain(retryRes.statusCode);

    const lockRes = await app.inject({
      method: "POST",
      url: "/admin/queue/locks/release",
    });
    expect([200, 302]).toContain(lockRes.statusCode);
    await app.close();
  });

  it("GET /files/forms/:filename/pdf and GET /files/resources/:filename serve inline PDFs", async () => {
    const { app } = await createTestApp();
    const formPdf = await app.inject({
      method: "GET",
      url: "/files/forms/jeanne_fictive_2026_11_06.pdf/pdf",
    });
    expect(formPdf.statusCode).toBe(200);
    expect(formPdf.headers["content-type"]).toContain("application/pdf");
    expect(formPdf.headers["content-disposition"]).toContain("inline");

    const resPdf = await app.inject({
      method: "GET",
      url: "/files/resources/TNCD_Pancreas_2026.pdf",
    });
    expect(resPdf.statusCode).toBe(200);
    expect(resPdf.headers["content-type"]).toContain("application/pdf");
    expect(resPdf.headers["x-frame-options"]).toBe("SAMEORIGIN");
    await app.close();
  });

  it("enforces Zero-Trust proxy secret in oauth_proxy mode, blocks open redirects, and blocks path traversal", async () => {
    expect(verifyProxySecret("secret-123", "secret-123")).toBe(true);
    expect(verifyProxySecret("wrong", "secret-123")).toBe(false);
    expect(verifyProxySecret(undefined, "secret-123")).toBe(false);

    expect(sanitizeLocalRedirect("https://evil.example.com/phish", "/worklist")).toBe("/phish");
    expect(sanitizeLocalRedirect("//evil.example.com", "/worklist")).toBe("/worklist");
    expect(sanitizeLocalRedirect("/\\evil.example.com", "/worklist")).toBe("/worklist");
    expect(sanitizeLocalRedirect("/patients/A-1042?domain=oncology", "/worklist")).toBe(
      "/patients/A-1042?domain=oncology",
    );

    expect(isSafeFilename("jeanne_fictive_2026_11_06.pdf")).toBe(true);
    expect(isSafeFilename("../etc/passwd")).toBe(false);
    expect(isSafeFilename("sub/file.pdf")).toBe(false);

    const api = new InMemoryOncoflowApiFake();
    const config = loadConfig({
      PORT_WEB: "0",
      APP_DEV_MODE: "false",
      APP_AUTH_MODE: "oauth_proxy",
      APP_PROXY_SECRET: "top-secret-proxy-key",
      APP_API_TOKEN: "top-secret-api-token",
      APP_ADMIN_USERS: "dr.admin",
    });
    expect(config.useFakeApiFallback).toBe(false);
    const app = await buildServer({ config, api });

    // Health endpoint remains accessible for Docker HEALTHCHECK
    const healthRes = await app.inject({ method: "GET", url: "/health" });
    expect(healthRes.statusCode).toBe(200);

    // Unauthenticated request without X-Oncoflow-Proxy-Secret is rejected with 403
    const deniedRes = await app.inject({ method: "GET", url: "/worklist" });
    expect(deniedRes.statusCode).toBe(403);

    // Authenticated request with valid X-Oncoflow-Proxy-Secret + OAuth2-Proxy user header succeeds
    const allowedRes = await app.inject({
      method: "GET",
      url: "/worklist",
      headers: {
        "x-oncoflow-proxy-secret": "top-secret-proxy-key",
        "x-auth-request-preferred-username": "dr.martin",
        "x-auth-request-email": "dr.martin@chu-exemple.fr",
      },
    });
    expect(allowedRes.statusCode).toBe(200);
    expect(allowedRes.headers["x-content-type-options"]).toBe("nosniff");
    expect(allowedRes.headers["x-frame-options"]).toBe("DENY");
    expect(allowedRes.body).toContain("dr.martin@chu-exemple.fr");

    // Non-admin user is denied queue mutation (403)
    const nonAdminQueueRes = await app.inject({
      method: "POST",
      url: "/admin/queue/locks/release",
      headers: {
        "x-oncoflow-proxy-secret": "top-secret-proxy-key",
        "x-auth-request-preferred-username": "dr.martin",
      },
    });
    expect(nonAdminQueueRes.statusCode).toBe(403);

    // Admin user is allowed queue mutation
    const adminQueueRes = await app.inject({
      method: "POST",
      url: "/admin/queue/locks/release",
      headers: {
        "x-oncoflow-proxy-secret": "top-secret-proxy-key",
        "x-auth-request-preferred-username": "dr.admin",
      },
    });
    expect(adminQueueRes.statusCode).toBe(302);

    // sma-new subdomain automatically resolves to the SMA clinical domain
    const smaNewRes = await app.inject({
      method: "GET",
      url: "/worklist",
      headers: {
        host: "sma-new.meddatasyntis.bricks-it.fr",
        "x-oncoflow-proxy-secret": "top-secret-proxy-key",
        "x-auth-request-preferred-username": "dr.martin",
      },
    });
    expect(smaNewRes.statusCode).toBe(200);
    expect(smaNewRes.body).toContain("Amyotrophie spinale");

    // oncologic-new subdomain automatically resolves to the Oncology clinical domain
    const oncoNewRes = await app.inject({
      method: "GET",
      url: "/worklist",
      headers: {
        host: "oncologic-new.meddatasyntis.bricks-it.fr",
        "x-oncoflow-proxy-secret": "top-secret-proxy-key",
        "x-auth-request-preferred-username": "dr.martin",
      },
    });
    expect(oncoNewRes.statusCode).toBe(200);
    expect(oncoNewRes.body).toContain("Oncologie");

    await app.close();
  });
});
