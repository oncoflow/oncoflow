import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
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
} from "./components/ai-chat.component.js";

export {
  renderAiChatComponent,
  renderAiChatDrawer,
  renderAiThinkingModule,
  renderChatLogMessagePartial,
};

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ICONS_SVG_PATH = path.resolve(__dirname, "../../public/img/icons.svg");
const INLINE_ICONS_SVG = fs.existsSync(ICONS_SVG_PATH)
  ? fs.readFileSync(ICONS_SVG_PATH, "utf8")
  : "";

export function esc(val: unknown): string {
  if (val === null || val === undefined) return "";
  return String(val)
    .replace(/(\d{4})-(\d{2})-(\d{2})T00:00:00(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?/g, "$3/$2/$1")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Formats a duration in seconds as "X min YY s" (e.g., "0 min 12 s", "1 min 08 s").
 */
export function formatDurationMinSec(seconds: number): string {
  const totalSec = Math.max(0, Math.round(Number(seconds) || 0));
  const mins = Math.floor(totalSec / 60);
  const secs = totalSec % 60;
  return `${mins} min ${String(secs).padStart(2, "0")} s`;
}

export function iconSvg(id: string, sizeClass = ""): string {
  const cls = sizeClass ? `ds-icon ${sizeClass}` : "ds-icon";
  return `<svg class="${cls}" aria-hidden="true"><use href="#${esc(id)}"/></svg>`;
}

export function deriveRcpTone(
  priorityLevel: string | undefined,
  isComplete = true,
): "red" | "orange" | "green" {
  const norm = (priorityLevel ?? "").toLowerCase();
  if (norm === "high" || (norm.includes("urgent") && !norm.includes("semi"))) {
    return "red";
  }
  if (norm === "medium" || norm.includes("semi") || norm.includes("mod") || !isComplete) {
    return "orange";
  }
  return "green";
}

export function extractDobFromPatientId(id: string | null | undefined): string | null {
  if (!id) return null;
  const m = id.match(/(?:_|-)(\d{4})[_-](\d{2})[_-](\d{2})$/);
  if (!m) return null;
  return `${m[3]}/${m[2]}/${m[1]}`;
}

export function formatPatientSubtitle(id: string, rcpCount: number): string {
  const rcpLabel = `${rcpCount} ${rcpCount > 1 ? "séances RCP" : "séance RCP"}`;
  const dob = extractDobFromPatientId(id);
  if (dob) {
    return `Né(e) le ${dob} · ${rcpLabel}`;
  }
  if (id && !id.includes("_") && !id.toLowerCase().endsWith(".pdf")) {
    return `Dossier ${id} · ${rcpLabel}`;
  }
  return rcpLabel;
}

export interface ShellLayoutOptions {
  title: string;
  activeNav: "worklist" | "ingest" | "guidelines" | "agents" | "feedback" | "queue" | "dossier";
  breadcrumbs: Array<{ label: string; href?: string }>;
  session: UserSession;
  queueStats: QueueStats;
  queueJobs: QueueJobItem[];
  bodyHtml: string;
  toastMessage?: string | null;
}

export function renderQueueBannerPartial(stats: QueueStats, session: UserSession): string {
  const lang = session.language;
  if (stats.failed > 0 && stats.running === 0) {
    return `<div class="ds-queue-banner ds-queue-banner--error" role="status" aria-live="polite" aria-atomic="true" id="queue-banner" data-testid="queue-banner">
      <span class="ds-queue-banner__text">
        ${iconSvg("ic-error")}
        <span class="ds-queue-banner__msg"><strong>${stats.failed} ${lang === "fr" ? "analyse(s) en échec" : "failed job(s)"}</strong>${stats.activeFormFile ? ` · ${esc(stats.activeFormFile)}` : ""}</span>
      </span>
      <button type="button" class="ds-btn ds-btn--sm ds-btn--secondary ds-queue-banner__action" data-open="queue-drawer" aria-haspopup="dialog" data-testid="btn_queue_open">${esc(t("queue.banner.open", lang))}</button>
    </div>`;
  }

  if (stats.running > 0 || stats.pending > 0) {
    return `<div class="ds-queue-banner" role="status" aria-live="polite" aria-atomic="true" id="queue-banner" data-testid="queue-banner">
      <span class="ds-queue-banner__text">
        <span class="ds-spinner" aria-hidden="true"></span>
        <span class="ds-queue-banner__msg"><strong>${stats.running} ${esc(t("queue.banner.running", lang))}</strong> · ${stats.pending} ${lang === "fr" ? "en attente" : "pending"}${stats.activeFormFile ? ` · ${esc(stats.activeFormFile)}` : ""}</span>
      </span>
      <progress class="ds-progress ds-queue-banner__progress" max="100" value="${Math.round(stats.activeProgressPct || 50)}" aria-label="Avancement de la file"></progress>
      <button type="button" class="ds-btn ds-btn--sm ds-btn--secondary ds-queue-banner__action" data-open="queue-drawer" aria-haspopup="dialog" data-testid="btn_queue_open">${esc(t("queue.banner.open", lang))}</button>
    </div>`;
  }

  return `<div class="ds-queue-banner ds-queue-banner--idle" role="status" aria-live="polite" aria-atomic="true" id="queue-banner" data-testid="queue-banner">
    <span class="ds-queue-banner__text">
      ${iconSvg("ic-clock")}
      <span class="ds-queue-banner__msg">${esc(t("queue.banner.idle", lang))}</span>
    </span>
    <button type="button" class="ds-btn ds-btn--sm ds-btn--ghost ds-queue-banner__action" data-open="queue-drawer" aria-haspopup="dialog" data-testid="btn_queue_open">${esc(t("queue.banner.open", lang))}</button>
  </div>`;
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
            return `<div class="ds-job">
              <span class="ds-job__title">${esc(j.filename ?? j.jobType)}</span>
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

  return `<!doctype html>
<html lang="${esc(lang)}" data-theme="${esc(session.theme)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${esc(title)} — DataSyntis</title>
  <link rel="icon" href="/public/img/datasyntis-icon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/public/css/tokens.css?v=m3-18">
  <link rel="stylesheet" href="/public/css/components.css?v=m3-18">
</head>
<body class="ds-shell">
  ${INLINE_ICONS_SVG}
  <a class="ds-skip-link" href="#main">${lang === "fr" ? "Aller au contenu" : "Skip to content"}</a>

  <!-- ===================== Sidebar (Material Design 3 Navigation Rail) ===================== -->
  <aside class="ds-sidebar ds-nav-rail" aria-label="Navigation principale" data-testid="sidebar">
    <a class="ds-brand" href="/worklist?domain=${domainParam}" title="DataSyntis — ${session.domain === "sma" ? "RCP Maladies Rares · SMA" : "RCP Oncologie Digestive"}">
      <img class="ds-brand__logo" src="/public/img/datasyntis-icon.svg" alt="" width="32" height="32">
      <span class="ds-brand__text">
        <span class="ds-brand__name">Data<b>Syntis</b></span>
        <span class="ds-brand__domain">${session.domain === "sma" ? "RCP Maladies Rares · SMA" : "RCP Oncologie Digestive"}</span>
      </span>
    </a>

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
            <span class="ds-nav__indicator">${iconSvg("ic-worklist")}</span>
            <span class="ds-nav__label">${esc(t("nav.worklist", lang))}</span>
          </a>
        </li>
        <li>
          <a class="ds-nav__link" href="/guidelines?domain=${domainParam}" ${activeNav === "guidelines" ? 'aria-current="page"' : ""} data-rail-label="${esc(t("nav.guidelines", lang))}" title="${esc(t("nav.guidelines", lang))}" data-testid="nav-guidelines">
            <span class="ds-nav__indicator">${iconSvg("ic-book")}</span>
            <span class="ds-nav__label">${esc(t("nav.guidelines", lang))}</span>
          </a>
        </li>
        <li>
          <a class="ds-nav__link" href="/agents?domain=${domainParam}" ${activeNav === "agents" ? 'aria-current="page"' : ""} data-rail-label="${esc(t("nav.agents", lang))}" title="${esc(t("nav.agents", lang))}" data-testid="nav-agents">
            <span class="ds-nav__indicator">${iconSvg("ic-users")}</span>
            <span class="ds-nav__label">${esc(t("nav.agents", lang))}</span>
          </a>
        </li>
      </ul>

      <p class="ds-nav__heading">${lang === "fr" ? "Supervision & Qualité" : "Supervision & Quality"}</p>
      <ul class="ds-nav">
        <li>
          <a class="ds-nav__link" href="/admin/queue?domain=${domainParam}" ${activeNav === "queue" ? 'aria-current="page"' : ""} data-rail-label="${esc(t("nav.queue", lang))}" title="${esc(t("nav.queue", lang))}" data-testid="nav-queue">
            <span class="ds-nav__indicator">${iconSvg("ic-layers")}</span>
            <span class="ds-nav__label">${esc(t("nav.queue", lang))}</span>
            ${activeCount > 0 ? `<span class="ds-nav__count">${activeCount}</span>` : ""}
          </a>
        </li>
        <li>
          <a class="ds-nav__link" href="/feedback?domain=${domainParam}" ${activeNav === "feedback" ? 'aria-current="page"' : ""} data-rail-label="${esc(t("nav.feedback", lang))}" title="${esc(t("nav.feedback", lang))}" data-testid="nav-feedback">
            <span class="ds-nav__indicator">${iconSvg("ic-bug")}</span>
            <span class="ds-nav__label">${esc(t("nav.feedback", lang))}</span>
          </a>
        </li>
        ${
          session.expertMode
            ? `<li>
                <a class="ds-nav__link" href="/styleguide" data-rail-label="${esc(t("nav.styleguide", lang))}" title="${esc(t("nav.styleguide", lang))}" data-testid="nav-styleguide">
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

  <div class="ds-main" id="top">
    <header class="ds-topbar">
      <button type="button" class="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon" id="sidebar-toggle" aria-label="Replier ou déplier le menu latéral" aria-expanded="true" data-tooltip="Navigation Rail M3" data-testid="btn_sidebar_toggle">
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

        <!-- Sélecteur de thème Clair / Sombre M3 -->
        <div class="ds-segmented" role="radiogroup" aria-label="Choix du thème (Clair ou Sombre)" data-testid="theme-selector">
          <input type="radio" name="ds-theme" id="theme-light" value="light" ${session.theme === "light" ? "checked" : ""}>
          <label for="theme-light">${iconSvg("ic-sun")} ${esc(t("topbar.theme.light", lang))}</label>
          <input type="radio" name="ds-theme" id="theme-dark" value="dark" ${session.theme === "dark" ? "checked" : ""}>
          <label for="theme-dark">${iconSvg("ic-moon")} ${esc(t("topbar.theme.dark", lang))}</label>
        </div>

        <!-- Menu contextuel M3 d'accès rapide (...) -->
        <details class="ds-menu" data-testid="menu-topbar-actions">
          <summary class="ds-menu__trigger" aria-label="Menu contextuel d'affichage et d'accès rapide" title="Plus d'options M3">
            ${iconSvg("ic-more-vert")}
          </summary>
          <div class="ds-menu__panel" role="menu">
            <div class="ds-menu__header">${lang === "fr" ? "Navigation & Affichage" : "Navigation & View"}</div>
            <button type="button" class="ds-menu__item" role="menuitem" data-menu-action="toggle-rail">
              ${iconSvg("ic-menu")}
              <span>${lang === "fr" ? "Replier / Déplier le Rail M3" : "Toggle M3 Navigation Rail"}</span>
            </button>
            <button type="button" class="ds-menu__item" role="menuitem" data-menu-action="toggle-theme">
              ${iconSvg(session.theme === "dark" ? "ic-sun" : "ic-moon")}
              <span>${lang === "fr" ? "Basculer Thème Clair / Sombre" : "Toggle Light / Dark Theme"}</span>
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

  <script src="/public/js/app.js?v=m3-18" defer></script>
</body>
</html>`;
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
            const compl = deriveCompletenessInfo(
              {
                is_complete: c.isComplete,
                missing_count: c.missingCount,
                missing_items: c.missingItems,
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
            const dossierHref = c.patientId
              ? `/patients/${encodeURIComponent(c.patientId)}?domain=${domainParam}`
              : `/forms/${encodeURIComponent(c.file)}?domain=${domainParam}`;
            const specsHtml = c.specialties
              .slice(0, 3)
              .map((s) => {
                const p = getAgentPresentation(s, lang);
                return `<span class="ds-badge ds-badge--specialty ds-badge--sm">${iconSvg(p.icon)} ${esc(p.label)}</span>`;
              })
              .join(" ");

            const completenessCell =
              !c.isComplete && c.missingItems.length > 0
                ? `<div class="ds-hovercard" tabindex="0">
                    <span class="ds-badge ${compl.badgeClass} ds-badge--sm">${iconSvg(compl.icon)} ${esc(compl.label)}</span>
                    <div class="ds-hovercard__panel" role="tooltip">
                      <span class="ds-hovercard__title">${iconSvg("ic-warning")} Éléments manquants</span>
                      <ul class="ds-hovercard__list">${c.missingItems.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>
                    </div>
                  </div>`
                : `<span class="ds-badge ${compl.badgeClass} ds-badge--sm">${iconSvg(compl.icon)} ${esc(compl.label)}</span>`;

            return `<tr class="${c.priorityLevel === "high" ? "is-urgent" : ""}" data-href="${dossierHref}" title="Double-cliquez pour ouvrir le dossier de ${esc(c.patientName)}" data-testid="worklist-row-${esc(c.id)}">
              <td>
                <span class="ds-badge ${prio.badgeClass} ds-badge--sm" data-testid="badge-priority-${esc(c.priorityLevel)}">
                  ${iconSvg(prio.icon)} ${esc(prio.label)}
                </span>
              </td>
              <td>
                <a class="ds-table__primary-link" href="${dossierHref}">${esc(c.patientName)}</a><br>
                <span class="ds-small ds-muted">${esc(formatPatientSubtitle(c.id, c.rcpCount))}</span>
              </td>
              <td>${completenessCell}</td>
              <td>
                <span class="ds-badge ${orient.badgeClass} ds-badge--sm" data-testid="badge-orientation-${esc(orient.status)}">
                  ${iconSvg(orient.icon)} ${esc(orient.label)}
                </span>
                ${c.proposedCareType ? `<div class="ds-small ds-muted">${esc(c.proposedCareType)}</div>` : ""}
              </td>
              <td>${specsHtml || '<span class="ds-small ds-muted">—</span>'}</td>
              <td class="ds-nowrap">${esc(c.mdtDate ?? "—")}</td>
              <td class="ds-table__actions">
                <div class="ds-cluster" style="justify-content:flex-end;flex-wrap:nowrap">
                  <a class="ds-btn ds-btn--tonal ds-btn--sm" href="${dossierHref}" data-testid="btn_open_${esc(c.id)}">Ouvrir</a>
                  <details class="ds-menu" data-testid="menu-patient-${esc(c.id)}">
                    <summary class="ds-menu__trigger" aria-label="Actions contextuelles pour ${esc(c.patientName)}" title="Actions patient M3">
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
                      <hr class="ds-menu__divider">
                      <a class="ds-menu__item" role="menuitem" href="/feedback?domain=${domainParam}&patientId=${encodeURIComponent(c.patientId ?? c.id)}">
                        ${iconSvg("ic-bug")}
                        <span>Signaler une anomalie</span>
                      </a>
                      <button type="button" class="ds-menu__item ds-menu__item--danger" role="menuitem" data-open="del-dialog-${esc(c.id)}" data-testid="btn_del_patient_${esc(c.id)}">
                        ${iconSvg("ic-delete")}
                        <span>Supprimer ce dossier…</span>
                      </button>
                    </div>
                  </details>
                </div>
                <dialog class="ds-modal ds-modal--danger" id="del-dialog-${esc(c.id)}" aria-labelledby="del-title-${esc(c.id)}">
                  <div class="ds-modal__header">
                    <span>${iconSvg("ic-delete")}</span>
                    <h2 id="del-title-${esc(c.id)}">Supprimer le dossier de ${esc(c.patientName)} ?</h2>
                  </div>
                  <div class="ds-modal__body">
                    <div class="ds-alert ds-alert--danger" role="alert">
                      <span class="ds-alert__icon">${iconSvg("ic-priority-high")}</span>
                      <div class="ds-alert__content">
                        <span class="ds-alert__title">Action irréversible</span>
                        <span>Les fiches RCP et les modifications manuelles associées à ${esc(c.patientName)} (#${esc(c.id)}) seront définitivement supprimées.</span>
                      </div>
                    </div>
                  </div>
                  <div class="ds-modal__footer">
                    <form method="dialog"><button class="ds-btn ds-btn--ghost" autofocus>Annuler</button></form>
                    <form method="post" action="/patients/${encodeURIComponent(c.id)}/delete?domain=${domainParam}">
                      <button type="submit" class="ds-btn ds-btn--danger" data-testid="btn_danger_confirm_${esc(c.id)}">${iconSvg("ic-delete")} Supprimer définitivement</button>
                    </form>
                  </div>
                </dialog>
              </td>
            </tr>`;
          })
          .join("");

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

    <!-- Filter Toolbar -->
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
          <option value="table" ${(filter.displayMode ?? "table") === "table" ? "selected" : ""}>Vue Table</option>
          <option value="cards" ${filter.displayMode === "cards" ? "selected" : ""}>Vue Cartes</option>
        </select>
      </div>
      <div class="ds-toolbar__end">
        <button type="submit" class="ds-btn ds-btn--tonal">${iconSvg("ic-search")} Filtrer</button>
        <a class="ds-btn ds-btn--ghost" href="/worklist?domain=${domainParam}">Réinitialiser</a>
      </div>
    </form>

    ${
      cards.length === 0
        ? `<div class="ds-empty" data-testid="empty-worklist">
            <span class="ds-empty__icon">${iconSvg("ic-folder-open")}</span>
            <span class="ds-empty__title">Aucun dossier correspondant aux critères</span>
            <p class="ds-empty__text">Importez des comptes rendus PDF ou réinitialisez les filtres de la worklist.</p>
            <a class="ds-btn ds-btn--primary" href="/ingest?domain=${domainParam}">${iconSvg("ic-upload")} Importer des PDF</a>
          </div>`
        : filter.displayMode === "cards"
          ? `<div class="ds-patient-grid" id="worklist" data-testid="worklist-table">
              ${cards
                .map((c) => {
                  const prio = derivePriorityBadgeInfo(c.priorityLevel, lang, true);
                  const compl = deriveCompletenessInfo(
                    {
                      is_complete: c.isComplete,
                      missing_count: c.missingCount,
                      missing_items: c.missingItems,
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
                  const dossierHref = c.patientId
                    ? `/patients/${encodeURIComponent(c.patientId)}?domain=${domainParam}`
                    : `/forms/${encodeURIComponent(c.file)}?domain=${domainParam}`;
                  const cardTone = deriveRcpTone(c.priorityLevel, c.isComplete);
                  return `<article class="ds-card ds-card--interactive ds-patient-card ds-patient-card--${cardTone}" data-href="${dossierHref}" title="Double-cliquez pour ouvrir le dossier de ${esc(c.patientName)}" data-testid="worklist-row-${esc(c.id)}">
                    <div class="ds-card__header">
                      <h2 class="ds-patient-card__name"><a href="${dossierHref}">${esc(c.patientName)}</a></h2>
                      <span class="ds-patient-card__id">${esc(formatPatientSubtitle(c.id, c.rcpCount))}</span>
                    </div>
                    <div class="ds-card__body">
                      <div class="ds-cluster">
                        <span class="ds-badge ${prio.badgeClass} ds-badge--sm">${iconSvg(prio.icon)} ${esc(prio.label)}</span>
                        <span class="ds-badge ${compl.badgeClass} ds-badge--sm">${iconSvg(compl.icon)} ${esc(compl.label)}</span>
                        <span class="ds-badge ${orient.badgeClass} ds-badge--sm">${iconSvg(orient.icon)} ${esc(orient.label)}</span>
                      </div>
                      ${c.summaryText ? `<p class="ds-small">${esc(c.summaryText)}</p>` : ""}
                      ${c.proposedCareType ? `<span class="ds-small ds-muted">${esc(c.proposedCareType)}</span>` : ""}
                    </div>
                    <div class="ds-card__footer">
                      <span class="ds-small ds-muted">RCP : ${esc(c.mdtDate ?? "—")}</span>
                      <div class="ds-card__footer-end">
                        <a class="ds-btn ds-btn--tonal ds-btn--sm" href="${dossierHref}" data-testid="btn_open_${esc(c.id)}">Ouvrir</a>
                        <details class="ds-menu" data-testid="menu-patient-${esc(c.id)}">
                          <summary class="ds-menu__trigger" aria-label="Actions contextuelles pour ${esc(c.patientName)}" title="Actions patient M3">
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
                          </div>
                        </details>
                      </div>
                    </div>
                  </article>`;
                })
                .join("")}
            </div>`
          : `<div class="ds-table-wrap">
            <table class="ds-table ds-table--dense" id="worklist" data-testid="worklist-table">
              <caption class="ds-sr-only">Worklist RCP triée par priorité</caption>
              <thead>
                <tr>
                  <th scope="col" aria-sort="descending">Priorité</th>
                  <th scope="col">Patient</th>
                  <th scope="col">Complétude</th>
                  <th scope="col">Orientation pré-RCP</th>
                  <th scope="col">Spécialités requises</th>
                  <th scope="col">Dernière RCP</th>
                  <th scope="col" class="ds-table__actions"><span class="ds-sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                ${rowsHtml}
              </tbody>
            </table>
          </div>`
    }
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
): string {
  const domainParam = encodeURIComponent(domain);
  const fileParam = encodeURIComponent(filename);
  const secParam = encodeURIComponent(sec.name);

  if (editing) {
    const inputsHtml = sec.fields
      .map(
        (f) => `<div class="ds-field">
          <label class="ds-label" for="inp-${esc(sec.name)}-${esc(f.key)}">${esc(f.label)}</label>
          <input class="ds-input" id="inp-${esc(sec.name)}-${esc(f.key)}" name="${esc(f.key)}" value="${esc(typeof f.rawValue === "object" ? f.value : (f.rawValue ?? f.value))}">
        </div>`,
      )
      .join("");

    return `<details class="ds-section is-editing" open id="section-${esc(sec.name)}" data-testid="section-${esc(sec.name)}">
      <summary>
        <span class="ds-section__title">${iconSvg(sec.meta.icon)} ${esc(sec.meta.title)}</span>
        <span class="ds-section__summary">Édition manuelle en cours…</span>
      </summary>
      <form class="ds-section__body" method="post" action="/forms/${fileParam}/sections/${secParam}?domain=${domainParam}" data-ajax-section="section-${esc(sec.name)}">
        ${inputsHtml}
        <div class="ds-section__actions">
          <button type="submit" class="ds-btn ds-btn--primary ds-btn--sm" data-testid="btn_save_section_${esc(sec.name)}">${iconSvg("ic-check")} Enregistrer</button>
          <a class="ds-btn ds-btn--ghost ds-btn--sm" href="/forms/${fileParam}?domain=${domainParam}#section-${esc(sec.name)}">Annuler</a>
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
              (f) => `<div class="ds-kv">
                <span class="ds-kv__label">${esc(f.label)}</span>
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
            (f) => `<div class="ds-rationale">
              <span class="ds-rationale__label">${esc(f.label)}</span>
              <p class="ds-rationale__text">${esc(f.value)}</p>
            </div>`,
          )
          .join("");

  const emptyHtml =
    shortFields.length === 0 && longFields.length === 0 && sec.subCards.length === 0
      ? `<p class="ds-small ds-muted">Aucune donnée extraite pour cette rubrique.</p>`
      : "";

  const refsHtml =
    sec.references.length === 0
      ? ""
      : `<ul class="ds-refs" aria-label="Références">
          ${sec.references
            .map(
              (r) =>
                `<li class="ds-ref"><span class="ds-ref__source">${iconSvg("ic-book", "ds-icon--xs")} ${esc(r.name)}${r.page ? ` p. ${esc(r.page)}` : ""}</span>${r.excerpt ? `<span class="ds-ref__quote">« ${esc(r.excerpt)} »</span>` : ""}</li>`,
            )
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
  return `<details class="ds-section ${sec.isManual ? "ds-section--manual" : ""} ${secToneClass}" id="section-${esc(sec.name)}" data-testid="section-${esc(sec.name)}">
    <summary>
      <span class="ds-section__title">${iconSvg(sec.meta.icon)} ${esc(sec.meta.title)}</span>
      ${
        sec.isManual
          ? `<span class="ds-badge ds-badge--manual ds-badge--sm" data-testid="badge-manual-edit">${iconSvg("ic-edit-note")} Modifié manuellement</span>`
          : ""
      }
      <span class="ds-section__summary">${esc(sec.summaryText)}</span>
    </summary>
    <div class="ds-section__body">
      ${emptyHtml}
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
        <form method="post" action="/forms/${fileParam}/sections/${secParam}/rerun?domain=${domainParam}" style="display:inline-flex">
          <input type="hidden" name="preserve_manual_edits" value="true">
          <button type="submit" class="ds-btn ds-btn--ghost ds-btn--sm" data-tooltip="Relance l'extraction IA en préservant les modifications manuelles" data-testid="btn_rerun_section_${esc(sec.name)}">
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

export function renderDossierPage(
  dossier: PatientDossierView,
  session: UserSession,
  queueStats: QueueStats,
  queueJobs: QueueJobItem[],
  chatHistory: Array<{ question: string; reply: ChatReply }> = [],
  editingSection?: string,
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
        <a class="ds-timeline__link ds-timeline__link--${stepTone}" href="${baseTargetUrl}?file=${encodeURIComponent(step.file)}&domain=${domainParam}" ${step.isCurrent ? 'aria-current="step"' : ""}>
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

  const clinicalSections = dossier.sections.filter((s) => s.meta.tab === "clinical");
  const opinionSections = dossier.sections.filter((s) => s.meta.tab === "opinions");

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
      ),
    )
    .join("");

  // Collapsible CareOrientationProposal card (collapsed by default) with M3 Tonal Gradient header
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
              ? `<div class="ds-kv-grid"><div class="ds-kv"><span class="ds-kv__label">Modalité proposée</span><span class="ds-kv__value">${esc(dossier.careProposal.proposedCareType)}</span></div></div>`
              : ""
          }
          <div class="ds-rationale">
            <span class="ds-rationale__label">${iconSvg("ic-compass", "ds-icon--xs")} Argumentaire clinique pré-RCP</span>
            <p class="ds-rationale__text">${esc(dossier.careProposal.clinicalRationale)}</p>
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
                (s, sIdx) => `<div class="ds-subcard" style="gap:var(--ds-space-2)">
                  <div class="ds-subcard__header">
                    <span class="ds-subcard__title">Proposition ${sIdx + 1}</span>
                  </div>
                  <p style="font-size:var(--ds-text-sm);color:var(--ds-color-text)">${esc(s.suggestion)}</p>
                  ${
                    s.why
                      ? `<div class="ds-rationale">
                          <span class="ds-rationale__label">Justification clinique</span>
                          <p class="ds-rationale__text">${esc(s.why)}</p>
                        </div>`
                      : ""
                  }
                  ${
                    s.references.length > 0
                      ? `<ul class="ds-refs" aria-label="Références">
                          ${s.references
                            .map(
                              (r) =>
                                `<li class="ds-ref"><span class="ds-ref__source">${iconSvg("ic-book", "ds-icon--xs")} ${esc(r.name)}${r.page ? ` p. ${esc(r.page)}` : ""}</span>${r.excerpt ? `<span class="ds-ref__quote">« ${esc(r.excerpt)} »</span>` : ""}</li>`,
                            )
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
                <div class="ds-stack--sm">
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

  // Build available clinical specialties for the Assistant IA tab (exclude technical pipeline extractors)
  const specialistAgents = dossier.agents.filter((a) => {
    const lower = a.name.toLowerCase();
    return (
      lower.includes("expert") &&
      !lower.includes("ressource") &&
      !lower.includes("administrative") &&
      !lower.includes("summary")
    );
  });
  const assistantAgents =
    specialistAgents.length > 0
      ? specialistAgents
      : dossier.specialties.map((s) => ({
          name: s.name,
          label: s.label,
          icon: s.icon,
          role: "",
          description: "",
          guidelines: [],
        }));
  const defaultAgentName =
    assistantAgents.find((a) => a.name.includes("expert"))?.name ??
    assistantAgents[0]?.name ??
    (session.domain === "sma" ? "neurologist expert" : "pancreas expert");

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
  });

  const bodyHtml = `
    <!-- Unified RCP Hero Card: M3 Tonal Gradient Header + Synoptic Markers + Longitudinal Timeline -->
    <div class="ds-synoptic ds-synoptic--static ds-synoptic--${dossierTone}" data-testid="synoptic-card">
      <!-- Top M3 Tonal Gradient Header (Vert / Orange / Rouge) -->
      <div class="ds-synoptic__row" data-testid="patient-rcp-header">
        <div class="ds-cluster" style="gap:var(--ds-space-2) var(--ds-space-3)">
          <h1 class="ds-patient-header__name" style="font-size:var(--ds-text-xl)">${esc(dossier.patientName)}</h1>
          <ul class="ds-patient-header__meta">
            ${displayDob ? `<li>Né(e) le ${esc(displayDob)}</li>` : ""}
            ${dossier.gender ? `<li>${esc(dossier.gender)}</li>` : ""}
            ${showShortPatientCode ? `<li class="ds-mono">Dossier ${esc(dossier.patientId)}</li>` : ""}
            <li>${dossier.rcpCount} ${dossier.rcpCount > 1 ? "séances RCP" : "séance RCP"}</li>
            <li><span class="ds-badge ds-badge--neutral ds-badge--sm">${iconSvg("ic-clock")} ${formatDurationMinSec(dossier.cumulativeDurationSec)}</span></li>
          </ul>
        </div>

        <div class="ds-cluster" style="gap:var(--ds-space-2)">
          <span class="ds-badge ${dossier.priorityBadge.badgeClass}">${iconSvg(dossier.priorityBadge.icon)} ${esc(dossier.priorityBadge.label)}</span>
          <div class="ds-hovercard" tabindex="0">
            <span class="ds-badge ${dossier.completenessBadge.badgeClass}">
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
          <span class="ds-badge ${dossier.orientationBadge.badgeClass}" data-testid="badge-orientation-adapt">
            ${iconSvg(dossier.orientationBadge.icon)} ${esc(dossier.orientationBadge.label)}
          </span>
          ${dossier.specialties
            .map(
              (s) =>
                `<span class="ds-badge ds-badge--specialty">${iconSvg(s.icon)} ${esc(s.label)}</span>`,
            )
            .join("")}
        </div>

        <div style="margin-left:auto;display:flex;align-items:center;gap:var(--ds-space-2)">
          <button type="button" class="ds-btn ds-btn--secondary ds-btn--sm" data-open="link-patient-modal" data-testid="btn_link_patient">
            ${iconSvg("ic-link")} Rattacher
          </button>
          <form method="post" action="/forms/${encodeURIComponent(dossier.currentForm.file)}/process?domain=${domainParam}" style="display:inline-flex">
            <input type="hidden" name="preserve_manual_edits" value="true">
            <button type="submit" class="ds-btn ds-btn--tonal ds-btn--sm" data-tooltip="Relance l'analyse complète en conservant les modifications manuelles" data-testid="btn_reprocess_form">
              ${iconSvg("ic-refresh")} Relancer l'IA
            </button>
          </form>
          <button type="button" class="ds-btn ds-btn--ghost ds-btn--sm ds-synoptic__collapse-btn" data-action="toggle-synoptic-banner" aria-expanded="true" title="Replier / Déplier le bandeau synoptique" data-testid="btn_toggle_synoptic">
            <span data-synoptic-label>Replier</span>
            <svg class="ds-icon ds-icon--xs ds-synoptic__chevron" aria-hidden="true" viewBox="0 0 24 24"><path d="m18 15-6-6-6 6"/></svg>
          </button>
          <details class="ds-menu" data-testid="menu-dossier-actions">
            <summary class="ds-menu__trigger" aria-label="Actions contextuelles du dossier patient" title="Actions du dossier M3">
              ${iconSvg("ic-more-vert")}
            </summary>
            <div class="ds-menu__panel" role="menu">
              <div class="ds-menu__header">Dossier ${esc(dossier.patientName)}</div>
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
              <button type="button" class="ds-menu__item" role="menuitem" data-open="link-patient-modal">
                ${iconSvg("ic-link")}
                <span>Rattacher à un autre patient…</span>
              </button>
              <hr class="ds-menu__divider">
              <a class="ds-menu__item" role="menuitem" href="/feedback?domain=${domainParam}&patientId=${encodeURIComponent(dossier.patientId ?? dossier.currentForm.file)}">
                ${iconSvg("ic-bug")}
                <span>Signaler une anomalie sur ce dossier</span>
              </a>
            </div>
          </details>
        </div>
      </div>

      <!-- Row 1: Synoptic Clinical Markers -->
      <div class="ds-synoptic__row">
        <dl class="ds-markers">
          ${markersHtml}
        </dl>
      </div>

      <!-- Row 2: Integrated Longitudinal Timeline Strip (with Prochaine séance pinned to far right) -->
      <div class="ds-synoptic__row" style="border-top:1px solid var(--ds-color-border);padding-top:var(--ds-space-3)">
        <nav aria-label="Historique longitudinal des séances RCP" style="width:100%">
          <ol class="ds-timeline" data-testid="session-timeline">
            ${timelineHtml}
          </ol>
        </nav>
      </div>
    </div>

    <!-- Split View: Source PDF (Left) + Clinical Tabs (Right) -->
    <div class="ds-split ds-split--40-60" id="dossier-split-view" data-testid="split-view">
      <div class="ds-split__pane ds-split__pane--sticky">
        <div class="ds-cluster" style="justify-content:space-between">
          <span class="ds-label">${iconSvg("ic-file-pdf")} Document source : <code class="ds-mono">${esc(dossier.currentForm.file)}</code></span>
          <div class="ds-cluster" style="gap:var(--ds-space-1)">
            <button type="button" class="ds-btn ds-btn--secondary ds-btn--sm" data-action="toggle-pdf-expand" data-testid="btn_pdf_expand">
              ${iconSvg("ic-eye")} Élargir PDF
            </button>
            <details class="ds-menu" data-testid="menu-pdf-actions">
              <summary class="ds-menu__trigger" aria-label="Options du lecteur PDF" title="Options PDF M3">
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
        <iframe class="ds-pdf-frame" src="/files/forms/${encodeURIComponent(dossier.currentForm.file)}/pdf?domain=${domainParam}#navpanes=0&amp;pagemode=none&amp;view=FitH&amp;toolbar=1" title="Document source PDF ${esc(dossier.currentForm.file)}"></iframe>
      </div>

      <div class="ds-split__pane">
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
  `;

  return renderLayout({
    title: dossier.patientName,
    activeNav: "dossier",
    breadcrumbs: [
      { label: t("nav.worklist", lang), href: `/worklist?domain=${domainParam}` },
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
          <h2 class="ds-card__title">${iconSvg("ic-info")} Étapes du pipeline local</h2>
        </div>
        <div class="ds-card__body ds-stack--sm">
          <p class="ds-small"><strong>1. Lecture &amp; OCR local :</strong> extraction du texte et des tableaux (Docling / PyMuPDF / Granite Vision).</p>
          <p class="ds-small"><strong>2. Consolidation longitudinale :</strong> rapprochement automatique avec les séances RCP antérieures du patient.</p>
          <p class="ds-small"><strong>3. Structuration clinique :</strong> extraction par pôle médical et contrôle de complétude pré-RCP.</p>
          <p class="ds-small"><strong>4. Avis experts &amp; référentiels :</strong> confrontation locale aux référentiels ${session.domain === "sma" ? "PNDS SMA" : "TNCD"}.</p>
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

  const resourcePillsHtml = overview.resources
    .map((r) => {
      const isSelected = activeRes?.filename === r.filename;
      return `<a class="ds-chip ${isSelected ? "is-active" : ""}" href="/guidelines?domain=${domainParam}&file=${encodeURIComponent(r.filename)}" aria-pressed="${isSelected ? "true" : "false"}" data-testid="resource-item-${esc(r.filename)}">
        ${iconSvg(isSelected ? "ic-check" : "ic-book", "ds-icon--xs")}
        <span>${esc(r.filename)}</span>
        <span class="ds-badge ${r.indexed ? "ds-badge--success" : "ds-badge--warning"} ds-badge--sm">
          ${iconSvg(r.indexed ? "ic-check-circle" : "ic-warning")}
          ${r.indexed ? "Indexé" : "Non indexé"}
        </span>
      </a>`;
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
  });

  const bodyHtml = `
    <div class="ds-page-header">
      <div class="ds-page-header__text">
        <h1>${esc(t("nav.guidelines", lang))}</h1>
        <p class="ds-muted">Référentiels scientifiques (${session.domain === "sma" ? "PNDS Maladies Rares" : "TNCD Cancérologie Digestive"}) indexés localement dans Milvus pour l'aide à la préparation des séances RCP.</p>
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

    <!-- Clean M3 Top Control Bar (Streamlit ressources.py parity) -->
    <div class="ds-card" data-testid="guideline-control-bar">
      <div class="ds-card__body ds-stack--sm">
        <div class="ds-cluster" style="justify-content:space-between">
          <div class="ds-cluster">
            <span class="ds-label">${iconSvg("ic-book", "ds-icon--xs")} Sélectionner un référentiel clinique (${overview.resources.length}) :</span>
            ${
              activeRes
                ? `<span class="ds-badge ${activeRes.indexed ? "ds-badge--success" : "ds-badge--warning"} ds-badge--sm">
                    ${iconSvg(activeRes.indexed ? "ic-check-circle" : "ic-warning")}
                    ${activeRes.indexed ? "Indexé dans Milvus" : "Non indexé — cliquez sur Ré-indexer"}
                  </span>`
                : ""
            }
          </div>
          ${
            activeRes
              ? `<div class="ds-cluster" style="gap:var(--ds-space-2)">
                  <form method="post" action="/guidelines/${encodeURIComponent(activeRes.filename)}/reindex?domain=${domainParam}" style="display:inline-flex">
                    <button type="submit" class="ds-btn ds-btn--tonal ds-btn--sm" data-testid="btn_reindex_${esc(activeRes.filename)}">
                      ${iconSvg("ic-refresh")} Ré-indexer (RAG)
                    </button>
                  </form>
                  <a class="ds-btn ds-btn--secondary ds-btn--sm" href="/files/resources/${encodeURIComponent(activeRes.filename)}?domain=${domainParam}" download="${esc(activeRes.filename)}">
                    ${iconSvg("ic-download")} Télécharger PDF
                  </a>
                </div>`
              : ""
          }
        </div>
        <div class="ds-prompt-chips" role="navigation" aria-label="Référentiels disponibles">
          ${resourcePillsHtml}
        </div>
      </div>
    </div>

    <!-- Full-Width Readable PDF Viewer + Non-blocking Co-Pilot Side Sheet -->
    ${
      activeRes
        ? `<div class="ds-card" style="padding:var(--ds-space-3)">
            <div class="ds-cluster" style="justify-content:space-between;margin-bottom:var(--ds-space-2)">
              <span class="ds-label">${iconSvg("ic-file-pdf")} Aperçu : <code class="ds-mono">${esc(activeRes.filename)}</code></span>
              <a class="ds-btn ds-btn--ghost ds-btn--sm" href="/files/resources/${encodeURIComponent(activeRes.filename)}?domain=${domainParam}#navpanes=0&amp;pagemode=none&amp;view=FitH" target="_blank" rel="noopener">
                ${iconSvg("ic-expand")} Plein écran
              </a>
            </div>
            <iframe class="ds-pdf-frame" style="height:44rem" src="/files/resources/${encodeURIComponent(activeRes.filename)}?domain=${domainParam}#navpanes=0&amp;pagemode=none&amp;view=FitH&amp;toolbar=1" title="Aperçu du référentiel ${esc(activeRes.filename)}"></iframe>
          </div>`
        : `<div class="ds-empty"><span class="ds-empty__title">Aucun référentiel PDF sélectionné</span></div>`
    }

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

  const agentsHtml = agents
    .map((a) => {
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
                      ${isIndexed ? "Indexé dans Milvus" : "À indexer"}
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
          ? `<div class="ds-stack--sm" data-testid="agent-user-prompts-${esc(a.name)}">
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
          ${a.role ? `<p class="ds-small ds-muted">${esc(a.role)}</p>` : ""}
          <div class="ds-stack--sm">
            <span class="ds-label">${iconSvg("ic-book", "ds-icon--xs")} Ressources documentaires rattachées (${a.guidelines.length}) :</span>
            ${attachedResourcesHtml}
          </div>
          ${userPromptsHtml}
          ${systemPromptHtml}
        </div>
      </details>`;
    })
    .join("");

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

    <div class="ds-stack" id="agents-list" data-testid="agents-list">
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
        <td class="ds-mono">${esc(b.id)}</td>
        <td>
          <strong>${esc(b.title)}</strong>
          <div class="ds-small ds-muted">${esc(b.description)}</div>
        </td>
        <td><span class="ds-badge ds-badge--neutral ds-badge--sm">${iconSvg("ic-bug")} ${esc(b.category)}</span></td>
        <td>
          <span class="ds-badge ${b.status === "resolved" ? "ds-badge--success" : b.status === "in_progress" ? "ds-badge--info" : "ds-badge--warning"} ds-badge--sm">
            ${iconSvg(b.status === "resolved" ? "ic-check-circle" : b.status === "in_progress" ? "ic-clock" : "ic-warning")}
            ${esc(b.status)}
          </span>
        </td>
        <td class="ds-mono">${esc(b.patientOrFile ?? "—")}</td>
        <td class="ds-nowrap">${esc(b.createdAt)}</td>
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
    .map(
      (j) => `<tr data-testid="queue-job-row-${esc(j.jobId)}">
        <td class="ds-mono">${esc(j.jobId)}</td>
        <td><span class="ds-badge ${j.domain === "sma" ? "ds-badge--domain-sma" : "ds-badge--domain-onco"} ds-badge--sm">${iconSvg(j.domain === "sma" ? "ic-dna" : "ic-ribbon")} ${esc(j.domain)}</span></td>
        <td class="ds-mono">${esc(j.filename ?? "—")}</td>
        <td>${esc(j.section ?? j.jobType)}</td>
        <td>
          <span class="ds-badge ${j.status === "RUNNING" ? "ds-badge--info" : j.status === "FAILED" ? "ds-badge--danger" : j.status === "COMPLETED" ? "ds-badge--success" : "ds-badge--neutral"} ds-badge--sm">
            ${j.status === "RUNNING" ? '<span class="ds-spinner" aria-hidden="true"></span>' : iconSvg(j.status === "FAILED" ? "ic-error" : j.status === "COMPLETED" ? "ic-check-circle" : "ic-clock")}
            ${esc(j.status)}
          </span>
        </td>
        <td>
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
      </tr>`,
    )
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
