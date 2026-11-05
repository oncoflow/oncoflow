import type { ClinicalDomain, PractitionerNoteItem, UserSession } from "../../domain/types.js";
import { esc, iconSvg } from "../views/html.js";

export interface PractitionerNotesDrawerOptions {
  patientIdOrFile: string;
  patientName: string;
  currentFormFile: string;
  domain: ClinicalDomain;
  session: UserSession;
  notes: PractitionerNoteItem[];
}

function formatNoteTimestamp(iso: string): string {
  if (!iso) return "";
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso.slice(0, 16);
    const dd = String(dt.getDate()).padStart(2, "0");
    const mm = String(dt.getMonth() + 1).padStart(2, "0");
    const yyyy = dt.getFullYear();
    const hh = String(dt.getHours()).padStart(2, "0");
    const min = String(dt.getMinutes()).padStart(2, "0");
    return `${dd}/${mm}/${yyyy} à ${hh}:${min}`;
  } catch {
    return iso.slice(0, 16);
  }
}

export function renderPractitionerNotesPanelPartial(opts: PractitionerNotesDrawerOptions): string {
  const domainParam = encodeURIComponent(opts.domain);
  const targetEncoded = encodeURIComponent(opts.patientIdOrFile);
  const currentUserId = opts.session.userId.trim().toLowerCase();
  const myNote =
    opts.notes.find((n) => n.practitionerId.trim().toLowerCase() === currentUserId) ?? null;
  const colleagueNotes = opts.notes.filter(
    (n) => n.practitionerId.trim().toLowerCase() !== currentUserId,
  );

  const actionSaveUrl = `/patients/${targetEncoded}/notes?domain=${domainParam}`;
  const actionDeleteUrl = `/patients/${targetEncoded}/notes/delete?domain=${domainParam}`;

  return `<div class="ds-notes-panel" id="practitioner-notes-panel" data-notes-count="${opts.notes.length}" data-has-my-note="${myNote ? "true" : "false"}" data-testid="practitioner-notes-panel">
    <!-- Section 1: Current Practitioner's Own Note (1 max per practitioner) -->
    <section class="ds-notes-my-card" aria-labelledby="my-note-heading" data-testid="my-practitioner-note-card">
      <div class="ds-notes-my-card__header">
        <div class="ds-notes-my-card__author">
          <span class="ds-badge ds-badge--info ds-badge--sm">${iconSvg("ic-stethoscope")} Ma note</span>
          <strong class="ds-notes-my-card__name" data-testid="my-note-author-name">${esc(opts.session.userName)}</strong>
        </div>
        ${
          myNote
            ? `<span class="ds-small ds-muted" data-testid="my-note-updated-at">Modifiée le ${esc(formatNoteTimestamp(myNote.updatedAt))}</span>`
            : `<span class="ds-small ds-muted">1 note max par praticien · Lecture humaine uniquement</span>`
        }
      </div>

      <form class="ds-notes-form" method="post" action="${actionSaveUrl}" data-ajax-notes="practitioner-notes-panel" data-testid="form-practitioner-note">
        <input type="hidden" name="filename" value="${esc(opts.currentFormFile)}">
        <div class="ds-field">
          <label class="ds-label" for="practitioner-note-input">Votre note confraternelle sur ce dossier</label>
          <textarea class="ds-textarea ds-notes-form__textarea" id="practitioner-note-input" name="content" rows="3" maxlength="2000" required placeholder="Point de vigilance, remarque clinique pour la séance RCP (non transmis à l'IA)…" data-testid="input-practitioner-note">${esc(myNote?.content ?? "")}</textarea>
        </div>
        <div class="ds-notes-form__actions">
          <button type="submit" class="ds-btn ds-btn--primary ds-btn--sm" data-testid="btn_save_practitioner_note">
            ${iconSvg("ic-check-circle")} <span>${myNote ? "Mettre à jour ma note" : "Enregistrer ma note"}</span>
          </button>
        </div>
      </form>

      ${
        myNote
          ? `<form class="ds-notes-delete-form" method="post" action="${actionDeleteUrl}" data-ajax-notes="practitioner-notes-panel" data-testid="form-delete-practitioner-note">
              <input type="hidden" name="filename" value="${esc(opts.currentFormFile)}">
              <button type="submit" class="ds-btn ds-btn--ghost ds-btn--sm ds-notes-delete-btn" data-testid="btn_del_practitioner_note">
                ${iconSvg("ic-delete")} <span>Supprimer ma note</span>
              </button>
            </form>`
          : ""
      }
    </section>

    <!-- Section 2: Colleagues' Notes Feed (Read-Only, Shared Visibility) -->
    <section class="ds-notes-feed" aria-labelledby="colleagues-notes-heading" data-testid="colleagues-notes-feed">
      <div class="ds-notes-feed__header">
        <h3 class="ds-notes-feed__title" id="colleagues-notes-heading">
          ${iconSvg("ic-stethoscope", "ds-icon--xs")}
          <span>Notes des autres praticiens</span>
        </h3>
        <span class="ds-badge ds-badge--neutral ds-badge--sm" data-testid="colleagues-notes-count">${colleagueNotes.length}</span>
      </div>

      ${
        colleagueNotes.length === 0
          ? `<p class="ds-notes-feed__empty ds-small ds-muted" data-testid="colleagues-notes-empty">Aucune note d'un autre praticien sur ce dossier pour le moment.</p>`
          : `<ul class="ds-notes-feed__list" data-testid="colleagues-notes-list">
              ${colleagueNotes
                .map(
                  (
                    note,
                  ) => `<li class="ds-notes-card" data-testid="practitioner-note-item" data-note-author="${esc(note.practitionerId)}">
                    <div class="ds-notes-card__header">
                      <strong class="ds-notes-card__author">${iconSvg("ic-stethoscope", "ds-icon--xs")} ${esc(note.practitionerName)}</strong>
                      <span class="ds-notes-card__date">${esc(formatNoteTimestamp(note.updatedAt))}</span>
                    </div>
                    <p class="ds-notes-card__content">${esc(note.content)}</p>
                  </li>`,
                )
                .join("")}
            </ul>`
      }
    </section>
  </div>`;
}

export function renderPractitionerNotesDrawer(opts: PractitionerNotesDrawerOptions): string {
  const currentUserId = opts.session.userId.trim().toLowerCase();
  const hasMyNote = opts.notes.some((n) => n.practitionerId.trim().toLowerCase() === currentUserId);

  return `
    <!-- Mobile Quick-Note Floating Trigger (Prioritized on Mobile / Live RCP Session) -->
    <div class="ds-fab-notes" id="practitioner-notes-fab" data-testid="practitioner-notes-fab">
      <button type="button" class="ds-fab-notes__trigger${hasMyNote ? " has-my-note" : ""}" data-action="open-notes-drawer" aria-controls="practitioner-notes-drawer" aria-expanded="false" aria-label="Notes des praticiens (${opts.notes.length})" data-testid="btn_fab_practitioner_notes">
        <span class="ds-fab-notes__icon" aria-hidden="true">${iconSvg("ic-edit", "ds-icon--sm")}</span>
        <span class="ds-fab-notes__label">Notes</span>
        <span class="ds-badge ds-badge--neutral ds-badge--sm" data-notes-count-badge>${opts.notes.length}</span>
      </button>
    </div>

    <!-- Non-Blocking Desktop Side Sheet / Mobile Bottom Sheet for Practitioner Notes -->
    <aside class="ds-copilot-drawer ds-notes-drawer" id="practitioner-notes-drawer" aria-label="Notes des praticiens — ${esc(opts.patientName)}" aria-hidden="true" data-testid="practitioner-notes-drawer">
      <button type="button" class="ds-copilot-drawer__handle" data-action="close-notes-drawer" aria-label="Replier le volet Notes des praticiens" title="Replier le volet (Échap)">
        <svg class="ds-icon ds-icon--xs" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
      </button>
      <header class="ds-copilot-drawer__header">
        <div class="ds-copilot-drawer__title-group">
          <span class="ds-copilot-drawer__avatar" aria-hidden="true">${iconSvg("ic-edit", "ds-icon--sm")}</span>
          <div>
            <h2 class="ds-copilot-drawer__title">Notes des praticiens</h2>
            <p class="ds-copilot-drawer__subtitle">${esc(opts.patientName)} · Lecture humaine uniquement (hors IA)</p>
          </div>
        </div>
        <button type="button" class="ds-copilot-drawer__close-pill" data-action="close-notes-drawer" aria-label="Replier le volet Notes des praticiens" title="Replier le volet (Échap)" data-testid="btn_close_practitioner_notes">
          <svg class="ds-icon ds-icon--xs" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="3"/>
            <path d="M15 3v18"/>
            <path d="m8 9 3 3-3 3"/>
          </svg>
          <span>Fermer</span>
        </button>
      </header>
      <div class="ds-copilot-drawer__body ds-notes-drawer__body">
        ${renderPractitionerNotesPanelPartial(opts)}
      </div>
    </aside>`;
}
