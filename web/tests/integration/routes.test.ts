import { describe, expect, it } from "vitest";
import { loadConfig } from "../../src/config.js";
import { InMemoryOncoflowApiFake } from "../../src/infrastructure/api/in-memory-oncoflow-api.fake.js";
import {
  renderChatLogMessagePartial,
  renderSafeMarkdown,
} from "../../src/ui/components/ai-chat.component.js";
import {
  buildServer,
  isSafeFilename,
  sanitizeLocalRedirect,
  verifyProxySecret,
} from "../../src/ui/server.js";
import { html, raw } from "../../src/ui/templates.js";

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
    expect(res.body).toContain('data-theme-pref="auto"');
    expect(res.body).toContain('data-testid="theme-selector"');
    expect(res.body).toContain('data-testid="btn_theme_auto"');
    expect(res.body).toContain('data-testid="btn_theme_light"');
    expect(res.body).toContain('data-testid="btn_theme_dark"');
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

    // Mobile User-Agent defaults to Cards view on /worklist when display is not explicitly passed
    const mobileCardsRes = await app.inject({
      method: "GET",
      url: "/worklist",
      headers: {
        "user-agent":
          "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
      },
    });
    expect(mobileCardsRes.statusCode).toBe(200);
    expect(mobileCardsRes.body).toContain('<option value="cards" selected>');
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
    // Collapsible RCP timeline drawer with label
    expect(res.body).toContain('data-testid="timeline-drawer"');
    expect(res.body).toContain("Frise chronologique RCP");
    // Missing items interactive list visible inside MTDCompleted
    expect(res.body).toContain('data-testid="missing-items-panel"');
    expect(res.body).toContain('data-testid="missing-items-list"');
    // PatientMDTFormCheck hidden outside expert mode
    expect(res.body).not.toContain('data-testid="section-PatientMDTFormCheck"');
    // Zero raw JSON blocks for MTDCompleted or RadiologicalExams
    expect(res.body).not.toContain('{"is_mtd_complete"');

    // Toggle individual missing item visibility
    const toggleMissingRes = await app.inject({
      method: "POST",
      url: "/forms/jeanne_fictive_2026_11_06.pdf/missing-items?domain=oncology",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      payload: "toggle_item=Compte+rendu+d%27anatomopathologie+définitif+%28biopsie+EUS%29",
    });
    expect([200, 302]).toContain(toggleMissingRes.statusCode);

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
    expect(agentsRes.body).toContain('data-testid="agents-group-coordination"');
    expect(agentsRes.body).toContain('data-testid="agents-group-experts"');
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
    expect(res.body).toContain(
      'data-href="/resolve?target=jeanne_fictive_2026_11_06.pdf&domain=oncology"',
    );
    expect(res.body).toContain('data-testid="drawer-job-job-running-1042"');

    const resolveKnown = await app.inject({
      method: "GET",
      url: "/resolve?target=jeanne_fictive_2026_11_06.pdf&domain=oncology",
    });
    expect(resolveKnown.statusCode).toBe(302);
    expect(resolveKnown.headers.location).toContain("/patients/A-1042");

    const resolvePending = await app.inject({
      method: "GET",
      url: "/resolve?target=courrier_scan_illisible_1039.pdf&domain=oncology",
    });
    expect(resolvePending.statusCode).toBe(302);
    expect(resolvePending.headers.location).toContain("/admin/queue?domain=oncology");

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

    const cleanRes = await app.inject({
      method: "POST",
      url: "/admin/queue/clean",
    });
    expect([200, 302]).toContain(cleanRes.statusCode);
    await app.close();
  });

  it("GET /ingest and POST /preferences persist theme, language, and expertMode cookies", async () => {
    const { app } = await createTestApp();
    const ingestRes = await app.inject({ method: "GET", url: "/ingest?domain=oncology" });
    expect(ingestRes.statusCode).toBe(200);
    expect(ingestRes.body).toContain('data-testid="input-ingest-files"');
    expect(ingestRes.body).toContain('data-testid="btn_ingest_submit"');

    const prefRes = await app.inject({
      method: "POST",
      url: "/preferences",
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        referer: "/worklist?domain=oncology",
      },
      payload: "theme=dark&language=en&expertMode=true",
    });
    expect(prefRes.statusCode).toBe(302);
    const setCookies = prefRes.headers["set-cookie"];
    const cookieStr = Array.isArray(setCookies) ? setCookies.join("; ") : String(setCookies ?? "");
    expect(cookieStr).toContain("ds_theme=dark");
    expect(cookieStr).toContain("ds_lang=en");
    expect(cookieStr).toContain("ds_expert=true");
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

    const citationPdf = await app.inject({
      method: "GET",
      url: "/files/resources/TNCD%20Pancr%C3%A9as%20%C2%A74.2?domain=oncology",
    });
    expect(citationPdf.statusCode).toBe(200);
    expect(citationPdf.headers["content-type"]).toContain("application/pdf");

    const pdfJsMod = await app.inject({
      method: "GET",
      url: "/public/vendor/pdfjs/pdf.mjs",
    });
    expect(pdfJsMod.statusCode).toBe(200);
    expect(pdfJsMod.headers["content-type"]).toContain("application/javascript");

    const pdfWorkerMod = await app.inject({
      method: "GET",
      url: "/public/vendor/pdfjs/pdf.worker.mjs",
    });
    expect(pdfWorkerMod.statusCode).toBe(200);
    expect(pdfWorkerMod.headers["content-type"]).toContain("application/javascript");
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

    // sma.<domain> subdomain automatically resolves to the SMA clinical domain and omits ?domain= query strings
    const smaRes = await app.inject({
      method: "GET",
      url: "/worklist",
      headers: {
        host: "sma.meddatasyntis.bricks-it.fr",
        "x-oncoflow-proxy-secret": "top-secret-proxy-key",
        "x-auth-request-preferred-username": "dr.martin",
      },
    });
    expect(smaRes.statusCode).toBe(200);
    expect(smaRes.body).toContain("Amyotrophie spinale");
    expect(smaRes.body).not.toContain("domain=sma");
    expect(smaRes.body).not.toContain('name="domain"');

    // oncologic.<domain> subdomain automatically resolves to the Oncology clinical domain and omits ?domain= query strings
    const oncoRes = await app.inject({
      method: "GET",
      url: "/worklist",
      headers: {
        host: "oncologic.meddatasyntis.bricks-it.fr",
        "x-oncoflow-proxy-secret": "top-secret-proxy-key",
        "x-auth-request-preferred-username": "dr.martin",
      },
    });
    expect(oncoRes.statusCode).toBe(200);
    expect(oncoRes.body).toContain("Oncologie");
    expect(oncoRes.body).not.toContain("domain=oncology");
    expect(oncoRes.body).not.toContain('name="domain"');

    // Redundant ?domain= query parameter on a domain-bound host redirects cleanly without domain=
    const redundantQueryRes = await app.inject({
      method: "GET",
      url: "/worklist?domain=oncology&priority=high",
      headers: {
        host: "oncologic.meddatasyntis.bricks-it.fr",
        "x-oncoflow-proxy-secret": "top-secret-proxy-key",
        "x-auth-request-preferred-username": "dr.martin",
      },
    });
    expect(redundantQueryRes.statusCode).toBe(302);
    expect(redundantQueryRes.headers.location).toBe("/worklist?priority=high");

    // 404 Not Found page with link back to index
    const notFoundRes = await app.inject({
      method: "GET",
      url: "/unknown-route-xyz",
      headers: {
        host: "oncologic.meddatasyntis.bricks-it.fr",
        "x-oncoflow-proxy-secret": "top-secret-proxy-key",
        "x-auth-request-preferred-username": "dr.martin",
      },
    });
    expect(notFoundRes.statusCode).toBe(404);
    expect(notFoundRes.body).toContain('data-testid="status-page-404"');
    expect(notFoundRes.body).toContain('href="/worklist"');

    // 503 Maintenance page with link back to index and retry action
    const maintenanceRes = await app.inject({
      method: "GET",
      url: "/maintenance",
      headers: {
        host: "sma.meddatasyntis.bricks-it.fr",
        "x-oncoflow-proxy-secret": "top-secret-proxy-key",
        "x-auth-request-preferred-username": "dr.martin",
      },
    });
    expect(maintenanceRes.statusCode).toBe(503);
    expect(maintenanceRes.body).toContain('data-testid="status-page-503"');
    expect(maintenanceRes.body).toContain('data-testid="btn_status_home"');
    expect(maintenanceRes.body).toContain('data-testid="btn_status_retry"');

    await app.close();
  });

  it("renders Markdown safely via marked inside AI chat assistant replies", () => {
    const markdown = [
      "## Synthèse clinique",
      "Le patient présente un **adénocarcinome** avec mutation `KRAS`.",
      "",
      "- Stade : *cT3N1M0*",
      "- Traitement : FOLFOX",
      "",
      "<script>alert(1)</script>",
    ].join("\n");

    const html = renderSafeMarkdown(markdown);
    expect(html).toContain("<h2>Synthèse clinique</h2>");
    expect(html).toContain("<strong>adénocarcinome</strong>");
    expect(html).toContain("<code>KRAS</code>");
    expect(html).toContain("<ul>");
    expect(html).toContain("<em>cT3N1M0</em>");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");

    const partial = renderChatLogMessagePartial("Quel bilan ?", {
      answer: "**Conclusion** : discuter en RCP.",
      references: [],
    });
    expect(partial).toContain('class="ds-chat__markdown"');
    expect(partial).toContain("<strong>Conclusion</strong>");
  });

  it("auto-escapes XSS in html tagged templates, supports HTTP Range (206) & ETag (304) on PDFs/assets, and emits SSE retry directives", async () => {
    const untrusted = '<img src=x onerror="alert(1)">';
    const trusted = "<strong>Validé</strong>";
    const rendered = html`<div data-date="${"2026-11-06T00:00:00Z"}">${untrusted} ${raw(trusted)}</div>`;
    expect(rendered).toBe(
      '<div data-date="06/11/2026">&lt;img src=x onerror=&quot;alert(1)&quot;&gt; <strong>Validé</strong></div>',
    );

    const { app } = await createTestApp();

    // 1. Static asset ETag + 304 Not Modified
    const assetRes = await app.inject({ method: "GET", url: "/public/css/tokens.css" });
    expect(assetRes.statusCode).toBe(200);
    const assetEtag = assetRes.headers.etag;
    expect(assetEtag).toBeTruthy();

    const assetCached = await app.inject({
      method: "GET",
      url: "/public/css/tokens.css",
      headers: { "if-none-match": String(assetEtag) },
    });
    expect(assetCached.statusCode).toBe(304);

    // 2. PDF Byte-Range (206 Partial Content) + ETag (304 Not Modified)
    const rangeRes = await app.inject({
      method: "GET",
      url: "/files/forms/jeanne_fictive_2026_11_06.pdf/pdf",
      headers: { range: "bytes=0-4" },
    });
    expect(rangeRes.statusCode).toBe(206);
    expect(rangeRes.headers["accept-ranges"]).toBe("bytes");
    expect(rangeRes.headers["content-range"]).toMatch(/^bytes 0-4\/\d+$/);
    expect(rangeRes.rawPayload.byteLength).toBe(5);

    const pdfEtag = rangeRes.headers.etag;
    const pdfNotModified = await app.inject({
      method: "GET",
      url: "/files/forms/jeanne_fictive_2026_11_06.pdf/pdf",
      headers: { "if-none-match": String(pdfEtag) },
    });
    expect(pdfNotModified.statusCode).toBe(304);

    // 3. SSE /events/queue includes adaptive retry directive
    const sseRes = await app.inject({ method: "GET", url: "/events/queue" });
    expect(sseRes.statusCode).toBe(200);
    expect(sseRes.headers["content-type"]).toContain("text/event-stream");
    expect(sseRes.body).toContain("retry: 3000\nevent: banner\ndata: ");

    await app.close();
  });
});
