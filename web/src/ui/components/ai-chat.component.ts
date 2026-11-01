import type { ChatReply } from "../../application/ports/oncoflow-api.port.js";
import type { AgentModuleInfo, ClinicalDomain } from "../../domain/types.js";

function esc(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function iconSvg(id: string, extraClass = ""): string {
  const cls = extraClass ? `ds-icon ${extraClass}` : "ds-icon";
  return `<svg class="${cls}" aria-hidden="true" focusable="false"><use href="#${id}"/></svg>`;
}

export function resolveCitationPdfHref(
  rawName: string,
  page: string | number | null | undefined,
  domain: ClinicalDomain = "oncology",
  fallbackFormFile?: string,
): string {
  const domainParam = encodeURIComponent(domain);
  const pageNum = page ? String(page).replace(/[^\d]/g, "") || "1" : "1";
  const pageHash = `#page=${encodeURIComponent(pageNum)}&amp;view=FitH`;

  const norm = (rawName || "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

  const isGuidelineRef =
    norm.includes("tncd") ||
    norm.includes("pnds") ||
    norm.includes("argumentaire") ||
    norm.includes("synthese") ||
    norm.includes("referentiel") ||
    norm.includes("recommandation") ||
    norm.includes("esmo") ||
    norm.includes("nccn") ||
    norm.includes("has");

  const isPatientRecordRef =
    !isGuidelineRef &&
    Boolean(fallbackFormFile) &&
    (norm.includes("cr ") ||
      norm.startsWith("cr") ||
      norm.includes("scanner") ||
      norm.includes("tdm") ||
      norm.includes("irm") ||
      norm.includes("tep") ||
      norm.includes("biologie") ||
      norm.includes("anapath") ||
      norm.includes("anatomopath") ||
      norm.includes("compte rendu") ||
      norm.includes("operatoire") ||
      norm.includes("dossier") ||
      norm.includes("consultation") ||
      norm.includes("courrier"));

  if (isPatientRecordRef && fallbackFormFile) {
    return `/files/forms/${encodeURIComponent(fallbackFormFile)}/pdf?domain=${domainParam}${pageHash}`;
  }

  let canonicalResource = (rawName || "").trim();
  const isCleanPdfFilename = /^[a-zA-Z0-9._\-]+\.pdf$/i.test(canonicalResource);
  if (!isCleanPdfFilename) {
    if (domain === "sma") {
      if (norm.includes("argumentaire")) {
        canonicalResource = "amyotrophie_spinale_infantile_-_argumentaire.pdf";
      } else if (norm.includes("synthese")) {
        canonicalResource = "synthese_mg_amyotrophie_spinale_infantile.pdf";
      } else {
        canonicalResource = "amyotrophie_spinale_infantile_-_pnds.pdf";
      }
    } else {
      if (norm.includes("chc") || norm.includes("foie") || norm.includes("hepato")) {
        canonicalResource = "TNCDCHC.pdf";
      } else if (
        norm.includes("oesophage") ||
        norm.includes("estomac") ||
        norm.includes("gastrique")
      ) {
        canonicalResource = "TNCDOESOPHAGE.pdf";
      } else {
        canonicalResource = "TNCDPANCREAS.pdf";
      }
    }
  }

  const formQuery = fallbackFormFile ? `&amp;formFile=${encodeURIComponent(fallbackFormFile)}` : "";
  return `/files/resources/${encodeURIComponent(canonicalResource)}?domain=${domainParam}${formQuery}${pageHash}`;
}

export interface AiChatScopeConfig {
  rcpCount: number;
  activeFormLabel: string;
}

export interface AiChatComponentOptions {
  formAction: string;
  formTestId: string;
  logId: string;
  inputId: string;
  inputTestId: string;
  inputPlaceholder: string;
  inputLabel: string;
  submitTestId: string;
  submitLabel: string;
  welcomeMessage: string;
  chatHistory: Array<{ question: string; reply: ChatReply }>;
  quickPrompts: string[];
  quickPromptsHeading?: string;
  quickPromptsTestId?: string;
  hiddenFields?: Record<string, string>;
  scopeConfig?: AiChatScopeConfig;
  agents?: Array<Pick<AgentModuleInfo, "name" | "label" | "icon">>;
  defaultAgentName?: string;
  domain?: ClinicalDomain;
}

/**
 * Dedicated Material Design 3 UX component displayed while waiting for clinical synthesis.
 */
export function renderAiThinkingModule(agentLabel = "Assistant clinique"): string {
  return `<li class="ds-chat__msg ds-chat__msg--assistant ds-chat__msg--thinking" data-chat-temp="true" data-testid="chat-thinking-indicator" role="status" aria-live="polite">
    <div class="ds-ai-thinking">
      <div class="ds-ai-thinking__header">
        <span class="ds-ai-thinking__avatar" aria-hidden="true">
          ${iconSvg("ic-sparkle", "ds-icon--xs")}
        </span>
        <div class="ds-ai-thinking__titles">
          <span class="ds-ai-thinking__agent" data-thinking-agent>${esc(agentLabel)}</span>
          <span class="ds-ai-thinking__status" data-thinking-status>Analyse clinique en cours…</span>
        </div>
        <span class="ds-ai-thinking__timer ds-mono" data-thinking-timer>0 min 00 s</span>
      </div>
      <div class="ds-ai-thinking__bar" aria-hidden="true">
        <span class="ds-ai-thinking__bar-fill"></span>
      </div>
      <ol class="ds-ai-thinking__steps" aria-label="Étapes d'analyse">
        <li class="ds-ai-thinking__step is-active" data-thinking-step="0">
          <span class="ds-ai-thinking__dot" aria-hidden="true"></span>
          <span>Lecture du dossier médical</span>
        </li>
        <li class="ds-ai-thinking__step" data-thinking-step="1">
          <span class="ds-ai-thinking__dot" aria-hidden="true"></span>
          <span>Consultation des recommandations de bonne pratique</span>
        </li>
        <li class="ds-ai-thinking__step" data-thinking-step="2">
          <span class="ds-ai-thinking__dot" aria-hidden="true"></span>
          <span>Rédaction de la réponse sourcée</span>
        </li>
      </ol>
    </div>
  </li>`;
}

/**
 * Renders a user question bubble + assistant reply bubble pair inside the chat log.
 */
export function renderChatLogMessagePartial(
  question: string,
  reply: ChatReply,
  domain: ClinicalDomain = "oncology",
  fallbackFormFile?: string,
): string {
  const refsHtml =
    reply.references.length === 0
      ? ""
      : `<ul class="ds-refs" aria-label="Sources">
          ${reply.references
            .map((r) => {
              const pdfHref = resolveCitationPdfHref(r.name, r.page, domain, fallbackFormFile);
              return `<li class="ds-ref"><a class="ds-ref__source ds-ref__link" href="${pdfHref}" target="_blank" rel="noopener" title="Ouvrir ${esc(r.name)}${r.page ? ` à la page ${esc(r.page)}` : ""}">${iconSvg("ic-file-pdf", "ds-icon--xs")} ${esc(r.name)}${r.page ? ` p. ${esc(r.page)}` : ""}</a>${r.excerpt ? `<span class="ds-ref__quote">« ${esc(r.excerpt)} »</span>` : ""}</li>`;
            })
            .join("")}
        </ul>`;

  return `<li class="ds-chat__msg ds-chat__msg--user">
    <span class="ds-chat__author">Vous</span>
    <div class="ds-chat__bubble">${esc(question)}</div>
  </li>
  <li class="ds-chat__msg ds-chat__msg--assistant" data-testid="chat-assistant-reply">
    <span class="ds-chat__author">${iconSvg("ic-sparkle", "ds-icon--xs")} Assistant clinique</span>
    <div class="ds-chat__bubble">
      <p style="white-space:pre-wrap">${esc(reply.answer)}</p>
      ${refsHtml}
    </div>
  </li>`;
}

/**
 * Standalone, fixed-height Material Design 3 Clinical AI Chat UX Component.
 * - Compact single-line header bar (Specialty M3 dropdown + Scope segmented pill)
 * - Fixed-height scrollable message log (never stretches the page as messages accumulate)
 * - Sleek M3 Composer Dock with M3 Split Button for inserting clinical suggestions
 * - Enter submits the question, Shift+Enter inserts a line break
 */
export function renderAiChatComponent(opts: AiChatComponentOptions): string {
  const hiddenInputsHtml = Object.entries(opts.hiddenFields ?? {})
    .map(([k, v]) => `<input type="hidden" name="${esc(k)}" value="${esc(v)}">`)
    .join("");

  const hasControlBar = Boolean(opts.scopeConfig || (opts.agents && opts.agents.length > 0));
  const agentOptionsHtml = (opts.agents ?? [])
    .map((ag, idx) => {
      const selected = ag.name === opts.defaultAgentName || (idx === 0 && !opts.defaultAgentName);
      return `<option value="${esc(ag.name)}" data-icon="${esc(ag.icon || "ic-stethoscope")}" data-agent-label="${esc(ag.label)}" ${selected ? "selected" : ""}>${esc(ag.label)}</option>`;
    })
    .join("");

  const controlBarHtml = hasControlBar
    ? `<div class="ds-assistant-bar" data-testid="assistant-control-bar">
        ${
          opts.agents && opts.agents.length > 0
            ? `<div class="ds-assistant-bar__specialty">
                <label class="ds-assistant-bar__label" for="${esc(opts.logId)}-specialty">
                  ${iconSvg("ic-stethoscope", "ds-icon--xs")} Spécialité médicale consultée
                </label>
                <select id="${esc(opts.logId)}-specialty" name="agentName" class="ds-select ds-select--specialty" data-testid="chat-agent-selector">
                  ${agentOptionsHtml}
                </select>
              </div>`
            : ""
        }
        ${
          opts.scopeConfig
            ? `<div class="ds-segmented ds-segmented--sm ds-assistant-bar__scope" role="radiogroup" aria-label="Périmètre du dossier">
                <input type="radio" name="scope" id="${esc(opts.logId)}-scope-patient" value="patient" checked>
                <label for="${esc(opts.logId)}-scope-patient">${iconSvg("ic-users", "ds-icon--xs")} Tout le suivi (${opts.scopeConfig.rcpCount} RCP)</label>
                <input type="radio" name="scope" id="${esc(opts.logId)}-scope-form" value="form">
                <label for="${esc(opts.logId)}-scope-form">${iconSvg("ic-file-pdf", "ds-icon--xs")} Séance du ${esc(opts.scopeConfig.activeFormLabel)}</label>
              </div>`
            : ""
        }
      </div>`
    : "";

  const chatMessagesHtml =
    opts.chatHistory.length === 0
      ? `<li class="ds-chat__msg ds-chat__msg--assistant">
          <span class="ds-chat__author">${iconSvg("ic-sparkle", "ds-icon--xs")} Assistant clinique</span>
          <div class="ds-chat__bubble">${esc(opts.welcomeMessage)}</div>
        </li>`
      : opts.chatHistory
          .map((h) => renderChatLogMessagePartial(h.question, h.reply, opts.domain ?? "oncology"))
          .join("");

  const mergedSubmitSplitBtnHtml =
    opts.quickPrompts.length === 0
      ? `<button type="submit" class="ds-btn ds-btn--primary ds-btn--sm" data-chat-submit-btn data-testid="${esc(opts.submitTestId)}">
          ${iconSvg("ic-send", "ds-icon--xs")} <span>${esc(opts.submitLabel)}</span>
        </button>`
      : `<div class="ds-split-btn ds-split-btn--primary" data-split-prompt ${opts.quickPromptsTestId ? `data-testid="${esc(opts.quickPromptsTestId)}"` : ""}>
          <button type="submit" class="ds-split-btn__main" data-chat-submit-btn data-testid="${esc(opts.submitTestId)}" title="${esc(opts.submitLabel)} (Entrée)">
            ${iconSvg("ic-send", "ds-icon--xs")}
            <span>${esc(opts.submitLabel)}</span>
          </button>
          <button type="button" class="ds-split-btn__toggle" data-split-prompt-toggle aria-haspopup="menu" aria-expanded="false" aria-label="Questions suggérées" title="Insérer une question suggérée">
            <svg class="ds-icon ds-icon--xs" aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9.5 6 6 6-6"/></svg>
          </button>
          <div class="ds-split-btn__menu" role="menu" aria-label="Questions suggérées">
            <div class="ds-menu__header">${esc(opts.quickPromptsHeading || "Questions suggérées")}</div>
            ${opts.quickPrompts
              .map(
                (qp) =>
                  `<button type="button" class="ds-menu__item" role="menuitem" data-quick-prompt="${esc(qp)}" data-target-input="${esc(opts.inputId)}">
                    ${iconSvg("ic-sparkle", "ds-icon--xs")}
                    <span>${esc(qp)}</span>
                  </button>`,
              )
              .join("")}
          </div>
        </div>`;

  return `<form class="ds-chat" method="post" action="${esc(opts.formAction)}" data-ajax-chat="${esc(opts.logId)}" data-testid="${esc(opts.formTestId)}">
    ${hiddenInputsHtml}
    ${controlBarHtml}

    <!-- Full-height scrollable conversation viewport -->
    <ol class="ds-chat__log" id="${esc(opts.logId)}" aria-live="polite" aria-label="Conversation avec l'assistant">
      ${chatMessagesHtml}
    </ol>

    <!-- Template cloned immediately on submit to display the M3 AI Reflection Module -->
    <template data-chat-thinking-template>
      ${renderAiThinkingModule()}
    </template>

    <!-- M3 Elevated Composer Dock with Unified M3 Primary Split Button (Send + Suggestions) -->
    <div class="ds-chat__composer">
      <span class="ds-chat__composer-icon" aria-hidden="true">${iconSvg("ic-chat", "ds-icon--sm")}</span>
      <label class="ds-sr-only" for="${esc(opts.inputId)}">${esc(opts.inputLabel)}</label>
      <textarea class="ds-textarea ds-chat__input" id="${esc(opts.inputId)}" name="question" rows="1" required placeholder="${esc(opts.inputPlaceholder)}" data-chat-enter-submit="true" data-testid="${esc(opts.inputTestId)}"></textarea>
      <div class="ds-chat__composer-actions">
        ${mergedSubmitSplitBtnHtml}
      </div>
    </div>
  </form>`;
}

export interface AiChatDrawerOptions extends AiChatComponentOptions {
  drawerTitle?: string;
  drawerSubtitle?: string;
  fabLabel?: string;
}

/**
 * Renders the Material Design 3 Floating Extended FAB (`.ds-fab-menu`)
 * that directly opens the Full-Height Non-Blocking Co-Pilot Side Sheet (`.ds-copilot-drawer`)
 * using M3 spatial transitions (suggestions remain inside the drawer's merged Split Button).
 */
export function renderAiChatDrawer(opts: AiChatDrawerOptions): string {
  const title = opts.drawerTitle ?? "Assistant clinique";
  const subtitle = opts.drawerSubtitle ?? "";
  const fabLabel = opts.fabLabel ?? "Assistant IA";

  return `
    <!-- Material Design 3 Floating Extended FAB (Directly Opens AI Co-Pilot Side Sheet) -->
    <div class="ds-fab-menu" id="ai-chat-fab" data-testid="ai-fab-menu">
      <button type="button" class="ds-fab-menu__trigger" data-action="open-chat-drawer" aria-controls="ai-chat-drawer" aria-expanded="false" aria-label="${esc(fabLabel)}" data-testid="btn_fab_ai_chat">
        <span class="ds-fab-menu__icon ds-fab-menu__icon--open" aria-hidden="true">${iconSvg("ic-sparkle", "ds-icon--md")}</span>
        <span class="ds-fab-menu__label">${esc(fabLabel)}</span>
      </button>
    </div>

    <!-- Material Design 3 Full-Height Non-Blocking Co-Pilot Side Sheet -->
    <aside class="ds-copilot-drawer" id="ai-chat-drawer" aria-label="${esc(title)}" aria-hidden="true" data-testid="ai-chat-drawer">
      <button type="button" class="ds-copilot-drawer__handle" data-action="close-chat-drawer" aria-label="Replier le panneau Assistant IA" title="Replier le bandeau latéral (Échap)">
        <svg class="ds-icon ds-icon--xs" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
      </button>
      <header class="ds-copilot-drawer__header">
        <div class="ds-copilot-drawer__title-group">
          <span class="ds-copilot-drawer__avatar" aria-hidden="true">${iconSvg("ic-sparkle", "ds-icon--sm")}</span>
          <div>
            <h2 class="ds-copilot-drawer__title">${esc(title)}</h2>
            ${subtitle ? `<p class="ds-copilot-drawer__subtitle">${esc(subtitle)}</p>` : ""}
          </div>
        </div>
        <button type="button" class="ds-copilot-drawer__close-pill" data-action="close-chat-drawer" aria-label="Replier le tiroir de l'assistant" title="Replier le panneau latéral (Échap)" data-testid="btn_close_ai_chat">
          <svg class="ds-icon ds-icon--xs" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="3"/>
            <path d="M15 3v18"/>
            <path d="m8 9 3 3-3 3"/>
          </svg>
          <span>Replier</span>
        </button>
      </header>
      <div class="ds-copilot-drawer__body">
        ${renderAiChatComponent(opts)}
      </div>
    </aside>`;
}
