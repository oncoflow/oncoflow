import * as echarts from "echarts";
import { formatFieldLabel, getSectionPresentation } from "../../domain/catalog.js";
import { t, translateValue } from "../../domain/i18n.js";
import type {
  ClinicalDomain,
  Language,
  PatientDashboardView,
  PatientMetricPointView,
  PatientMetricSeriesView,
  PatientRecordSummaryView,
} from "../../domain/types.js";
import { esc, iconSvg } from "../views/html.js";

function formatDateTimeDisplay(iso: string | null, lang: Language): string {
  if (!iso) return lang === "fr" ? "Non généré" : "Not generated";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  const day = pad(d.getDate());
  const month = pad(d.getMonth() + 1);
  const year = d.getFullYear();
  const hours = pad(d.getHours());
  const mins = pad(d.getMinutes());
  return lang === "fr"
    ? `${day}/${month}/${year} à ${hours}h${mins}`
    : `${year}-${month}-${day} ${hours}:${mins}`;
}

function resolveClinicalMetricLabel(series: PatientMetricSeriesView, lang: Language): string {
  if (series.label && !series.label.includes(".")) {
    return series.label;
  }
  return formatFieldLabel(series.field, lang) || series.label;
}

function resolveTranslatedPointDisplay(
  pt: PatientMetricPointView,
  valueType: string,
  lang: Language,
): string {
  if (valueType === "numeric_or_mixed") {
    return pt.displayValue;
  }
  if (Array.isArray(pt.rawValue)) {
    const items = pt.rawValue
      .map((x) => translateValue(String(x ?? "").trim(), lang))
      .filter((x) => Boolean(x) && x !== "—");
    return items.length > 0 ? items.join(", ") : pt.displayValue;
  }
  if (pt.rawValue !== null && pt.rawValue !== undefined && String(pt.rawValue).trim() !== "") {
    return translateValue(pt.rawValue, lang);
  }
  return translateValue(pt.displayValue, lang);
}

/**
 * Render an Apache ECharts multi-year raw clinical line chart to an SSR SVG string.
 */
export function renderMetricSeriesEChartsSvg(
  series: PatientMetricSeriesView,
  lang: Language,
): string {
  const width = 680;
  const height = 210;
  const chart = echarts.init(null, null, {
    renderer: "svg",
    ssr: true,
    width,
    height,
  });

  try {
    const xLabels = series.points.map((pt, idx) => {
      const base =
        pt.formDateLabel || (lang === "fr" ? `Séance #${idx + 1}` : `Session #${idx + 1}`);
      return series.points.length > 1 && pt.daysSinceFirstRcp > 0
        ? `${base}\n(J+${pt.daysSinceFirstRcp})`
        : idx === 0 && series.points.length > 1
          ? `${base}\n(J0)`
          : base;
    });

    const primaryData = series.points.map((pt) => ({
      value: pt.numericValue,
      rawDisplay: pt.displayValue,
      formId: pt.formId,
      isManual: pt.isManual,
      isAnnotativeOnly: pt.isAnnotativeOnly,
      itemStyle: {
        color: pt.isManual ? "#b45309" : "#0f766e",
        borderColor: "#ffffff",
        borderWidth: 2,
      },
    }));

    const hasBilateralD = series.points.some(
      (pt) => pt.subValues && typeof pt.subValues.D === "number",
    );
    const hasBilateralG = series.points.some(
      (pt) => pt.subValues && typeof pt.subValues.G === "number",
    );

    const echartsSeries: Record<string, unknown>[] = [
      {
        name: resolveClinicalMetricLabel(series, lang),
        type: "line",
        smooth: false,
        connectNulls: false,
        symbol: "circle",
        symbolSize: 9,
        lineStyle: {
          width: 3,
          color: "#0f766e",
        },
        label: {
          show: true,
          position: "top",
          distance: 6,
          color: "#0f172a",
          fontSize: 11,
          fontWeight: "bold",
          formatter: (params: { data?: { rawDisplay?: string } }) => params?.data?.rawDisplay ?? "",
        },
        data: primaryData,
      },
    ];

    if (hasBilateralD && hasBilateralG) {
      echartsSeries.push(
        {
          name: lang === "fr" ? "Droite (D)" : "Right (D)",
          type: "line",
          smooth: false,
          symbol: "diamond",
          symbolSize: 7,
          lineStyle: { width: 1.5, type: "dashed", color: "#0284c7" },
          itemStyle: { color: "#0284c7" },
          data: series.points.map((pt) => pt.subValues?.D ?? null),
        },
        {
          name: lang === "fr" ? "Gauche (G)" : "Left (G)",
          type: "line",
          smooth: false,
          symbol: "triangle",
          symbolSize: 7,
          lineStyle: { width: 1.5, type: "dotted", color: "#7c3aed" },
          itemStyle: { color: "#7c3aed" },
          data: series.points.map((pt) => pt.subValues?.G ?? null),
        },
      );
    }

    chart.setOption({
      animation: false,
      grid: {
        left: 48,
        right: 28,
        top: 34,
        bottom: 42,
      },
      xAxis: {
        type: "category",
        boundaryGap: true,
        data: xLabels,
        axisLine: { lineStyle: { color: "#94a3b8" } },
        axisLabel: {
          color: "#334155",
          fontSize: 11,
          interval: 0,
        },
      },
      yAxis: {
        type: "value",
        min: typeof series.scaleMin === "number" ? series.scaleMin : undefined,
        max: typeof series.scaleMax === "number" ? series.scaleMax : undefined,
        splitLine: { lineStyle: { type: "dashed", color: "#e2e8f0" } },
        axisLabel: {
          color: "#475569",
          fontSize: 11,
        },
      },
      series: echartsSeries,
    });

    return chart.renderToSVGString();
  } finally {
    chart.dispose();
  }
}

function renderSummaryCard(
  dashboard: PatientDashboardView,
  summary: PatientRecordSummaryView,
  lang: Language,
): string {
  const activeJob = summary.activeJob;
  const isQueuedOrRunning = Boolean(
    activeJob &&
      (activeJob.status === "PENDING" ||
        activeJob.status === "PROCESSING" ||
        activeJob.status === "RUNNING"),
  );

  const actionUrl = `/patients/${encodeURIComponent(dashboard.patientId)}/summary?domain=${encodeURIComponent(dashboard.domain)}`;

  let statusBadgeHtml = "";
  if (isQueuedOrRunning) {
    statusBadgeHtml = `<span class="ds-badge ds-badge--processing ds-badge--sm" data-testid="badge_summary_queued"><span class="ds-spinner" aria-hidden="true"></span> ${
      lang === "fr" ? "En file d'attente IA" : "Queued in AI Worker"
    }</span>`;
  } else if (!summary.hasSummary) {
    statusBadgeHtml = `<span class="ds-badge ds-badge--neutral ds-badge--sm" data-testid="badge_summary_empty">${iconSvg("ic-clock")} ${
      lang === "fr" ? "Non généré (à la demande)" : "Not generated (on-demand)"
    }</span>`;
  } else if (summary.isObsolete) {
    statusBadgeHtml = `<span class="ds-badge ds-badge--incomplete ds-badge--sm" data-testid="badge_summary_obsolete">${iconSvg("ic-warning")} ${
      lang === "fr" ? "Obsolète" : "Obsolete"
    }</span>`;
  } else {
    statusBadgeHtml = `<span class="ds-badge ds-badge--complete ds-badge--sm" data-testid="badge_summary_up_to_date">${iconSvg("ic-check-circle")} ${
      lang === "fr" ? "À jour" : "Up to date"
    }</span>`;
  }

  const buttonIcon = isQueuedOrRunning
    ? '<span class="ds-spinner" aria-hidden="true"></span>'
    : summary.hasSummary
      ? iconSvg("ic-refresh")
      : iconSvg("ic-sparkle");

  const buttonText = isQueuedOrRunning
    ? lang === "fr"
      ? "Génération en cours dans la file IA…"
      : "Generating in AI queue…"
    : summary.hasSummary
      ? lang === "fr"
        ? "Régénérer le résumé global"
        : "Regenerate global summary"
      : lang === "fr"
        ? "Générer le résumé global du dossier"
        : "Generate global record summary";

  const obsoleteAlertHtml =
    summary.hasSummary && summary.isObsolete
      ? `<div class="ds-alert ds-alert--warning" role="status" data-testid="alert_summary_obsolete">
          <span class="ds-alert__icon" aria-hidden="true">${iconSvg("ic-warning")}</span>
          <div class="ds-alert__content">
            <span class="ds-alert__title">${
              lang === "fr"
                ? "Résumé global obsolète — Nouvelles données détectées dans le dossier"
                : "Global summary is obsolete — Newer record data detected"
            }</span>
            <span>${
              summary.newFormsSinceSummary.length > 0
                ? lang === "fr"
                  ? `${summary.newFormsSinceSummary.length} nouvelle(s) séance(s) RCP présente(s) depuis la génération du ${esc(formatDateTimeDisplay(summary.generatedAt, lang))} (${summary.newFormsSinceSummary.map(esc).join(", ")}).`
                  : `${summary.newFormsSinceSummary.length} new MDT session(s) added since ${esc(formatDateTimeDisplay(summary.generatedAt, lang))} (${summary.newFormsSinceSummary.map(esc).join(", ")}).`
                : lang === "fr"
                  ? `Une ou plusieurs séances RCP ont été modifiées depuis la génération du ${esc(formatDateTimeDisplay(summary.generatedAt, lang))}.`
                  : `One or more MDT sessions were updated since ${esc(formatDateTimeDisplay(summary.generatedAt, lang))}.`
            }</span>
          </div>
        </div>`
      : "";

  const queuedBannerHtml = isQueuedOrRunning
    ? `<div class="ds-processing-banner" role="status" aria-live="polite" data-testid="alert_summary_queued">
        <div class="ds-processing-banner__main">
          <span class="ds-spinner" aria-hidden="true"></span>
          <div class="ds-processing-banner__content">
            <strong class="ds-processing-banner__title">${
              lang === "fr"
                ? "Tâche enregistrée dans la file prioritaire IA (PriorityQueue)"
                : "Task queued in AI PriorityQueue"
            }</strong>
            <span class="ds-processing-banner__meta">${esc(
              activeJob?.current_step ??
                (lang === "fr"
                  ? "Consolidation longitudinale en attente d'un worker IA"
                  : "Longitudinal synthesis waiting for AI worker"),
            )}</span>
          </div>
        </div>
      </div>`
    : "";

  const generatedMetaHtml = summary.hasSummary
    ? `<div class="ds-cluster" data-testid="summary_generated_meta">
        <span class="ds-badge ds-badge--neutral ds-badge--sm">${iconSvg("ic-clock")} ${
          lang === "fr" ? "Généré le" : "Generated on"
        } ${esc(formatDateTimeDisplay(summary.generatedAt, lang))}</span>
        <span class="ds-badge ds-badge--neutral ds-badge--sm">${iconSvg("ic-layers")} ${
          lang === "fr" ? "Séances consolidées" : "Consolidated sessions"
        } : ${summary.coveredFormIds.length} / ${dashboard.rcpCount}</span>
      </div>`
    : `<div class="ds-alert ds-alert--guidance" role="note">
        <span class="ds-alert__icon" aria-hidden="true">${iconSvg("ic-sparkle")}</span>
        <div class="ds-alert__content">
          <span class="ds-alert__title">${
            lang === "fr"
              ? "Synthèse longitudinale à la demande"
              : "On-demand longitudinal synthesis"
          }</span>
          <span>${
            lang === "fr"
              ? `Consolide l'ensemble des ${dashboard.rcpCount} séance(s) RCP du patient via la file IA (PriorityQueue).`
              : `Consolidates all ${dashboard.rcpCount} MDT session(s) for this patient via the AI PriorityQueue.`
          }</span>
        </div>
      </div>`;

  const content = summary.content;
  const contentHtml = content
    ? `<div class="ds-stack" data-testid="summary_content_body">
        <div class="ds-rationale ds-rationale--orientation">
          <span class="ds-rationale__label">${iconSvg("ic-compass", "ds-icon--xs")} ${
            lang === "fr" ? "Trajectoire clinique globale" : "Global clinical trajectory"
          }</span>
          <p class="ds-rationale__text">${esc(content.clinicalTrajectoryOverview)}</p>
        </div>
        <div class="ds-rationale">
          <span class="ds-rationale__label">${iconSvg("ic-stethoscope", "ds-icon--xs")} ${
            lang === "fr"
              ? "Évolution de la maladie & des traitements"
              : "Disease & treatment evolution"
          }</span>
          <p class="ds-rationale__text">${esc(content.diseaseAndTreatmentEvolution)}</p>
        </div>
        <div class="ds-grid">
          ${
            content.notableMetricChanges.length > 0
              ? `<div class="ds-subcard">
                  <div class="ds-subcard__header">
                    <span class="ds-subcard__title">${iconSvg("ic-trend-up", "ds-icon--xs")} ${
                      lang === "fr"
                        ? "Variations notables des métriques brutes"
                        : "Notable raw metric variations"
                    }</span>
                  </div>
                  <ul class="ds-hovercard__list">
                    ${content.notableMetricChanges.map((item) => `<li>${esc(item)}</li>`).join("")}
                  </ul>
                </div>`
              : ""
          }
          ${
            content.mdtDecisionsRecap.length > 0
              ? `<div class="ds-subcard">
                  <div class="ds-subcard__header">
                    <span class="ds-subcard__title">${iconSvg("ic-calendar", "ds-icon--xs")} ${
                      lang === "fr" ? "Historique des propositions RCP" : "MDT orientation history"
                    }</span>
                  </div>
                  <ul class="ds-hovercard__list">
                    ${content.mdtDecisionsRecap.map((item) => `<li>${esc(item)}</li>`).join("")}
                  </ul>
                </div>`
              : ""
          }
          ${
            content.unresolvedVigilancePoints.length > 0
              ? `<div class="ds-subcard">
                  <div class="ds-subcard__header">
                    <span class="ds-subcard__title">${iconSvg("ic-warning", "ds-icon--xs")} ${
                      lang === "fr"
                        ? "Points de vigilance & éléments manquants"
                        : "Vigilance points & missing items"
                    }</span>
                  </div>
                  <ul class="ds-hovercard__list">
                    ${content.unresolvedVigilancePoints.map((item) => `<li>${esc(item)}</li>`).join("")}
                  </ul>
                </div>`
              : ""
          }
        </div>
        <p class="ds-disclaimer">${esc(t("disclaimer.ml", lang))}</p>
      </div>`
    : "";

  return `<section class="ds-card" id="patient-summary-card" data-testid="patient_summary_card">
    <div class="ds-card__header">
      <div class="ds-cluster">
        <h3 class="ds-card__title">
          <span class="ds-icon-box">${iconSvg("ic-sparkle")}</span>
          ${lang === "fr" ? "Résumé global du dossier patient" : "Global Patient Record Summary"}
        </h3>
        ${statusBadgeHtml}
      </div>
      <div class="ds-card__header-actions">
        <form method="POST" action="${actionUrl}" style="display:inline-flex;margin:0">
          <input type="hidden" name="force" value="true" />
          <button
            type="submit"
            class="ds-btn ${summary.isObsolete || !summary.hasSummary ? "ds-btn--primary" : "ds-btn--tonal"} ds-btn--sm"
            data-testid="btn_generate_patient_summary"
            ${isQueuedOrRunning ? "disabled" : ""}
          >
            ${buttonIcon}
            <span>${buttonText}</span>
          </button>
        </form>
      </div>
    </div>
    <div class="ds-card__body ds-stack">
      ${generatedMetaHtml}
      ${obsoleteAlertHtml}
      ${queuedBannerHtml}
      ${contentHtml}
    </div>
  </section>`;
}

function renderPointPills(points: PatientMetricPointView[], unit: string, lang: Language): string {
  return `<div class="ds-metric-points-strip" role="list" aria-label="${
    lang === "fr" ? "Valeurs brutes par séance RCP" : "Raw values per MDT session"
  }">
    ${points
      .map((pt) => {
        const unitStr =
          unit && !pt.displayValue.includes(unit.replace(/\s+/g, "")) ? ` ${unit}` : "";
        const manualBadge = pt.isManual
          ? `<span class="ds-badge ds-badge--manual ds-badge--sm" title="${
              lang === "fr" ? "Valeur corrigée manuellement" : "Manually edited value"
            }">${iconSvg("ic-edit-note", "ds-icon--xs")}</span>`
          : "";
        const deltaBadge = pt.deltaDisplay
          ? `<span class="ds-raw-pill__delta">Δ ${esc(pt.deltaDisplay)}</span>`
          : "";
        const annotBadge = pt.isAnnotativeOnly
          ? `<span class="ds-badge ds-badge--incomplete ds-badge--sm" title="${
              lang === "fr" ? "Observation qualitative brute" : "Raw qualitative note"
            }">${iconSvg("ic-info", "ds-icon--xs")}</span>`
          : "";
        return `<div class="ds-raw-pill ${pt.isAnnotativeOnly ? "ds-raw-pill--annotative" : ""}" role="listitem" data-form-id="${esc(pt.formId)}">
          <span class="ds-raw-pill__date">${esc(pt.formDateLabel)}</span>
          <strong class="ds-raw-pill__val">${esc(pt.displayValue)}${esc(unitStr)}</strong>
          ${manualBadge}${annotBadge}${deltaBadge}
        </div>`;
      })
      .join("")}
  </div>`;
}

function renderNumericChartCard(
  series: PatientMetricSeriesView,
  domain: ClinicalDomain,
  lang: Language,
): string {
  const svgMarkup = renderMetricSeriesEChartsSvg(series, lang);
  const secMeta = getSectionPresentation(series.section, domain, lang);
  const clinicalLabel = resolveClinicalMetricLabel(series, lang);
  const lastPt = series.points[series.points.length - 1];
  const firstPt = series.points[0];
  const spanYears =
    firstPt && lastPt && lastPt.daysSinceFirstRcp >= 365
      ? `${(lastPt.daysSinceFirstRcp / 365.25).toFixed(1)} ${lang === "fr" ? "ans" : "yrs"}`
      : firstPt && lastPt && lastPt.daysSinceFirstRcp > 0
        ? `${lastPt.daysSinceFirstRcp} ${lang === "fr" ? "jours" : "days"}`
        : lang === "fr"
          ? "1 séance"
          : "1 session";

  return `<article class="ds-card ds-metric-chart-card" data-testid="metric_chart_${esc(series.metricKey)}" data-metric-key="${esc(series.metricKey)}">
    <div class="ds-card__header">
      <div>
        <h4 class="ds-card__title">
          <span class="ds-icon-box">${iconSvg(secMeta.icon)}</span>
          ${esc(clinicalLabel)}
        </h4>
        <span class="ds-card__subtitle">
          ${esc(secMeta.title)} · ${lang === "fr" ? "Données brutes" : "Raw data"}${series.unit ? ` (${esc(series.unit)})` : ""} · ${series.points.length} ${lang === "fr" ? "séance(s)" : "session(s)"} (${esc(spanYears)})
        </span>
      </div>
      ${
        lastPt
          ? `<div class="ds-card__header-actions">
              <span class="ds-badge ds-badge--specialty ds-badge--sm" title="${lang === "fr" ? "Dernier relevé" : "Latest"} (${esc(lastPt.formDateLabel)})">
                ${iconSvg("ic-trend-up")} ${esc(lastPt.displayValue)}${series.unit ? ` ${esc(series.unit)}` : ""} · ${esc(lastPt.formDateLabel)}
              </span>
            </div>`
          : ""
      }
    </div>
    <div class="ds-card__body ds-stack">
      <div class="ds-metric-chart-card__canvas" role="img" aria-label="${esc(clinicalLabel)}">
        ${svgMarkup}
      </div>
      ${renderPointPills(series.points, series.unit, lang)}
    </div>
  </article>`;
}

function renderQualitativeSwimlanes(
  qualitativeSeries: PatientMetricSeriesView[],
  domain: ClinicalDomain,
  lang: Language,
): string {
  if (qualitativeSeries.length === 0) return "";
  return `<section class="ds-card" data-testid="qualitative_metrics_swimlanes">
    <div class="ds-card__header">
      <div>
        <h3 class="ds-card__title">
          <span class="ds-icon-box">${iconSvg("ic-compass")}</span>
          ${
            lang === "fr"
              ? "Évolution des statuts cliniques, stades & jalons fonctionnels"
              : "Clinical Statuses, Staging & Functional Milestones Evolution"
          }
        </h3>
        <p class="ds-card__subtitle">
          ${
            lang === "fr"
              ? "Suivi chronologique des paramètres non numériques (stades TNM, jalons moteurs, mode ventilatoire ou nutritionnel, lignes thérapeutiques) relevés à chaque séance RCP."
              : "Chronological tracking of non-numeric parameters (TNM staging, motor milestones, ventilation or feeding support, treatment lines) across MDT sessions."
          }
        </p>
      </div>
    </div>
    <div class="ds-card__body ds-stack--sm">
      ${qualitativeSeries
        .map((s) => {
          const secMeta = getSectionPresentation(s.section, domain, lang);
          const clinicalLabel = resolveClinicalMetricLabel(s, lang);
          return `<div class="ds-subcard ds-swimlane-row" data-testid="swimlane_${esc(s.metricKey)}">
            <div class="ds-swimlane-row__label">
              <span class="ds-subcard__title">${iconSvg(secMeta.icon, "ds-icon--xs")} ${esc(clinicalLabel)}</span>
              <span class="ds-small ds-muted">${esc(secMeta.title)}</span>
            </div>
            <div class="ds-swimlane-row__steps" role="list" aria-label="${esc(clinicalLabel)}">
              ${s.points
                .map((pt, idx) => {
                  const currentDisplay = resolveTranslatedPointDisplay(pt, s.valueType, lang);
                  const prevPt = idx > 0 ? s.points[idx - 1] : undefined;
                  const prevDisplay = prevPt
                    ? resolveTranslatedPointDisplay(prevPt, s.valueType, lang)
                    : null;
                  const hasChanged = prevDisplay !== null && prevDisplay !== currentDisplay;
                  const badgeClass = hasChanged
                    ? "ds-badge--orientation-adapt"
                    : "ds-badge--neutral";
                  return `<div class="ds-step-node" role="listitem">
                    <span class="ds-step-node__date">${esc(pt.formDateLabel)}</span>
                    <span class="ds-badge ${badgeClass} ds-badge--sm">${esc(currentDisplay)}</span>
                    ${
                      pt.isManual
                        ? `<span class="ds-badge ds-badge--manual ds-badge--sm" title="${
                            lang === "fr" ? "Modifié manuellement" : "Manually edited"
                          }">${iconSvg("ic-edit-note", "ds-icon--xs")}</span>`
                        : ""
                    }
                    ${
                      idx < s.points.length - 1
                        ? `<span class="ds-step-node__arrow" aria-hidden="true">${iconSvg("ic-arrow-right", "ds-icon--xs")}</span>`
                        : ""
                    }
                  </div>`;
                })
                .join("")}
            </div>
          </div>`;
        })
        .join("")}
    </div>
  </section>`;
}

function renderRawMatrixTable(
  dashboard: PatientDashboardView,
  seriesList: PatientMetricSeriesView[],
  lang: Language,
): string {
  if (seriesList.length === 0) return "";
  const formColumns = new Map<string, string>();
  for (const s of seriesList) {
    for (const pt of s.points) {
      if (!formColumns.has(pt.formId)) {
        formColumns.set(pt.formId, pt.formDateLabel);
      }
    }
  }
  const colEntries = Array.from(formColumns.entries());
  const domainParam = encodeURIComponent(dashboard.domain);
  const patientBaseUrl = `/patients/${encodeURIComponent(dashboard.patientId)}`;

  return `<section class="ds-card" id="dashboard-raw-table-panel" data-testid="patient_dashboard_raw_table">
    <div class="ds-card__header">
      <div>
        <h3 class="ds-card__title">
          <span class="ds-icon-box">${iconSvg("ic-layers")}</span>
          ${
            lang === "fr" ? "Tableau comparatif brut multi-RCP" : "Multi-MDT Raw Comparative Matrix"
          }
        </h3>
        <p class="ds-card__subtitle">
          ${
            lang === "fr"
              ? "Valeurs exactes extraites ou corrigées manuellement par séance RCP."
              : "Exact extracted or manually edited values across MDT sessions."
          }
        </p>
      </div>
    </div>
    <div class="ds-card__body">
      <div class="ds-table-wrap">
        <table class="ds-table">
          <thead>
            <tr>
              <th scope="col">${lang === "fr" ? "Paramètre clinique" : "Clinical parameter"}</th>
              ${colEntries
                .map(([formId, dateLabel], idx) => {
                  const sessionTitle =
                    dateLabel && dateLabel !== "Date non renseignée"
                      ? lang === "fr"
                        ? `Séance du ${dateLabel}`
                        : `Session ${dateLabel}`
                      : lang === "fr"
                        ? `Séance #${idx + 1}`
                        : `Session #${idx + 1}`;
                  return `<th scope="col">
                    <a class="ds-table__primary-link" href="${patientBaseUrl}?file=${encodeURIComponent(formId)}&domain=${domainParam}">
                      ${esc(sessionTitle)}
                    </a>
                  </th>`;
                })
                .join("")}
            </tr>
          </thead>
          <tbody>
            ${seriesList
              .map((s) => {
                const secMeta = getSectionPresentation(s.section, dashboard.domain, lang);
                const clinicalLabel = resolveClinicalMetricLabel(s, lang);
                const byForm = new Map(s.points.map((p) => [p.formId, p]));
                return `<tr>
                  <td data-label="${lang === "fr" ? "Paramètre clinique" : "Clinical parameter"}" class="ds-table__primary-cell">
                    <strong>${esc(clinicalLabel)}</strong>
                    ${s.unit ? ` <span class="ds-small ds-muted">(${esc(s.unit)})</span>` : ""}
                    <br/>
                    <span class="ds-small ds-muted">${esc(secMeta.title)}</span>
                  </td>
                  ${colEntries
                    .map(([formId, dateLabel]) => {
                      const pt = byForm.get(formId);
                      if (!pt) {
                        return `<td data-label="${esc(dateLabel)}" class="ds-muted">—</td>`;
                      }
                      const displayVal = resolveTranslatedPointDisplay(pt, s.valueType, lang);
                      return `<td data-label="${esc(dateLabel)}">
                        <div class="ds-cluster">
                          <strong>${esc(displayVal)}</strong>
                          ${
                            pt.isManual
                              ? `<span class="ds-badge ds-badge--manual ds-badge--sm" title="${
                                  lang === "fr" ? "Corrigé manuellement" : "Manually edited"
                                }">${iconSvg("ic-edit-note", "ds-icon--xs")}</span>`
                              : ""
                          }
                          ${
                            pt.deltaDisplay
                              ? `<span class="ds-raw-pill__delta">(${esc(pt.deltaDisplay)})</span>`
                              : ""
                          }
                        </div>
                      </td>`;
                    })
                    .join("")}
                </tr>`;
              })
              .join("")}
          </tbody>
        </table>
      </div>
    </div>
  </section>`;
}

export function renderPatientDashboardPanel(
  dashboard: PatientDashboardView,
  lang: Language,
): string {
  const numericSeries = dashboard.metrics.filter((s) => s.valueType === "numeric_or_mixed");
  const qualitativeSeries = dashboard.metrics.filter((s) => s.valueType !== "numeric_or_mixed");

  const emptyMetricsHtml =
    dashboard.metrics.length === 0
      ? `<div class="ds-alert ds-alert--guidance" data-testid="dashboard_metrics_empty">
          <span class="ds-alert__icon" aria-hidden="true">${iconSvg("ic-info")}</span>
          <div class="ds-alert__content">
            <span class="ds-alert__title">${
              lang === "fr"
                ? "Aucune métrique longitudinale brute relevée"
                : "No raw longitudinal metrics found"
            }</span>
            <span>${
              lang === "fr"
                ? "Les courbes et jalons apparaîtront automatiquement dès que des scores ou statuts cliniques seront extraits des fiches RCP de ce patient."
                : "Charts and milestones will appear automatically once clinical scores or statuses are extracted from this patient's MDT forms."
            }</span>
          </div>
        </div>`
      : "";

  return `<div class="ds-patient-dashboard ds-stack--lg" data-testid="patient_dashboard_root" data-patient-id="${esc(dashboard.patientId)}">
    ${renderSummaryCard(dashboard, dashboard.summary, lang)}

    <div class="ds-pole-heading">
      ${iconSvg("ic-trend-up", "ds-icon--xs")}
      ${
        lang === "fr"
          ? "Suivi longitudinal brut des métriques cliniques (Multi-années)"
          : "Multi-Year Raw Longitudinal Clinical Metrics Tracking"
      }
    </div>

    ${emptyMetricsHtml}

    ${
      numericSeries.length > 0
        ? `<div class="ds-metric-charts-grid" data-testid="patient_dashboard_charts_grid">
            ${numericSeries.map((s) => renderNumericChartCard(s, dashboard.domain, lang)).join("")}
          </div>`
        : ""
    }

    ${renderQualitativeSwimlanes(qualitativeSeries, dashboard.domain, lang)}
    ${renderRawMatrixTable(dashboard, dashboard.metrics, lang)}
  </div>`;
}
