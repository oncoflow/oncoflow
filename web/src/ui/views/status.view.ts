import type { UserSession } from "../../domain/types.js";
import { html, INLINE_ICONS_SVG, iconSvg, raw, stripDomainQuery } from "./html.js";

export interface StatusPageOptions {
  statusCode: number;
  kind?: "not_found" | "maintenance" | "server_error";
  title?: string;
  message?: string;
  session: UserSession;
}

export function renderStatusPage(opts: StatusPageOptions): string {
  const { statusCode, session } = opts;
  const lang = session.language;
  const kind =
    opts.kind ??
    (statusCode === 404 ? "not_found" : statusCode === 503 ? "maintenance" : "server_error");
  const domainParam = encodeURIComponent(session.domain);
  const homeHref = session.hostBoundDomain ? "/worklist" : `/worklist?domain=${domainParam}`;

  const badgeHtml =
    kind === "not_found"
      ? html`<span class="ds-badge ds-badge--warning">${raw(iconSvg("ic-warning"))} 404 · ${lang === "fr" ? "Page introuvable" : "Page Not Found"}</span>`
      : kind === "maintenance"
        ? html`<span class="ds-badge ds-badge--info">${raw(iconSvg("ic-clock"))} 503 · ${lang === "fr" ? "Maintenance en cours" : "Scheduled Maintenance"}</span>`
        : html`<span class="ds-badge ds-badge--danger">${raw(iconSvg("ic-error"))} ${statusCode} · ${lang === "fr" ? "Incident technique" : "Server Error"}</span>`;

  const defaultTitle =
    kind === "not_found"
      ? lang === "fr"
        ? "Page ou dossier introuvable"
        : "Page or record not found"
      : kind === "maintenance"
        ? lang === "fr"
          ? "Plateforme en cours de maintenance"
          : "Platform under maintenance"
        : lang === "fr"
          ? "Service temporairement indisponible"
          : "Service temporarily unavailable";

  const defaultMessage =
    kind === "not_found"
      ? lang === "fr"
        ? "L'adresse demandée n'existe pas ou le dossier clinique a été déplacé."
        : "The requested URL does not exist or the clinical record has been moved."
      : kind === "maintenance"
        ? lang === "fr"
          ? "Une mise à jour ou une maintenance technique est en cours. Vos dossiers patients et analyses RCP locales sont intégralement préservés."
          : "A system update or maintenance is in progress. Your local patient records and MDT analyses remain safely preserved."
        : lang === "fr"
          ? "Une erreur interne est survenue lors du traitement de la requête. Veuillez réessayer dans quelques instants ou revenir à l'accueil."
          : "An internal error occurred while processing your request. Please try again in a moment or return to the home page.";

  const title = opts.title ?? defaultTitle;
  const message = opts.message ?? defaultMessage;
  const iconName =
    kind === "not_found" ? "ic-folder-open" : kind === "maintenance" ? "ic-clock" : "ic-error";

  const pageHtml = html`<!doctype html>
<html lang="${lang}" data-theme="${session.theme}" data-theme-pref="${session.theme}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${title} (${statusCode}) — DataSyntis</title>
  <link rel="icon" href="/public/img/datasyntis-icon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/public/css/tokens.css?v=29">
  <link rel="stylesheet" href="/public/css/components.css?v=29">
</head>
<body class="ds-shell" style="min-height:100dvh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:var(--ds-space-6)">
  ${raw(INLINE_ICONS_SVG)}
  <main id="main" style="width:100%;max-width:34rem">
    <section class="ds-card" style="padding:var(--ds-space-6);text-align:center;align-items:center;gap:var(--ds-space-4)" data-testid="status-page-${statusCode}">
      <a class="ds-brand" href="${raw(homeHref)}" style="justify-content:center;margin-bottom:var(--ds-space-1)">
        <img class="ds-brand__logo" src="/public/img/datasyntis-icon.svg" alt="" width="36" height="36">
        <span class="ds-brand__text" style="text-align:left">
          <span class="ds-brand__name">Data<b>Syntis</b></span>
          <span class="ds-brand__domain">${session.domain === "sma" ? "RCP Maladies Rares · SMA" : "RCP Oncologie Digestive"}</span>
        </span>
      </a>
      <div>${raw(badgeHtml)}</div>
      <div class="ds-empty__icon" style="margin-inline:auto">${raw(iconSvg(iconName, "ds-icon--lg"))}</div>
      <h1 style="font-size:var(--ds-text-xl);margin:0">${title}</h1>
      <p class="ds-muted" style="margin:0;max-width:28rem;line-height:1.5">${message}</p>
      <div style="display:flex;flex-wrap:wrap;justify-content:center;gap:var(--ds-space-3);margin-top:var(--ds-space-2)">
        <a class="ds-btn ds-btn--primary" href="${raw(homeHref)}" data-testid="btn_status_home">
          ${raw(iconSvg("ic-worklist"))} ${lang === "fr" ? "Retour à l'accueil" : "Back to home"}
        </a>
        ${raw(
          kind !== "not_found"
            ? `<a class="ds-btn ds-btn--tonal" href="" data-testid="btn_status_retry">
                 ${iconSvg("ic-refresh")} ${lang === "fr" ? "Réessayer" : "Retry"}
               </a>`
            : "",
        )}
      </div>
    </section>
  </main>
</body>
</html>`;

  return session.hostBoundDomain ? stripDomainQuery(pageHtml) : pageHtml;
}
