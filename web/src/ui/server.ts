import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import fastifyCookie from "@fastify/cookie";
import fastifyFormbody from "@fastify/formbody";
import fastifyMultipart from "@fastify/multipart";
import Fastify, { type FastifyInstance, type FastifyRequest } from "fastify";
import type { OncoflowApiPort } from "../application/ports/oncoflow-api.port.js";
import { FeedbackUseCase } from "../application/use-cases/feedback.use-case.js";
import { GuidelinesUseCase } from "../application/use-cases/guidelines.use-case.js";
import { IngestUseCase } from "../application/use-cases/ingest.use-case.js";
import { PatientDossierUseCase } from "../application/use-cases/patient-dossier.use-case.js";
import { QueueAdminUseCase } from "../application/use-cases/queue-admin.use-case.js";
import { WorklistUseCase } from "../application/use-cases/worklist.use-case.js";
import type { WebAppConfig } from "../config.js";
import type {
  ClinicalDomain,
  Language,
  ThemeMode,
  UserSession,
  WorklistFilter,
} from "../domain/types.js";
import {
  renderAgentsPage,
  renderChatLogMessagePartial,
  renderDossierPage,
  renderFeedbackPage,
  renderGuidelinesPage,
  renderIngestPage,
  renderQueueAdminPage,
  renderQueueBannerPartial,
  renderSectionDetailsPartial,
  renderWorklistPage,
} from "./templates.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = path.resolve(__dirname, "../../public");
const STYLEGUIDE_PATH = path.resolve(__dirname, "../../styleguide/index.html");

const SAFE_IDENTIFIER_RE = /^[a-zA-Z0-9._\-\s()[\]+@]+$/;

export function verifyProxySecret(provided: string | undefined, expected: string): boolean {
  if (!provided || !expected) return false;
  const a = crypto.createHash("sha256").update(provided, "utf8").digest();
  const b = crypto.createHash("sha256").update(expected, "utf8").digest();
  return crypto.timingSafeEqual(a, b);
}

export function sanitizeLocalRedirect(
  rawReferer: string | undefined,
  fallback = "/worklist",
): string {
  if (!rawReferer) return fallback;
  try {
    if (rawReferer.startsWith("/")) {
      if (rawReferer.startsWith("//") || rawReferer.startsWith("/\\")) return fallback;
      return rawReferer;
    }
    const parsed = new URL(rawReferer);
    const candidate = `${parsed.pathname}${parsed.search}${parsed.hash}`;
    if (!candidate.startsWith("/") || candidate.startsWith("//") || candidate.startsWith("/\\")) {
      return fallback;
    }
    return candidate;
  } catch {
    return fallback;
  }
}

export function isSafeFilename(name: string): boolean {
  if (!name || name.length > 255) return false;
  if (name.includes("..") || name.includes("/") || name.includes("\\") || name.includes("\0")) {
    return false;
  }
  return SAFE_IDENTIFIER_RE.test(name);
}

export function sanitizeContentDispositionFilename(name: string): string {
  return path.basename(name).replace(/["\\\r\n\0]/g, "_");
}

const PUBLIC_MIME_TYPES: Record<string, string> = {
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".svg": "image/svg+xml; charset=utf-8",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".json": "application/json; charset=utf-8",
  ".woff2": "font/woff2",
};

export interface BuildServerOptions {
  config: WebAppConfig;
  api: OncoflowApiPort;
}

export async function buildServer({ config, api }: BuildServerOptions): Promise<FastifyInstance> {
  const app = Fastify({ logger: false });

  await app.register(fastifyCookie);
  await app.register(fastifyFormbody);
  await app.register(fastifyMultipart, {
    limits: {
      fileSize: 52_428_800, // 50 MB
      files: 20,
    },
  });

  // Hardened canonical static asset server for /public/* (zero external glob/send attack surface)
  app.get("/public/*", async (req, reply) => {
    const wildcard = ((req.params as Record<string, string>)["*"] ?? "").replace(/^\/+/, "");
    if (!wildcard || wildcard.includes("\0") || wildcard.includes("..")) {
      return reply.code(400).send("Chemin statique invalide");
    }
    const resolved = path.resolve(PUBLIC_DIR, wildcard);
    if (!resolved.startsWith(`${PUBLIC_DIR}${path.sep}`)) {
      return reply.code(403).send("Accès interdit");
    }
    const ext = path.extname(resolved).toLowerCase();
    const mime = PUBLIC_MIME_TYPES[ext];
    if (!mime || !fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
      return reply.code(404).send("Ressource statique introuvable");
    }
    reply.header("Content-Type", mime);
    reply.header("Cache-Control", "no-store, max-age=0");
    return reply.send(fs.readFileSync(resolved));
  });

  // Zero-Trust Proxy Secret Verification when running behind Caddy + OAuth2-Proxy
  app.addHook("onRequest", async (req, reply) => {
    if (req.url === "/health" || req.url.startsWith("/public/")) {
      return;
    }
    if (config.authMode === "oauth_proxy") {
      const providedSecret =
        (req.headers["x-oncoflow-proxy-secret"] as string | undefined) ||
        (req.headers["x-proxy-secret"] as string | undefined);
      if (!verifyProxySecret(providedSecret, config.proxySecret)) {
        return reply
          .code(403)
          .type("text/plain; charset=utf-8")
          .send("Accès refusé : secret proxy invalide.");
      }
    }
  });

  // Strict Hospital-Grade HTTP Security Headers (100% self-hosted)
  app.addHook("onSend", async (req, reply, payload) => {
    const isStyleguide = req.url.startsWith("/styleguide");
    const isPdfFile = req.url.startsWith("/files/");
    if (!reply.getHeader("content-security-policy")) {
      const scriptSrc = isStyleguide ? "script-src 'self' 'unsafe-inline'" : "script-src 'self'";
      reply.header(
        "Content-Security-Policy",
        `default-src 'self'; style-src 'self' 'unsafe-inline'; ${scriptSrc}; img-src 'self' data:; frame-src 'self'; frame-ancestors 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'`,
      );
    }
    reply.header("X-Content-Type-Options", "nosniff");
    reply.header("X-Frame-Options", isPdfFile ? "SAMEORIGIN" : "DENY");
    reply.header("Referrer-Policy", "same-origin");
    reply.header(
      "Permissions-Policy",
      "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    );
    reply.header("Cross-Origin-Opener-Policy", "same-origin");
    reply.header("Cross-Origin-Resource-Policy", "same-origin");
    if (!req.url.startsWith("/public/") && !reply.getHeader("cache-control")) {
      reply.header("Cache-Control", "no-store, max-age=0");
    }
    return payload;
  });

  const worklistUseCase = new WorklistUseCase(api);
  const dossierUseCase = new PatientDossierUseCase(api);
  const ingestUseCase = new IngestUseCase(api);
  const guidelinesUseCase = new GuidelinesUseCase(api);
  const feedbackUseCase = new FeedbackUseCase(api);
  const queueAdminUseCase = new QueueAdminUseCase(api);

  function detectHostDomain(
    req: FastifyRequest,
    trustProxyHeaders: boolean,
  ): ClinicalDomain | undefined {
    const headerDomain = trustProxyHeaders
      ? (req.headers["x-oncoflow-domain"] as string | undefined)?.trim().toLowerCase()
      : undefined;
    if (headerDomain === "sma" || headerDomain === "oncology") {
      return headerDomain;
    }
    const rawHost =
      String(req.headers.host || "")
        .split(",")[0]
        ?.trim()
        .toLowerCase() ?? "";
    if (
      rawHost.startsWith("sma.") ||
      rawHost.startsWith("sma-new.") ||
      rawHost.startsWith("sma-")
    ) {
      return "sma";
    }
    if (
      rawHost.startsWith("oncologic.") ||
      rawHost.startsWith("oncologic-new.") ||
      rawHost.startsWith("oncology.") ||
      rawHost.startsWith("oncology-")
    ) {
      return "oncology";
    }
    return undefined;
  }

  function resolveSession(req: FastifyRequest): UserSession {
    const query = (req.query ?? {}) as Record<string, string | undefined>;
    const cookies = req.cookies ?? {};

    const providedSecret =
      (req.headers["x-oncoflow-proxy-secret"] as string | undefined) ||
      (req.headers["x-proxy-secret"] as string | undefined);
    const trustIdentityHeaders = config.proxySecret
      ? verifyProxySecret(providedSecret, config.proxySecret)
      : config.devMode !== false;

    const hostDomain = detectHostDomain(req, trustIdentityHeaders);
    const rawDomain = (
      hostDomain ||
      query.domain ||
      cookies.ds_domain ||
      config.defaultDomain
    ).toLowerCase();
    const domain: ClinicalDomain =
      rawDomain === "sma" && config.allowedDomains.includes("sma") ? "sma" : "oncology";

    const rawLang = (query.lang || cookies.ds_lang || config.defaultLanguage).toLowerCase();
    const language: Language = rawLang === "en" ? "en" : "fr";

    const rawTheme = (query.theme || cookies.ds_theme || config.defaultTheme).toLowerCase();
    const theme: ThemeMode = rawTheme === "dark" ? "dark" : "light";

    const expertMode = cookies.ds_expert === "true" || query.expert === "true";

    const headerUser = trustIdentityHeaders
      ? (req.headers["x-auth-request-preferred-username"] as string | undefined) ||
        (req.headers["x-auth-request-user"] as string | undefined) ||
        (req.headers["x-oncoflow-user"] as string | undefined)
      : undefined;
    const headerEmailOrName = trustIdentityHeaders
      ? (req.headers["x-oncoflow-user-name"] as string | undefined) ||
        (req.headers["x-auth-request-email"] as string | undefined) ||
        headerUser
      : undefined;

    const userId = String(headerUser || "dr.local")
      .trim()
      .slice(0, 128);
    const userName = String(headerEmailOrName || "Dr A. Exemple (Local)")
      .trim()
      .slice(0, 128);

    const adminList = config.adminUsers ?? [];
    const isAdmin =
      adminList.length === 0 ||
      adminList.includes(userId.toLowerCase()) ||
      adminList.includes(userName.toLowerCase());

    return {
      userId,
      userName,
      isAdmin,
      domain,
      allowedDomains: config.allowedDomains,
      language,
      theme,
      expertMode,
    };
  }

  async function loadShellQueue(domain: ClinicalDomain) {
    const [queueStats, queueJobs] = await Promise.all([
      api.getQueueStats(domain, true),
      api.listQueueJobs(domain, true),
    ]);
    return { queueStats, queueJobs };
  }

  // 1. Root & Styleguide
  app.get("/", async (_req, reply) => {
    return reply.redirect("/worklist");
  });

  app.get("/health", async () => {
    return { status: "ok", service: "datasyntis-web" };
  });

  app.get("/styleguide", async (_req, reply) => {
    const rawHtml = fs.readFileSync(STYLEGUIDE_PATH, "utf8");
    const servedHtml = rawHtml.replace(/\.\.\/public\//g, "/public/");
    return reply.type("text/html; charset=utf-8").send(servedHtml);
  });

  // 2. Preferences (Theme, Language, Domain, Expert Mode)
  app.post("/preferences", async (req, reply) => {
    const body = (req.body ?? {}) as Record<string, string | undefined>;
    const cookieOpts = {
      path: "/",
      httpOnly: false,
      sameSite: "lax" as const,
      secure: config.devMode === false,
    };

    if (body.theme === "light" || body.theme === "dark") {
      reply.setCookie("ds_theme", body.theme, cookieOpts);
    }
    if (body.language === "fr" || body.language === "en") {
      reply.setCookie("ds_lang", body.language, cookieOpts);
    }
    if (body.domain === "oncology" || body.domain === "sma") {
      reply.setCookie("ds_domain", body.domain, cookieOpts);
    }
    if (body.expertMode === "true" || body.expertMode === "false") {
      reply.setCookie("ds_expert", body.expertMode, cookieOpts);
    }

    if (req.headers["hx-request"] === "true" && body.theme && !body.domain && !body.language) {
      return reply.code(204).send();
    }

    if (body.domain === "oncology" || body.domain === "sma") {
      return reply.redirect(`/worklist?domain=${encodeURIComponent(body.domain)}`);
    }
    return reply.redirect(sanitizeLocalRedirect(req.headers.referer, "/worklist"));
  });

  // 3. Worklist
  app.get("/worklist", async (req, reply) => {
    const session = resolveSession(req);
    const query = (req.query ?? {}) as Record<string, string | undefined>;
    if (query.domain === "oncology" || query.domain === "sma") {
      reply.setCookie("ds_domain", query.domain, {
        path: "/",
        sameSite: "lax",
        secure: config.devMode === false,
      });
    }

    const filter: WorklistFilter = {
      query: query.q,
      completeness:
        query.completeness === "complete" || query.completeness === "incomplete"
          ? query.completeness
          : "all",
      priority:
        query.priority === "high" || query.priority === "medium" || query.priority === "low"
          ? query.priority
          : "all",
      orientation:
        query.orientation === "adapt" ||
        query.orientation === "standard" ||
        query.orientation === "pending"
          ? query.orientation
          : "all",
      viewMode: query.viewMode === "rcp" ? "rcp" : "patients",
      displayMode: query.display === "cards" ? "cards" : "table",
      domain: session.domain,
    };

    const [view, { queueStats, queueJobs }] = await Promise.all([
      worklistUseCase.execute(session.domain, filter),
      loadShellQueue(session.domain),
    ]);

    const html = renderWorklistPage(view, session, queueStats, queueJobs);
    return reply.type("text/html; charset=utf-8").send(html);
  });

  app.post("/patients/:patientId/delete", async (req, reply) => {
    const session = resolveSession(req);
    const { patientId } = req.params as { patientId: string };
    await worklistUseCase.deletePatient(patientId, session.domain);
    return reply.redirect(`/worklist?domain=${encodeURIComponent(session.domain)}`);
  });

  app.delete("/patients/:patientId", async (req, reply) => {
    const session = resolveSession(req);
    const { patientId } = req.params as { patientId: string };
    await worklistUseCase.deletePatient(patientId, session.domain);
    return reply.code(200).send({ deleted: patientId });
  });

  // 4. Ingest & Batch Tracking
  app.get("/ingest", async (req, reply) => {
    const session = resolveSession(req);
    const query = (req.query ?? {}) as Record<string, string | undefined>;
    const [patients, batch, { queueStats, queueJobs }] = await Promise.all([
      ingestUseCase.listExistingPatients(session.domain),
      query.batchId
        ? ingestUseCase.getBatchStatus(query.batchId, session.domain)
        : Promise.resolve(null),
      loadShellQueue(session.domain),
    ]);

    const html = renderIngestPage(
      patients,
      batch,
      session,
      queueStats,
      queueJobs,
      query.patientId ?? null,
    );
    return reply.type("text/html; charset=utf-8").send(html);
  });

  app.post("/ingest/upload", async (req, reply) => {
    const session = resolveSession(req);
    const files: Array<{ filename: string; content: Buffer; patientId?: string | null }> = [];
    let patientId: string | null = null;

    if (req.isMultipart()) {
      for await (const part of req.parts()) {
        if (part.type === "file") {
          const buf = await part.toBuffer();
          const cleanName = path.basename(part.filename || "");
          if (cleanName.toLowerCase().endsWith(".pdf") && isSafeFilename(cleanName)) {
            files.push({ filename: cleanName, content: buf });
          }
        } else if (part.fieldname === "patientId" && typeof part.value === "string") {
          patientId = part.value.trim() || null;
        }
      }
    }

    for (const f of files) {
      f.patientId = patientId;
    }

    const res = await ingestUseCase.uploadBatch(files, session.domain);
    return reply.redirect(
      `/ingest?domain=${encodeURIComponent(session.domain)}&batchId=${encodeURIComponent(res.batchId)}`,
    );
  });

  app.get("/ingest/batches/:batchId", async (req, reply) => {
    const session = resolveSession(req);
    const { batchId } = req.params as { batchId: string };
    const status = await ingestUseCase.getBatchStatus(batchId, session.domain);
    return reply.send(status);
  });

  // 5. Patient Dossier & RCP Forms
  app.get("/resolve", async (req, reply) => {
    const session = resolveSession(req);
    const query = (req.query ?? {}) as Record<string, string | undefined>;
    const target = query.target ?? "";
    const resolved = await api.resolveTarget(target, session.domain);
    if (resolved.patientId) {
      return reply.redirect(
        `/patients/${encodeURIComponent(resolved.patientId)}?domain=${encodeURIComponent(session.domain)}`,
      );
    }
    return reply.redirect(
      `/forms/${encodeURIComponent(resolved.filename ?? target)}?domain=${encodeURIComponent(session.domain)}`,
    );
  });

  app.get("/patients/:patientId", async (req, reply) => {
    const session = resolveSession(req);
    const { patientId } = req.params as { patientId: string };
    const query = (req.query ?? {}) as Record<string, string | undefined>;

    const [dossier, { queueStats, queueJobs }] = await Promise.all([
      dossierUseCase.getDossier(patientId, session.domain, session.language, query.file),
      loadShellQueue(session.domain),
    ]);
    if (!dossier) {
      return reply.code(404).type("text/html; charset=utf-8").send("<h1>Dossier introuvable</h1>");
    }

    const html = renderDossierPage(dossier, session, queueStats, queueJobs, [], query.editSection);
    return reply.type("text/html; charset=utf-8").send(html);
  });

  app.get("/forms/:filename", async (req, reply) => {
    const session = resolveSession(req);
    const { filename } = req.params as { filename: string };
    const query = (req.query ?? {}) as Record<string, string | undefined>;

    const [dossier, { queueStats, queueJobs }] = await Promise.all([
      dossierUseCase.getDossier(filename, session.domain, session.language, filename),
      loadShellQueue(session.domain),
    ]);
    if (!dossier) {
      return reply
        .code(404)
        .type("text/html; charset=utf-8")
        .send("<h1>Fiche RCP introuvable</h1>");
    }

    const html = renderDossierPage(dossier, session, queueStats, queueJobs, [], query.editSection);
    return reply.type("text/html; charset=utf-8").send(html);
  });

  app.get("/forms/:filename/sections/:section/edit", async (req, reply) => {
    const session = resolveSession(req);
    const { filename, section } = req.params as { filename: string; section: string };
    const dossier = await dossierUseCase.getDossier(
      filename,
      session.domain,
      session.language,
      filename,
    );
    const secView = dossier?.sections.find((s) => s.name === section);
    if (!dossier || !secView) {
      return reply.code(404).send("Rubrique introuvable");
    }

    if (req.headers["hx-request"] === "true") {
      return reply
        .type("text/html; charset=utf-8")
        .send(
          renderSectionDetailsPartial(secView, filename, session.domain, true, session.expertMode),
        );
    }

    const { queueStats, queueJobs } = await loadShellQueue(session.domain);
    const html = renderDossierPage(dossier, session, queueStats, queueJobs, [], section);
    return reply.type("text/html; charset=utf-8").send(html);
  });

  app.post("/forms/:filename/sections/:section", async (req, reply) => {
    const session = resolveSession(req);
    const { filename, section } = req.params as { filename: string; section: string };
    const body = (req.body ?? {}) as Record<string, unknown>;

    await dossierUseCase.updateSection(filename, section, body, session.userName, session.domain);

    const dossier = await dossierUseCase.getDossier(
      filename,
      session.domain,
      session.language,
      filename,
    );
    const secView = dossier?.sections.find((s) => s.name === section);

    if (req.headers["hx-request"] === "true" && secView) {
      return reply
        .type("text/html; charset=utf-8")
        .send(
          renderSectionDetailsPartial(secView, filename, session.domain, false, session.expertMode),
        );
    }

    const targetUrl = dossier?.patientId
      ? `/patients/${encodeURIComponent(dossier.patientId)}?file=${encodeURIComponent(filename)}&domain=${encodeURIComponent(session.domain)}#section-${encodeURIComponent(section)}`
      : `/forms/${encodeURIComponent(filename)}?domain=${encodeURIComponent(session.domain)}#section-${encodeURIComponent(section)}`;
    return reply.redirect(targetUrl);
  });

  app.post("/forms/:filename/sections/:section/rerun", async (req, reply) => {
    const session = resolveSession(req);
    const { filename, section } = req.params as { filename: string; section: string };
    const body = (req.body ?? {}) as Record<string, string | undefined>;
    const preserve = body.preserve_manual_edits !== "false";

    await dossierUseCase.rerunSection(filename, section, preserve, session.domain);
    return reply.redirect(
      `/forms/${encodeURIComponent(filename)}?domain=${encodeURIComponent(session.domain)}#section-${encodeURIComponent(section)}`,
    );
  });

  app.post("/forms/:filename/process", async (req, reply) => {
    const session = resolveSession(req);
    const { filename } = req.params as { filename: string };
    const body = (req.body ?? {}) as Record<string, string | undefined>;
    const preserve = body.preserve_manual_edits !== "false";

    await dossierUseCase.processFullForm(filename, preserve, session.domain);
    return reply.redirect(
      `/forms/${encodeURIComponent(filename)}?domain=${encodeURIComponent(session.domain)}`,
    );
  });

  app.post("/forms/:filename/link-patient", async (req, reply) => {
    const session = resolveSession(req);
    const { filename } = req.params as { filename: string };
    const body = (req.body ?? {}) as Record<string, string | undefined>;
    const patientId = (body.patientId ?? "").trim() || null;

    await dossierUseCase.linkPatient(filename, patientId, session.domain);
    if (patientId) {
      return reply.redirect(
        `/patients/${encodeURIComponent(patientId)}?domain=${encodeURIComponent(session.domain)}`,
      );
    }
    return reply.redirect(
      `/forms/${encodeURIComponent(filename)}?domain=${encodeURIComponent(session.domain)}`,
    );
  });

  app.post("/patients/:patientId/chat", async (req, reply) => {
    const session = resolveSession(req);
    const { patientId } = req.params as { patientId: string };
    const body = (req.body ?? {}) as Record<string, string | undefined>;
    const question = (body.question ?? "").trim();
    const scope = body.scope === "form" ? "form" : "patient";
    const target =
      scope === "form" && body.filename
        ? { filename: body.filename }
        : { patientId, filename: body.filename };

    const chatReply = await dossierUseCase.askQuestion(
      target,
      question,
      session.domain,
      session.language,
      body.agentName || undefined,
    );

    if (req.headers["hx-request"] === "true") {
      return reply
        .type("text/html; charset=utf-8")
        .send(renderChatLogMessagePartial(question, chatReply));
    }

    const [dossier, { queueStats, queueJobs }] = await Promise.all([
      dossierUseCase.getDossier(patientId, session.domain, session.language, body.filename),
      loadShellQueue(session.domain),
    ]);
    if (!dossier) return reply.redirect(`/worklist?domain=${encodeURIComponent(session.domain)}`);
    return reply
      .type("text/html; charset=utf-8")
      .send(
        renderDossierPage(dossier, session, queueStats, queueJobs, [
          { question, reply: chatReply },
        ]),
      );
  });

  app.post("/forms/:filename/chat", async (req, reply) => {
    const session = resolveSession(req);
    const { filename } = req.params as { filename: string };
    const body = (req.body ?? {}) as Record<string, string | undefined>;
    const question = (body.question ?? "").trim();

    const chatReply = await dossierUseCase.askQuestion(
      { filename },
      question,
      session.domain,
      session.language,
      body.agentName || undefined,
    );

    if (req.headers["hx-request"] === "true") {
      return reply
        .type("text/html; charset=utf-8")
        .send(renderChatLogMessagePartial(question, chatReply));
    }

    const [dossier, { queueStats, queueJobs }] = await Promise.all([
      dossierUseCase.getDossier(filename, session.domain, session.language, filename),
      loadShellQueue(session.domain),
    ]);
    if (!dossier) return reply.redirect(`/worklist?domain=${encodeURIComponent(session.domain)}`);
    return reply
      .type("text/html; charset=utf-8")
      .send(
        renderDossierPage(dossier, session, queueStats, queueJobs, [
          { question, reply: chatReply },
        ]),
      );
  });

  // 6. Same-Origin PDF Streaming (Forms & Guidelines)
  app.get("/files/forms/:filename/pdf", async (req, reply) => {
    const session = resolveSession(req);
    const { filename } = req.params as { filename: string };
    if (!isSafeFilename(filename)) {
      return reply.code(400).send("Nom de fichier invalide");
    }
    const query = (req.query ?? {}) as Record<string, string | undefined>;
    const variant = query.variant === "bbox" ? "bbox" : "plain";
    const buf = await api.getFormPdfBuffer(filename, session.domain, variant);
    if (!buf) {
      return reply.code(404).send("PDF introuvable");
    }
    reply.header("Content-Type", "application/pdf");
    reply.header(
      "Content-Disposition",
      `inline; filename="${sanitizeContentDispositionFilename(filename)}"`,
    );
    return reply.send(buf);
  });

  app.get("/files/resources/:filename", async (req, reply) => {
    const session = resolveSession(req);
    const { filename } = req.params as { filename: string };
    if (!isSafeFilename(filename)) {
      return reply.code(400).send("Nom de fichier invalide");
    }
    const buf = await api.getResourcePdfBuffer(filename, session.domain);
    if (!buf) {
      return reply.code(404).send("Référentiel PDF introuvable");
    }
    reply.header("Content-Type", "application/pdf");
    reply.header(
      "Content-Disposition",
      `inline; filename="${sanitizeContentDispositionFilename(filename)}"`,
    );
    return reply.send(buf);
  });

  // 7. Guidelines & Specialty Agents
  app.get("/guidelines", async (req, reply) => {
    const session = resolveSession(req);
    const query = (req.query ?? {}) as Record<string, string | undefined>;
    const [overview, { queueStats, queueJobs }] = await Promise.all([
      guidelinesUseCase.getOverview(session.domain, session.language, query.file),
      loadShellQueue(session.domain),
    ]);

    const html = renderGuidelinesPage(overview, session, queueStats, queueJobs);
    return reply.type("text/html; charset=utf-8").send(html);
  });

  app.get("/agents", async (req, reply) => {
    const session = resolveSession(req);
    const [agents, resources, { queueStats, queueJobs }] = await Promise.all([
      api.listAgents(session.domain, session.language),
      api.listResources(session.domain),
      loadShellQueue(session.domain),
    ]);
    const html = renderAgentsPage(agents, session, queueStats, queueJobs, resources);
    return reply.type("text/html; charset=utf-8").send(html);
  });

  app.post("/guidelines/upload", async (req, reply) => {
    const session = resolveSession(req);
    if (req.isMultipart()) {
      for await (const part of req.parts()) {
        if (part.type === "file" && part.filename) {
          const cleanName = path.basename(part.filename);
          const buf = await part.toBuffer();
          if (cleanName.toLowerCase().endsWith(".pdf") && isSafeFilename(cleanName)) {
            await guidelinesUseCase.uploadResource(cleanName, buf, session.domain);
          }
        }
      }
    }
    return reply.redirect(`/guidelines?domain=${encodeURIComponent(session.domain)}`);
  });

  app.post("/guidelines/:filename/reindex", async (req, reply) => {
    const session = resolveSession(req);
    const { filename } = req.params as { filename: string };
    if (!isSafeFilename(filename)) {
      return reply.code(400).send("Nom de fichier invalide");
    }
    await guidelinesUseCase.reindexResource(filename, session.domain);
    return reply.redirect(
      `/guidelines?file=${encodeURIComponent(filename)}&domain=${encodeURIComponent(session.domain)}`,
    );
  });

  app.post("/guidelines/chat", async (req, reply) => {
    const session = resolveSession(req);
    const body = (req.body ?? {}) as Record<string, string | undefined>;
    const question = (body.question ?? "").trim();
    const filename = (body.filename ?? "").trim() || undefined;
    const chatReply = await guidelinesUseCase.askGuidelineQuestion(
      question,
      session.domain,
      session.language,
      filename,
    );

    if (req.headers["hx-request"] === "true") {
      return reply
        .type("text/html; charset=utf-8")
        .send(renderChatLogMessagePartial(question, chatReply));
    }

    const [overview, { queueStats, queueJobs }] = await Promise.all([
      guidelinesUseCase.getOverview(session.domain, session.language, filename),
      loadShellQueue(session.domain),
    ]);
    return reply
      .type("text/html; charset=utf-8")
      .send(
        renderGuidelinesPage(overview, session, queueStats, queueJobs, [
          { question, reply: chatReply },
        ]),
      );
  });

  // 8. Feedback & Bug Reports
  app.get("/feedback", async (req, reply) => {
    const session = resolveSession(req);
    const query = (req.query ?? {}) as Record<string, string | undefined>;
    const [bugs, { queueStats, queueJobs }] = await Promise.all([
      feedbackUseCase.listBugs(session.domain, {
        status: query.status,
        category: query.category,
      }),
      loadShellQueue(session.domain),
    ]);

    const html = renderFeedbackPage(bugs, session, queueStats, queueJobs);
    return reply.type("text/html; charset=utf-8").send(html);
  });

  app.post("/feedback", async (req, reply) => {
    const session = resolveSession(req);
    const body = (req.body ?? {}) as Record<string, string | undefined>;
    await feedbackUseCase.createBug({
      title: (body.title ?? "Signalement").trim(),
      description: (body.description ?? "").trim(),
      category: body.category ?? "extraction",
      severity: body.severity ?? "medium",
      domain: session.domain,
      patientOrFile: body.patientOrFile?.trim() || null,
      author: session.userName,
    });
    return reply.redirect(`/feedback?domain=${encodeURIComponent(session.domain)}`);
  });

  app.post("/feedback/:bugId/status", async (req, reply) => {
    const session = resolveSession(req);
    const { bugId } = req.params as { bugId: string };
    const body = (req.body ?? {}) as Record<string, string | undefined>;
    await feedbackUseCase.updateStatus(bugId, body.status ?? "open", session.domain);
    return reply.redirect(`/feedback?domain=${encodeURIComponent(session.domain)}`);
  });

  // 9. Queue Supervision & SSE Stream
  app.get("/admin/queue", async (req, reply) => {
    const session = resolveSession(req);
    const dashboard = await queueAdminUseCase.getDashboard(session.domain, true);
    const html = renderQueueAdminPage(dashboard, session);
    return reply.type("text/html; charset=utf-8").send(html);
  });

  app.post("/admin/queue/jobs/:jobId/retry", async (req, reply) => {
    const session = resolveSession(req);
    if (!session.isAdmin) {
      return reply.code(403).send("Accès réservé aux administrateurs.");
    }
    const { jobId } = req.params as { jobId: string };
    await queueAdminUseCase.retryJob(jobId, session.domain);
    return reply.redirect(`/admin/queue?domain=${encodeURIComponent(session.domain)}`);
  });

  app.post("/admin/queue/jobs/:jobId/delete", async (req, reply) => {
    const session = resolveSession(req);
    if (!session.isAdmin) {
      return reply.code(403).send("Accès réservé aux administrateurs.");
    }
    const { jobId } = req.params as { jobId: string };
    await queueAdminUseCase.cancelOrDeleteJob(jobId, session.domain);
    return reply.redirect(`/admin/queue?domain=${encodeURIComponent(session.domain)}`);
  });

  app.post("/admin/queue/clean", async (req, reply) => {
    const session = resolveSession(req);
    if (!session.isAdmin) {
      return reply.code(403).send("Accès réservé aux administrateurs.");
    }
    const body = (req.body ?? {}) as Record<string, string | undefined>;
    const mode = body.mode === "failed" || body.mode === "all" ? body.mode : ("completed" as const);
    await queueAdminUseCase.cleanQueue(mode, session.domain);
    return reply.redirect(`/admin/queue?domain=${encodeURIComponent(session.domain)}`);
  });

  app.post("/admin/queue/locks/release", async (req, reply) => {
    const session = resolveSession(req);
    if (!session.isAdmin) {
      return reply.code(403).send("Accès réservé aux administrateurs.");
    }
    await queueAdminUseCase.releaseLocks(session.domain);
    return reply.redirect(`/admin/queue?domain=${encodeURIComponent(session.domain)}`);
  });

  app.get("/events/queue", async (req, reply) => {
    const session = resolveSession(req);
    const stats = await api.getQueueStats(session.domain, true);
    const bannerHtml = renderQueueBannerPartial(stats, session).replace(/\n/g, " ");
    reply.header("Content-Type", "text/event-stream; charset=utf-8");
    reply.header("Cache-Control", "no-cache, no-transform");
    reply.header("Connection", "keep-alive");
    return reply.send(`event: banner\ndata: ${bannerHtml}\n\n`);
  });

  return app;
}
