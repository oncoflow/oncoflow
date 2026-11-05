import type { ChatReply } from "../application/ports/oncoflow-api.port.js";
import type { BugListResult } from "../application/use-cases/feedback.use-case.js";
import type { GuidelinesOverview } from "../application/use-cases/guidelines.use-case.js";
import type {
  DossierSectionView,
  PatientDossierView,
} from "../application/use-cases/patient-dossier.use-case.js";
import type { QueueDashboardView } from "../application/use-cases/queue-admin.use-case.js";
import type { WorklistViewResult } from "../application/use-cases/worklist.use-case.js";
import { getAgentPresentation, getDomainQuickPrompts } from "../domain/catalog.js";
import { t } from "../domain/i18n.js";
import {
  deriveCompletenessInfo,
  deriveOrientationInfo,
  derivePriorityBadgeInfo,
} from "../domain/triage.js";
import type {
  AgentModuleInfo,
  BatchStatus,
  ClinicalDomain,
  MdtAgendaView,
  PatientListItem,
  QueueJobItem,
  QueueStats,
  ResourceDocument,
  UserSession,
} from "../domain/types.js";
import {
  renderAiChatComponent,
  renderAiChatDrawer,
  renderAiThinkingModule,
  renderChatLogMessagePartial,
  resolveCitationPdfHref,
} from "./components/ai-chat.component.js";
import {
  INLINE_ICONS_SVG,
  SafeHtml,
  deriveRcpTone,
  esc,
  escapeHtml,
  extractDobFromPatientId,
  formatDurationMinSec,
  formatPatientSubtitle,
  html,
  iconSvg,
  raw,
  stripDomainQuery,
} from "./views/html.js";
import { type StatusPageOptions, renderStatusPage } from "./views/status.view.js";

export {
  SafeHtml,
  type StatusPageOptions,
  deriveRcpTone,
  esc,
  escapeHtml,
  extractDobFromPatientId,
  formatDurationMinSec,
  formatPatientSubtitle,
  html,
  iconSvg,
  raw,
  renderAiChatComponent,
  renderAiChatDrawer,
  renderAiThinkingModule,
  renderChatLogMessagePartial,
  renderStatusPage,
  stripDomainQuery,
};

export interface ShellLayoutOptions {
  title: string;
  activeNav:
    | "worklist"
    | "agenda"
    | "ingest"
    | "guidelines"
    | "agents"
    | "feedback"
    | "queue"
    | "dossier";
  breadcrumbs: Array<{ label: string; href?: string }>;
  session: UserSession;
  queueStats: QueueStats;
  queueJobs: QueueJobItem[];
  bodyHtml: string;
  toastMessage?: string | null;
}

export interface FormProcessingState {
  isProcessing: boolean;
  isFailed: boolean;
  label: string;
  stepLabel: string | null;
  progressPct: number;
}

const ACTIVE_PROCESSING_STATUSES = new Set([
  "PENDING",
  "RUNNING",
  "PROCESSING",
  "IN_PROGRESS",
  "QUEUED",
  "PENDING_ADMIN",
  "PROCESSING_ADMIN",
  "PENDING_CLINICAL",
  "PROCESSING_CLINICAL",
  "PENDING_EXPERTS",
  "PROCESSING_EXPERTS",
]);

export function deriveFormProcessingState(
  processingStatus: string | null | undefined,
  processingStep: string | null | undefined,
  processingProgressPct: number | null | undefined,
  filename: string,
  queueJobs: QueueJobItem[],
  queueStats: QueueStats,
  lang: "fr" | "en" = "fr",
  extraFiles: string[] = [],
): FormProcessingState {
  const candidateFiles = new Set([filename, ...extraFiles].filter(Boolean));
  const statusUpper = String(processingStatus ?? "")
    .trim()
    .toUpperCase();

  const matchingJobs = queueJobs.filter((j) => j.filename && candidateFiles.has(j.filename));
  const runningJob = matchingJobs.find((j) => j.status === "RUNNING");
  const pendingJob = matchingJobs.find((j) => j.status === "PENDING");
  const isActiveInBanner =
    Boolean(queueStats.activeFormFile && candidateFiles.has(queueStats.activeFormFile)) &&
    queueStats.running + queueStats.pending > 0;
  const isStatusCompleted = statusUpper === "COMPLETED";
  const isStatusProcessing = ACTIVE_PROCESSING_STATUSES.has(statusUpper);
  const activeJobForForm = !isStatusCompleted
    ? runningJob || pendingJob
    : matchingJobs.find(
        (j) => (j.status === "RUNNING" || j.status === "PENDING") && j.jobType === "SECTION_RERUN",
      );

  const isProcessing = Boolean(
    isStatusProcessing || activeJobForForm || (!isStatusCompleted && isActiveInBanner),
  );
  const isFailed =
    !isProcessing &&
    (statusUpper === "FAILED" ||
      statusUpper === "ERROR" ||
      matchingJobs.some((j) => j.status === "FAILED" && statusUpper !== "COMPLETED"));

  let label = lang === "fr" ? "Traitement terminée" : "Completed";
  if (isProcessing) {
    if (statusUpper.includes("ADMIN")) {
      label = lang === "fr" ? "Extraction administrative en cours" : "Extracting admin data";
    } else if (statusUpper.includes("CLINICAL")) {
      label = lang === "fr" ? "Extraction clinique en cours" : "Extracting clinical data";
    } else if (statusUpper.includes("EXPERTS")) {
      label = lang === "fr" ? "Concertation IA en cours" : "Generating AI opinions";
    } else if (runningJob) {
      label = runningJob.section
        ? lang === "fr"
          ? `Analyse ${runningJob.section} en cours`
          : `Analyzing ${runningJob.section}`
        : lang === "fr"
          ? "Traitement IA en cours"
          : "Processing in progress";
    } else if (pendingJob || statusUpper.startsWith("PENDING") || statusUpper === "QUEUED") {
      label = lang === "fr" ? "En cours de traitement" : "Queued for processing";
    } else {
      label = lang === "fr" ? "Traitement en cours" : "Processing";
    }
  } else if (isFailed) {
    label = lang === "fr" ? "Échec du traitement" : "Processing failed";
  }

  const stepLabel =
    runningJob?.step ||
    processingStep ||
    (runningJob?.section ? `Rubrique : ${runningJob.section}` : null) ||
    pendingJob?.step ||
    null;

  const rawProgress =
    runningJob?.progressPct ||
    processingProgressPct ||
    (isActiveInBanner ? queueStats.activeProgressPct : 0) ||
    (statusUpper.includes("EXPERTS")
      ? 75
      : statusUpper.includes("CLINICAL")
        ? 45
        : statusUpper.includes("ADMIN")
          ? 25
          : isProcessing
            ? 35
            : 0);
  const progressPct = isProcessing ? Math.max(8, Math.min(98, Math.round(rawProgress))) : 100;

  return {
    isProcessing,
    isFailed,
    label,
    stepLabel,
    progressPct,
  };
}

export function formatDeleteDialogPatientInfo(
  patientName: string | null | undefined,
  id: string,
  file: string,
  patientId: string | null | undefined,
  domainParam: string,
  viewMode: string | undefined,
): {
  displayName: string;
  metaSuffix: string;
  actionUrl: string;
  isFormOnly: boolean;
} {
  const rawName = (patientName ?? "").trim();
  const cleanName =
    rawName && rawName.toLowerCase() !== "inconnu" && rawName !== file
      ? rawName.replace(/_/g, " ")
      : id && !id.toLowerCase().endsWith(".pdf")
        ? id
            .replace(/[_-](\d{4})[_-](\d{2})[_-](\d{2})$/, "")
            .replace(/_/g, " ")
            .trim()
        : file.replace(/\.pdf$/i, "").replace(/_/g, " ");

  const dob = extractDobFromPatientId(patientId ?? id);
  const shortCode =
    (patientId ?? id) &&
    !(patientId ?? id).includes("_") &&
    !(patientId ?? id).toLowerCase().endsWith(".pdf") &&
    (patientId ?? id) !== cleanName
      ? `#${patientId ?? id}`
      : null;

  const metaParts: string[] = [];
  if (shortCode) metaParts.push(shortCode);
  if (dob) metaParts.push(`né(e) le ${dob}`);
  const metaSuffix = metaParts.length > 0 ? ` (${metaParts.join(" · ")})` : "";

  const isFormOnly = viewMode === "rcp" || (!patientId && id.toLowerCase().endsWith(".pdf"));
  const actionUrl = isFormOnly
    ? `/forms/${encodeURIComponent(file)}/delete?domain=${domainParam}`
    : `/patients/${encodeURIComponent(patientId ?? id)}/delete?domain=${domainParam}`;

  return {
    displayName: cleanName || file,
    metaSuffix,
    actionUrl,
    isFormOnly,
  };
}

export function renderQueueBannerPartial(stats: QueueStats, session: UserSession): string {
  const lang = session.language;
  const isQueueActive = stats.running + stats.pending > 0;
  const queueDataAttrs = `data-queue-active="${isQueueActive ? "true" : "false"}" data-queue-running="${stats.running}" data-queue-pending="${stats.pending}" data-queue-completed="${stats.completed}" data-active-file="${esc(stats.activeFormFile ?? "")}"`;
  if (stats.failed > 0 && stats.running === 0) {
    return `<div class="ds-queue-banner ds-queue-banner--error" role="status" aria-live="polite" aria-atomic="true" id="queue-banner" data-testid="queue-banner" ${queueDataAttrs}>
      <span class="ds-queue-banner__text">
        ${iconSvg("ic-error")}
        <span class="ds-queue-banner__msg"><strong>${stats.failed} ${lang === "fr" ? "analyse(s) en échec" : "failed job(s)"}</strong>${stats.activeFormFile ? ` · ${esc(stats.activeFormFile)}` : ""}</span>
      </span>
      <button type="button" class="ds-btn ds-btn--sm ds-btn--secondary ds-queue-banner__action" data-open="queue-drawer" aria-haspopup="dialog" data-testid="btn_queue_open">${esc(t("queue.banner.open", lang))}</button>
    </div>`;
  }

  if (stats.running > 0 || stats.pending > 0) {
    return `<div class="ds-queue-banner" role="status" aria-live="polite" aria-atomic="true" id="queue-banner" data-testid="queue-banner" ${queueDataAttrs}>
      <span class="ds-queue-banner__text">
        <span class="ds-spinner" aria-hidden="true"></span>
        <span class="ds-queue-banner__msg"><strong>${stats.running} ${esc(t("queue.banner.running", lang))}</strong> · ${stats.pending} ${lang === "fr" ? "en attente" : "pending"}${stats.activeFormFile ? ` · ${esc(stats.activeFormFile)}` : ""}</span>
      </span>
      <progress class="ds-progress ds-queue-banner__progress" max="100" value="${Math.round(stats.activeProgressPct || 50)}" aria-label="Avancement de la file"></progress>
      <button type="button" class="ds-btn ds-btn--sm ds-btn--secondary ds-queue-banner__action" data-open="queue-drawer" aria-haspopup="dialog" data-testid="btn_queue_open">${esc(t("queue.banner.open", lang))}</button>
    </div>`;
  }

  return `<div class="ds-queue-banner ds-queue-banner--idle" role="status" aria-live="polite" aria-atomic="true" id="queue-banner" data-testid="queue-banner" ${queueDataAttrs}>
    <span class="ds-queue-banner__text">
      ${iconSvg("ic-clock")}
      <span class="ds-queue-banner__msg">${esc(t("queue.banner.idle", lang))}</span>
    </span>
    <button type="button" class="ds-btn ds-btn--sm ds-btn--ghost ds-queue-banner__action" data-open="queue-drawer" aria-haspopup="dialog" data-testid="btn_queue_open">${esc(t("queue.banner.open", lang))}</button>
  </div>`;
}

function resolveQueueJobHref(j: QueueJobItem, fallbackDomain: string): string {
  if (!j.filename) return "";
  const dom = encodeURIComponent(j.domain || fallbackDomain);
  const upperType = (j.jobType ?? "").toUpperCase();
  if (upperType.includes("RESOURCE") || upperType.includes("GUIDELINE")) {
    return `/guidelines?domain=${dom}&file=${encodeURIComponent(j.filename)}`;
  }
  return `/resolve?target=${encodeURIComponent(j.filename)}&domain=${dom}`;
}

export function renderLayout(opts: ShellLayoutOptions): string {
  const { session, queueStats, queueJobs, activeNav, breadcrumbs, bodyHtml, title } = opts;
  const lang = session.language;
  const domainParam = encodeURIComponent(session.domain);
  const activeCount = queueStats.running + queueStats.pending;
  const domainBadge =
    session.domain === "sma"
      ? `<span class="ds-badge ds-badge--domain-sma">${iconSvg("ic-dna")} ${lang === "fr" ? "Amyotrophie spinale" : "SMA"}</span>`
      : `<span class="ds-badge ds-badge--domain-onco">${iconSvg("ic-ribbon")} ${lang === "fr" ? "Oncologie" : "Oncology"}</span>`;

  const breadcrumbHtml = breadcrumbs
    .map((b, i) => {
      const isLast = i === breadcrumbs.length - 1;
      if (isLast || !b.href) {
        return `<li><span aria-current="page">${esc(b.label)}</span></li>`;
      }
      return `<li><a href="${esc(b.href)}">${esc(b.label)}</a></li>`;
    })
    .join("");

  const drawerJobsHtml =
    queueJobs.length === 0
      ? `<div class="ds-empty" style="padding:var(--ds-space-6)"><span class="ds-empty__title">${lang === "fr" ? "File d'analyse vide" : "Queue is empty"}</span></div>`
      : queueJobs
          .slice(0, 8)
          .map((j) => {
            const badgeCls =
              j.status === "RUNNING"
                ? "ds-badge--info"
                : j.status === "FAILED"
                  ? "ds-badge--danger"
                  : j.status === "COMPLETED"
                    ? "ds-badge--success"
                    : "ds-badge--neutral";
            const badgeIcon =
              j.status === "RUNNING"
                ? '<span class="ds-spinner" aria-hidden="true"></span>'
                : j.status === "FAILED"
                  ? iconSvg("ic-error")
                  : j.status === "COMPLETED"
                    ? iconSvg("ic-check-circle")
                    : iconSvg("ic-clock");
            const jobHref = resolveQueueJobHref(j, session.domain);
            const jobDataAttr = jobHref
              ? ` data-href="${jobHref}" title="${lang === "fr" ? "Cliquer pour ouvrir" : "Click to open"} ${esc(j.filename ?? j.jobType)}"`
              : "";
            return `<div class="ds-job"${jobDataAttr} data-testid="drawer-job-${esc(j.jobId)}">
              <span class="ds-job__title">${jobHref ? `<a class="ds-table__primary-link" href="${jobHref}">${esc(j.filename ?? j.jobType)}</a>` : esc(j.filename ?? j.jobType)}</span>
              <span class="ds-badge ${badgeCls} ds-badge--sm">${badgeIcon} ${esc(j.status)}</span>
              <span class="ds-job__meta">${esc(j.step ?? j.jobType)}${j.section ? ` · ${esc(j.section)}` : ""}${j.error ? ` · ${esc(j.error)}` : ""}</span>
              ${
                j.status === "RUNNING"
                  ? `<div class="ds-job__progress"><progress class="ds-progress" max="100" value="${Math.round(j.progressPct)}" aria-label="${Math.round(j.progressPct)} %"></progress></div>`
                  : ""
              }
            </div>`;
          })
          .join("");

  const html = `<!doctype html>
<html lang="${esc(lang)}" data-theme="${esc(session.theme)}" data-theme-pref="${esc(session.theme)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, interactive-widget=resizes-content">
  <title>${esc(title)} — DataSyntis</title>
  <link rel="icon" href="/public/img/datasyntis-icon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/public/css/tokens.css?v=30">
  <link rel="stylesheet" href="/public/css/components.css?v=30">
</head>
<body class="ds-shell">
  ${INLINE_ICONS_SVG}
  <a class="ds-skip-link" href="#main">${lang === "fr" ? "Aller au contenu" : "Skip to content"}</a>

  <!-- ===================== Sidebar (Material Design 3 Navigation Rail) ===================== -->
  <aside class="ds-sidebar ds-nav-rail" id="sidebar-nav" aria-label="Navigation principale" data-testid="sidebar">
    <div class="ds-rail__header">
      <a class="ds-brand" href="/worklist?domain=${domainParam}" title="DataSyntis — ${session.domain === "sma" ? "RCP Maladies Rares · SMA" : "RCP Oncologie Digestive"}">
        <img class="ds-brand__logo" src="/public/img/datasyntis-icon.svg" alt="" width="32" height="32">
        <span class="ds-brand__text">
          <span class="ds-brand__name">Data<b>Syntis</b></span>
          <span class="ds-brand__domain">${session.domain === "sma" ? "RCP Maladies Rares · SMA" : "RCP Oncologie Digestive"}</span>
        </span>
      </a>
      <button type="button" class="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon ds-rail__burger" id="sidebar-toggle" aria-label="Replier ou déplier le menu latéral" aria-expanded="true" data-tooltip="Replier / Déplier le menu" data-testid="btn_sidebar_toggle">
        ${iconSvg("ic-menu")}
      </button>
    </div>

    <!-- M3 Navigation Rail Tonal FAB (+ Importer PDF) -->
    <a class="ds-rail__fab" href="/ingest?domain=${domainParam}" ${activeNav === "ingest" ? 'aria-current="page"' : ""} title="${esc(t("nav.ingest", lang))}" data-testid="rail-fab-ingest">
      ${iconSvg("ic-add")}
      <span class="ds-rail__fab-label">${lang === "fr" ? "Importer PDF" : "Upload PDF"}</span>
    </a>

    <nav aria-label="Navigation clinique">
      <p class="ds-nav__heading">${lang === "fr" ? "Séance RCP" : "MDT Session"}</p>
      <ul class="ds-nav">
        <li>
          <a class="ds-nav__link" href="/worklist?domain=${domainParam}" ${activeNav === "worklist" || activeNav === "dossier" ? 'aria-current="page"' : ""} data-rail-label="${esc(t("nav.worklist", lang))}" title="${esc(t("nav.worklist", lang))}" data-testid="nav-worklist">
            <span class="ds-nav__bg" aria-hidden="true"></span>
            <span class="ds-nav__indicator">${iconSvg("ic-worklist")}</span>
            <span class="ds-nav__label">${esc(t("nav.worklist", lang))}</span>
          </a>
        </li>
        <li>
          <a class="ds-nav__link" href="/agenda?domain=${domainParam}" ${activeNav === "agenda" ? 'aria-current="page"' : ""} data-rail-label="${esc(t("nav.agenda", lang))}" title="${esc(t("nav.agenda", lang))}" data-testid="nav-agenda">
            <span class="ds-nav__bg" aria-hidden="true"></span>
            <span class="ds-nav__indicator">${iconSvg("ic-calendar")}</span>
            <span class="ds-nav__label">${esc(t("nav.agenda", lang))}</span>
          </a>
        </li>
        <li>
          <a class="ds-nav__link" href="/guidelines?domain=${domainParam}" ${activeNav === "guidelines" ? 'aria-current="page"' : ""} data-rail-label="${esc(t("nav.guidelines", lang))}" title="${esc(t("nav.guidelines", lang))}" data-testid="nav-guidelines">
            <span class="ds-nav__bg" aria-hidden="true"></span>
            <span class="ds-nav__indicator">${iconSvg("ic-book")}</span>
            <span class="ds-nav__label">${esc(t("nav.guidelines", lang))}</span>
          </a>
        </li>
        <li>
          <a class="ds-nav__link" href="/agents?domain=${domainParam}" ${activeNav === "agents" ? 'aria-current="page"' : ""} data-rail-label="${esc(t("nav.agents", lang))}" title="${esc(t("nav.agents", lang))}" data-testid="nav-agents">
            <span class="ds-nav__bg" aria-hidden="true"></span>
            <span class="ds-nav__indicator">${iconSvg("ic-users")}</span>
            <span class="ds-nav__label">${esc(t("nav.agents", lang))}</span>
          </a>
        </li>
      </ul>

      <p class="ds-nav__heading">${lang === "fr" ? "Supervision & Qualité" : "Supervision & Quality"}</p>
      <ul class="ds-nav">
        <li>
          <a class="ds-nav__link" href="/admin/queue?domain=${domainParam}" ${activeNav === "queue" ? 'aria-current="page"' : ""} data-rail-label="${esc(t("nav.queue", lang))}" title="${esc(t("nav.queue", lang))}" data-testid="nav-queue">
            <span class="ds-nav__bg" aria-hidden="true"></span>
            <span class="ds-nav__indicator">${iconSvg("ic-layers")}</span>
            <span class="ds-nav__label">${esc(t("nav.queue", lang))}</span>
            ${activeCount > 0 ? `<span class="ds-nav__count">${activeCount}</span>` : ""}
          </a>
        </li>
        <li>
          <a class="ds-nav__link" href="/feedback?domain=${domainParam}" ${activeNav === "feedback" ? 'aria-current="page"' : ""} data-rail-label="${esc(t("nav.feedback", lang))}" title="${esc(t("nav.feedback", lang))}" data-testid="nav-feedback">
            <span class="ds-nav__bg" aria-hidden="true"></span>
            <span class="ds-nav__indicator">${iconSvg("ic-bug")}</span>
            <span class="ds-nav__label">${esc(t("nav.feedback", lang))}</span>
          </a>
        </li>
        ${
          session.expertMode
            ? `<li>
                <a class="ds-nav__link" href="/styleguide" data-rail-label="${esc(t("nav.styleguide", lang))}" title="${esc(t("nav.styleguide", lang))}" data-testid="nav-styleguide">
                  <span class="ds-nav__bg" aria-hidden="true"></span>
                  <span class="ds-nav__indicator">${iconSvg("ic-palette")}</span>
                  <span class="ds-nav__label">${esc(t("nav.styleguide", lang))}</span>
                </a>
              </li>`
            : ""
        }
      </ul>
    </nav>

    <div class="ds-sidebar__footer">
      <p>${iconSvg("ic-check-circle", "ds-icon--xs")} ${lang === "fr" ? "Exécution 100 % locale" : "100% Local Execution"}</p>
      <p style="margin-top:4px">${esc(session.userName)}</p>
    </div>
  </aside>
  <div class="ds-sidebar-backdrop" id="sidebar-backdrop" aria-hidden="true"></div>

  <div class="ds-main" id="top">
    <header class="ds-topbar">
      <button type="button" class="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon ds-topbar__burger" id="mobile-nav-toggle" aria-label="${lang === "fr" ? "Ouvrir le menu de navigation" : "Open navigation menu"}" aria-controls="sidebar-nav" aria-expanded="false" data-testid="btn_mobile_nav_toggle">
        ${iconSvg("ic-menu")}
      </button>
      <ol class="ds-breadcrumb" aria-label="Fil d'Ariane">
        <li><a href="/worklist?domain=${domainParam}">DataSyntis</a></li>
        ${breadcrumbHtml}
      </ol>
      <div class="ds-topbar__actions">
        ${domainBadge}

        <!-- Langue FR / EN -->
        <form method="post" action="/preferences" style="display:inline-flex">
          <input type="hidden" name="language" value="${lang === "fr" ? "en" : "fr"}">
          <button type="submit" class="ds-btn ds-btn--ghost ds-btn--sm" data-tooltip="Changer la langue (FR / EN)" data-testid="btn_lang_toggle">
            ${lang.toUpperCase()}
          </button>
        </form>

        <!-- Mode Expert -->
        <form method="post" action="/preferences" style="display:inline-flex">
          <input type="hidden" name="expertMode" value="${session.expertMode ? "false" : "true"}">
          <button type="submit" class="ds-chip" aria-pressed="${session.expertMode ? "true" : "false"}" data-testid="btn_expert_toggle">
            ${iconSvg("ic-sparkle")} ${esc(t("topbar.expert", lang))}
          </button>
        </form>

        <!-- Menu contextuel d'accès rapide (...) -->
        <details class="ds-menu" data-testid="menu-topbar-actions">
          <summary class="ds-menu__trigger" aria-label="Menu contextuel d'affichage et d'accès rapide" title="Plus d'options">
            ${iconSvg("ic-more-vert")}
          </summary>
          <div class="ds-menu__panel" role="menu">
            <div class="ds-menu__header">${lang === "fr" ? "Thème d'affichage" : "Display Theme"}</div>
            <div role="group" aria-label="${lang === "fr" ? "Choix du thème" : "Theme selection"}" data-testid="theme-selector">
              <button type="button" class="ds-menu__item ${session.theme === "auto" ? "ds-menu__item--active" : ""}" role="menuitemradio" aria-checked="${session.theme === "auto" ? "true" : "false"}" data-menu-action="set-theme" data-theme-value="auto" data-testid="btn_theme_auto">
                ${iconSvg("ic-palette")}
                <span>${esc(t("topbar.theme.auto", lang))}</span>
              </button>
              <button type="button" class="ds-menu__item ${session.theme === "light" ? "ds-menu__item--active" : ""}" role="menuitemradio" aria-checked="${session.theme === "light" ? "true" : "false"}" data-menu-action="set-theme" data-theme-value="light" data-testid="btn_theme_light">
                ${iconSvg("ic-sun")}
                <span>${esc(t("topbar.theme.light", lang))}</span>
              </button>
              <button type="button" class="ds-menu__item ${session.theme === "dark" ? "ds-menu__item--active" : ""}" role="menuitemradio" aria-checked="${session.theme === "dark" ? "true" : "false"}" data-menu-action="set-theme" data-theme-value="dark" data-testid="btn_theme_dark">
                ${iconSvg("ic-moon")}
                <span>${esc(t("topbar.theme.dark", lang))}</span>
              </button>
            </div>
            <hr class="ds-menu__divider">
            <div class="ds-menu__header">${lang === "fr" ? "Navigation & Affichage" : "Navigation & View"}</div>
            <button type="button" class="ds-menu__item" role="menuitem" data-menu-action="toggle-rail">
              ${iconSvg("ic-menu")}
              <span>${lang === "fr" ? "Replier / Déplier le menu latéral" : "Toggle sidebar menu"}</span>
            </button>
            <button type="button" class="ds-menu__item" role="menuitem" data-open="queue-drawer">
              ${iconSvg("ic-layers")}
              <span>${lang === "fr" ? "Ouvrir le tiroir des analyses" : "Open Queue Side Sheet"}</span>
              ${activeCount > 0 ? `<span class="ds-menu__meta">${activeCount}</span>` : ""}
            </button>
            <hr class="ds-menu__divider">
            <div class="ds-menu__header">${lang === "fr" ? "Raccourcis cliniques" : "Clinical Shortcuts"}</div>
            <a class="ds-menu__item" role="menuitem" href="/ingest?domain=${domainParam}">
              ${iconSvg("ic-upload")}
              <span>${esc(t("nav.ingest", lang))}</span>
            </a>
            <a class="ds-menu__item" role="menuitem" href="/agents?domain=${domainParam}">
              ${iconSvg("ic-users")}
              <span>${esc(t("nav.agents", lang))}</span>
            </a>
            <a class="ds-menu__item" role="menuitem" href="/feedback?domain=${domainParam}">
              ${iconSvg("ic-bug")}
              <span>${esc(t("nav.feedback", lang))}</span>
            </a>
            ${
              session.expertMode
                ? `<hr class="ds-menu__divider">
                   <a class="ds-menu__item" role="menuitem" href="/styleguide">
                     ${iconSvg("ic-palette")}
                     <span>${esc(t("nav.styleguide", lang))}</span>
                   </a>`
                : ""
            }
          </div>
        </details>
      </div>
    </header>

    <main class="ds-workspace" id="main">
      ${
        opts.toastMessage
          ? `<div class="ds-alert ds-alert--success" role="status"><span class="ds-alert__icon" aria-hidden="true">${iconSvg("ic-check-circle")}</span><div class="ds-alert__content"><span class="ds-alert__title">${esc(opts.toastMessage)}</span></div></div>`
          : ""
      }
      ${bodyHtml}
    </main>

    ${renderQueueBannerPartial(queueStats, session)}
  </div>

  <!-- ===================== Queue Drawer (M3 Side Sheet) ===================== -->
  <dialog class="ds-drawer" id="queue-drawer" aria-labelledby="queue-drawer-title" data-testid="queue-drawer">
    <div class="ds-drawer__header">
      ${iconSvg("ic-layers", "ds-icon--md")}
      <h2 id="queue-drawer-title">${esc(t("nav.queue", lang))}</h2>
      <form method="dialog" class="ds-drawer__close">
        <button class="ds-btn ds-btn--ghost ds-btn--icon" aria-label="Fermer la file d'analyse">${iconSvg("ic-close")}</button>
      </form>
    </div>
    <div class="ds-drawer__body" id="queue-drawer-body">
      ${
        queueStats.thinkingPreview
          ? `<div class="ds-alert ds-alert--guidance" role="note"><span class="ds-alert__icon">${iconSvg("ic-sparkle")}</span><div class="ds-alert__content"><span class="ds-alert__title">Raisonnement IA en direct</span><span>${esc(queueStats.thinkingPreview)}</span></div></div>`
          : ""
      }
      ${drawerJobsHtml}
    </div>
    <div class="ds-drawer__footer">
      <a class="ds-btn ds-btn--secondary" href="/admin/queue?domain=${esc(session.domain)}">Ouvrir la supervision complète</a>
    </div>
  </dialog>

  <!-- ===================== Mobile Bottom Navigation Bar (M3 Compact < 48rem) ===================== -->
  <nav class="ds-bottom-nav" aria-label="${lang === "fr" ? "Navigation principale mobile" : "Mobile primary navigation"}" data-testid="bottom-nav">
    <a class="ds-bottom-nav__item" href="/worklist?domain=${domainParam}" ${activeNav === "worklist" || activeNav === "dossier" ? 'aria-current="page"' : ""}>
      <span class="ds-bottom-nav__pill"><span class="ds-bottom-nav__bg" aria-hidden="true"></span>${iconSvg("ic-worklist")}</span>
      <span class="ds-bottom-nav__label">${esc(t("nav.worklist", lang))}</span>
    </a>
    <a class="ds-bottom-nav__item" href="/agenda?domain=${domainParam}" ${activeNav === "agenda" ? 'aria-current="page"' : ""}>
      <span class="ds-bottom-nav__pill"><span class="ds-bottom-nav__bg" aria-hidden="true"></span>${iconSvg("ic-calendar")}</span>
      <span class="ds-bottom-nav__label">${lang === "fr" ? "Ordre RCP" : "Agenda"}</span>
    </a>
    <a class="ds-bottom-nav__item" href="/ingest?domain=${domainParam}" ${activeNav === "ingest" ? 'aria-current="page"' : ""}>
      <span class="ds-bottom-nav__pill"><span class="ds-bottom-nav__bg" aria-hidden="true"></span>${iconSvg("ic-add")}</span>
      <span class="ds-bottom-nav__label">${lang === "fr" ? "Importer" : "Upload"}</span>
    </a>
    <a class="ds-bottom-nav__item" href="/guidelines?domain=${domainParam}" ${activeNav === "guidelines" ? 'aria-current="page"' : ""}>
      <span class="ds-bottom-nav__pill"><span class="ds-bottom-nav__bg" aria-hidden="true"></span>${iconSvg("ic-book")}</span>
      <span class="ds-bottom-nav__label">${lang === "fr" ? "Référentiels" : "Guidelines"}</span>
    </a>
    <a class="ds-bottom-nav__item" href="/agents?domain=${domainParam}" ${activeNav === "agents" ? 'aria-current="page"' : ""}>
      <span class="ds-bottom-nav__pill"><span class="ds-bottom-nav__bg" aria-hidden="true"></span>${iconSvg("ic-users")}</span>
      <span class="ds-bottom-nav__label">${lang === "fr" ? "Experts IA" : "AI Experts"}</span>
    </a>
  </nav>

  <script src="/public/js/app.js?v=30"></script>
</body>
</html>`;
  return session.hostBoundDomain ? stripDomainQuery(html) : html;
}

export function renderWorklistPage(
  view: WorklistViewResult,
  session: UserSession,
  queueStats: QueueStats,
  queueJobs: QueueJobItem[],
): string {
  const lang = session.language;
  const { kpis, cards, filter } = view;
  const domainParam = encodeURIComponent(session.domain);

  const rowsHtml =
    cards.length === 0
      ? ""
      : cards
          .map((c) => {
            const prio = derivePriorityBadgeInfo(c.priorityLevel, lang, true);
            const proc = deriveFormProcessingState(
              c.processingStatus,
              c.processingStep,
              c.processingProgressPct,
              c.file,
              queueJobs,
              queueStats,
              lang,
            );
            const effectiveComplete = !proc.isProcessing && c.isComplete;
            const compl = deriveCompletenessInfo(
              {
                is_complete: effectiveComplete,
                missing_count: c.missingCount,
                missing_items: c.missingItems,
                processing_status: proc.isProcessing ? "RUNNING" : c.processingStatus,
              },
              lang,
            );
            const orient = deriveOrientationInfo(
              {
                care_adaptation_suggested: c.careAdaptationSuggested,
                proposed_care_type: c.proposedCareType,
              },
              lang,
            );
            const delInfo = formatDeleteDialogPatientInfo(
              c.patientName,
              c.id,
              c.file,
              c.patientId,
              domainParam,
              filter.viewMode,
            );
            const shortProcLabel = lang === "fr" ? "IA en cours" : "Processing";
            const procBadgeHtml = proc.isProcessing
              ? ` <span class="ds-badge ds-badge--processing ds-badge--sm" title="${esc(proc.stepLabel ? `${proc.label} (${proc.stepLabel})` : proc.label)}" data-testid="badge-processing-${esc(c.id)}"><span class="ds-spinner" aria-hidden="true"></span> ${esc(shortProcLabel)}</span>`
              : proc.isFailed
                ? ` <span class="ds-badge ds-badge--danger ds-badge--sm" title="${esc(proc.stepLabel ?? proc.label)}" data-testid="badge-processing-${esc(c.id)}">${iconSvg("ic-error")} ${esc(lang === "fr" ? "Échec IA" : "Failed")}</span>`
                : "";
            const dossierHref = c.patientId
              ? `/patients/${encodeURIComponent(c.patientId)}?domain=${domainParam}`
              : `/forms/${encodeURIComponent(c.file)}?domain=${domainParam}`;
            const specsBadges = c.specialties
              .slice(0, 3)
              .map((s) => {
                const p = getAgentPresentation(s, lang);
                return `<span class="ds-badge ds-badge--specialty ds-badge--sm" title="${esc(p.label)}">${iconSvg(p.icon)} ${esc(p.shortLabel)}</span>`;
              })
              .join("");
            const specsHtml = specsBadges
              ? `<div class="ds-table__cell-badges">${specsBadges}${
                  c.specialties.length > 3
                    ? `<span class="ds-badge ds-badge--neutral ds-badge--sm">+${c.specialties.length - 3}</span>`
                    : ""
                }</div>`
              : "";

            const completenessCell =
              !effectiveComplete && c.missingItems.length > 0
                ? `<div class="ds-hovercard" tabindex="0">
                    <span class="ds-badge ${compl.badgeClass} ds-badge--sm">${iconSvg(compl.icon)} ${esc(compl.label)}</span>
                    <div class="ds-hovercard__panel" role="tooltip">
                      <span class="ds-hovercard__title">${iconSvg("ic-warning")} Éléments manquants</span>
                      <ul class="ds-hovercard__list">${c.missingItems.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>
                    </div>
                  </div>`
                : `<span class="ds-badge ${compl.badgeClass} ds-badge--sm">${iconSvg(compl.icon)} ${esc(compl.label)}</span>`;

            const orientationCell =
              c.proposedCareType || c.summaryText
                ? `<div class="ds-hovercard" tabindex="0">
                    <span class="ds-badge ${orient.badgeClass} ds-badge--sm" data-testid="badge-orientation-${esc(orient.status)}">
                      ${iconSvg(orient.icon)} ${esc(orient.label)}
                    </span>
                    <div class="ds-hovercard__panel" role="tooltip">
                      <span class="ds-hovercard__title">${iconSvg("ic-compass")} Orientation pré-RCP</span>
                      ${c.proposedCareType ? `<p style="font-weight:var(--ds-weight-semibold);margin-bottom:4px">${esc(c.proposedCareType)}</p>` : ""}
                      ${c.summaryText ? `<p>${esc(c.summaryText)}</p>` : ""}
                    </div>
                  </div>`
                : `<span class="ds-badge ${orient.badgeClass} ds-badge--sm" data-testid="badge-orientation-${esc(orient.status)}">
                    ${iconSvg(orient.icon)} ${esc(orient.label)}
                  </span>`;

            const prioSortVal =
              c.priorityLevel === "high" ? "1" : c.priorityLevel === "medium" ? "2" : "3";
            const complSortVal = effectiveComplete ? "1" : String(2 + Math.max(1, c.missingCount));
            const orientSortVal = c.careAdaptationSuggested ? "1" : "2";
            const rowCls = [
              c.priorityLevel === "high" ? "is-urgent" : "",
              proc.isProcessing ? "is-processing" : "",
            ]
              .filter(Boolean)
              .join(" ");
            const procDataAttrs = proc.isProcessing
              ? ` data-processing-active="true" data-processing-file="${esc(c.file)}"`
              : "";

            return `<tr class="${rowCls}" data-href="${dossierHref}" title="Cliquer pour ouvrir le dossier de ${esc(c.patientName)}" data-testid="worklist-row-${esc(c.id)}"${procDataAttrs}>
              <td data-label="Priorité" data-sort-value="${prioSortVal}">
                <span class="ds-badge ${prio.badgeClass} ds-badge--sm" data-testid="badge-priority-${esc(c.priorityLevel)}">
                  ${iconSvg(prio.icon)} ${esc(prio.label)}
                </span>
              </td>
              <td data-label="Patient" class="ds-table__primary-cell" data-sort-value="${esc(c.patientName)}">
                <a class="ds-table__primary-link" href="${dossierHref}">${esc(c.patientName)}</a><br>
                <span class="ds-small ds-muted">${esc(formatPatientSubtitle(c.id, c.rcpCount))}</span>${procBadgeHtml ? `<div style="margin-top:2px">${procBadgeHtml.trim()}</div>` : ""}
              </td>
              <td data-label="Complétude" data-sort-value="${complSortVal}">${completenessCell}</td>
              <td data-label="Orientation pré-RCP" data-sort-value="${orientSortVal}">
                ${orientationCell}
              </td>
              <td data-label="Spécialités" data-sort-value="${c.specialties.length}">${specsHtml || '<span class="ds-small ds-muted">—</span>'}</td>
              <td data-label="Dernière RCP" class="ds-nowrap" data-sort-value="${esc(c.mdtDate ?? "")}">${esc(c.mdtDate ?? "—")}</td>
              <td class="ds-table__actions">
                <div class="ds-cluster" style="justify-content:flex-end;flex-wrap:nowrap">
                  <a class="ds-btn ds-btn--tonal ds-btn--sm" href="${dossierHref}" data-testid="btn_open_${esc(c.id)}">Ouvrir</a>
                  <details class="ds-menu" data-testid="menu-patient-${esc(c.id)}">
                    <summary class="ds-menu__trigger" aria-label="Actions contextuelles pour ${esc(c.patientName)}" title="Actions patient">
                      ${iconSvg("ic-more-vert")}
                    </summary>
                    <div class="ds-menu__panel" role="menu">
                      <div class="ds-menu__header">${esc(c.patientName)}</div>
                      <a class="ds-menu__item" role="menuitem" href="${dossierHref}">
                        ${iconSvg("ic-folder")}
                        <span>Ouvrir le dossier longitudinal</span>
                      </a>
                      <a class="ds-menu__item" role="menuitem" href="${dossierHref}&tab=opinions#panel-opinions">
                        ${iconSvg("ic-compass")}
                        <span>Avis &amp; orientation pré-RCP</span>
                      </a>
                      <a class="ds-menu__item" role="menuitem" href="${dossierHref}&chat=open">
                        ${iconSvg("ic-sparkle")}
                        <span>Interroger l'assistant IA</span>
                      </a>
                      <a class="ds-menu__item" role="menuitem" href="/ingest?domain=${domainParam}&patientId=${encodeURIComponent(c.patientId ?? c.id)}">
                        ${iconSvg("ic-upload")}
                        <span>Importer une pièce PDF</span>
                      </a>
                      <form method="post" action="/agenda/patients?domain=${domainParam}">
                        <input type="hidden" name="patientId" value="${esc(c.patientId ?? c.id)}">
                        <button type="submit" class="ds-menu__item" role="menuitem" data-testid="btn_enroll_agenda_${esc(c.id)}">
                          ${iconSvg("ic-calendar")}
                          <span>Inscrire à la prochaine RCP</span>
                        </button>
                      </form>
                      <hr class="ds-menu__divider">
                      <a class="ds-menu__item" role="menuitem" href="/feedback?domain=${domainParam}&patientId=${encodeURIComponent(c.patientId ?? c.id)}">
                        ${iconSvg("ic-bug")}
                        <span>Signaler une anomalie</span>
                      </a>
                      <button type="button" class="ds-menu__item ds-menu__item--danger" role="menuitem" data-open="del-dialog-${esc(c.id)}" data-patient-name="${esc(delInfo.displayName)}" data-testid="btn_del_patient_${esc(c.id)}">
                        ${iconSvg("ic-delete")}
                        <span>Supprimer ce dossier…</span>
                      </button>
                    </div>
                  </details>
                </div>
              </td>
            </tr>`;
          })
          .join("");

  const cardsGridHtml =
    cards.length === 0
      ? ""
      : `<div class="ds-patient-grid" id="worklist" data-testid="worklist-table">
          ${cards
            .map((c) => {
              const prio = derivePriorityBadgeInfo(c.priorityLevel, lang, true);
              const proc = deriveFormProcessingState(
                c.processingStatus,
                c.processingStep,
                c.processingProgressPct,
                c.file,
                queueJobs,
                queueStats,
                lang,
              );
              const effectiveComplete = !proc.isProcessing && c.isComplete;
              const compl = deriveCompletenessInfo(
                {
                  is_complete: effectiveComplete,
                  missing_count: c.missingCount,
                  missing_items: c.missingItems,
                  processing_status: proc.isProcessing ? "RUNNING" : c.processingStatus,
                },
                lang,
              );
              const orient = deriveOrientationInfo(
                {
                  care_adaptation_suggested: c.careAdaptationSuggested,
                  proposed_care_type: c.proposedCareType,
                },
                lang,
              );
              const delInfo = formatDeleteDialogPatientInfo(
                c.patientName,
                c.id,
                c.file,
                c.patientId,
                domainParam,
                filter.viewMode,
              );
              const procBadgeHtml = proc.isProcessing
                ? `<span class="ds-badge ds-badge--processing ds-badge--sm" title="${esc(proc.stepLabel ?? proc.label)}" data-testid="badge-processing-${esc(c.id)}"><span class="ds-spinner" aria-hidden="true"></span> ${esc(proc.label)}</span>`
                : proc.isFailed
                  ? `<span class="ds-badge ds-badge--danger ds-badge--sm" title="${esc(proc.stepLabel ?? proc.label)}" data-testid="badge-processing-${esc(c.id)}">${iconSvg("ic-error")} ${esc(proc.label)}</span>`
                  : "";
              const dossierHref = c.patientId
                ? `/patients/${encodeURIComponent(c.patientId)}?domain=${domainParam}`
                : `/forms/${encodeURIComponent(c.file)}?domain=${domainParam}`;
              const cardTone = deriveRcpTone(c.priorityLevel, effectiveComplete);
              const procDataAttrs = proc.isProcessing
                ? ` data-processing-active="true" data-processing-file="${esc(c.file)}"`
                : "";
              return `<article class="ds-card ds-card--interactive ds-patient-card ds-patient-card--${cardTone}${proc.isProcessing ? " is-processing" : ""}" data-href="${dossierHref}" title="Cliquer pour ouvrir le dossier de ${esc(c.patientName)}" data-testid="worklist-row-${esc(c.id)}"${procDataAttrs}>
                <div class="ds-card__header">
                  <h2 class="ds-patient-card__name"><a href="${dossierHref}">${esc(c.patientName)}</a></h2>
                  <span class="ds-patient-card__id">${esc(formatPatientSubtitle(c.id, c.rcpCount))}</span>
                </div>
                <div class="ds-card__body">
                  <div class="ds-cluster">
                    ${procBadgeHtml}
                    <span class="ds-badge ${prio.badgeClass} ds-badge--sm">${iconSvg(prio.icon)} ${esc(prio.label)}</span>
                    ${
                      !effectiveComplete && c.missingItems.length > 0
                        ? `<div class="ds-hovercard" tabindex="0">
                            <span class="ds-badge ${compl.badgeClass} ds-badge--sm">${iconSvg(compl.icon)} ${esc(compl.label)}</span>
                            <div class="ds-hovercard__panel" role="tooltip">
                              <span class="ds-hovercard__title">${iconSvg("ic-warning")} Éléments manquants</span>
                              <ul class="ds-hovercard__list">${c.missingItems.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>
                            </div>
                          </div>`
                        : `<span class="ds-badge ${compl.badgeClass} ds-badge--sm">${iconSvg(compl.icon)} ${esc(compl.label)}</span>`
                    }
                    ${
                      c.proposedCareType || c.summaryText
                        ? `<div class="ds-hovercard" tabindex="0">
                            <span class="ds-badge ${orient.badgeClass} ds-badge--sm">${iconSvg(orient.icon)} ${esc(orient.label)}</span>
                            <div class="ds-hovercard__panel" role="tooltip">
                              <span class="ds-hovercard__title">${iconSvg("ic-compass")} Orientation pré-RCP</span>
                              ${c.proposedCareType ? `<p style="font-weight:var(--ds-weight-semibold);margin-bottom:4px">${esc(c.proposedCareType)}</p>` : ""}
                              ${c.summaryText ? `<p>${esc(c.summaryText)}</p>` : ""}
                            </div>
                          </div>`
                        : `<span class="ds-badge ${orient.badgeClass} ds-badge--sm">${iconSvg(orient.icon)} ${esc(orient.label)}</span>`
                    }
                  </div>
                  ${c.summaryText ? `<p class="ds-small">${esc(c.summaryText)}</p>` : ""}
                </div>
                <div class="ds-card__footer">
                  <span class="ds-small ds-muted">RCP : ${esc(c.mdtDate ?? "—")}</span>
                  <div class="ds-card__footer-end">
                    <a class="ds-btn ds-btn--tonal ds-btn--sm" href="${dossierHref}" data-testid="btn_open_${esc(c.id)}">Ouvrir</a>
                    <details class="ds-menu" data-testid="menu-patient-${esc(c.id)}">
                      <summary class="ds-menu__trigger" aria-label="Actions contextuelles pour ${esc(c.patientName)}" title="Actions patient">
                        ${iconSvg("ic-more-vert")}
                      </summary>
                      <div class="ds-menu__panel" role="menu">
                        <div class="ds-menu__header">${esc(c.patientName)}</div>
                        <a class="ds-menu__item" role="menuitem" href="${dossierHref}">
                          ${iconSvg("ic-folder")}
                          <span>Ouvrir le dossier longitudinal</span>
                        </a>
                        <a class="ds-menu__item" role="menuitem" href="${dossierHref}&tab=opinions#panel-opinions">
                          ${iconSvg("ic-compass")}
                          <span>Avis &amp; orientation pré-RCP</span>
                        </a>
                        <a class="ds-menu__item" role="menuitem" href="/ingest?domain=${domainParam}&patientId=${encodeURIComponent(c.patientId ?? c.id)}">
                          ${iconSvg("ic-upload")}
                          <span>Importer une pièce PDF</span>
                        </a>
                        <hr class="ds-menu__divider">
                        <a class="ds-menu__item" role="menuitem" href="/feedback?domain=${domainParam}&patientId=${encodeURIComponent(c.patientId ?? c.id)}">
                          ${iconSvg("ic-bug")}
                          <span>Signaler une anomalie</span>
                        </a>
                        <button type="button" class="ds-menu__item ds-menu__item--danger" role="menuitem" data-open="del-dialog-${esc(c.id)}" data-patient-name="${esc(delInfo.displayName)}" data-testid="btn_del_patient_${esc(c.id)}">
                          ${iconSvg("ic-delete")}
                          <span>Supprimer ce dossier…</span>
                        </button>
                      </div>
                    </details>
                  </div>
                </div>
              </article>`;
            })
            .join("")}
        </div>`;

  const deleteDialogsHtml =
    cards.length === 0
      ? ""
      : cards
          .map((c) => {
            const delInfo = formatDeleteDialogPatientInfo(
              c.patientName,
              c.id,
              c.file,
              c.patientId,
              domainParam,
              filter.viewMode,
            );
            return `<dialog class="ds-modal ds-modal--danger" id="del-dialog-${esc(c.id)}" aria-labelledby="del-title-${esc(c.id)}">
              <div class="ds-modal__header">
                <span>${iconSvg("ic-delete")}</span>
                <h2 id="del-title-${esc(c.id)}">${delInfo.isFormOnly ? "Supprimer la fiche RCP de" : "Supprimer le dossier de"} <span data-del-patient-name>${esc(delInfo.displayName)}</span> ?</h2>
              </div>
              <div class="ds-modal__body">
                <div class="ds-alert ds-alert--danger" role="alert">
                  <span class="ds-alert__icon">${iconSvg("ic-priority-high")}</span>
                  <div class="ds-alert__content">
                    <span class="ds-alert__title">Action irréversible</span>
                    <span>${delInfo.isFormOnly ? "La fiche RCP et les modifications manuelles associées à" : "Les fiches RCP et les modifications manuelles associées à"} <strong data-del-patient-name>${esc(delInfo.displayName)}</strong>${esc(delInfo.metaSuffix)} seront définitivement supprimées.</span>
                  </div>
                </div>
              </div>
              <div class="ds-modal__footer">
                <form method="dialog"><button class="ds-btn ds-btn--ghost" autofocus>Annuler</button></form>
                <form method="post" action="${delInfo.actionUrl}">
                  <button type="submit" class="ds-btn ds-btn--danger" data-testid="btn_danger_confirm_${esc(c.id)}">${iconSvg("ic-delete")} Supprimer définitivement</button>
                </form>
              </div>
            </dialog>`;
          })
          .join("");

  const tableWrapHtml =
    cards.length === 0
      ? ""
      : `<div class="ds-table-wrap">
          <table class="ds-table ds-table--dense" id="worklist" data-testid="worklist-table">
            <caption class="ds-sr-only">Worklist RCP triée par priorité</caption>
            <thead>
              <tr>
                ${(
                  [
                    { key: "priority", label: "Priorité", col: 0 },
                    { key: "patient", label: "Patient", col: 1 },
                    { key: "completeness", label: "Complétude", col: 2 },
                    {
                      key: "orientation",
                      label: "Orientation pré-RCP",
                      col: 3,
                    },
                    {
                      key: "specialties",
                      label: "Spécialités requises",
                      col: 4,
                    },
                    { key: "mdtDate", label: "Dernière RCP", col: 5 },
                  ] as const
                )
                  .map((colDef) => {
                    const activeSort = filter.sortBy ?? "priority";
                    const activeDir = filter.sortDir ?? "asc";
                    const isSorted = activeSort === colDef.key;
                    const nextDir = isSorted && activeDir === "asc" ? "desc" : "asc";
                    const ariaSort = isSorted
                      ? activeDir === "asc"
                        ? "ascending"
                        : "descending"
                      : "none";
                    const sortUrl = `/worklist?domain=${domainParam}&sortBy=${colDef.key}&sortDir=${nextDir}${filter.query ? `&q=${encodeURIComponent(filter.query)}` : ""}${filter.completeness && filter.completeness !== "all" ? `&completeness=${encodeURIComponent(filter.completeness)}` : ""}${filter.priority && filter.priority !== "all" ? `&priority=${encodeURIComponent(filter.priority)}` : ""}${filter.viewMode ? `&viewMode=${encodeURIComponent(filter.viewMode)}` : ""}`;
                    return `<th scope="col" aria-sort="${ariaSort}" data-sort-col="${colDef.col}">
                      <a class="ds-sort ${isSorted ? "is-sorted" : ""}" href="${sortUrl}" data-sort-trigger="${colDef.col}" data-testid="sort-${colDef.key}">
                        <span>${colDef.label}</span>
                        <span class="ds-sort__icon" aria-hidden="true">${isSorted ? (activeDir === "asc" ? "↑" : "↓") : "↕"}</span>
                      </a>
                    </th>`;
                  })
                  .join("")}
                <th scope="col" class="ds-table__actions"><span class="ds-sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml}
            </tbody>
          </table>
        </div>
        <template id="worklist-mobile-cards-tpl">${cardsGridHtml}</template>`;

  const bodyHtml = `
    <div class="ds-page-header">
      <div class="ds-page-header__text">
        <h1>${esc(t("nav.worklist", lang))}</h1>
        <p class="ds-muted">${
          session.domain === "sma"
            ? "Préparation collégiale de la RCP neuromusculaire (Amyotrophie spinale SMA) — priorisation et contrôle de complétude."
            : "Préparation collégiale de la RCP d'oncologie digestive — priorisation, contrôle de complétude et orientations pré-RCP."
        }</p>
      </div>
      <div class="ds-page-header__actions">
        <a class="ds-btn ds-btn--tonal" href="/agenda?domain=${domainParam}" data-testid="btn_go_agenda">
          ${iconSvg("ic-calendar")} ${esc(t("nav.agenda", lang))}
        </a>
      </div>
    </div>

    <!-- 4 M3 KPI Tiles -->
    <div class="ds-kpi-grid">
      <a class="ds-kpi ds-kpi--success" href="/worklist?domain=${domainParam}" data-testid="kpi-structured">
        <span class="ds-kpi__label"><span class="ds-icon-box ds-icon-box--success" aria-hidden="true">${iconSvg("ic-folder", "ds-icon--md")}</span> ${esc(t("kpi.structured", lang))}</span>
        <span class="ds-kpi__value">${kpis.structuredCount}</span>
        <span class="ds-kpi__meta">${esc(t("kpi.structured.meta", lang))}</span>
      </a>
      <a class="ds-kpi ds-kpi--danger" href="/worklist?domain=${domainParam}&priority=high" data-testid="kpi-priority-high">
        <span class="ds-kpi__label"><span class="ds-icon-box ds-icon-box--danger" aria-hidden="true">${iconSvg("ic-priority-high", "ds-icon--md")}</span> ${esc(t("kpi.priorityHigh", lang))}</span>
        <span class="ds-kpi__value">${kpis.highPriorityCount}</span>
        <span class="ds-kpi__meta">${esc(t("kpi.priorityHigh.meta", lang))}</span>
      </a>
      <a class="ds-kpi ds-kpi--warning" href="/worklist?domain=${domainParam}&completeness=incomplete" data-testid="kpi-completeness">
        <span class="ds-kpi__label"><span class="ds-icon-box ds-icon-box--warning" aria-hidden="true">${iconSvg("ic-warning", "ds-icon--md")}</span> ${esc(t("kpi.completeness", lang))}</span>
        <span class="ds-kpi__value">${kpis.incompleteCount}</span>
        <span class="ds-kpi__meta">${esc(t("kpi.completeness.meta", lang))}</span>
      </a>
      <a class="ds-kpi" href="/worklist?domain=${domainParam}&orientation=adapt" data-testid="kpi-orientation">
        <span class="ds-kpi__label"><span class="ds-icon-box" aria-hidden="true">${iconSvg("ic-compass", "ds-icon--md")}</span> ${esc(t("kpi.orientation", lang))}</span>
        <span class="ds-kpi__value">${kpis.adaptationSuggestedCount}</span>
        <span class="ds-kpi__meta">${esc(t("kpi.orientation.meta", lang))}</span>
      </a>
    </div>

    <!-- Filter Toolbar (Collapsible on Mobile, Always Open on Desktop) -->
    <details class="ds-toolbar-drawer" open data-mobile-collapsible="true" data-testid="worklist-filters-drawer">
      <summary class="ds-toolbar-drawer__summary" data-testid="btn_toggle_filters">
        <span class="ds-toolbar-drawer__title">${iconSvg("ic-search", "ds-icon--sm")} ${lang === "fr" ? "Rechercher & filtrer les dossiers" : "Search & filter records"}</span>
        <span class="ds-cluster" style="gap:var(--ds-space-2)">
          <span class="ds-badge ds-badge--neutral ds-badge--sm">${cards.length} ${lang === "fr" ? "dossier(s)" : "record(s)"}</span>
          <svg class="ds-icon ds-icon--md ds-toolbar-drawer__chevron" aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>
        </span>
      </summary>
      <form class="ds-toolbar" method="get" action="/worklist" role="search" data-testid="worklist-filters">
        <input type="hidden" name="domain" value="${esc(session.domain)}">
        <div class="ds-field">
          <label class="ds-label" for="q">Rechercher un dossier</label>
          <input id="q" name="q" class="ds-input" type="search" value="${esc(filter.query ?? "")}" placeholder="Nom, #ID, organe, spécialité…" data-testid="input-search">
        </div>
        <div class="ds-field">
          <label class="ds-label" for="f-compl">Complétude</label>
          <select id="f-compl" name="completeness" class="ds-select" data-autosubmit="true" data-testid="select-completeness">
            <option value="all" ${(filter.completeness ?? "all") === "all" ? "selected" : ""}>Tous les dossiers</option>
            <option value="incomplete" ${filter.completeness === "incomplete" ? "selected" : ""}>Incomplets uniquement</option>
            <option value="complete" ${filter.completeness === "complete" ? "selected" : ""}>Complets uniquement</option>
          </select>
        </div>
        <div class="ds-field">
          <label class="ds-label" for="f-prio">Priorité</label>
          <select id="f-prio" name="priority" class="ds-select" data-autosubmit="true" data-testid="select-priority">
            <option value="all" ${(filter.priority ?? "all") === "all" ? "selected" : ""}>Toutes priorités</option>
            <option value="high" ${filter.priority === "high" ? "selected" : ""}>Priorité haute</option>
            <option value="medium" ${filter.priority === "medium" ? "selected" : ""}>Priorité modérée</option>
            <option value="low" ${filter.priority === "low" ? "selected" : ""}>Priorité standard</option>
          </select>
        </div>
        <div class="ds-field">
          <label class="ds-label" for="f-view">Regroupement</label>
          <select id="f-view" name="viewMode" class="ds-select" data-autosubmit="true" data-testid="select-viewmode">
            <option value="patients" ${(filter.viewMode ?? "patients") === "patients" ? "selected" : ""}>Par patient longitudinal</option>
            <option value="rcp" ${filter.viewMode === "rcp" ? "selected" : ""}>Par fiche RCP</option>
          </select>
        </div>
        <div class="ds-field">
          <label class="ds-label" for="f-display">Affichage</label>
          <select id="f-display" name="display" class="ds-select" data-autosubmit="true" data-testid="select-displaymode">
            <option value="table" ${(filter.displayMode ?? "table") === "table" ? "selected" : ""}>Table</option>
            <option value="cards" ${filter.displayMode === "cards" ? "selected" : ""}>Cartes</option>
          </select>
        </div>
        <div class="ds-toolbar__end">
          <button type="submit" class="ds-btn ds-btn--tonal">${iconSvg("ic-search")} Filtrer</button>
          <a class="ds-btn ds-btn--ghost" href="/worklist?domain=${domainParam}">Réinitialiser</a>
        </div>
      </form>
    </details>

    ${
      cards.length === 0
        ? `<div class="ds-empty" data-testid="empty-worklist">
            <span class="ds-empty__icon">${iconSvg("ic-folder-open")}</span>
            <span class="ds-empty__title">Aucun dossier correspondant aux critères</span>
            <p class="ds-empty__text">Importez des comptes rendus PDF ou réinitialisez les filtres de la worklist.</p>
            <a class="ds-btn ds-btn--primary" href="/ingest?domain=${domainParam}">${iconSvg("ic-upload")} Importer des PDF</a>
          </div>`
        : filter.displayMode === "cards"
          ? cardsGridHtml
          : tableWrapHtml
    }
    ${deleteDialogsHtml}
  `;

  return renderLayout({
    title: t("nav.worklist", lang),
    activeNav: "worklist",
    breadcrumbs: [{ label: t("nav.worklist", lang) }],
    session,
    queueStats,
    queueJobs,
    bodyHtml,
  });
}

export function renderSectionDetailsPartial(
  sec: DossierSectionView,
  filename: string,
  domain: string,
  editing = false,
  expertMode = false,
  missingItemsState?: PatientDossierView["missingItemsState"],
  isProcessingSection = false,
): string {
  const domainParam = encodeURIComponent(domain);
  const fileParam = encodeURIComponent(filename);
  const secParam = encodeURIComponent(sec.name);

  if (editing) {
    const renderEditControl = (f: DossierSectionView["fields"][number]): string => {
      const inputId = `inp-${esc(sec.name)}-${esc(f.key)}`;
      const unitSuffix = f.unit ? ` <span class="ds-text-muted">(${esc(f.unit)})</span>` : "";

      if (f.inputType === "exams_list") {
        const items =
          f.examItems && f.examItems.length > 0
            ? f.examItems
            : [
                {
                  exam_name: "",
                  exam_date: null,
                  exam_type: "CT" as const,
                  exam_result: null,
                },
              ];
        const rowsHtml = items
          .map(
            (
              ex,
              idx,
            ) => `<div class="ds-subcard" data-exam-row="${idx}" style="margin-bottom:var(--ds-space-2)">
              <div class="ds-kv-grid">
                <div class="ds-field">
                  <label class="ds-label" for="${inputId}-name-${idx}">Nom de l'examen #${idx + 1}</label>
                  <input class="ds-input" type="text" id="${inputId}-name-${idx}" name="exam_name_${idx}" value="${esc(ex.exam_name)}" data-field-type="text" placeholder="Ex : Scanner TAP injecté">
                </div>
                <div class="ds-field">
                  <label class="ds-label" for="${inputId}-type-${idx}">Modalité (Type)</label>
                  <select class="ds-select" id="${inputId}-type-${idx}" name="exam_type_${idx}" data-field-type="select">
                    <option value="CT" ${ex.exam_type === "CT" ? "selected" : ""}>CT — Scanner (TDM)</option>
                    <option value="MRI" ${ex.exam_type === "MRI" ? "selected" : ""}>MRI — IRM</option>
                    <option value="PET" ${ex.exam_type === "PET" ? "selected" : ""}>PET — TEP-TDM</option>
                    <option value="EUS" ${ex.exam_type === "EUS" ? "selected" : ""}>EUS — Écho-endoscopie</option>
                  </select>
                </div>
                <div class="ds-field">
                  <label class="ds-label" for="${inputId}-date-${idx}">Date de l'examen</label>
                  <input class="ds-input" type="date" id="${inputId}-date-${idx}" name="exam_date_${idx}" value="${esc(ex.exam_date ?? "")}" data-field-type="date">
                </div>
              </div>
              <div class="ds-field" style="margin-top:var(--ds-space-2)">
                <label class="ds-label" for="${inputId}-res-${idx}">Conclusion / Résultat</label>
                <textarea class="ds-textarea" rows="2" id="${inputId}-res-${idx}" name="exam_result_${idx}" data-field-type="textarea" placeholder="Résumé des conclusions radiologiques">${esc(ex.exam_result ?? "")}</textarea>
              </div>
            </div>`,
          )
          .join("");
        return `<div class="ds-field" data-exams-list-container="${esc(sec.name)}">
          <span class="ds-label">${esc(f.label)}</span>
          <div data-exams-rows>${rowsHtml}</div>
          <button type="button" class="ds-btn ds-btn--tonal ds-btn--sm" data-add-exam-row="${esc(sec.name)}" style="align-self:flex-start;margin-top:var(--ds-space-1)">
            ${iconSvg("ic-plus")} Ajouter un examen
          </button>
        </div>`;
      }

      if (f.inputType === "chemotherapy_list") {
        const items =
          f.chemoItems && f.chemoItems.length > 0
            ? f.chemoItems
            : [
                {
                  chemotherapy_name: "",
                  chemotherapy_start_date: null,
                  chemotherapy_end_date: null,
                  chemotherapy_tolerance: "Good" as const,
                },
              ];
        const rowsHtml = items
          .map(
            (
              ch,
              idx,
            ) => `<div class="ds-subcard" data-chemo-row="${idx}" style="margin-bottom:var(--ds-space-2)">
              <div class="ds-kv-grid">
                <div class="ds-field">
                  <label class="ds-label" for="${inputId}-name-${idx}">Protocole / Molécule #${idx + 1}</label>
                  <input class="ds-input" type="text" id="${inputId}-name-${idx}" name="chemotherapy_name_${idx}" value="${esc(ch.chemotherapy_name)}" data-field-type="text" placeholder="Ex : FOLFIRINOX">
                </div>
                <div class="ds-field">
                  <label class="ds-label" for="${inputId}-tol-${idx}">Tolérance</label>
                  <select class="ds-select" id="${inputId}-tol-${idx}" name="chemotherapy_tolerance_${idx}" data-field-type="select">
                    <option value="Good" ${ch.chemotherapy_tolerance === "Good" ? "selected" : ""}>Bonne (Good)</option>
                    <option value="Medium" ${ch.chemotherapy_tolerance === "Medium" ? "selected" : ""}>Moyenne / Modérée (Medium)</option>
                    <option value="Poor" ${ch.chemotherapy_tolerance === "Poor" ? "selected" : ""}>Mauvaise / Toxicité (Poor)</option>
                  </select>
                </div>
                <div class="ds-field">
                  <label class="ds-label" for="${inputId}-start-${idx}">Date de début</label>
                  <input class="ds-input" type="date" id="${inputId}-start-${idx}" name="chemotherapy_start_date_${idx}" value="${esc(ch.chemotherapy_start_date ?? "")}" data-field-type="date">
                </div>
                <div class="ds-field">
                  <label class="ds-label" for="${inputId}-end-${idx}">Date de fin</label>
                  <input class="ds-input" type="date" id="${inputId}-end-${idx}" name="chemotherapy_end_date_${idx}" value="${esc(ch.chemotherapy_end_date ?? "")}" data-field-type="date">
                </div>
              </div>
            </div>`,
          )
          .join("");
        return `<div class="ds-field" data-chemo-list-container="${esc(sec.name)}">
          <span class="ds-label">${esc(f.label)}</span>
          <div data-chemo-rows>${rowsHtml}</div>
          <button type="button" class="ds-btn ds-btn--tonal ds-btn--sm" data-add-chemo-row="${esc(sec.name)}" style="align-self:flex-start;margin-top:var(--ds-space-1)">
            ${iconSvg("ic-plus")} Ajouter une ligne de traitement
          </button>
        </div>`;
      }

      if (
        (f.inputType === "boolean" ||
          f.inputType === "nullable_boolean" ||
          f.inputType === "select" ||
          f.inputType === "integer_select") &&
        f.options &&
        f.options.length > 0
      ) {
        const optsHtml = f.options
          .map(
            (opt) =>
              `<option value="${esc(opt.value)}" ${f.editValue === opt.value ? "selected" : ""}>${esc(opt.label)}</option>`,
          )
          .join("");
        return `<div class="ds-field">
          <label class="ds-label" for="${inputId}">${esc(f.label)}${unitSuffix}</label>
          <select class="ds-select" id="${inputId}" name="${esc(f.key)}" data-field-type="${esc(f.inputType)}">
            ${optsHtml}
          </select>
        </div>`;
      }

      if (f.inputType === "integer" || f.inputType === "float") {
        const minAttr = f.min !== undefined ? ` min="${f.min}"` : "";
        const maxAttr = f.max !== undefined ? ` max="${f.max}"` : "";
        const stepAttr = ` step="${f.step ?? (f.inputType === "integer" ? 1 : 0.5)}"`;
        const modeAttr = f.inputType === "integer" ? "numeric" : "decimal";
        const ph = f.placeholder || (f.nullable ? "Non renseigné (optionnel)" : "");
        return `<div class="ds-field">
          <label class="ds-label" for="${inputId}">${esc(f.label)}${unitSuffix}</label>
          <input class="ds-input" type="number" id="${inputId}" name="${esc(f.key)}" value="${esc(f.editValue)}" data-field-type="${esc(f.inputType)}"${minAttr}${maxAttr}${stepAttr} inputmode="${modeAttr}" placeholder="${esc(ph)}">
        </div>`;
      }

      if (f.inputType === "date") {
        return `<div class="ds-field">
          <label class="ds-label" for="${inputId}">${esc(f.label)}</label>
          <input class="ds-input" type="date" id="${inputId}" name="${esc(f.key)}" value="${esc(f.editValue)}" data-field-type="date">
        </div>`;
      }

      if (f.inputType === "textarea") {
        const ph = f.placeholder || (f.nullable ? "Non renseigné (optionnel)" : "");
        return `<div class="ds-field">
          <label class="ds-label" for="${inputId}">${esc(f.label)}</label>
          <textarea class="ds-textarea" rows="3" id="${inputId}" name="${esc(f.key)}" data-field-type="textarea" placeholder="${esc(ph)}">${esc(f.editValue)}</textarea>
        </div>`;
      }

      const ph =
        f.placeholder ||
        (f.inputType === "string_list"
          ? "Séparer les éléments par une virgule"
          : f.nullable
            ? "Non renseigné (optionnel)"
            : "");
      return `<div class="ds-field">
        <label class="ds-label" for="${inputId}">${esc(f.label)}${unitSuffix}</label>
        <input class="ds-input" type="text" id="${inputId}" name="${esc(f.key)}" value="${esc(f.editValue)}" data-field-type="${esc(f.inputType)}" placeholder="${esc(ph)}">
      </div>`;
    };

    const inputsHtml = sec.fields.map(renderEditControl).join("");

    return `<details class="ds-section is-editing" open id="section-${esc(sec.name)}" data-testid="section-${esc(sec.name)}">
      <summary>
        <span class="ds-section__title">${iconSvg(sec.meta.icon)} ${esc(sec.meta.title)}</span>
        <span class="ds-section__summary">Édition manuelle en cours…</span>
      </summary>
      <form class="ds-section__body" method="post" action="/forms/${fileParam}/sections/${secParam}?domain=${domainParam}" data-ajax-section="section-${esc(sec.name)}">
        ${inputsHtml}
        <div class="ds-section__actions">
          <button type="submit" class="ds-btn ds-btn--primary ds-btn--sm" data-testid="btn_save_section_${esc(sec.name)}">${iconSvg("ic-check")} Enregistrer</button>
          <a class="ds-btn ds-btn--ghost ds-btn--sm" href="/forms/${fileParam}/sections/${secParam}/edit?view=1&domain=${domainParam}" data-edit-section="section-${esc(sec.name)}" data-testid="btn_cancel_section_${esc(sec.name)}">Annuler</a>
        </div>
      </form>
    </details>`;
  }

  const visibleFields = sec.fields.filter((f) => !f.hiddenInReadView);
  const shortFields = visibleFields.filter((f) => !f.isLongText);
  const longFields = visibleFields.filter((f) => f.isLongText);

  const subCardsHtml =
    sec.subCards.length === 0
      ? ""
      : `<div class="ds-subcards">
          ${sec.subCards
            .map(
              (sc) => `<div class="ds-subcard">
                <div class="ds-subcard__header">
                  <span class="ds-subcard__title">${esc(sc.title)}</span>
                  <div class="ds-cluster" style="gap:var(--ds-space-1)">
                    ${sc.badge ? `<span class="ds-badge ds-badge--info ds-badge--sm">${iconSvg("ic-info")} ${esc(sc.badge)}</span>` : ""}
                    ${sc.subtitle ? `<span class="ds-badge ds-badge--neutral ds-badge--sm">${iconSvg("ic-calendar", "ds-icon--xs")} ${esc(sc.subtitle)}</span>` : ""}
                  </div>
                </div>
                <p class="ds-subcard__body">${esc(sc.body)}</p>
              </div>`,
            )
            .join("")}
        </div>`;

  const shortFieldsHtml =
    shortFields.length === 0
      ? ""
      : `<div class="ds-kv-grid">
          ${shortFields
            .map(
              (f) => `<div class="ds-kv${f.isModified ? " ds-kv--manual" : ""}"${
                f.isModified
                  ? ` data-tooltip="Valeur IA initiale : ${esc(f.originalAiValue ?? "Non renseigné")}" tabindex="0" data-testid="field-manual-${esc(f.key)}"`
                  : ""
              }>
                <span class="ds-kv__label">${f.isModified ? `${iconSvg("ic-edit-note", "ds-icon--xs")} ` : ""}${esc(f.label)}</span>
                <span class="ds-kv__value ${f.value === "Non renseigné" || f.value === "Not documented" ? "is-missing" : ""}">${esc(f.value)}</span>
              </div>`,
            )
            .join("")}
        </div>`;

  const longFieldsHtml =
    longFields.length === 0
      ? ""
      : longFields
          .map(
            (f) => `<div class="ds-rationale${f.isModified ? " ds-rationale--manual" : ""}"${
              f.isModified
                ? ` data-tooltip="Valeur IA initiale : ${esc(f.originalAiValue ?? "Non renseigné")}" tabindex="0" data-testid="field-manual-${esc(f.key)}"`
                : ""
            }>
              <span class="ds-rationale__label">${f.isModified ? `${iconSvg("ic-edit-note", "ds-icon--xs")} ` : ""}${esc(f.label)}</span>
              <p class="ds-rationale__text">${esc(f.value)}</p>
            </div>`,
          )
          .join("");

  const canDismissPerItem = (missingItemsState?.allItems.length ?? 0) > 1;
  const missingItemsInteractiveHtml =
    sec.name === "MTDCompleted" && missingItemsState && missingItemsState.allItems.length > 0
      ? `<div class="ds-missing-panel" data-testid="missing-items-panel">
          <div class="ds-cluster" style="justify-content:space-between;margin-bottom:var(--ds-space-2)">
            <span class="ds-label">${iconSvg("ic-warning", "ds-icon--xs")} Éléments manquants détectés (${missingItemsState.visibleItems.length} affiché${missingItemsState.visibleItems.length > 1 ? "s" : ""}${missingItemsState.hiddenItems.length > 0 ? ` · ${missingItemsState.hiddenItems.length} masqué${missingItemsState.hiddenItems.length > 1 ? "s" : ""}` : ""})</span>
            <form method="post" action="/forms/${fileParam}/missing-items?domain=${domainParam}" style="display:inline-flex">
              <input type="hidden" name="hidden" value="${missingItemsState.hideAll ? "false" : "true"}">
              <button type="submit" class="ds-btn ds-btn--ghost ds-btn--sm" data-testid="btn_toggle_missing_list">
                ${iconSvg("ic-eye")} ${missingItemsState.hideAll ? "Afficher la liste" : "Masquer la liste"}
              </button>
            </form>
          </div>
          ${
            !missingItemsState.hideAll
              ? `<ul class="ds-missing-list" data-testid="missing-items-list">
                  ${missingItemsState.visibleItems
                    .map(
                      (
                        item: string,
                        idx: number,
                      ) => `<li class="ds-missing-list__item" data-testid="missing-item-${idx}">
                        <span class="ds-missing-list__text">${iconSvg("ic-warning", "ds-icon--xs")} ${esc(item)}</span>
                        ${
                          canDismissPerItem
                            ? `<form method="post" action="/forms/${fileParam}/missing-items?domain=${domainParam}" style="display:inline-flex">
                                <input type="hidden" name="toggle_item" value="${esc(item)}">
                                <button type="submit" class="ds-btn ds-btn--ghost ds-btn--sm" title="Masquer cet élément" data-testid="btn_dismiss_missing_${idx}">
                                  Masquer
                                </button>
                              </form>`
                            : ""
                        }
                      </li>`,
                    )
                    .join("")}
                </ul>`
              : `<p class="ds-small ds-muted">La liste des éléments manquants est actuellement masquée pour ce dossier.</p>`
          }
          ${
            missingItemsState.hiddenItems.length > 0
              ? `<details class="ds-missing-dismissed" style="margin-top:var(--ds-space-2)">
                  <summary class="ds-small ds-muted" style="cursor:pointer">${missingItemsState.hiddenItems.length} élément(s) masqué(s) manuellement</summary>
                  <ul class="ds-missing-list" style="margin-top:var(--ds-space-1)">
                    ${missingItemsState.hiddenItems
                      .map(
                        (item: string) => `<li class="ds-missing-list__item is-dismissed">
                          <span class="ds-missing-list__text" style="text-decoration:line-through;opacity:0.7">${esc(item)}</span>
                          <form method="post" action="/forms/${fileParam}/missing-items?domain=${domainParam}" style="display:inline-flex">
                            <input type="hidden" name="toggle_item" value="${esc(item)}">
                            <button type="submit" class="ds-btn ds-btn--ghost ds-btn--sm">Restaurer</button>
                          </form>
                        </li>`,
                      )
                      .join("")}
                  </ul>
                </details>`
              : ""
          }
        </div>`
      : "";

  const emptyHtml =
    shortFields.length === 0 &&
    longFields.length === 0 &&
    sec.subCards.length === 0 &&
    !missingItemsInteractiveHtml
      ? `<p class="ds-small ds-muted">Aucune donnée extraite pour cette rubrique.</p>`
      : "";

  const refsHtml =
    sec.references.length === 0
      ? ""
      : `<ul class="ds-refs" aria-label="Références">
          ${sec.references
            .map((r) => {
              const pageNum = r.page ? String(r.page).replace(/[^\d]/g, "") || "1" : "1";
              const refHref = resolveCitationPdfHref(
                r.name,
                r.page,
                domain as ClinicalDomain,
                filename,
              );
              return `<li class="ds-ref"><a class="ds-ref__source ds-ref__link" href="${refHref}" target="_blank" rel="noopener" title="Ouvrir ${esc(r.name)} à la page ${esc(pageNum)}">${iconSvg("ic-book", "ds-icon--xs")} ${esc(r.name)}${r.page ? ` p. ${esc(r.page)}` : ""}</a>${r.excerpt ? `<span class="ds-ref__quote">« ${esc(r.excerpt)} »</span>` : ""}</li>`;
            })
            .join("")}
        </ul>`;

  // Discreet M3 floating popover in the bottom-right footer of the section
  const reasoningPopoverHtml = sec.reasoningThinking
    ? `<details class="ds-popover" data-testid="reasoning-${esc(sec.name)}">
        <summary class="ds-popover__trigger" title="Afficher le raisonnement IA d'extraction">
          ${iconSvg("ic-sparkle", "ds-icon--xs")} Réflexion IA
        </summary>
        <div class="ds-popover__panel" role="dialog" aria-label="Réflexion IA — ${esc(sec.meta.title)}">
          <div class="ds-popover__title">${iconSvg("ic-sparkle", "ds-icon--xs")} Réflexion IA — ${esc(sec.meta.title)}</div>
          <div>${esc(sec.reasoningThinking)}</div>
        </div>
      </details>`
    : "";

  const userPromptPopoverHtml =
    expertMode && sec.userPrompt
      ? `<details class="ds-popover" data-testid="prompt-${esc(sec.name)}">
          <summary class="ds-popover__trigger" title="Prompt utilisateur d'extraction">
            ${iconSvg("ic-chat", "ds-icon--xs")} Prompt
          </summary>
          <div class="ds-popover__panel" role="dialog" aria-label="Prompt utilisateur — ${esc(sec.meta.title)}">
            <div class="ds-popover__title">${iconSvg("ic-chat", "ds-icon--xs")} Prompt utilisateur d'extraction</div>
            <div>${esc(sec.userPrompt)}</div>
          </div>
        </details>`
      : "";

  const manualDiffPopoverHtml =
    expertMode && sec.manualDiffs.length > 0
      ? `<details class="ds-popover" data-testid="trace-${esc(sec.name)}">
          <summary class="ds-popover__trigger" title="Trace IA vs Humain">
            ${iconSvg("ic-search", "ds-icon--xs")} Trace (${sec.manualDiffs.length})
          </summary>
          <div class="ds-popover__panel" role="dialog" aria-label="Trace IA vs Humain">
            <div class="ds-popover__title">${iconSvg("ic-edit-note", "ds-icon--xs")} Trace IA vs Humain</div>
            <div>${sec.manualDiffs
              .map((d) => `${d.label} : IA « ${d.aiValue} » → Humain « ${d.humanValue} »`)
              .join("\n")}</div>
          </div>
        </details>`
      : "";

  // Collapsed by default (no `open` attribute) as requested by the user
  const secToneClass =
    sec.name === "MTDCompleted"
      ? sec.summaryText.toLowerCase().includes("incomplet") ||
        sec.summaryText.toLowerCase().includes("manquant")
        ? "ds-section--orange"
        : "ds-section--green"
      : "";
  return `<details class="ds-section ${sec.isManual ? "ds-section--manual" : ""} ${secToneClass}${isProcessingSection ? " is-processing" : ""}" id="section-${esc(sec.name)}" data-testid="section-${esc(sec.name)}"${isProcessingSection ? ' data-processing-active="true"' : ""}>
    <summary>
      <span class="ds-section__title">${iconSvg(sec.meta.icon)} ${esc(sec.meta.title)}</span>
      ${
        isProcessingSection
          ? `<span class="ds-badge ds-badge--processing ds-badge--sm" data-testid="badge-processing-section-${esc(sec.name)}"><span class="ds-spinner" aria-hidden="true"></span> Analyse en cours…</span>`
          : ""
      }
      ${
        sec.isManual
          ? `<span class="ds-badge ds-badge--manual ds-badge--sm" data-testid="badge-manual-edit">${iconSvg("ic-edit-note")} Modifié manuellement</span>`
          : ""
      }
      <span class="ds-section__summary">${esc(sec.summaryText)}</span>
    </summary>
    <div class="ds-section__body">
      ${emptyHtml}
      ${missingItemsInteractiveHtml}
      ${shortFieldsHtml}
      ${subCardsHtml}
      ${longFieldsHtml}
      ${refsHtml}
      ${
        sec.isManual && sec.manualMeta
          ? `<p class="ds-section__provenance">Modifié manuellement par ${esc(sec.manualMeta.edited_by ?? "Clinicien")} · protégé lors des relances IA</p>`
          : ""
      }
      <div class="ds-section__actions">
        ${
          sec.meta.editable
            ? `<a class="ds-btn ds-btn--secondary ds-btn--sm" href="/forms/${fileParam}/sections/${secParam}/edit?domain=${domainParam}" data-edit-section="section-${esc(sec.name)}" data-testid="btn_edit_section_${esc(sec.name)}">${iconSvg("ic-edit")} Modifier</a>`
            : ""
        }
        ${
          sec.isManual
            ? `<form method="post" action="/forms/${fileParam}/sections/${secParam}/rollback?domain=${domainParam}" data-ajax-section="section-${esc(sec.name)}" style="display:inline-flex">
                <button type="submit" class="ds-btn ds-btn--ghost ds-btn--sm ds-btn--rollback" data-tooltip="Annuler la modification manuelle et restaurer la valeur IA initiale" data-testid="btn_rollback_section_${esc(sec.name)}">
                  ${iconSvg("ic-undo")} Rétablir
                </button>
              </form>`
            : ""
        }
        <form method="post" action="/forms/${fileParam}/sections/${secParam}/rerun?domain=${domainParam}" style="display:inline-flex">
          <input type="hidden" name="preserve_manual_edits" value="true">
          <button type="submit" class="ds-btn ds-btn--ghost ds-btn--sm" data-tooltip="Relance l'extraction IA de cette rubrique (les modifications manuelles sont préservées)" data-testid="btn_rerun_section_${esc(sec.name)}">
            ${iconSvg("ic-refresh")} Relancer
          </button>
        </form>
        <div class="ds-cluster" style="margin-left:auto;gap:var(--ds-space-2)">
          ${userPromptPopoverHtml}
          ${manualDiffPopoverHtml}
          ${reasoningPopoverHtml}
          ${
            sec.durationSec !== null
              ? `<span class="ds-section__duration">${iconSvg("ic-clock", "ds-icon--xs")} ${formatDurationMinSec(sec.durationSec)}</span>`
              : ""
          }
        </div>
      </div>
    </div>
  </details>`;
}

export interface AgendaDossierNavContext {
  position: number;
  total: number;
  sessionDate: string;
  prevPatientId: string | null;
  prevPatientName: string | null;
  prevFilename?: string | null;
  nextPatientId: string | null;
  nextPatientName: string | null;
  nextFilename?: string | null;
}

export function renderDossierPage(
  dossier: PatientDossierView,
  session: UserSession,
  queueStats: QueueStats,
  queueJobs: QueueJobItem[],
  chatHistory: Array<{ question: string; reply: ChatReply }> = [],
  editingSection?: string,
  agendaNav?: AgendaDossierNavContext,
): string {
  const lang = session.language;
  const domainParam = encodeURIComponent(session.domain);
  const baseTargetUrl = dossier.patientId
    ? `/patients/${encodeURIComponent(dossier.patientId)}`
    : `/forms/${encodeURIComponent(dossier.currentForm.file)}`;

  const upcomingHref = dossier.patientId
    ? `/ingest?domain=${domainParam}&patientId=${encodeURIComponent(dossier.patientId)}`
    : `/ingest?domain=${domainParam}`;

  const timelineHtml = `${dossier.timeline
    .map((step) => {
      const markerCls =
        step.priorityLevel === "high"
          ? "ds-timeline__marker--high"
          : step.priorityLevel === "medium"
            ? "ds-timeline__marker--medium"
            : "ds-timeline__marker--low";
      const markerIcon =
        step.priorityLevel === "high"
          ? "ic-priority-high"
          : step.priorityLevel === "medium"
            ? "ic-trend-up"
            : "ic-check";
      const stepTone =
        step.priorityLevel === "high"
          ? "red"
          : step.priorityLevel === "medium"
            ? "orange"
            : "green";
      return `<li class="ds-timeline__item">
        <a class="ds-timeline__link ds-timeline__link--${stepTone}" href="${baseTargetUrl}?file=${encodeURIComponent(step.file)}&domain=${domainParam}${agendaNav ? "&from=agenda" : ""}" ${step.isCurrent ? 'aria-current="step"' : ""}>
          <span class="ds-timeline__marker ${markerCls}" aria-hidden="true">${iconSvg(markerIcon, "ds-icon--xs")}</span>
          <span class="ds-timeline__content">
            <span class="ds-timeline__date">${esc(step.mdtDate)} ${step.isLatest ? iconSvg("ic-star", "ds-icon--xs") : ""}</span>
            <span class="ds-timeline__meta">${esc(step.priorityLabel)} · ${esc(step.orientationLabel)}</span>
          </span>
        </a>
      </li>`;
    })
    .join("")}
    <li class="ds-timeline__item ds-timeline__item--upcoming">
      <a class="ds-timeline__link ds-timeline__link--upcoming" href="${upcomingHref}" data-testid="timeline-upcoming">
        <span class="ds-timeline__marker ds-timeline__marker--upcoming" aria-hidden="true">${iconSvg("ic-add", "ds-icon--xs")}</span>
        <span class="ds-timeline__content">
          <span class="ds-timeline__date">${lang === "fr" ? "Prochaine séance" : "Next MDT session"}</span>
          <span class="ds-timeline__meta">${lang === "fr" ? "Non programmée · Importer PDF" : "Unscheduled · Upload PDF"}</span>
        </span>
      </a>
    </li>`;

  const markersHtml = dossier.synopticMarkers
    .map((m) => {
      const deltaHtml = m.delta
        ? ` <span class="ds-delta ds-delta--${m.delta.direction}">${iconSvg(m.delta.icon, "ds-icon--xs")} ${esc(m.delta.deltaText)}</span>`
        : "";
      return `<div class="ds-markers__item">
        <dt>${esc(m.label)}</dt>
        <dd class="${m.isMissing ? "is-missing" : ""}">${esc(m.value)}${deltaHtml}</dd>
      </div>`;
    })
    .join("");

  const clinicalSections = dossier.sections.filter(
    (s) => s.meta.tab === "clinical" && (s.name !== "PatientMDTFormCheck" || session.expertMode),
  );
  const opinionSections = dossier.sections.filter(
    (s) => s.meta.tab === "opinions" && (s.name !== "PatientMDTFormCheck" || session.expertMode),
  );

  const activeSectionNames = new Set(
    queueJobs
      .filter(
        (j) =>
          j.filename === dossier.currentForm.file &&
          (j.status === "RUNNING" || j.status === "PENDING") &&
          j.section,
      )
      .map((j) => j.section as string),
  );
  const proc = deriveFormProcessingState(
    dossier.currentForm.processingStatus,
    dossier.currentForm.processingStep,
    dossier.currentForm.processingProgressPct,
    dossier.currentForm.file,
    queueJobs,
    queueStats,
    lang,
    dossier.timeline.map((tStep) => tStep.file),
  );
  const dossierDelInfo = formatDeleteDialogPatientInfo(
    dossier.patientName,
    dossier.patientId ?? dossier.currentForm.file,
    dossier.currentForm.file,
    dossier.patientId,
    domainParam,
    dossier.patientId ? "patients" : "rcp",
  );

  // Group clinical sections by Clinical Pole with clean pole headings
  const poleIcons: Record<string, string> = {
    clinical: "ic-stethoscope",
    paraclinical: "ic-radiation",
    treatments: "ic-pill",
    identity: "ic-folder",
    synthesis: "ic-compass",
  };
  let lastPole = "";
  const sectionsHtml = clinicalSections
    .map((s) => {
      let heading = "";
      if (s.meta.pole !== lastPole) {
        lastPole = s.meta.pole;
        const pIcon = poleIcons[s.meta.pole] ?? "ic-stethoscope";
        heading = `<div class="ds-pole-heading">${iconSvg(pIcon, "ds-icon--xs")} ${esc(s.meta.poleLabel)}</div>`;
      }
      return `${heading}${renderSectionDetailsPartial(
        s,
        dossier.currentForm.file,
        session.domain,
        editingSection === s.name,
        session.expertMode,
        s.name === "MTDCompleted" ? dossier.missingItemsState : undefined,
        activeSectionNames.has(s.name),
      )}`;
    })
    .join("");

  const opinionSectionsHtml = opinionSections
    .map((s) =>
      renderSectionDetailsPartial(
        s,
        dossier.currentForm.file,
        session.domain,
        editingSection === s.name,
        session.expertMode,
        s.name === "MTDCompleted" ? dossier.missingItemsState : undefined,
        activeSectionNames.has(s.name),
      ),
    )
    .join("");

  // Collapsible CareOrientationProposal card (collapsed by default) with M3 Tonal surface
  const careTone =
    dossier.priorityBadge.level === "high"
      ? "red"
      : dossier.careProposal.careAdaptationSuggested
        ? "orange"
        : "green";
  const careOrientationHtml = dossier.careProposal.clinicalRationale
    ? `<details class="ds-section ds-section--${careTone}" id="section-CareOrientationProposal" data-testid="section-CareOrientationProposal">
        <summary>
          <span class="ds-section__title">${iconSvg("ic-compass")} Proposition d'orientation pré-RCP</span>
          <span class="ds-badge ${dossier.orientationBadge.badgeClass} ds-badge--sm">${iconSvg(dossier.orientationBadge.icon)} ${esc(dossier.orientationBadge.label)}</span>
          <span class="ds-section__summary">${esc(dossier.careProposal.proposedCareType ?? dossier.orientationBadge.label)}</span>
        </summary>
        <div class="ds-section__body">
          ${
            dossier.careProposal.proposedCareType
              ? `<div class="ds-rationale ds-rationale--orientation">
                  <span class="ds-rationale__label">Modalité de prise en charge proposée</span>
                  <div class="ds-rationale__text">${esc(dossier.careProposal.proposedCareType)}</div>
                </div>`
              : ""
          }
          <div class="ds-rationale ds-rationale--orientation">
            <span class="ds-rationale__label">${iconSvg("ic-compass", "ds-icon--xs")} Argumentaire clinique pré-RCP</span>
            <div class="ds-rationale__text">${esc(dossier.careProposal.clinicalRationale)}</div>
          </div>
          <p class="ds-disclaimer">${esc(t("disclaimer.ml", lang))}</p>
          <div class="ds-section__actions">
            <form method="post" action="/forms/${encodeURIComponent(dossier.currentForm.file)}/sections/CareOrientationProposal/rerun?domain=${domainParam}" style="display:inline-flex">
              <input type="hidden" name="preserve_manual_edits" value="true">
              <button type="submit" class="ds-btn ds-btn--ghost ds-btn--sm">
                ${iconSvg("ic-refresh")} Relancer la synthèse
              </button>
            </form>
            <div class="ds-cluster" style="margin-left:auto;gap:var(--ds-space-2)">
              ${
                dossier.careProposal.reasoningThinking
                  ? `<details class="ds-popover" data-testid="reasoning-CareOrientationProposal">
                      <summary class="ds-popover__trigger">${iconSvg("ic-sparkle", "ds-icon--xs")} Réflexion IA</summary>
                      <div class="ds-popover__panel" role="dialog" aria-label="Réflexion IA — Orientation pré-RCP">
                        <div class="ds-popover__title">${iconSvg("ic-sparkle", "ds-icon--xs")} Réflexion IA — Orientation pré-RCP</div>
                        <div>${esc(dossier.careProposal.reasoningThinking)}</div>
                      </div>
                    </details>`
                  : ""
              }
              ${
                dossier.careProposal.durationSec !== null
                  ? `<span class="ds-section__duration">${iconSvg("ic-clock", "ds-icon--xs")} ${formatDurationMinSec(dossier.careProposal.durationSec)}</span>`
                  : ""
              }
            </div>
          </div>
        </div>
      </details>`
    : "";

  const opinionsHtml =
    dossier.opinions.length === 0
      ? `<div class="ds-empty"><span class="ds-empty__title">Aucun avis spécialisé disponible pour cette séance</span></div>`
      : dossier.opinions
          .map((op) => {
            const prio = derivePriorityBadgeInfo(op.priorityLevel, lang, true);
            const suggestionsHtml = op.suggestions
              .map(
                (
                  s,
                  sIdx,
                ) => `<div class="ds-subcard ds-opinion-proposal" style="gap:var(--ds-space-2)">
                  <div class="ds-subcard__header">
                    <span class="ds-subcard__title">Proposition ${sIdx + 1}</span>
                    ${
                      s.why
                        ? `<div class="ds-hovercard" tabindex="0">
                            <span class="ds-badge ds-badge--info ds-badge--sm">${iconSvg("ic-info", "ds-icon--xs")} Justification clinique</span>
                            <div class="ds-hovercard__panel" role="tooltip">
                              <span class="ds-hovercard__title">${iconSvg("ic-info", "ds-icon--xs")} Justification clinique — Proposition ${sIdx + 1}</span>
                              <p>${esc(s.why)}</p>
                            </div>
                          </div>`
                        : ""
                    }
                  </div>
                  <p class="ds-opinion-proposal__text">${esc(s.suggestion)}</p>
                  ${
                    s.references.length > 0
                      ? `<ul class="ds-refs" aria-label="Références">
                          ${s.references
                            .map((r) => {
                              const pageNum = r.page
                                ? String(r.page).replace(/[^\d]/g, "") || "1"
                                : "1";
                              const refHref = resolveCitationPdfHref(
                                r.name,
                                r.page,
                                session.domain,
                                dossier.currentForm.file,
                              );
                              return `<li class="ds-ref"><a class="ds-ref__source ds-ref__link" href="${refHref}" target="_blank" rel="noopener" title="Ouvrir ${esc(r.name)} à la page ${esc(pageNum)}">${iconSvg("ic-book", "ds-icon--xs")} ${esc(r.name)}${r.page ? ` p. ${esc(r.page)}` : ""}</a>${r.excerpt ? `<span class="ds-ref__quote">« ${esc(r.excerpt)} »</span>` : ""}</li>`;
                            })
                            .join("")}
                        </ul>`
                      : ""
                  }
                </div>`,
              )
              .join("");

            const opReasoningPopoverHtml = op.reasoningThinking
              ? `<details class="ds-popover" data-testid="opinion-reasoning-${esc(op.agentKey)}">
                  <summary class="ds-popover__trigger">${iconSvg("ic-sparkle", "ds-icon--xs")} Réflexion IA</summary>
                  <div class="ds-popover__panel" role="dialog" aria-label="Réflexion IA — ${esc(op.agentLabel)}">
                    <div class="ds-popover__title">${iconSvg("ic-sparkle", "ds-icon--xs")} Réflexion IA — ${esc(op.agentLabel)}</div>
                    <div>${esc(op.reasoningThinking)}</div>
                  </div>
                </details>`
              : "";

            // Collapsed by default as requested by the user
            return `<details class="ds-opinion" data-testid="opinion-${esc(op.agentKey)}">
              <summary>
                <span class="ds-section__title">${iconSvg(op.agentIcon)} Avis — ${esc(op.agentLabel)}</span>
                <span class="ds-badge ${prio.badgeClass} ds-badge--sm">${iconSvg(prio.icon)} ${esc(prio.label)}</span>
                <span class="ds-badge ds-badge--neutral ds-badge--sm">${iconSvg("ic-layers")} ${op.suggestions.length} proposition(s)</span>
                <span class="ds-section__summary">${esc(op.suggestions[0]?.suggestion ?? op.whyRelevant)}</span>
              </summary>
              <div class="ds-opinion__body">
                ${
                  op.whyRelevant
                    ? `<div class="ds-rationale">
                        <span class="ds-rationale__label">Pertinence clinique</span>
                        <p class="ds-rationale__text">${esc(op.whyRelevant)}</p>
                      </div>`
                    : ""
                }
                <div class="ds-stack" style="gap:var(--ds-space-3)">
                  ${suggestionsHtml}
                </div>
                <div class="ds-section__actions">
                  <span class="ds-disclaimer" style="border:0;padding:0">${esc(t("disclaimer.ml", lang))}</span>
                  <div class="ds-cluster" style="margin-left:auto;gap:var(--ds-space-2)">
                    ${opReasoningPopoverHtml}
                    ${
                      op.executionSeconds !== null && op.executionSeconds !== undefined
                        ? `<span class="ds-section__duration">${iconSvg("ic-clock", "ds-icon--xs")} ${formatDurationMinSec(op.executionSeconds)}</span>`
                        : ""
                    }
                  </div>
                </div>
              </div>
            </details>`;
          })
          .join("");

  const quickPrompts = getDomainQuickPrompts(session.domain, "dossier", lang);

  // Build available clinical specialties + Administrative agent for the Assistant IA tab
  const specialistAgents = dossier.agents.filter((a) => {
    const lower = a.name.toLowerCase();
    return (
      (lower.includes("expert") || lower === "administrative") &&
      !lower.includes("ressource") &&
      !lower.includes("summary")
    );
  });
  const hasAdminInAgents = specialistAgents.some((a) => a.name.toLowerCase() === "administrative");
  const adminPresentation = getAgentPresentation("Administrative", lang);
  const assistantAgents =
    specialistAgents.length > 0
      ? hasAdminInAgents
        ? specialistAgents
        : [
            ...specialistAgents,
            {
              name: "Administrative",
              label: adminPresentation.label,
              icon: adminPresentation.icon,
              role: "Extraction administrative & clinique",
              description: "",
              guidelines: [],
            },
          ]
      : [
          ...dossier.specialties.map((s) => ({
            name: s.name,
            label: s.label,
            icon: s.icon,
            role: "",
            description: "",
            guidelines: [],
          })),
          {
            name: "Administrative",
            label: adminPresentation.label,
            icon: adminPresentation.icon,
            role: "Extraction administrative & clinique",
            description: "",
            guidelines: [],
          },
        ];
  const defaultAgentName =
    assistantAgents.find((a) => a.name.toLowerCase().includes("expert"))?.name ??
    assistantAgents[0]?.name ??
    "Administrative";

  const dossierTone = deriveRcpTone(
    dossier.priorityBadge.level,
    dossier.completenessBadge.status === "complete",
  );
  const displayDob = dossier.dateBirth ?? extractDobFromPatientId(dossier.patientId);
  const showShortPatientCode =
    Boolean(dossier.patientId) &&
    !dossier.patientId?.includes("_") &&
    !dossier.patientId?.toLowerCase().endsWith(".pdf");

  const dossierChatDrawerHtml = renderAiChatDrawer({
    drawerTitle: "Assistant clinique",
    drawerSubtitle: `${dossier.patientName}${showShortPatientCode ? ` · #${dossier.patientId}` : ""}`,
    fabLabel: "Assistant IA",
    formAction: `${baseTargetUrl}/chat?domain=${domainParam}`,
    formTestId: "chat",
    logId: "dossier-chat-log",
    inputId: "chat-input",
    inputTestId: "input-chat-question",
    inputPlaceholder: "Poser une question sur ce dossier…",
    inputLabel: "Votre question sur le dossier",
    submitTestId: "btn_chat_send",
    submitLabel: "Envoyer",
    welcomeMessage: `Posez une question sur le dossier de ${dossier.patientName} pour obtenir une synthèse sourcée à partir des comptes rendus et des recommandations.`,
    chatHistory,
    quickPrompts,
    quickPromptsHeading: "Questions suggérées",
    quickPromptsTestId: "quick-prompt-chips",
    hiddenFields: { filename: dossier.currentForm.file },
    scopeConfig: {
      rcpCount: dossier.rcpCount,
      activeFormLabel: dossier.currentForm.mdtDate ?? dossier.currentForm.file,
    },
    agents: assistantAgents,
    defaultAgentName,
    domain: session.domain,
  });

  const agendaNavHtml = agendaNav
    ? `<nav class="ds-card ds-agenda-dossier-nav" aria-label="Navigation de l'ordre du jour RCP" data-testid="agenda-dossier-nav">
        <div class="ds-agenda-dossier-nav__prev">
          ${
            agendaNav.prevPatientId
              ? `<a class="ds-btn ds-btn--secondary ds-btn--sm" href="/patients/${encodeURIComponent(agendaNav.prevPatientId)}?domain=${domainParam}&from=agenda${agendaNav.prevFilename ? `&file=${encodeURIComponent(agendaNav.prevFilename)}` : ""}" aria-label="Dossier précédent" title="${esc(agendaNav.prevPatientName ?? "")}" data-testid="btn_agenda_prev_dossier">
                  ${iconSvg("ic-arrow-left", "ds-icon--md")} <span class="ds-agenda-dossier-nav__btn-prefix">Dossier </span>précédent (#${agendaNav.position - 1})<span class="ds-agenda-dossier-nav__patient-name">${agendaNav.prevPatientName ? ` · ${esc(agendaNav.prevPatientName)}` : ""}</span>
                </a>`
              : `<button type="button" class="ds-btn ds-btn--ghost ds-btn--sm" disabled aria-label="Dossier précédent" data-testid="btn_agenda_prev_dossier">
                  ${iconSvg("ic-arrow-left", "ds-icon--md")} <span class="ds-agenda-dossier-nav__btn-prefix">Dossier </span>précédent
                </button>`
          }
        </div>
        <div class="ds-agenda-dossier-nav__center">
          <a class="ds-btn ds-btn--ghost ds-btn--sm" href="/agenda?domain=${domainParam}" data-testid="btn_back_to_agenda">
            ${iconSvg("ic-calendar")} <span class="ds-agenda-dossier-nav__back-label">Ordre du jour RCP</span>
          </a>
          <span class="ds-badge ds-badge--complete ds-badge--sm" data-testid="agenda-dossier-position">
            <span class="ds-agenda-dossier-nav__pos-label">Dossier </span>#${agendaNav.position}/${agendaNav.total}<span class="ds-agenda-dossier-nav__session-date"> · ${esc(agendaNav.sessionDate)}</span>
          </span>
        </div>
        <div class="ds-agenda-dossier-nav__next">
          ${
            agendaNav.nextPatientId
              ? `<a class="ds-btn ds-btn--primary ds-btn--sm" href="/patients/${encodeURIComponent(agendaNav.nextPatientId)}?domain=${domainParam}&from=agenda${agendaNav.nextFilename ? `&file=${encodeURIComponent(agendaNav.nextFilename)}` : ""}" aria-label="Dossier suivant" title="${esc(agendaNav.nextPatientName ?? "")}" data-testid="btn_agenda_next_dossier">
                  <span class="ds-agenda-dossier-nav__btn-prefix">Dossier </span>suivant (#${agendaNav.position + 1})<span class="ds-agenda-dossier-nav__patient-name">${agendaNav.nextPatientName ? ` · ${esc(agendaNav.nextPatientName)}` : ""}</span> ${iconSvg("ic-arrow-right", "ds-icon--md")}
                </a>`
              : `<button type="button" class="ds-btn ds-btn--ghost ds-btn--sm" disabled aria-label="Dossier suivant" data-testid="btn_agenda_next_dossier">
                  <span class="ds-agenda-dossier-nav__btn-prefix">Dossier </span>suivant ${iconSvg("ic-arrow-right", "ds-icon--md")}
                </button>`
          }
        </div>
      </nav>`
    : "";

  const dossierProcBadgeHtml = proc.isProcessing
    ? `<span class="ds-badge ds-badge--processing ds-badge--sm" title="${esc(proc.stepLabel ?? proc.label)}" data-testid="badge-processing-status"><span class="ds-spinner" aria-hidden="true"></span> ${esc(proc.label)}</span>`
    : proc.isFailed
      ? `<span class="ds-badge ds-badge--danger ds-badge--sm" title="${esc(proc.stepLabel ?? proc.label)}" data-testid="badge-processing-status">${iconSvg("ic-error")} ${esc(proc.label)}</span>`
      : "";
  const dossierProcBannerHtml = proc.isProcessing
    ? `<div class="ds-processing-banner" role="status" aria-live="polite" data-processing-active="true" data-processing-file="${esc(dossier.currentForm.file)}" data-testid="dossier-processing-banner">
        <div class="ds-processing-banner__main">
          <span class="ds-spinner" aria-hidden="true"></span>
          <div class="ds-processing-banner__content">
            <strong class="ds-processing-banner__title">Fiche en cours de traitement — ${esc(proc.label)}</strong>
            <span class="ds-processing-banner__meta">${proc.stepLabel ? `${esc(proc.stepLabel)} · ` : ""}Rafraîchissement automatique activé — les rubriques se mettent à jour au fil de l'analyse.</span>
          </div>
        </div>
        <div class="ds-processing-banner__end">
          <progress class="ds-progress ds-processing-banner__progress" max="100" value="${proc.progressPct}" aria-label="Avancement du traitement (${proc.progressPct} %)"></progress>
          <a class="ds-btn ds-btn--secondary ds-btn--sm" href="${baseTargetUrl}?file=${encodeURIComponent(dossier.currentForm.file)}&domain=${domainParam}" data-testid="btn_refresh_dossier">${iconSvg("ic-refresh")} Actualiser</a>
        </div>
      </div>`
    : "";

  const bodyHtml = `
    ${agendaNavHtml}
    <!-- Unified RCP Hero Card: Compact 2-Line Header + Always-Visible Synoptic Markers + Collapsible RCP Timeline -->
    <div class="ds-synoptic ds-synoptic--static ds-synoptic--${dossierTone}${proc.isProcessing ? " is-processing" : ""}" data-testid="synoptic-card"${proc.isProcessing ? ` data-processing-active="true" data-processing-file="${esc(dossier.currentForm.file)}"` : ""}>
      <!-- Top M3 Tonal Header (Line 1: Name + Badges + Actions | Line 2: Compact Identity Metadata) -->
      <div class="ds-synoptic__row ds-patient-header" data-testid="patient-rcp-header">
        <div class="ds-patient-header__top">
          <h1 class="ds-patient-header__name">${esc(dossier.patientName)}</h1>

          <div class="ds-patient-header__badges">
            ${dossierProcBadgeHtml}
            <span class="ds-badge ${dossier.priorityBadge.badgeClass} ds-badge--sm">${iconSvg(dossier.priorityBadge.icon)} ${esc(dossier.priorityBadge.label)}</span>
            <div class="ds-hovercard" tabindex="0">
              <span class="ds-badge ${dossier.completenessBadge.badgeClass} ds-badge--sm">
                ${iconSvg(dossier.completenessBadge.icon)} ${esc(dossier.completenessBadge.label)}
              </span>
              ${
                dossier.completenessBadge.missingItems.length > 0
                  ? `<div class="ds-hovercard__panel" role="tooltip">
                      <span class="ds-hovercard__title">${iconSvg("ic-warning")} Pièces manquantes</span>
                      <ul class="ds-hovercard__list">
                        ${dossier.completenessBadge.missingItems.map((m) => `<li>${esc(m)}</li>`).join("")}
                      </ul>
                    </div>`
                  : ""
              }
            </div>
            ${
              dossier.careProposal?.proposedCareType || dossier.careProposal?.clinicalRationale
                ? `<div class="ds-hovercard" tabindex="0">
                    <span class="ds-badge ${dossier.orientationBadge.badgeClass} ds-badge--sm" data-testid="badge-orientation-adapt">
                      ${iconSvg(dossier.orientationBadge.icon)} ${esc(dossier.orientationBadge.label)}
                    </span>
                    <div class="ds-hovercard__panel" role="tooltip">
                      <span class="ds-hovercard__title">${iconSvg("ic-compass")} Orientation pré-RCP</span>
                      ${dossier.careProposal.proposedCareType ? `<p style="font-weight:var(--ds-weight-semibold);margin-bottom:4px">${esc(dossier.careProposal.proposedCareType)}</p>` : ""}
                      ${dossier.careProposal.clinicalRationale ? `<p>${esc(dossier.careProposal.clinicalRationale)}</p>` : ""}
                    </div>
                  </div>`
                : `<span class="ds-badge ${dossier.orientationBadge.badgeClass} ds-badge--sm" data-testid="badge-orientation-adapt">
                    ${iconSvg(dossier.orientationBadge.icon)} ${esc(dossier.orientationBadge.label)}
                  </span>`
            }
            ${
              dossier.specialties[0]
                ? `<span class="ds-badge ds-badge--specialty ds-badge--sm ds-badge--truncate">${iconSvg(dossier.specialties[0].icon)} ${esc(dossier.specialties[0].label)}</span>`
                : ""
            }
            ${
              dossier.specialties.length > 1
                ? `<div class="ds-hovercard" tabindex="0">
                    <span class="ds-badge ds-badge--specialty ds-badge--sm">+${dossier.specialties.length - 1} ${lang === "fr" ? "spécialité(s)" : "specialties"}</span>
                    <div class="ds-hovercard__panel" role="tooltip">
                      <span class="ds-hovercard__title">${iconSvg("ic-stethoscope")} ${lang === "fr" ? "Spécialités mobilisées" : "Involved specialties"} (${dossier.specialties.length})</span>
                      <ul class="ds-hovercard__list">
                        ${dossier.specialties.map((s) => `<li>${esc(s.label)}</li>`).join("")}
                      </ul>
                    </div>
                  </div>`
                : ""
            }
          </div>

          <div class="ds-patient-header__actions">
            <button type="button" class="ds-btn ds-btn--secondary ds-btn--sm ds-patient-header__quick-action" data-open="link-patient-modal" data-testid="btn_link_patient">
              ${iconSvg("ic-link")} Rattacher
            </button>
            <form class="ds-patient-header__quick-action" method="post" action="/forms/${encodeURIComponent(dossier.currentForm.file)}/process?domain=${domainParam}" style="display:inline-flex">
              <input type="hidden" name="preserve_manual_edits" value="true">
              <button type="submit" class="ds-btn ds-btn--tonal ds-btn--sm" data-tooltip="Relance l'analyse complète en conservant les modifications manuelles" data-testid="btn_reprocess_form">
                ${iconSvg("ic-refresh")} Relancer l'IA
              </button>
            </form>
            <details class="ds-menu" data-testid="menu-dossier-actions">
              <summary class="ds-menu__trigger" aria-label="Actions contextuelles du dossier patient" title="Actions du dossier">
                ${iconSvg("ic-more-vert")}
              </summary>
              <div class="ds-menu__panel" role="menu">
                <div class="ds-menu__header">Dossier ${esc(dossier.patientName)}</div>
                <button type="button" class="ds-menu__item" role="menuitem" data-open="link-patient-modal">
                  ${iconSvg("ic-link")}
                  <span>Rattacher à un autre patient…</span>
                </button>
                <form method="post" action="/forms/${encodeURIComponent(dossier.currentForm.file)}/process?domain=${domainParam}" style="margin:0">
                  <input type="hidden" name="preserve_manual_edits" value="true">
                  <button type="submit" class="ds-menu__item" role="menuitem">
                    ${iconSvg("ic-refresh")}
                    <span>Relancer l'analyse IA</span>
                  </button>
                </form>
                <hr class="ds-menu__divider">
                <button type="button" class="ds-menu__item" role="menuitem" data-action="toggle-all-accordions" data-target-panel="panel-clinical">
                  ${iconSvg("ic-layers")}
                  <span>Tout déplier / Tout replier les rubriques</span>
                </button>
                <button type="button" class="ds-menu__item" role="menuitem" data-action="toggle-pdf-expand">
                  ${iconSvg("ic-expand")}
                  <span>Élargir / Réduire le lecteur PDF</span>
                </button>
                <a class="ds-menu__item" role="menuitem" href="${upcomingHref}">
                  ${iconSvg("ic-upload")}
                  <span>Importer une nouvelle séance PDF</span>
                </a>
                <hr class="ds-menu__divider">
                <a class="ds-menu__item" role="menuitem" href="/feedback?domain=${domainParam}&patientId=${encodeURIComponent(dossier.patientId ?? dossier.currentForm.file)}">
                  ${iconSvg("ic-bug")}
                  <span>Signaler une anomalie sur ce dossier</span>
                </a>
                <button type="button" class="ds-menu__item ds-menu__item--danger" role="menuitem" data-open="delete-dossier-modal" data-patient-name="${esc(dossierDelInfo.displayName)}" data-testid="btn_del_dossier">
                  ${iconSvg("ic-delete")}
                  <span>Supprimer ce dossier…</span>
                </button>
              </div>
            </details>
          </div>
        </div>

        <ul class="ds-patient-header__meta">
          ${displayDob ? `<li>Né(e) le ${esc(displayDob)}</li>` : ""}
          ${dossier.gender ? `<li>${esc(dossier.gender)}</li>` : ""}
          ${showShortPatientCode ? `<li class="ds-mono">Dossier ${esc(dossier.patientId)}</li>` : ""}
          <li>${dossier.rcpCount} ${dossier.rcpCount > 1 ? "séances RCP" : "séance RCP"}</li>
          <li><span class="ds-section__duration" title="Temps cumulé d'analyse IA">${iconSvg("ic-clock", "ds-icon--xs")} ${formatDurationMinSec(dossier.cumulativeDurationSec)}</span></li>
        </ul>
      </div>

      ${dossierProcBannerHtml}

      <!-- Row 1: Synoptic Clinical Markers (Always Visible) -->
      <div class="ds-synoptic__row">
        <dl class="ds-markers">
          ${markersHtml}
        </dl>
      </div>

      <!-- Row 2: Compact Collapsible Longitudinal RCP Timeline Strip -->
      <div class="ds-synoptic__row ds-synoptic__row--timeline">
        <details class="ds-timeline-drawer" open data-testid="timeline-drawer">
          <summary class="ds-timeline-drawer__summary">
            <span class="ds-timeline-drawer__label">
              ${iconSvg("ic-calendar", "ds-icon--xs")}
              <span>Frise chronologique RCP</span>
              <span class="ds-badge ds-badge--neutral ds-badge--sm">${dossier.rcpCount} ${dossier.rcpCount > 1 ? "séances" : "séance"}</span>
            </span>
            <span class="ds-timeline-drawer__toggle">
              <span class="ds-small ds-muted">Séance affichée : ${esc(dossier.currentForm.mdtDate ?? dossier.currentForm.file)}</span>
              <svg class="ds-icon ds-icon--md ds-timeline-drawer__chevron" aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>
            </span>
          </summary>
          <nav aria-label="Historique longitudinal des séances RCP" class="ds-timeline-drawer__body">
            <ol class="ds-timeline" data-testid="session-timeline">
              ${timelineHtml}
            </ol>
          </nav>
        </details>
      </div>
    </div>

    <!-- Split View: Source PDF (Left) + Clinical Tabs (Right) -->
    <div class="ds-split ds-split--40-60" id="dossier-split-view" data-testid="split-view">
      <div class="ds-split__pane ds-split__pane--sticky ds-split__pane--pdf" data-pdf-pane>
        <div class="ds-pdf-mobile-bar">
          <button type="button" class="ds-btn ds-btn--secondary ds-pdf-mobile-toggle" data-action="toggle-mobile-pdf" aria-expanded="false" data-label-show="Voir le fichier source" data-label-hide="Masquer le fichier source" data-testid="btn_mobile_pdf_toggle">
            ${iconSvg("ic-file-pdf")} <span data-pdf-toggle-text>Voir le fichier source</span>
          </button>
        </div>
        <div class="ds-cluster ds-pdf-desktop-bar" style="justify-content:space-between">
          <span class="ds-label">${iconSvg("ic-file-pdf")} Document source : <code class="ds-mono">${esc(dossier.currentForm.file)}</code></span>
          <div class="ds-cluster" style="gap:var(--ds-space-1)">
            <button type="button" class="ds-btn ds-btn--secondary ds-btn--sm" data-action="toggle-pdf-expand" data-testid="btn_pdf_expand">
              ${iconSvg("ic-eye")} Élargir PDF
            </button>
            <details class="ds-menu" data-testid="menu-pdf-actions">
              <summary class="ds-menu__trigger" aria-label="Options du lecteur PDF" title="Options du lecteur PDF">
                ${iconSvg("ic-more-vert")}
              </summary>
              <div class="ds-menu__panel" role="menu">
                <div class="ds-menu__header">Lecteur PDF</div>
                <button type="button" class="ds-menu__item" role="menuitem" data-action="toggle-pdf-expand">
                  ${iconSvg("ic-expand")}
                  <span>Élargir / Réduire le volet PDF</span>
                </button>
                <a class="ds-menu__item" role="menuitem" href="/files/forms/${encodeURIComponent(dossier.currentForm.file)}/pdf?domain=${domainParam}#navpanes=0&amp;pagemode=none&amp;view=FitH" target="_blank" rel="noopener">
                  ${iconSvg("ic-file-pdf")}
                  <span>Ouvrir dans un nouvel onglet</span>
                </a>
                <a class="ds-menu__item" role="menuitem" href="/files/forms/${encodeURIComponent(dossier.currentForm.file)}/pdf?domain=${domainParam}" download="${esc(dossier.currentForm.file)}">
                  ${iconSvg("ic-download")}
                  <span>Télécharger le PDF source</span>
                </a>
                <hr class="ds-menu__divider">
                <a class="ds-menu__item" role="menuitem" href="${upcomingHref}">
                  ${iconSvg("ic-upload")}
                  <span>Importer une nouvelle pièce PDF</span>
                </a>
              </div>
            </details>
          </div>
        </div>
        <div class="ds-pdf-viewer-wrap">
          <iframe class="ds-pdf-frame" src="/files/forms/${encodeURIComponent(dossier.currentForm.file)}/pdf?domain=${domainParam}#navpanes=0&amp;pagemode=none&amp;view=FitH&amp;toolbar=1" title="Document source PDF ${esc(dossier.currentForm.file)}"></iframe>
          <div class="ds-pdf-canvas-viewer" data-pdf-canvas-viewer data-pdf-url="/files/forms/${encodeURIComponent(dossier.currentForm.file)}/pdf?domain=${domainParam}" data-pdf-filename="${esc(dossier.currentForm.file)}"></div>
        </div>
      </div>

      <div class="ds-split__pane ds-split__pane--clinical">
        <div class="ds-tabs" role="tablist" aria-label="Vues du dossier patient">
          <button type="button" class="ds-tab" role="tab" id="tab-clinical" aria-selected="true" aria-controls="panel-clinical" data-testid="tab-clinical">
            ${iconSvg("ic-stethoscope")} Dossier clinique (${clinicalSections.length})
          </button>
          <button type="button" class="ds-tab" role="tab" id="tab-opinions" aria-selected="false" aria-controls="panel-opinions" tabindex="-1" data-testid="tab-opinions">
            ${iconSvg("ic-scale")} Avis &amp; orientation pré-RCP (${dossier.opinions.length})
          </button>
          ${
            session.expertMode
              ? `<button type="button" class="ds-tab" role="tab" id="tab-expert" aria-selected="false" aria-controls="panel-expert" tabindex="-1" data-testid="tab-expert">${iconSvg("ic-file-pdf")} Texte Markdown &amp; Chunks</button>`
              : ""
          }
        </div>

        <!-- Tab 1: Editable Clinical Sections (Collapsed by default, grouped by Clinical Pole) -->
        <div class="ds-tabpanel ds-stack" role="tabpanel" id="panel-clinical" aria-labelledby="tab-clinical" tabindex="0">
          <div class="ds-cluster" style="justify-content:space-between">
            <span class="ds-small ds-muted">${clinicalSections.length} rubriques structurées · Cliquez sur une catégorie pour la déplier</span>
            <button type="button" class="ds-btn ds-btn--tonal ds-btn--sm" data-action="toggle-all-accordions" data-target-panel="panel-clinical" data-testid="btn_toggle_all_sections">
              ${iconSvg("ic-layers")} Tout déplier / Tout replier
            </button>
          </div>
          ${sectionsHtml}
        </div>

        <!-- Tab 2: Pre-MDT Orientation, Completeness Check & Specialty Opinions (Collapsed by default) -->
        <div class="ds-tabpanel ds-stack" role="tabpanel" id="panel-opinions" aria-labelledby="tab-opinions" tabindex="0" hidden>
          <div class="ds-cluster" style="justify-content:space-between">
            <span class="ds-small ds-muted">Synthèse pré-RCP &amp; ${dossier.opinions.length} avis spécialisé(s)</span>
            <button type="button" class="ds-btn ds-btn--tonal ds-btn--sm" data-action="toggle-all-accordions" data-target-panel="panel-opinions" data-testid="btn_toggle_all_opinions">
              ${iconSvg("ic-layers")} Tout déplier / Tout replier
            </button>
          </div>
          ${careOrientationHtml}
          ${opinionSectionsHtml}
          ${opinionsHtml}
        </div>

        ${
          session.expertMode
            ? `<div class="ds-tabpanel ds-stack" role="tabpanel" id="panel-expert" aria-labelledby="tab-expert" tabindex="0" hidden>
                <div class="ds-card">
                  <div class="ds-card__header"><h3 class="ds-card__title">${iconSvg("ic-file-pdf")} Texte Markdown extrait</h3></div>
                  <div class="ds-card__body"><pre style="white-space:pre-wrap;margin:0">${esc(dossier.currentForm.markdownText ?? "Aucun texte markdown disponible.")}</pre></div>
                </div>
                ${
                  dossier.currentForm.chunks && dossier.currentForm.chunks.length > 0
                    ? `<div class="ds-card">
                        <div class="ds-card__header"><h3 class="ds-card__title">${iconSvg("ic-layers")} Segments vectoriels indexés (${dossier.currentForm.chunks.length} chunks)</h3></div>
                        <div class="ds-card__body ds-stack--sm">
                          ${dossier.currentForm.chunks
                            .map(
                              (ch) => `<div class="ds-subcard">
                                <div class="ds-subcard__header">
                                  <span class="ds-subcard__title">Chunk #${ch.index}</span>
                                  ${ch.metadata?.page ? `<span class="ds-badge ds-badge--neutral ds-badge--sm">${iconSvg("ic-file-pdf")} p. ${esc(ch.metadata.page)}</span>` : ""}
                                </div>
                                <p class="ds-subcard__body">${esc(ch.content)}</p>
                              </div>`,
                            )
                            .join("")}
                        </div>
                      </div>`
                    : ""
                }
              </div>`
            : ""
        }
      </div>
    </div>

    ${dossierChatDrawerHtml}

    <!-- Modal: Link Form to Patient -->
    <dialog class="ds-modal" id="link-patient-modal" aria-labelledby="link-modal-title">
      <form method="post" action="/forms/${encodeURIComponent(dossier.currentForm.file)}/link-patient?domain=${domainParam}">
        <div class="ds-modal__header">
          <span>${iconSvg("ic-link")}</span>
          <h2 id="link-modal-title">Rattacher la fiche à un patient</h2>
        </div>
        <div class="ds-modal__body">
          <div class="ds-field">
            <label class="ds-label" for="link-patient-id">Identifiant patient (ex. A-1042, S-0007)</label>
            <input class="ds-input" id="link-patient-id" name="patientId" value="${esc(dossier.patientId ?? "")}" list="existing-patients-list">
            <datalist id="existing-patients-list">
              ${dossier.allPatients.map((p) => `<option value="${esc(p.id)}">${esc(p.lastName)} ${esc(p.firstName)}</option>`).join("")}
            </datalist>
          </div>
        </div>
        <div class="ds-modal__footer">
          <button type="button" class="ds-btn ds-btn--ghost" data-close="link-patient-modal">Annuler</button>
          <button type="submit" class="ds-btn ds-btn--primary">Enregistrer le rattachement</button>
        </div>
      </form>
    </dialog>

    <!-- Modal: Delete Dossier -->
    <dialog class="ds-modal ds-modal--danger" id="delete-dossier-modal" aria-labelledby="del-dossier-title">
      <div class="ds-modal__header">
        <span>${iconSvg("ic-delete")}</span>
        <h2 id="del-dossier-title">${dossierDelInfo.isFormOnly ? "Supprimer la fiche RCP de" : "Supprimer le dossier de"} <span data-del-patient-name>${esc(dossierDelInfo.displayName)}</span> ?</h2>
      </div>
      <div class="ds-modal__body">
        <div class="ds-alert ds-alert--danger" role="alert">
          <span class="ds-alert__icon">${iconSvg("ic-priority-high")}</span>
          <div class="ds-alert__content">
            <span class="ds-alert__title">Action irréversible</span>
            <span>${dossierDelInfo.isFormOnly ? "La fiche RCP et les modifications manuelles associées à" : "Les fiches RCP et les modifications manuelles associées à"} <strong data-del-patient-name>${esc(dossierDelInfo.displayName)}</strong>${esc(dossierDelInfo.metaSuffix)} seront définitivement supprimées.</span>
          </div>
        </div>
      </div>
      <div class="ds-modal__footer">
        <form method="dialog"><button class="ds-btn ds-btn--ghost" autofocus>Annuler</button></form>
        <form method="post" action="${dossierDelInfo.actionUrl}">
          <button type="submit" class="ds-btn ds-btn--danger" data-testid="btn_danger_confirm_dossier">${iconSvg("ic-delete")} Supprimer définitivement</button>
        </form>
      </div>
    </dialog>
  `;

  return renderLayout({
    title: dossier.patientName,
    activeNav: agendaNav ? "agenda" : "dossier",
    breadcrumbs: [
      agendaNav
        ? {
            label: t("nav.agenda", lang),
            href: `/agenda?domain=${domainParam}`,
          }
        : {
            label: t("nav.worklist", lang),
            href: `/worklist?domain=${domainParam}`,
          },
      { label: dossier.patientName },
    ],
    session,
    queueStats,
    queueJobs,
    bodyHtml,
  });
}

export function renderIngestPage(
  patients: PatientListItem[],
  batch: BatchStatus | null,
  session: UserSession,
  queueStats: QueueStats,
  queueJobs: QueueJobItem[],
  preselectedPatientId?: string | null,
): string {
  const lang = session.language;
  const domainParam = encodeURIComponent(session.domain);

  const batchHtml = !batch
    ? ""
    : `<div class="ds-card" data-testid="batch-tracker">
        <div class="ds-card__header">
          <h2 class="ds-card__title">${iconSvg("ic-layers")} Suivi du lot <code class="ds-mono">${esc(batch.batchId)}</code></h2>
          <span class="ds-badge ds-badge--success">${iconSvg("ic-check-circle")} ${batch.completed} / ${batch.total} traités</span>
        </div>
        <div class="ds-card__body">
          <progress class="ds-progress" max="100" value="${Math.round(batch.progressPct)}" aria-label="Avancement du lot"></progress>
          <ul class="ds-file-list" aria-label="Fichiers du lot">
            ${batch.files
              .map(
                (f) => `<li class="ds-file-list__item">
                  ${iconSvg("ic-file-pdf")}
                  <span class="ds-file-list__name">${esc(f.filename)}</span>
                  <span class="ds-badge ${f.status === "COMPLETED" ? "ds-badge--success" : f.status === "FAILED" ? "ds-badge--danger" : "ds-badge--info"} ds-badge--sm">
                    ${iconSvg(f.status === "COMPLETED" ? "ic-check-circle" : f.status === "FAILED" ? "ic-error" : "ic-clock")}
                    ${esc(f.status)}
                  </span>
                  <a class="ds-btn ds-btn--tonal ds-btn--sm" href="/forms/${encodeURIComponent(f.filename)}?domain=${domainParam}">Ouvrir</a>
                </li>`,
              )
              .join("")}
          </ul>
        </div>
      </div>`;

  const bodyHtml = `
    <div class="ds-page-header">
      <div class="ds-page-header__text">
        <h1>${esc(t("nav.ingest", lang))}</h1>
        <p class="ds-muted">Déposez un ou plusieurs comptes rendus PDF pour structurer automatiquement les dossiers de la prochaine séance RCP.</p>
      </div>
    </div>

    ${batchHtml}

    <div class="ds-grid">
      <form class="ds-card" method="post" action="/ingest/upload?domain=${domainParam}" enctype="multipart/form-data" data-testid="ingest-form">
        <div class="ds-card__body ds-stack">
          <label class="ds-dropzone" data-testid="ingest-dropzone">
            <input type="file" name="files" id="ingest-files" class="ds-sr-only" multiple accept="application/pdf" required data-testid="input-ingest-files">
            <span class="ds-dropzone__icon">${iconSvg("ic-upload")}</span>
            <span class="ds-dropzone__title">Déposez les PDF du dossier patient</span>
            <span class="ds-small ds-muted">ou <u>parcourez votre poste</u> · PDF uniquement · traitement 100 % local</span>
          </label>
          <ul class="ds-file-list" id="ingest-preview-list" aria-label="Fichiers sélectionnés"></ul>
          <div class="ds-field">
            <label class="ds-label" for="ingest-patient">Rattacher à un patient existant <span class="ds-label__optional">(facultatif — détection automatique sinon)</span></label>
            <select id="ingest-patient" name="patientId" class="ds-select" data-testid="select-ingest-patient">
              <option value="">Détection automatique de l'identité (IA)</option>
              ${patients
                .map(
                  (p) =>
                    `<option value="${esc(p.id)}" ${preselectedPatientId === p.id ? "selected" : ""}>#${esc(p.id)} — ${esc(p.lastName)} ${esc(p.firstName)} (${p.rcpCount} RCP)</option>`,
                )
                .join("")}
            </select>
          </div>
          <button type="submit" class="ds-btn ds-btn--primary ds-btn--block" data-testid="btn_ingest_submit">
            ${iconSvg("ic-play")} Lancer l'import et la structuration IA
          </button>
        </div>
      </form>

      <div class="ds-card ds-card--filled">
        <div class="ds-card__header">
          <h2 class="ds-card__title">${iconSvg("ic-info")} Étapes de préparation automatique du dossier</h2>
        </div>
        <div class="ds-card__body ds-stack--sm">
          <p class="ds-small"><strong>1. Lecture du compte rendu :</strong> extraction automatique du texte et des tableaux du document PDF.</p>
          <p class="ds-small"><strong>2. Consolidation longitudinale :</strong> rapprochement automatique avec les séances RCP antérieures du patient.</p>
          <p class="ds-small"><strong>3. Structuration clinique :</strong> synthèse par pôle médical et vérification des pièces requises avant la séance.</p>
          <p class="ds-small"><strong>4. Avis spécialisés &amp; référentiels :</strong> confrontation aux référentiels scientifiques (${session.domain === "sma" ? "PNDS SMA" : "TNCD"}).</p>
        </div>
      </div>
    </div>
  `;

  return renderLayout({
    title: t("nav.ingest", lang),
    activeNav: "ingest",
    breadcrumbs: [{ label: t("nav.ingest", lang) }],
    session,
    queueStats,
    queueJobs,
    bodyHtml,
  });
}

export function renderGuidelinesPage(
  overview: GuidelinesOverview,
  session: UserSession,
  queueStats: QueueStats,
  queueJobs: QueueJobItem[],
  chatHistory: Array<{ question: string; reply: ChatReply }> = [],
): string {
  const lang = session.language;
  const domainParam = encodeURIComponent(session.domain);
  const activeRes = overview.selectedResource ?? overview.resources[0] ?? null;

  const resourceMenuItemsHtml = overview.resources
    .map((r) => {
      const isSelected = activeRes?.filename === r.filename;
      return `<li class="ds-guidelines-nav__item ${isSelected ? "is-active" : ""}" data-guideline-item="${esc(r.filename.toLowerCase())}">
        <a class="ds-guidelines-nav__link ${isSelected ? "is-active" : ""}" href="/guidelines?domain=${domainParam}&file=${encodeURIComponent(r.filename)}" aria-current="${isSelected ? "page" : "false"}" data-testid="resource-item-${esc(r.filename)}">
          <span class="ds-guidelines-nav__icon">${iconSvg(isSelected ? "ic-check" : "ic-book", "ds-icon--xs")}</span>
          <span class="ds-guidelines-nav__name">${esc(r.filename)}</span>
          <span class="ds-badge ${r.indexed ? "ds-badge--success" : "ds-badge--warning"} ds-badge--sm">
            ${iconSvg(r.indexed ? "ic-check-circle" : "ic-warning")}
            ${r.indexed ? "Indexé" : "Non indexé"}
          </span>
        </a>
        <form method="post" action="/guidelines/${encodeURIComponent(r.filename)}/delete?domain=${domainParam}" style="display:inline-flex">
          <button type="submit" class="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon" aria-label="Supprimer ${esc(r.filename)}" title="Supprimer ce référentiel" data-testid="btn_del_guideline_${esc(r.filename)}">
            ${iconSvg("ic-delete", "ds-icon--xs")}
          </button>
        </form>
      </li>`;
    })
    .join("");

  const quickPrompts = getDomainQuickPrompts(session.domain, "guidelines", lang);
  const guidelineChatDrawerHtml = renderAiChatDrawer({
    drawerTitle: "Assistant référentiel",
    drawerSubtitle: activeRes?.filename ?? "Référentiels scientifiques",
    fabLabel: "Assistant IA",
    formAction: `/guidelines/chat?domain=${domainParam}`,
    formTestId: "guidelines-chat",
    logId: "guidelines-chat-log",
    inputId: "guideline-q",
    inputTestId: "input-guideline-question",
    inputPlaceholder: "Poser une question sur ce référentiel…",
    inputLabel: "Question sur le référentiel",
    submitTestId: "btn_guideline_chat_send",
    submitLabel: "Interroger",
    welcomeMessage:
      "Posez une question sur ce référentiel pour retrouver les recommandations et passages correspondants.",
    chatHistory,
    quickPrompts,
    quickPromptsHeading: "Questions suggérées",
    hiddenFields: { filename: activeRes?.filename ?? "" },
    domain: session.domain,
  });

  const bodyHtml = `
    <div class="ds-page-header">
      <div class="ds-page-header__text">
        <h1>${esc(t("nav.guidelines", lang))}</h1>
        <p class="ds-muted">Référentiels scientifiques (${session.domain === "sma" ? "PNDS Maladies Rares" : "TNCD Cancérologie Digestive"}) consultables et interrogeables pour l'aide à la préparation des séances RCP.</p>
      </div>
      <div class="ds-page-header__actions">
        <button type="button" class="ds-btn ds-btn--secondary" data-open="upload-guideline-modal">
          ${iconSvg("ic-upload")} Ajouter un référentiel PDF
        </button>
        <a class="ds-btn ds-btn--tonal" href="/agents?domain=${domainParam}" data-testid="btn_goto_agents">
          ${iconSvg("ic-users")} Modules d'expertise &amp; Prompts IA (${overview.agents.length})
        </a>
      </div>
    </div>

    <!-- Split Layout: Left Vertical Document Menu + Right PDF Preview with Top Action Bar -->
    <div class="ds-guidelines-layout" data-testid="guideline-control-bar">
      <aside class="ds-card ds-guidelines-nav" aria-label="Liste des référentiels scientifiques">
        <div class="ds-guidelines-nav__header">
          <span class="ds-label">${iconSvg("ic-book", "ds-icon--xs")} Documents (${overview.resources.length})</span>
          <input type="search" class="ds-input ds-input--sm" placeholder="Filtrer les référentiels…" aria-label="Filtrer les référentiels" data-guideline-search>
        </div>
        <ul class="ds-guidelines-nav__list" role="list">
          ${resourceMenuItemsHtml}
        </ul>
      </aside>

      <div class="ds-guidelines-preview">
        ${
          activeRes
            ? `<div class="ds-card ds-guidelines-preview__card" data-pdf-pane>
                <div class="ds-guidelines-preview__toolbar">
                  <div class="ds-cluster" style="gap:var(--ds-space-2)">
                    <span class="ds-label">${iconSvg("ic-file-pdf")} Aperçu : <code class="ds-mono">${esc(activeRes.filename)}</code></span>
                    <span class="ds-badge ${activeRes.indexed ? "ds-badge--success" : "ds-badge--warning"} ds-badge--sm">
                      ${iconSvg(activeRes.indexed ? "ic-check-circle" : "ic-warning")}
                      ${activeRes.indexed ? "Indexé" : "Non indexé"}
                    </span>
                  </div>
                  <div class="ds-cluster" style="gap:var(--ds-space-2)">
                    <form method="post" action="/guidelines/${encodeURIComponent(activeRes.filename)}/reindex?domain=${domainParam}" style="display:inline-flex">
                      <button type="submit" class="ds-btn ds-btn--tonal ds-btn--sm" data-testid="btn_reindex_${esc(activeRes.filename)}">
                        ${iconSvg("ic-refresh")} Ré-indexer
                      </button>
                    </form>
                    <a class="ds-btn ds-btn--secondary ds-btn--sm" href="/files/resources/${encodeURIComponent(activeRes.filename)}?domain=${domainParam}" download="${esc(activeRes.filename)}">
                      ${iconSvg("ic-download")} Télécharger PDF
                    </a>
                    <a class="ds-btn ds-btn--ghost ds-btn--sm" href="/files/resources/${encodeURIComponent(activeRes.filename)}?domain=${domainParam}#navpanes=0&amp;pagemode=none&amp;view=FitH" target="_blank" rel="noopener">
                      ${iconSvg("ic-expand")} Plein écran
                    </a>
                  </div>
                </div>
                <div class="ds-pdf-mobile-bar">
                  <button type="button" class="ds-btn ds-btn--secondary ds-pdf-mobile-toggle" data-action="toggle-mobile-pdf" aria-expanded="false" data-label-show="Voir le fichier source" data-label-hide="Masquer le fichier source" data-testid="btn_mobile_guideline_pdf_toggle">
                    ${iconSvg("ic-file-pdf")} <span data-pdf-toggle-text>Voir le fichier source</span>
                  </button>
                </div>
                <div class="ds-pdf-viewer-wrap">
                  <iframe class="ds-pdf-frame" style="height:46rem" src="/files/resources/${encodeURIComponent(activeRes.filename)}?domain=${domainParam}#navpanes=0&amp;pagemode=none&amp;view=FitH&amp;toolbar=1" title="Aperçu du référentiel ${esc(activeRes.filename)}"></iframe>
                  <div class="ds-pdf-canvas-viewer" data-pdf-canvas-viewer data-pdf-url="/files/resources/${encodeURIComponent(activeRes.filename)}?domain=${domainParam}" data-pdf-filename="${esc(activeRes.filename)}"></div>
                </div>
              </div>`
            : `<div class="ds-empty"><span class="ds-empty__title">Aucun référentiel PDF sélectionné</span></div>`
        }
      </div>
    </div>

    ${guidelineChatDrawerHtml}

    <!-- Modal: Upload Guideline PDF -->
    <dialog class="ds-modal" id="upload-guideline-modal" aria-labelledby="upload-guideline-title">
      <form method="post" action="/guidelines/upload?domain=${domainParam}" enctype="multipart/form-data">
        <div class="ds-modal__header">
          <span>${iconSvg("ic-upload")}</span>
          <h2 id="upload-guideline-title">Ajouter un référentiel PDF</h2>
        </div>
        <div class="ds-modal__body">
          <div class="ds-field">
            <label class="ds-label" for="guideline-file-input">Fichier PDF du référentiel</label>
            <input id="guideline-file-input" type="file" name="file" accept="application/pdf" required class="ds-input">
          </div>
        </div>
        <div class="ds-modal__footer">
          <button type="button" class="ds-btn ds-btn--ghost" data-close="upload-guideline-modal">Annuler</button>
          <button type="submit" class="ds-btn ds-btn--primary">${iconSvg("ic-upload")} Importer et indexer</button>
        </div>
      </form>
    </dialog>
  `;

  return renderLayout({
    title: t("nav.guidelines", lang),
    activeNav: "guidelines",
    breadcrumbs: [{ label: t("nav.guidelines", lang) }],
    session,
    queueStats,
    queueJobs,
    bodyHtml,
  });
}

export function renderAgentsPage(
  agents: AgentModuleInfo[],
  session: UserSession,
  queueStats: QueueStats,
  queueJobs: QueueJobItem[],
  resources: ResourceDocument[] = [],
): string {
  const lang = session.language;
  const domainParam = encodeURIComponent(session.domain);
  const resourceMap = new Map(resources.map((r) => [r.filename, r]));

  const renderSingleAgentCard = (a: AgentModuleInfo) => {
    const modelsHtml =
      a.models && a.models.length > 0
        ? a.models
            .map(
              (m) =>
                `<span class="ds-badge ds-badge--info ds-badge--sm">${iconSvg("ic-sparkle", "ds-icon--xs")} ${esc(m)}</span>`,
            )
            .join("")
        : "";

    const attachedResourcesHtml =
      a.guidelines.length === 0
        ? `<p class="ds-small ds-muted">Aucune ressource PDF rattachée (agent transversal d'extraction ou de coordination).</p>`
        : `<ul class="ds-file-list" aria-label="Ressources documentaires rattachées" data-testid="agent-resources-${esc(a.name)}">
            ${a.guidelines
              .map((g) => {
                const resDoc = resourceMap.get(g);
                const isIndexed = resDoc ? resDoc.indexed : true;
                return `<li class="ds-file-list__item">
                  ${iconSvg("ic-book")}
                  <a class="ds-file-list__name" href="/guidelines?domain=${domainParam}&file=${encodeURIComponent(g)}">${esc(g)}</a>
                  <span class="ds-badge ${isIndexed ? "ds-badge--success" : "ds-badge--warning"} ds-badge--sm">
                    ${iconSvg(isIndexed ? "ic-check-circle" : "ic-warning")}
                    ${isIndexed ? "Indexé" : "À indexer"}
                  </span>
                  <a class="ds-btn ds-btn--secondary ds-btn--sm" href="/guidelines?domain=${domainParam}&file=${encodeURIComponent(g)}">
                    ${iconSvg("ic-eye")} Consulter
                  </a>
                  <form method="post" action="/guidelines/${encodeURIComponent(g)}/reindex?domain=${domainParam}" style="display:inline-flex">
                    <button type="submit" class="ds-btn ds-btn--tonal ds-btn--sm">
                      ${iconSvg("ic-refresh")} Ré-indexer
                    </button>
                  </form>
                </li>`;
              })
              .join("")}
          </ul>`;

    const userPromptsHtml =
      a.userPrompts && a.userPrompts.length > 0
        ? `<div class="ds-stack ds-stack--sm" data-testid="agent-user-prompts-${esc(a.name)}">
            <span class="ds-label">${iconSvg("ic-chat", "ds-icon--xs")} Prompts utilisateurs d'extraction (${a.userPrompts.length} rubrique(s)) :</span>
            <div class="ds-subcards">
              ${a.userPrompts
                .map(
                  (up) => `<div class="ds-subcard">
                    <div class="ds-subcard__header">
                      <span class="ds-subcard__title">${esc(up.title)}</span>
                      <code class="ds-small ds-muted ds-mono">${esc(up.section)}</code>
                    </div>
                    <p class="ds-subcard__body">${esc(up.prompt)}</p>
                  </div>`,
                )
                .join("")}
            </div>
          </div>`
        : "";

    const systemPromptHtml = a.systemPrompt
      ? `<details class="ds-trace-box" data-testid="agent-system-prompt-${esc(a.name)}">
          <summary>${iconSvg("ic-settings", "ds-icon--xs")} Instructions système de l'agent (System Prompt)</summary>
          <div class="ds-trace-box__body">${esc(a.systemPrompt)}</div>
        </details>`
      : "";

    // Compact collapsible M3 card (collapsed by default, expandable on demand)
    return `<details class="ds-section ds-agent-card" data-testid="agent-card-${esc(a.name)}">
      <summary>
        <span class="ds-section__title">${iconSvg(a.icon)} ${esc(a.label)}</span>
        <code class="ds-small ds-muted ds-mono">${esc(a.name)}</code>
        ${modelsHtml}
        <span class="ds-badge ds-badge--neutral ds-badge--sm">${iconSvg("ic-book", "ds-icon--xs")} ${a.guidelines.length} référentiel(s)</span>
        <span class="ds-section__summary">${a.guidelines.length > 0 ? esc(a.guidelines.join(", ")) : esc(a.role)}</span>
      </summary>
      <div class="ds-section__body">
        ${a.role ? `<p class="ds-small ds-muted" style="margin:0">${esc(a.role)}</p>` : ""}
        <div class="ds-stack ds-stack--sm">
          <span class="ds-label">${iconSvg("ic-book", "ds-icon--xs")} Ressources documentaires rattachées (${a.guidelines.length}) :</span>
          ${attachedResourcesHtml}
        </div>
        ${userPromptsHtml}
        ${systemPromptHtml}
      </div>
    </details>`;
  };

  const isCoordinatorOrAdmin = (a: AgentModuleInfo) => {
    const lower = a.name.toLowerCase();
    return (
      lower.includes("administrative") ||
      lower.includes("coordinator") ||
      lower.includes("ressource") ||
      lower.includes("summary") ||
      !lower.includes("expert")
    );
  };

  const coordinationAgents = agents.filter(isCoordinatorOrAdmin);
  const medicalExpertAgents = agents.filter((a) => !isCoordinatorOrAdmin(a));

  const agentsHtml = `
    <section class="ds-stack ds-agent-group" data-testid="agents-group-coordination">
      <div class="ds-pole-heading">${iconSvg("ic-folder", "ds-icon--xs")} Coordination &amp; Extraction administrative (${coordinationAgents.length})</div>
      <div class="ds-stack ds-agent-group__list">
        ${coordinationAgents.map(renderSingleAgentCard).join("")}
      </div>
    </section>
    <section class="ds-stack ds-agent-group" data-testid="agents-group-experts">
      <div class="ds-pole-heading">${iconSvg("ic-stethoscope", "ds-icon--xs")} Spécialistes médicaux (${medicalExpertAgents.length})</div>
      <div class="ds-stack ds-agent-group__list">
        ${medicalExpertAgents.map(renderSingleAgentCard).join("")}
      </div>
    </section>
  `;

  const bodyHtml = `
    <div class="ds-page-header">
      <div class="ds-page-header__text">
        <h1>${esc(t("nav.agents", lang))}</h1>
        <p class="ds-muted">Collège d'agents spécialisés (${agents.length}), ressources PDF rattachées, prompts d'extraction par rubrique et instructions système configurés pour le domaine ${session.domain === "sma" ? "Amyotrophie spinale (SMA)" : "Oncologie digestive"}.</p>
      </div>
      <div class="ds-page-header__actions">
        <button type="button" class="ds-btn ds-btn--tonal" data-action="toggle-all-accordions" data-target-panel="agents-list" data-testid="btn_toggle_all_agents">
          ${iconSvg("ic-layers")} Tout déplier / Tout replier
        </button>
        <a class="ds-btn ds-btn--secondary" href="/guidelines?domain=${domainParam}">
          ${iconSvg("ic-book")} Voir les référentiels PDF
        </a>
      </div>
    </div>

    <div class="ds-stack ds-stack--lg" id="agents-list" data-testid="agents-list">
      ${agentsHtml}
    </div>
  `;

  return renderLayout({
    title: t("nav.agents", lang),
    activeNav: "agents",
    breadcrumbs: [{ label: t("nav.agents", lang) }],
    session,
    queueStats,
    queueJobs,
    bodyHtml,
  });
}

export function renderFeedbackPage(
  bugs: BugListResult,
  session: UserSession,
  queueStats: QueueStats,
  queueJobs: QueueJobItem[],
): string {
  const lang = session.language;
  const domainParam = encodeURIComponent(session.domain);

  const rowsHtml = bugs.items
    .map(
      (b) => `<tr data-testid="bug-row-${esc(b.id)}">
        <td data-label="ID" class="ds-mono">${esc(b.id)}</td>
        <td data-label="Signalement" class="ds-table__primary-cell">
          <strong>${esc(b.title)}</strong>
          <div class="ds-small ds-muted">${esc(b.description)}</div>
        </td>
        <td data-label="Catégorie"><span class="ds-badge ds-badge--neutral ds-badge--sm">${iconSvg("ic-bug")} ${esc(b.category)}</span></td>
        <td data-label="Statut">
          <span class="ds-badge ${b.status === "resolved" ? "ds-badge--success" : b.status === "in_progress" ? "ds-badge--info" : "ds-badge--warning"} ds-badge--sm">
            ${iconSvg(b.status === "resolved" ? "ic-check-circle" : b.status === "in_progress" ? "ic-clock" : "ic-warning")}
            ${esc(b.status)}
          </span>
        </td>
        <td data-label="Dossier" class="ds-mono">${esc(b.patientOrFile ?? "—")}</td>
        <td data-label="Date" class="ds-nowrap">${esc(b.createdAt)}</td>
        <td class="ds-table__actions">
          <form method="post" action="/feedback/${encodeURIComponent(b.id)}/status?domain=${domainParam}" style="display:inline-flex;gap:var(--ds-space-1)">
            <select name="status" class="ds-select ds-select--sm" data-autosubmit="true">
              <option value="open" ${b.status === "open" ? "selected" : ""}>Ouvert</option>
              <option value="in_progress" ${b.status === "in_progress" ? "selected" : ""}>En cours</option>
              <option value="resolved" ${b.status === "resolved" ? "selected" : ""}>Résolu</option>
            </select>
          </form>
        </td>
      </tr>`,
    )
    .join("");

  const bodyHtml = `
    <div class="ds-page-header">
      <div class="ds-page-header__text">
        <h1>${esc(t("nav.feedback", lang))}</h1>
        <p class="ds-muted">Signalez une anomalie d'extraction ou une suggestion d'ergonomie clinique pour améliorer DataSyntis.</p>
      </div>
    </div>

    <div class="ds-kpi-grid">
      <div class="ds-kpi"><span class="ds-kpi__label"><span class="ds-icon-box" aria-hidden="true">${iconSvg("ic-bug", "ds-icon--md")}</span> Total signalements</span><span class="ds-kpi__value">${bugs.counts.total}</span></div>
      <div class="ds-kpi ds-kpi--warning"><span class="ds-kpi__label"><span class="ds-icon-box ds-icon-box--warning" aria-hidden="true">${iconSvg("ic-warning", "ds-icon--md")}</span> Ouverts</span><span class="ds-kpi__value">${bugs.counts.open}</span></div>
      <div class="ds-kpi ds-kpi--info"><span class="ds-kpi__label"><span class="ds-icon-box ds-icon-box--info" aria-hidden="true">${iconSvg("ic-clock", "ds-icon--md")}</span> En cours</span><span class="ds-kpi__value">${bugs.counts.inProgress}</span></div>
      <div class="ds-kpi ds-kpi--success"><span class="ds-kpi__label"><span class="ds-icon-box ds-icon-box--success" aria-hidden="true">${iconSvg("ic-check-circle", "ds-icon--md")}</span> Résolus</span><span class="ds-kpi__value">${bugs.counts.resolved}</span></div>
    </div>

    <div class="ds-split ds-split--40-60">
      <form class="ds-card" method="post" action="/feedback?domain=${domainParam}" data-testid="form-create-bug">
        <div class="ds-card__header">
          <h2 class="ds-card__title">${iconSvg("ic-add")} Nouveau signalement</h2>
        </div>
        <div class="ds-card__body ds-stack">
          <div class="ds-field">
            <label class="ds-label" for="bug-title">Titre du signalement</label>
            <input class="ds-input" id="bug-title" name="title" required placeholder="Ex. : Date d'examen radiologique inversée" data-testid="input-bug-title">
          </div>
          <div class="ds-field">
            <label class="ds-label" for="bug-cat">Catégorie</label>
            <select class="ds-select" id="bug-cat" name="category">
              <option value="extraction">Extraction IA / Rubrique</option>
              <option value="guidelines">Référentiel TNCD / PNDS</option>
              <option value="ui">Ergonomie &amp; Affichage</option>
            </select>
          </div>
          <div class="ds-field">
            <label class="ds-label" for="bug-ref">Dossier ou fichier concerné <span class="ds-label__optional">(facultatif)</span></label>
            <input class="ds-input" id="bug-ref" name="patientOrFile" placeholder="Ex. : #A-1042">
          </div>
          <div class="ds-field">
            <label class="ds-label" for="bug-desc">Description constatée</label>
            <textarea class="ds-textarea" id="bug-desc" name="description" required placeholder="Précisez la valeur attendue…" data-testid="input-bug-desc"></textarea>
          </div>
          <button type="submit" class="ds-btn ds-btn--primary" data-testid="btn_bug_submit">
            ${iconSvg("ic-send")} Enregistrer le signalement
          </button>
        </div>
      </form>

      <div class="ds-table-wrap">
        <table class="ds-table ds-table--dense" data-testid="bugs-table">
          <thead>
            <tr>
              <th scope="col">ID</th>
              <th scope="col">Signalement</th>
              <th scope="col">Catégorie</th>
              <th scope="col">Statut</th>
              <th scope="col">Dossier</th>
              <th scope="col">Date</th>
              <th scope="col" class="ds-table__actions">Action</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
    </div>
  `;

  return renderLayout({
    title: t("nav.feedback", lang),
    activeNav: "feedback",
    breadcrumbs: [{ label: t("nav.feedback", lang) }],
    session,
    queueStats,
    queueJobs,
    bodyHtml,
  });
}

export function renderQueueAdminPage(dashboard: QueueDashboardView, session: UserSession): string {
  const lang = session.language;
  const domainParam = encodeURIComponent(session.domain);
  const { stats, jobs } = dashboard;

  const jobsRows = jobs
    .map((j) => {
      const jobHref = resolveQueueJobHref(j, session.domain);
      const rowDataAttr = jobHref
        ? ` data-href="${jobHref}" title="Cliquer pour ouvrir ${esc(j.filename ?? j.jobId)}"`
        : "";
      const fileCellHtml =
        j.filename && jobHref
          ? `<a class="ds-table__primary-link" href="${jobHref}">${esc(j.filename)}</a>`
          : esc(j.filename ?? "—");
      return `<tr${rowDataAttr} data-testid="queue-job-row-${esc(j.jobId)}">
        <td data-label="ID Job" class="ds-mono">${esc(j.jobId)}</td>
        <td data-label="Domaine"><span class="ds-badge ${j.domain === "sma" ? "ds-badge--domain-sma" : "ds-badge--domain-onco"} ds-badge--sm">${iconSvg(j.domain === "sma" ? "ic-dna" : "ic-ribbon")} ${esc(j.domain)}</span></td>
        <td data-label="Fichier" class="ds-mono ds-table__primary-cell">${fileCellHtml}</td>
        <td data-label="Étape">${esc(j.section ?? j.jobType)}</td>
        <td data-label="Statut">
          <span class="ds-badge ${j.status === "RUNNING" ? "ds-badge--info" : j.status === "FAILED" ? "ds-badge--danger" : j.status === "COMPLETED" ? "ds-badge--success" : "ds-badge--neutral"} ds-badge--sm">
            ${j.status === "RUNNING" ? '<span class="ds-spinner" aria-hidden="true"></span>' : iconSvg(j.status === "FAILED" ? "ic-error" : j.status === "COMPLETED" ? "ic-check-circle" : "ic-clock")}
            ${esc(j.status)}
          </span>
        </td>
        <td data-label="Progression">
          <progress class="ds-progress" max="100" value="${Math.round(j.progressPct)}" style="width:6rem"></progress>
          <span class="ds-small ds-muted">${Math.round(j.progressPct)} %</span>
        </td>
        <td class="ds-table__actions">
          <div class="ds-cluster" style="justify-content:flex-end">
            ${
              j.status === "FAILED"
                ? `<form method="post" action="/admin/queue/jobs/${encodeURIComponent(j.jobId)}/retry?domain=${domainParam}"><button type="submit" class="ds-btn ds-btn--tonal ds-btn--sm" data-testid="btn_retry_${esc(j.jobId)}">${iconSvg("ic-refresh")} Relancer</button></form>`
                : ""
            }
            <form method="post" action="/admin/queue/jobs/${encodeURIComponent(j.jobId)}/delete?domain=${domainParam}">
              <button type="submit" class="ds-btn ds-btn--danger-soft ds-btn--sm ds-btn--icon" aria-label="Supprimer le job ${esc(j.jobId)}" data-testid="btn_del_job_${esc(j.jobId)}">${iconSvg("ic-delete")}</button>
            </form>
          </div>
        </td>
      </tr>`;
    })
    .join("");

  const bodyHtml = `
    <div class="ds-page-header">
      <div class="ds-page-header__text">
        <h1>Supervision de la file d'analyse &amp; verrous GPU</h1>
        <p class="ds-muted">Suivi temps réel Cross-Domains (Oncologie &amp; SMA) de la file PriorityQueue et de l'inférence LLM locale.</p>
      </div>
      <div class="ds-page-header__actions">
        <form method="post" action="/admin/queue/locks/release?domain=${domainParam}">
          <button type="submit" class="ds-btn ds-btn--secondary" data-testid="btn_release_locks">
            ${iconSvg("ic-refresh")} Libérer les verrous GPU (${stats.gpuLocksCount})
          </button>
        </form>
        <form method="post" action="/admin/queue/clean?domain=${domainParam}">
          <input type="hidden" name="mode" value="completed">
          <button type="submit" class="ds-btn ds-btn--tonal" data-testid="btn_clean_completed">
            ${iconSvg("ic-check")} Purger les terminés
          </button>
        </form>
      </div>
    </div>

    <div class="ds-kpi-grid">
      <div class="ds-kpi ds-kpi--info"><span class="ds-kpi__label"><span class="ds-icon-box ds-icon-box--info" aria-hidden="true">${iconSvg("ic-play", "ds-icon--md")}</span> En cours</span><span class="ds-kpi__value">${stats.running}</span></div>
      <div class="ds-kpi"><span class="ds-kpi__label"><span class="ds-icon-box" aria-hidden="true">${iconSvg("ic-clock", "ds-icon--md")}</span> En attente</span><span class="ds-kpi__value">${stats.pending}</span></div>
      <div class="ds-kpi ds-kpi--success"><span class="ds-kpi__label"><span class="ds-icon-box ds-icon-box--success" aria-hidden="true">${iconSvg("ic-check-circle", "ds-icon--md")}</span> Terminés</span><span class="ds-kpi__value">${stats.completed}</span></div>
      <div class="ds-kpi ds-kpi--danger"><span class="ds-kpi__label"><span class="ds-icon-box ds-icon-box--danger" aria-hidden="true">${iconSvg("ic-error", "ds-icon--md")}</span> En échec</span><span class="ds-kpi__value">${stats.failed}</span></div>
    </div>

    <div class="ds-table-wrap">
      <table class="ds-table ds-table--dense" data-testid="queue-jobs-table">
        <thead>
          <tr>
            <th scope="col">ID Job</th>
            <th scope="col">Domaine</th>
            <th scope="col">Fichier</th>
            <th scope="col">Étape / Rubrique</th>
            <th scope="col">Statut</th>
            <th scope="col">Progression</th>
            <th scope="col" class="ds-table__actions">Actions</th>
          </tr>
        </thead>
        <tbody>
          ${jobsRows}
        </tbody>
      </table>
    </div>
  `;

  return renderLayout({
    title: t("nav.queue", lang),
    activeNav: "queue",
    breadcrumbs: [{ label: t("nav.queue", lang) }],
    session,
    queueStats: stats,
    queueJobs: jobs,
    bodyHtml,
  });
}

export function renderAgendaPage(
  agenda: MdtAgendaView,
  session: UserSession,
  queueStats: QueueStats,
  queueJobs: QueueJobItem[],
  openOnboarding = false,
  focusExpert: string | null = null,
): string {
  const lang = session.language;
  const domainParam = encodeURIComponent(session.domain);
  const attendingSet = new Set(agenda.attendingExperts);
  const activeFocusExpert =
    focusExpert && agenda.availableExperts.includes(focusExpert) ? focusExpert : null;

  const strategyOptions: Array<{ value: string; label: string }> = [
    {
      value: "hybrid",
      label: lang === "fr" ? "Hybride (Urgences + Spécialités)" : "Hybrid (Urgency + Specialties)",
    },
    {
      value: "urgency_first",
      label: lang === "fr" ? "Par urgence clinique" : "By clinical urgency",
    },
    {
      value: "expert_grouping",
      label: lang === "fr" ? "Par spécialistes présents" : "By attending specialists",
    },
    {
      value: "manual",
      label: lang === "fr" ? "Ordre personnalisé" : "Custom order",
    },
  ];

  // 1. Compact Dropdown Selector Items for Attending Experts + Passage Windows
  const expertSelectorItemsHtml = agenda.availableExperts
    .map((expKey) => {
      const pres = getAgentPresentation(expKey, lang);
      const isPresent = attendingSet.has(expKey);
      const win = agenda.expertWindows.find((w) => w.expertName === expKey);
      const caseCount = win?.caseCount ?? 0;
      const windowLabel =
        win && win.firstPosition !== null && win.lastPosition !== null
          ? win.firstPosition === win.lastPosition
            ? `#${win.firstPosition}`
            : `#${win.firstPosition}→#${win.lastPosition}`
          : `${caseCount} doss.`;

      return `<form method="post" action="/agenda/options?domain=${domainParam}" class="ds-agenda-dropdown__form">
        <input type="hidden" name="toggleExpert" value="${esc(expKey)}">
        <button
          type="submit"
          class="ds-agenda-dropdown__item ${isPresent ? "is-selected" : "is-unselected"}"
          aria-pressed="${isPresent ? "true" : "false"}"
          title="${isPresent ? "Cliquer pour marquer absent" : "Cliquer pour marquer présent"}"
          data-testid="chip_expert_${esc(expKey)}"
        >
          <span class="ds-agenda-dropdown__check" aria-hidden="true">${isPresent ? "☑" : "☐"}</span>
          ${iconSvg(pres.icon, "ds-icon--xs")}
          <span class="ds-agenda-dropdown__item-label" title="${esc(pres.label)}">${esc(pres.shortLabel)}</span>
          <span class="ds-badge ${isPresent ? "ds-badge--complete" : "ds-badge--incomplete"} ds-badge--sm" data-testid="expert-window-${esc(expKey)}">
            ${isPresent ? esc(windowLabel) : `Absent (${caseCount})`}
          </span>
        </button>
      </form>`;
    })
    .join("");

  // 2. Ordered Agenda Rows (Main visual focus)
  const enrolledHtml =
    agenda.items.length === 0
      ? `<div class="ds-empty" data-testid="empty-agenda">
          <span class="ds-empty__icon">${iconSvg("ic-calendar")}</span>
          <span class="ds-empty__title">Aucune réunion RCP programmée</span>
          <p class="ds-empty__text">Cliquez sur « Programmer une nouvelle réunion » pour définir la date, les spécialistes présents et inscrire les patients à l'ordre du jour.</p>
          <button type="button" class="ds-btn ds-btn--primary" data-open="schedule-meeting-dialog">
            ${iconSvg("ic-add")} Programmer une nouvelle réunion
          </button>
        </div>`
      : `<ol class="ds-agenda-list" data-testid="agenda-items-list" data-domain="${esc(session.domain)}">
          ${agenda.items
            .map((item, idx) => {
              const prio = derivePriorityBadgeInfo(item.priorityLevel, lang, false);
              const compl = deriveCompletenessInfo(
                {
                  is_complete: item.isComplete,
                  missing_count: item.missingCount,
                  missing_items: item.missingItems,
                },
                lang,
              );
              const orient = deriveOrientationInfo(
                {
                  care_adaptation_suggested: item.careAdaptationSuggested,
                  proposed_care_type: item.proposedCareType,
                },
                lang,
              );
              const dossierHref = `/patients/${encodeURIComponent(item.patientId)}?domain=${domainParam}&from=agenda${item.filename ? `&file=${encodeURIComponent(item.filename)}` : ""}`;

              const reqBadgesHtml = item.requiredExperts
                .map((expKey) => {
                  const p = getAgentPresentation(expKey, lang);
                  const isPresent = item.presentRequiredExperts.includes(expKey);
                  const isFocusedBadge = activeFocusExpert === expKey;
                  const focusClass = isFocusedBadge ? " ds-badge--focused-specialty" : "";
                  if (isPresent) {
                    return `<button type="button" class="ds-badge ds-badge--complete ds-badge--sm ds-agenda-item__exp-badge${focusClass}" data-focus-expert="${esc(expKey)}" aria-pressed="${isFocusedBadge ? "true" : "false"}" title="Cliquer pour mettre en surbrillance les dossiers concernant ${esc(p.label)}">${iconSvg("ic-check", "ds-icon--xs")} ${esc(p.shortLabel)}</button>`;
                  }
                  return `<button type="button" class="ds-badge ds-badge--urgency-high ds-badge--sm ds-agenda-item__exp-badge${focusClass}" data-focus-expert="${esc(expKey)}" aria-pressed="${isFocusedBadge ? "true" : "false"}" title="Spécialiste requis mais absent · Cliquer pour mettre en surbrillance les dossiers concernant ${esc(p.label)}">${iconSvg("ic-warning", "ds-icon--xs")} ${esc(p.shortLabel)} (absent)</button>`;
                })
                .join(" ");

              const completenessBadge =
                !item.isComplete && item.missingItems.length > 0
                  ? `<div class="ds-hovercard" tabindex="0">
                      <span class="ds-badge ${compl.badgeClass} ds-badge--sm">${iconSvg(compl.icon)} ${esc(compl.label)}</span>
                      <div class="ds-hovercard__panel" role="tooltip">
                        <span class="ds-hovercard__title">${iconSvg("ic-warning")} Éléments manquants</span>
                        <ul class="ds-hovercard__list">${item.missingItems.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>
                      </div>
                    </div>`
                  : `<span class="ds-badge ${compl.badgeClass} ds-badge--sm">${iconSvg(compl.icon)} ${esc(compl.label)}</span>`;

              const isFirst = idx === 0;
              const isLast = idx === agenda.items.length - 1;
              const rankTone =
                item.priorityLevel === "high"
                  ? "ds-agenda-item__rank--high"
                  : !item.isComplete || !item.quorumMet
                    ? "ds-agenda-item__rank--warning"
                    : "ds-agenda-item__rank--standard";

              const isItemFocused =
                activeFocusExpert !== null && item.requiredExperts.includes(activeFocusExpert);
              const isItemDimmed =
                activeFocusExpert !== null && !item.requiredExperts.includes(activeFocusExpert);

              return `<li class="ds-card ds-agenda-item ${item.priorityLevel === "high" ? "ds-agenda-item--urgent" : ""} ${!item.quorumMet ? "ds-agenda-item--quorum-warn" : ""} ${isItemFocused ? "ds-agenda-item--focused" : ""} ${isItemDimmed ? "ds-agenda-item--dimmed" : ""}" data-href="${dossierHref}" data-patient-id="${esc(item.patientId)}" data-position="${item.position}" data-required-experts="${esc(item.requiredExperts.join("|"))}" title="Cliquer pour ouvrir le dossier de ${esc(item.patientName)}" data-testid="agenda-item-${esc(item.patientId)}">
                <div class="ds-agenda-item__rank ${rankTone}" data-agenda-drag-handle="true" data-testid="agenda-rank-${esc(item.patientId)}" title="Maintenir cliqué et glisser pour modifier l'ordre de passage" aria-label="Rang de passage ${item.position}">
                  <span class="ds-agenda-item__pos">#${item.position}</span>
                  ${item.pinned ? `<span class="ds-agenda-item__pin-indicator" title="Position verrouillée manuellement">${iconSvg("ic-lock", "ds-icon--xs")}</span>` : ""}
                </div>

                <div class="ds-agenda-item__main">
                  <div class="ds-agenda-item__top">
                    <div class="ds-agenda-item__identity">
                      <a class="ds-agenda-item__name" href="${dossierHref}">${esc(item.patientName)}</a>
                      ${item.dateBirth ? `<span class="ds-small ds-muted">Né(e) le ${esc(item.dateBirth)}</span>` : ""}
                    </div>
                    <div class="ds-cluster">
                      <span class="ds-badge ${prio.badgeClass} ds-badge--sm">${iconSvg(prio.icon)} ${esc(prio.label)}</span>
                      ${completenessBadge}
                      <span class="ds-badge ${orient.badgeClass} ds-badge--sm">${iconSvg(orient.icon)} ${esc(orient.label)}</span>
                    </div>
                  </div>

                  ${
                    item.proposedCareType
                      ? `<p class="ds-small ds-agenda-item__proposal"><strong>Orientation pré-RCP :</strong> ${esc(item.proposedCareType)}</p>`
                      : ""
                  }

                  <div class="ds-agenda-item__bottom">
                    <div class="ds-cluster" aria-label="Quorum des spécialités requises">
                      ${reqBadgesHtml || '<span class="ds-small ds-muted">Collège général</span>'}
                    </div>
                    <div class="ds-agenda-item__reason" data-testid="rank-reason-${esc(item.patientId)}">
                      ${iconSvg("ic-compass", "ds-icon--xs")}
                      <span>${esc(item.rankReason)}</span>
                    </div>
                  </div>
                </div>

                <div class="ds-agenda-item__actions" aria-label="Actions d'ordonnancement pour ${esc(item.patientName)}">
                  <form method="post" action="/agenda/patients/${encodeURIComponent(item.patientId)}/move?domain=${domainParam}">
                    <input type="hidden" name="direction" value="up">
                    <button type="submit" class="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon" ${isFirst ? "disabled" : ""} title="Monter d'un rang" aria-label="Monter ${esc(item.patientName)}" data-testid="btn_move_up_${esc(item.patientId)}">
                      ${iconSvg("ic-arrow-up", "ds-icon--md")}
                    </button>
                  </form>
                  <form method="post" action="/agenda/patients/${encodeURIComponent(item.patientId)}/move?domain=${domainParam}">
                    <input type="hidden" name="direction" value="down">
                    <button type="submit" class="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon" ${isLast ? "disabled" : ""} title="Descendre d'un rang" aria-label="Descendre ${esc(item.patientName)}" data-testid="btn_move_down_${esc(item.patientId)}">
                      ${iconSvg("ic-arrow-down", "ds-icon--md")}
                    </button>
                  </form>
                  <form method="post" action="/agenda/patients/${encodeURIComponent(item.patientId)}/move?domain=${domainParam}">
                    <input type="hidden" name="pinned" value="${item.pinned ? "false" : "true"}">
                    <button type="submit" class="ds-btn ${item.pinned ? "ds-btn--tonal" : "ds-btn--ghost"} ds-btn--sm ds-btn--icon" aria-pressed="${item.pinned ? "true" : "false"}" title="${item.pinned ? "Déverrouiller la position" : "Verrouiller à ce rang"}" aria-label="${item.pinned ? "Déverrouiller" : "Verrouiller"} ${esc(item.patientName)}" data-testid="btn_pin_${esc(item.patientId)}">
                      ${iconSvg(item.pinned ? "ic-lock" : "ic-unlock", "ds-icon--sm")}
                    </button>
                  </form>
                  <a class="ds-btn ds-btn--tonal ds-btn--sm" href="${dossierHref}" data-testid="btn_open_agenda_${esc(item.patientId)}">Ouvrir</a>
                  <form method="post" action="/agenda/patients/${encodeURIComponent(item.patientId)}/remove?domain=${domainParam}">
                    <button type="submit" class="ds-btn ds-btn--danger-soft ds-btn--sm ds-btn--icon" title="Retirer de la séance RCP" aria-label="Retirer ${esc(item.patientName)} de la séance" data-testid="btn_del_agenda_${esc(item.patientId)}">
                      ${iconSvg("ic-close", "ds-icon--sm")}
                    </button>
                  </form>
                </div>
              </li>`;
            })
            .join("")}
        </ol>`;

  // 3. Compact Candidate Selector Dropdown Content (for adding removed patients)
  const candidatesHtml =
    agenda.candidates.length === 0
      ? `<p class="ds-small ds-muted" style="padding:var(--ds-space-2)" data-testid="empty-candidates">Tous les patients du domaine sont inscrits à l'ordre du jour.</p>`
      : `<ul class="ds-agenda-candidates" data-testid="agenda-candidates-list">
          ${agenda.candidates
            .map((cand) => {
              const prio = derivePriorityBadgeInfo(cand.priorityLevel, lang, true);
              return `<li class="ds-agenda-candidate" data-testid="agenda-candidate-${esc(cand.patientId)}">
                <div class="ds-agenda-candidate__info">
                  <span class="ds-agenda-candidate__name">${esc(cand.patientName)}${cand.dateBirth ? ` <span class="ds-small ds-muted">· Né(e) le ${esc(cand.dateBirth)}</span>` : ""}</span>
                  <span class="ds-badge ${prio.badgeClass} ds-badge--sm">${iconSvg(prio.icon)} ${esc(prio.label)}</span>
                </div>
                <form method="post" action="/agenda/patients?domain=${domainParam}">
                  <input type="hidden" name="patientId" value="${esc(cand.patientId)}">
                  <button type="submit" class="ds-btn ds-btn--tonal ds-btn--sm" data-testid="btn_add_candidate_${esc(cand.patientId)}">
                    ${iconSvg("ic-add", "ds-icon--xs")} Ajouter
                  </button>
                </form>
              </li>`;
            })
            .join("")}
        </ul>`;

  // 4. All domain patients for the Direct Onboarding Modal (checked by default)
  const allOnboardingPatients = [
    ...agenda.items.map((item) => ({
      patientId: item.patientId,
      patientName: item.patientName,
      priorityLevel: item.priorityLevel,
      isComplete: item.isComplete,
      requiredExperts: item.requiredExperts,
      checked: true,
    })),
    ...agenda.candidates.map((cand) => ({
      patientId: cand.patientId,
      patientName: cand.patientName,
      priorityLevel: cand.priorityLevel,
      isComplete: cand.isComplete,
      requiredExperts: cand.requiredExperts,
      checked: true,
    })),
  ];

  const onboardingExpertsHtml = agenda.availableExperts
    .map((expKey) => {
      const pres = getAgentPresentation(expKey, lang);
      const isChecked = attendingSet.has(expKey) || agenda.attendingExperts.length === 0;
      return `<label class="ds-agenda-onboarding__check-row" title="${esc(pres.label)}">
        <input type="checkbox" name="attendingExperts" value="${esc(expKey)}" ${isChecked ? "checked" : ""}>
        ${iconSvg(pres.icon, "ds-icon--xs")}
        <span>${esc(pres.shortLabel)}</span>
      </label>`;
    })
    .join("");

  const onboardingPatientsHtml = allOnboardingPatients
    .map((p) => {
      const prio = derivePriorityBadgeInfo(p.priorityLevel, lang, true);
      return `<label class="ds-agenda-onboarding__check-row">
        <input type="checkbox" name="patientIds" value="${esc(p.patientId)}" ${p.checked ? "checked" : ""}>
        <span class="ds-agenda-onboarding__patient-name">${esc(p.patientName)}</span>
        <span class="ds-badge ${prio.badgeClass} ds-badge--sm">${iconSvg(prio.icon)} ${esc(prio.label)}</span>
      </label>`;
    })
    .join("");

  const hasMeeting = agenda.items.length > 0 && Boolean(agenda.sessionDate);

  const specialtyFocusOptionsHtml = agenda.availableExperts
    .map((expKey) => {
      const pres = getAgentPresentation(expKey, lang);
      const win = agenda.expertWindows.find((w) => w.expertName === expKey);
      const caseCount = win?.caseCount ?? 0;
      const isFocused = activeFocusExpert === expKey;

      return `<option value="${esc(expKey)}" data-icon="${esc(pres.icon)}" ${isFocused ? "selected" : ""}>${esc(pres.shortLabel)} (${caseCount})</option>`;
    })
    .join("");

  const specialtyFocusBarHtml = hasMeeting
    ? `<form method="get" action="/agenda" class="ds-agenda-focus-bar" role="search" aria-label="Focus sur une spécialité pour mettre en surbrillance les dossiers concernés" data-testid="agenda-specialty-focus-bar">
        <input type="hidden" name="domain" value="${esc(session.domain)}">
        <label class="ds-agenda-focus-bar__label" for="agenda-focus-expert">
          ${iconSvg("ic-stethoscope", "ds-icon--xs")} <span>Focus<span class="ds-agenda-focus-bar__label-suffix"> spécialité</span> :</span>
        </label>
        <div class="ds-agenda-focus-bar__control">
          <select
            id="agenda-focus-expert"
            name="focusExpert"
            class="ds-select ds-select--sm"
            data-agenda-focus-select="true"
            data-testid="select-focus-specialty"
          >
            <option value="" ${activeFocusExpert === null ? "selected" : ""}>Toutes (${agenda.items.length})</option>
            ${specialtyFocusOptionsHtml}
          </select>
        </div>
        <noscript>
          <button type="submit" class="ds-btn ds-btn--tonal ds-btn--sm">Filtrer</button>
        </noscript>
      </form>`
    : "";

  const configToolbarHtml = hasMeeting
    ? `<!-- Session Configuration Section (only shown when a meeting is active; collapsed by default on mobile) -->
      <details class="ds-card ds-agenda-config-section" open data-mobile-collapsible="true" aria-labelledby="heading-agenda-settings" data-testid="agenda-config-card">
        <summary class="ds-agenda-config-section__header">
          <span id="heading-agenda-settings" class="ds-agenda-config-section__title">
            ${iconSvg("ic-compass", "ds-icon--xs")} Paramétrage de la réunion RCP
          </span>
          <span class="ds-agenda-config-section__meta">
            <span class="ds-small ds-muted ds-agenda-config-section__hint">Date, mode d'organisation, spécialistes présents et patients</span>
            <svg class="ds-icon ds-icon--md ds-agenda-config-section__chevron" aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>
          </span>
        </summary>

        <div class="ds-agenda-toolbar">
          <form method="post" action="/agenda/options?domain=${domainParam}" class="ds-agenda-toolbar__form" data-testid="form-agenda-options">
            <div class="ds-field ds-agenda-toolbar__date">
              <label class="ds-label" for="agenda-session-date">${iconSvg("ic-calendar", "ds-icon--xs")} Date de la RCP</label>
              <input
                type="date"
                id="agenda-session-date"
                name="sessionDate"
                class="ds-input"
                value="${esc(agenda.sessionDate)}"
                data-autosubmit="true"
                data-testid="input-session-date"
              >
            </div>

            <div class="ds-field ds-agenda-toolbar__strategy">
              <label class="ds-label" for="agenda-sort-strategy">${iconSvg("ic-compass", "ds-icon--xs")} Organisation de l'ordre du jour</label>
              <select
                id="agenda-sort-strategy"
                name="sortStrategy"
                class="ds-select"
                data-autosubmit="true"
                data-testid="select-sort-strategy"
              >
                ${strategyOptions
                  .map(
                    (opt) =>
                      `<option value="${esc(opt.value)}" ${agenda.sortStrategy === opt.value ? "selected" : ""}>${esc(opt.label)}</option>`,
                  )
                  .join("")}
              </select>
            </div>

            <noscript>
              <button type="submit" class="ds-btn ds-btn--tonal ds-btn--sm" data-testid="btn_apply_agenda_options">Actualiser</button>
            </noscript>
          </form>

          <!-- Specialist Multi-Select Dropdown -->
          <div class="ds-field ds-agenda-toolbar__selector">
            <span class="ds-label">${iconSvg("ic-users", "ds-icon--xs")} Spécialistes présents</span>
            <details class="ds-agenda-dropdown" data-testid="agenda-expert-chips">
              <summary class="ds-select ds-agenda-dropdown__trigger" data-testid="btn_toggle_expert_selector">
                <span>${agenda.attendingExperts.length}/${agenda.availableExperts.length} présents</span>
                <svg class="ds-icon ds-icon--md ds-agenda-dropdown__chevron" aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>
              </summary>
              <div class="ds-agenda-dropdown__panel" data-testid="agenda-expert-windows">
                <div class="ds-agenda-dropdown__header">
                  <span>Cocher / décocher les spécialistes présents</span>
                </div>
                <div class="ds-agenda-dropdown__list">
                  ${expertSelectorItemsHtml}
                </div>
              </div>
            </details>
          </div>

          <!-- Patient Add Selector Dropdown -->
          <div class="ds-field ds-agenda-toolbar__selector">
            <span class="ds-label">${iconSvg("ic-folder-open", "ds-icon--xs")} Ajouter / Retirer</span>
            <details class="ds-agenda-dropdown" data-testid="agenda-candidate-pool">
              <summary class="ds-select ds-agenda-dropdown__trigger" data-testid="btn_toggle_candidate_selector">
                <span>${agenda.candidates.length > 0 ? `+ Ajouter (${agenda.candidates.length} dispo.)` : "Tous inscrits"}</span>
                <svg class="ds-icon ds-icon--md ds-agenda-dropdown__chevron" aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>
              </summary>
              <div class="ds-agenda-dropdown__panel ds-agenda-dropdown__panel--right">
                ${
                  agenda.candidates.length > 0
                    ? `<div class="ds-cluster" style="margin-bottom:var(--ds-space-2)">
                        <form method="post" action="/agenda/patients?domain=${domainParam}">
                          <input type="hidden" name="enrollAllCandidates" value="true">
                          <input type="hidden" name="filterMode" value="all">
                          <button type="submit" class="ds-btn ds-btn--secondary ds-btn--sm" data-testid="btn_enroll_all">
                            ${iconSvg("ic-add", "ds-icon--xs")} Tout inscrire
                          </button>
                        </form>
                        <form method="post" action="/agenda/patients?domain=${domainParam}">
                          <input type="hidden" name="enrollAllCandidates" value="true">
                          <input type="hidden" name="filterMode" value="urgent">
                          <button type="submit" class="ds-btn ds-btn--tonal ds-btn--sm" data-testid="btn_enroll_all_urgent">
                            + Urgences
                          </button>
                        </form>
                        <form method="post" action="/agenda/patients?domain=${domainParam}">
                          <input type="hidden" name="enrollAllCandidates" value="true">
                          <input type="hidden" name="filterMode" value="complete">
                          <button type="submit" class="ds-btn ds-btn--tonal ds-btn--sm" data-testid="btn_enroll_all_complete">
                            + Complets
                          </button>
                        </form>
                      </div>`
                    : ""
                }
                ${candidatesHtml}
              </div>
            </details>
          </div>
        </div>
      </details>`
    : "";

  const firstItemHref =
    hasMeeting && agenda.items[0]
      ? `/patients/${encodeURIComponent(agenda.items[0].patientId)}?domain=${domainParam}&from=agenda${agenda.items[0].filename ? `&file=${encodeURIComponent(agenda.items[0].filename)}` : ""}`
      : null;

  const bodyHtml = `
    <div class="ds-page-header ds-agenda-header">
      <div class="ds-page-header__text">
        <div class="ds-agenda-header__title-row">
          <h1 id="heading-ordered-agenda">${esc(t("nav.agenda", lang))}${hasMeeting ? ` <span class="ds-agenda-header__date">· ${esc(agenda.sessionDate)}</span>` : ""}</h1>
          ${
            hasMeeting
              ? `<div class="ds-agenda-summary-strip" aria-label="Résumé de la séance RCP">
                  <span class="ds-badge ds-badge--complete ds-badge--sm" data-testid="kpi-agenda-enrolled">
                    ${iconSvg("ic-layers", "ds-icon--xs")} ${agenda.totalEnrolled} dossier${agenda.totalEnrolled > 1 ? "s" : ""}
                  </span>
                  <span class="ds-badge ${agenda.urgentCount > 0 ? "ds-badge--urgency-high" : "ds-badge--neutral"} ds-badge--sm" data-testid="kpi-agenda-urgent">
                    ${iconSvg("ic-priority-high", "ds-icon--xs")} ${agenda.urgentCount} urgence${agenda.urgentCount > 1 ? "s" : ""}
                  </span>
                  <span class="ds-badge ${agenda.quorumWarningCount > 0 ? "ds-badge--incomplete" : "ds-badge--neutral"} ds-badge--sm" data-testid="kpi-agenda-quorum">
                    ${iconSvg("ic-users", "ds-icon--xs")} ${agenda.attendingExperts.length}/${agenda.availableExperts.length} experts${agenda.quorumWarningCount > 0 ? ` · ${agenda.quorumWarningCount} alerte(s) quorum` : ""}
                  </span>
                  ${
                    agenda.incompleteCount > 0
                      ? `<span class="ds-badge ds-badge--incomplete ds-badge--sm" data-testid="kpi-agenda-incomplete">
                          ${iconSvg("ic-warning", "ds-icon--xs")} ${agenda.incompleteCount} incomplet${agenda.incompleteCount > 1 ? "s" : ""}
                        </span>`
                      : ""
                  }
                </div>`
              : ""
          }
        </div>
      </div>
      <div class="ds-page-header__actions">
        ${
          firstItemHref
            ? `<a class="ds-btn ds-btn--primary ds-btn--sm ds-agenda-header__start-btn" href="${firstItemHref}" data-testid="btn_start_session">
                ${iconSvg("ic-play")} Ouvrir le 1er dossier (#1)
              </a>`
            : ""
        }
        <button type="button" class="ds-btn ${hasMeeting ? "ds-btn--tonal ds-btn--sm" : "ds-btn--primary"} ds-agenda-header__desktop-action" data-open="schedule-meeting-dialog" data-testid="btn_schedule_new_meeting">
          ${iconSvg("ic-calendar")} Programmer une nouvelle réunion
        </button>
        <a class="ds-btn ds-btn--secondary ds-btn--sm ds-agenda-header__desktop-action" href="/worklist?domain=${domainParam}" data-testid="btn_agenda_worklist">
          ${iconSvg("ic-worklist")} Worklist
        </a>
        ${
          hasMeeting
            ? `<button type="button" class="ds-btn ds-btn--danger-soft ds-btn--sm ds-agenda-header__desktop-action" data-open="clear-agenda-dialog" data-testid="btn_del_clear_agenda">
                ${iconSvg("ic-delete")} Vider
              </button>`
            : ""
        }
        <details class="ds-menu ds-agenda-header__mobile-menu" data-testid="menu-agenda-actions">
          <summary class="ds-menu__trigger" aria-label="Actions de l'ordre du jour RCP" title="Actions de l'ordre du jour">
            ${iconSvg("ic-more-vert")}
          </summary>
          <div class="ds-menu__panel" role="menu">
            <div class="ds-menu__header">${esc(t("nav.agenda", lang))}</div>
            <button type="button" class="ds-menu__item" role="menuitem" data-open="schedule-meeting-dialog">
              ${iconSvg("ic-calendar")}
              <span>Programmer une nouvelle réunion</span>
            </button>
            <a class="ds-menu__item" role="menuitem" href="/worklist?domain=${domainParam}">
              ${iconSvg("ic-worklist")}
              <span>Worklist</span>
            </a>
            ${
              hasMeeting
                ? `<hr class="ds-menu__divider">
                  <button type="button" class="ds-menu__item ds-menu__item--danger" role="menuitem" data-open="clear-agenda-dialog">
                    ${iconSvg("ic-delete")}
                    <span>Vider l'ordre du jour</span>
                  </button>`
                : ""
            }
          </div>
        </details>
      </div>
    </div>

    ${configToolbarHtml}

    <!-- Main Full-Width Focus: Ordered Agenda List -->
    <section class="ds-stack ds-agenda-focus" aria-labelledby="heading-ordered-agenda">
      ${hasMeeting ? specialtyFocusBarHtml : ""}
      ${enrolledHtml}
    </section>

    <!-- Direct Onboarding Modal: "Programmer une nouvelle réunion" -->
    <dialog class="ds-modal ds-agenda-onboarding" id="schedule-meeting-dialog" ${openOnboarding ? "open" : ""} aria-labelledby="schedule-meeting-title" data-testid="schedule-meeting-dialog">
      <form method="post" action="/agenda/schedule?domain=${domainParam}" data-testid="form-schedule-meeting">
        <div class="ds-modal__header">
          <span>${iconSvg("ic-calendar")}</span>
          <h2 id="schedule-meeting-title">Programmer une nouvelle réunion RCP</h2>
        </div>
        <div class="ds-modal__body ds-stack">
          <div class="ds-agenda-onboarding__grid">
            <div class="ds-field">
              <label class="ds-label" for="onb-session-date">1. Date de la réunion RCP</label>
              <input
                type="date"
                id="onb-session-date"
                name="sessionDate"
                class="ds-input"
                value="${esc(agenda.sessionDate)}"
                required
                data-testid="input-onboarding-date"
              >
            </div>
            <div class="ds-field">
              <label class="ds-label" for="onb-sort-strategy">2. Mode d'organisation</label>
              <select id="onb-sort-strategy" name="sortStrategy" class="ds-select" data-testid="select-onboarding-strategy">
                ${strategyOptions
                  .map(
                    (opt) =>
                      `<option value="${esc(opt.value)}" ${agenda.sortStrategy === opt.value ? "selected" : ""}>${esc(opt.label)}</option>`,
                  )
                  .join("")}
              </select>
            </div>
          </div>

          <div class="ds-field">
            <span class="ds-label">3. Spécialistes présents à la réunion</span>
            <input type="hidden" name="attendingExpertsPresent" value="true">
            <div class="ds-agenda-onboarding__checklist" data-testid="onboarding-experts-list">
              ${onboardingExpertsHtml}
            </div>
          </div>

          <div class="ds-field">
            <span class="ds-label">4. Patients inscrits par défaut (${allOnboardingPatients.length})</span>
            <input type="hidden" name="patientIdsPresent" value="true">
            <div class="ds-agenda-onboarding__checklist" data-testid="onboarding-patients-list">
              ${onboardingPatientsHtml}
            </div>
          </div>
        </div>
        <div class="ds-modal__footer">
          <button type="button" class="ds-btn ds-btn--ghost" data-close="schedule-meeting-dialog">Annuler</button>
          <button type="submit" class="ds-btn ds-btn--primary" data-testid="btn_confirm_schedule_meeting">
            ${iconSvg("ic-check")} Générer l'ordre du jour
          </button>
        </div>
      </form>
    </dialog>

    <!-- Destructive Confirmation Modal for Clearing Agenda (DataSyntis Rose) -->
    <dialog class="ds-modal ds-modal--danger" id="clear-agenda-dialog" aria-labelledby="clear-agenda-title">
      <div class="ds-modal__header">
        <span>${iconSvg("ic-delete")}</span>
        <h2 id="clear-agenda-title">Vider l'ordre du jour de la séance RCP ?</h2>
      </div>
      <div class="ds-modal__body">
        <div class="ds-alert ds-alert--danger" role="alert">
          <span class="ds-alert__icon">${iconSvg("ic-priority-high")}</span>
          <div class="ds-alert__content">
            <span class="ds-alert__title">Réinitialisation de la liste de passage</span>
            <span>Les ${agenda.items.length} dossiers seront retirés de l'ordre du jour (les dossiers patients eux-mêmes ne sont pas supprimés).</span>
          </div>
        </div>
      </div>
      <div class="ds-modal__footer">
        <form method="dialog"><button class="ds-btn ds-btn--ghost" autofocus>Annuler</button></form>
        <form method="post" action="/agenda/patients/clear?domain=${domainParam}">
          <button type="submit" class="ds-btn ds-btn--danger" data-testid="btn_danger_confirm_clear_agenda">
            ${iconSvg("ic-delete")} Confirmer la réinitialisation
          </button>
        </form>
      </div>
    </dialog>
  `;

  return renderLayout({
    title: t("nav.agenda", lang),
    activeNav: "agenda",
    breadcrumbs: [{ label: t("nav.agenda", lang) }],
    session,
    queueStats,
    queueJobs,
    bodyHtml,
  });
}
