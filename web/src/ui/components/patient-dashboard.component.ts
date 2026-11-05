import * as echarts from "echarts";
import type {
  Language,
  PatientDashboardView,
  PatientMetricPointView,
  PatientMetricSeriesView,
  PatientRecordSummaryView,
} from "../../domain/types.js";

function escapeHtml(str: unknown): string {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

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
      const base = pt.formDateLabel || pt.formId;
      return series.points.length > 1 && pt.daysSinceFirstRcp > 0
        ? `${base}\n(J+${pt.daysSinceFirstRcp})`
        : idx === 0 && series.points.length > 1
          ? `${base}\n(J0)`
          : base;
    });

    const primaryData = series.points.map((pt) => ({
      value: pt.numericValue,
      rawDisplay: `${pt.displayValue}${pt.isManual ? " ✍️" : ""}`,
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
        name: series.label,
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
  const isQueuedOrRunning =
    activeJob &&
    (activeJob.status === "PENDING" ||
      activeJob.status === "PROCESSING" ||
      activeJob.status === "RUNNING");

  const actionUrl = `/patients/${encodeURIComponent(dashboard.patientId)}/summary?domain=${encodeURIComponent(dashboard.domain)}`;

  let statusBadgeHtml = "";
  if (isQueuedOrRunning) {
    statusBadgeHtml = `<span class="ds-badge ds-badge--info" data-testid="badge_summary_queued">⏳ ${
      lang === "fr" ? "En file d'attente IA" : "Queued in AI Worker"
    }</span>`;
  } else if (!summary.hasSummary) {
    statusBadgeHtml = `<span class="ds-badge ds-badge--neutral" data-testid="badge_summary_empty">${
      lang === "fr" ? "Non généré (à la demande)" : "Not generated (on-demand)"
    }</span>`;
  } else if (summary.isObsolete) {
    statusBadgeHtml = `<span class="ds-badge ds-badge--warning" data-testid="badge_summary_obsolete">⚠️ ${
      lang === "fr" ? "Obsolète" : "Obsolete"
    }</span>`;
  } else {
    statusBadgeHtml = `<span class="ds-badge ds-badge--success" data-testid="badge_summary_up_to_date">✅ ${
      lang === "fr" ? "À jour" : "Up to date"
    }</span>`;
  }

  const buttonLabel = isQueuedOrRunning
    ? lang === "fr"
      ? "⏳ Génération en cours dans la file IA…"
      : "⏳ Generating in AI queue…"
    : summary.hasSummary
      ? lang === "fr"
        ? "🔄 Régénérer le résumé global"
        : "🔄 Regenerate global summary"
      : lang === "fr"
        ? "✨ Générer le résumé global du dossier"
        : "✨ Generate global record summary";

  const obsoleteAlertHtml =
    summary.hasSummary && summary.isObsolete
      ? `<div class="ds-summary-obsolete-banner" role="status" data-testid="alert_summary_obsolete">
          <div class="ds-summary-obsolete-banner__title">
            ⚠️ ${
              lang === "fr"
                ? "Résumé global obsolète — Nouvelles données détectées dans le dossier"
                : "Global summary is obsolete — Newer record data detected"
            }
          </div>
          <div class="ds-summary-obsolete-banner__body">
            ${
              summary.newFormsSinceSummary.length > 0
                ? lang === "fr"
                  ? `Nouvelle(s) fiche(s) RCP présente(s) depuis la génération du ${escapeHtml(formatDateTimeDisplay(summary.generatedAt, lang))} : <strong>${summary.newFormsSinceSummary.map(escapeHtml).join(", ")}</strong>.`
                  : `New MDT form(s) added since ${escapeHtml(formatDateTimeDisplay(summary.generatedAt, lang))}: <strong>${summary.newFormsSinceSummary.map(escapeHtml).join(", ")}</strong>.`
                : lang === "fr"
                  ? `Une ou plusieurs fiches RCP ont été modifiées depuis la génération du ${escapeHtml(formatDateTimeDisplay(summary.generatedAt, lang))}.`
                  : `One or more MDT forms were updated since ${escapeHtml(formatDateTimeDisplay(summary.generatedAt, lang))}.`
            }
          </div>
        </div>`
      : "";

  const queuedBannerHtml = isQueuedOrRunning
    ? `<div class="ds-summary-queued-banner" role="status" data-testid="alert_summary_queued">
        <strong>⏳ ${
          lang === "fr"
            ? "Tâche enregistrée dans la file prioritaire IA (PriorityQueue)"
            : "Task queued in AI PriorityQueue"
        }</strong> — ${escapeHtml(activeJob?.current_step ?? (lang === "fr" ? "En attente d'un worker GPU" : "Waiting for GPU worker"))}
      </div>`
    : "";

  const generatedMetaHtml = summary.hasSummary
    ? `<div class="ds-summary-card__meta" data-testid="summary_generated_meta">
        <span>🕒 ${lang === "fr" ? "Généré le" : "Generated on"} : <strong>${escapeHtml(formatDateTimeDisplay(summary.generatedAt, lang))}</strong></span>
        <span>📄 ${lang === "fr" ? "Fiches consolidées" : "Covered forms"} : <strong>${summary.coveredFormIds.length} / ${dashboard.rcpCount}</strong> (${summary.coveredFormIds.map(escapeHtml).join(", ")})</span>
      </div>`
    : `<div class="ds-summary-card__meta">
        <span>${
          lang === "fr"
            ? `Consolidation longitudinale à la demande sur l'ensemble des ${dashboard.rcpCount} fiche(s) RCP du patient via la file IA.`
            : `On-demand longitudinal synthesis across all ${dashboard.rcpCount} MDT form(s) via the AI queue.`
        }</span>
      </div>`;

  const content = summary.content;
  const contentHtml = content
    ? `<div class="ds-summary-card__content ${summary.isObsolete ? "is-obsolete" : ""}" data-testid="summary_content_body">
        <div class="ds-summary-block">
          <h4 class="ds-summary-block__title">${lang === "fr" ? "Trajectoire clinique globale" : "Global clinical trajectory"}</h4>
          <p class="ds-summary-block__text">${escapeHtml(content.clinicalTrajectoryOverview)}</p>
        </div>
        <div class="ds-summary-block">
          <h4 class="ds-summary-block__title">${lang === "fr" ? "Évolution de la maladie & des traitements" : "Disease & treatment evolution"}</h4>
          <p class="ds-summary-block__text">${escapeHtml(content.diseaseAndTreatmentEvolution)}</p>
        </div>
        ${
          content.notableMetricChanges.length > 0
            ? `<div class="ds-summary-block">
                <h4 class="ds-summary-block__title">${lang === "fr" ? "Variations notables des métriques brutes" : "Notable raw metric variations"}</h4>
                <ul class="ds-summary-list">
                  ${content.notableMetricChanges.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
                </ul>
              </div>`
            : ""
        }
        ${
          content.mdtDecisionsRecap.length > 0
            ? `<div class="ds-summary-block">
                <h4 class="ds-summary-block__title">${lang === "fr" ? "Historique des propositions RCP" : "MDT orientation history"}</h4>
                <ul class="ds-summary-list">
                  ${content.mdtDecisionsRecap.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
                </ul>
              </div>`
            : ""
        }
        ${
          content.unresolvedVigilancePoints.length > 0
            ? `<div class="ds-summary-block">
                <h4 class="ds-summary-block__title">${lang === "fr" ? "Points de vigilance & éléments manquants" : "Vigilance points & missing items"}</h4>
                <ul class="ds-summary-list">
                  ${content.unresolvedVigilancePoints.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
                </ul>
              </div>`
            : ""
        }
      </div>`
    : "";

  return `<section class="ds-card ds-summary-card ${summary.isObsolete ? "ds-summary-card--obsolete" : ""}" id="patient-summary-card" data-testid="patient_summary_card">
    <div class="ds-summary-card__header">
      <div class="ds-summary-card__title-group">
        <h3 class="ds-summary-card__title">📋 ${
          lang === "fr" ? "Résumé global du dossier patient" : "Global Patient Record Summary"
        }</h3>
        ${statusBadgeHtml}
      </div>
      <form method="POST" action="${actionUrl}" class="ds-summary-card__form">
        <input type="hidden" name="force" value="true" />
        <button
          type="submit"
          class="ds-btn ${summary.isObsolete || !summary.hasSummary ? "ds-btn--primary" : "ds-btn--secondary"} ds-btn--sm"
          data-testid="btn_generate_patient_summary"
          ${isQueuedOrRunning ? "disabled" : ""}
        >
          ${buttonLabel}
        </button>
      </form>
    </div>
    ${generatedMetaHtml}
    ${obsoleteAlertHtml}
    ${queuedBannerHtml}
    ${contentHtml}
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
          ? `<span class="ds-raw-pill__manual" title="${
              lang === "fr" ? "Valeur corrigée manuellement" : "Manually edited value"
            }">✍️</span>`
          : "";
        const deltaBadge = pt.deltaDisplay
          ? `<span class="ds-raw-pill__delta">Δ ${escapeHtml(pt.deltaDisplay)}</span>`
          : "";
        const annotBadge = pt.isAnnotativeOnly
          ? `<span class="ds-raw-pill__annot" title="${
              lang === "fr" ? "Observation qualitative brute" : "Raw qualitative note"
            }">📝</span>`
          : "";
        return `<div class="ds-raw-pill ${pt.isAnnotativeOnly ? "ds-raw-pill--annotative" : ""}" role="listitem" data-form-id="${escapeHtml(pt.formId)}">
          <span class="ds-raw-pill__date">${escapeHtml(pt.formDateLabel)}</span>
          <strong class="ds-raw-pill__val">${escapeHtml(pt.displayValue)}${escapeHtml(unitStr)}</strong>
          ${manualBadge}${annotBadge}${deltaBadge}
        </div>`;
      })
      .join("")}
  </div>`;
}

function renderNumericChartCard(series: PatientMetricSeriesView, lang: Language): string {
  const svgMarkup = renderMetricSeriesEChartsSvg(series, lang);
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

  return `<article class="ds-card ds-metric-chart-card" data-testid="metric_chart_${escapeHtml(series.metricKey)}" data-metric-key="${escapeHtml(series.metricKey)}">
    <div class="ds-metric-chart-card__header">
      <div>
        <h4 class="ds-metric-chart-card__title">${escapeHtml(series.label)}</h4>
        <span class="ds-metric-chart-card__subtitle">
          ${lang === "fr" ? "Données brutes" : "Raw data"} ${series.unit ? `(${escapeHtml(series.unit)})` : ""} · ${series.points.length} RCP (${escapeHtml(spanYears)})
        </span>
      </div>
      ${
        lastPt
          ? `<div class="ds-metric-chart-card__latest">
              <span class="ds-metric-chart-card__latest-label">${lang === "fr" ? "Dernier relevé" : "Latest"} (${escapeHtml(lastPt.formDateLabel)})</span>
              <strong class="ds-metric-chart-card__latest-val">${escapeHtml(lastPt.displayValue)} ${escapeHtml(series.unit)}</strong>
            </div>`
          : ""
      }
    </div>
    <div class="ds-metric-chart-card__canvas" role="img" aria-label="${escapeHtml(series.label)}">
      ${svgMarkup}
    </div>
    ${renderPointPills(series.points, series.unit, lang)}
  </article>`;
}

function renderQualitativeSwimlanes(
  qualitativeSeries: PatientMetricSeriesView[],
  lang: Language,
): string {
  if (qualitativeSeries.length === 0) return "";
  return `<section class="ds-card ds-qualitative-swimlanes" data-testid="qualitative_metrics_swimlanes">
    <div class="ds-qualitative-swimlanes__header">
      <h3 class="ds-qualitative-swimlanes__title">🧭 ${
        lang === "fr"
          ? "Paliers qualitatifs, stades & jalons cliniques bruts"
          : "Raw qualitative stages, milestones & clinical modalities"
      }</h3>
    </div>
    <div class="ds-qualitative-swimlanes__rows">
      ${qualitativeSeries
        .map(
          (s) => `<div class="ds-Swimlane-row" data-testid="swimlane_${escapeHtml(s.metricKey)}">
            <div class="ds-Swimlane-row__label">
              <strong>${escapeHtml(s.label)}</strong>
              <span>${escapeHtml(s.section)}.${escapeHtml(s.field)}</span>
            </div>
            <div class="ds-Swimlane-row__steps">
              ${s.points
                .map(
                  (pt, idx) => `<div class="ds-step-node">
                    <span class="ds-step-node__date">${escapeHtml(pt.formDateLabel)}</span>
                    <span class="ds-step-node__value">${escapeHtml(pt.displayValue)}${pt.isManual ? " ✍️" : ""}</span>
                    ${idx < s.points.length - 1 ? '<span class="ds-step-node__arrow" aria-hidden="true">→</span>' : ""}
                  </div>`,
                )
                .join("")}
            </div>
          </div>`,
        )
        .join("")}
    </div>
  </section>`;
}

function renderRawMatrixTable(seriesList: PatientMetricSeriesView[], lang: Language): string {
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

  return `<section class="ds-card ds-raw-matrix-card" id="dashboard-raw-table-panel" data-testid="patient_dashboard_raw_table">
    <div class="ds-raw-matrix-card__header">
      <h3 class="ds-raw-matrix-card__title">📋 ${
        lang === "fr"
          ? "Tableau comparatif brut multi-RCP (Valeurs exactes extraites / corrigées)"
          : "Multi-MDT Raw Comparative Matrix (Exact extracted / edited values)"
      }</h3>
    </div>
    <div class="ds-table-scroll">
      <table class="ds-table ds-raw-matrix-table">
        <thead>
          <tr>
            <th scope="col">${lang === "fr" ? "Métrique clinique (champ brut)" : "Clinical metric (raw field)"}</th>
            ${colEntries
              .map(
                ([formId, dateLabel]) =>
                  `<th scope="col">${escapeHtml(dateLabel)}<br/><small>${escapeHtml(formId)}</small></th>`,
              )
              .join("")}
          </tr>
        </thead>
        <tbody>
          ${seriesList
            .map((s) => {
              const byForm = new Map(s.points.map((p) => [p.formId, p]));
              return `<tr>
                <th scope="row">
                  <strong>${escapeHtml(s.label)}</strong>
                  ${s.unit ? `<span class="ds-text-muted">(${escapeHtml(s.unit)})</span>` : ""}
                </th>
                ${colEntries
                  .map(([formId]) => {
                    const pt = byForm.get(formId);
                    if (!pt) return `<td class="ds-text-muted">—</td>`;
                    return `<td>
                      <strong>${escapeHtml(pt.displayValue)}</strong>
                      ${pt.isManual ? '<span title="Corrigé manuellement">✍️</span>' : ""}
                      ${pt.deltaDisplay ? `<small class="ds-raw-pill__delta">(${escapeHtml(pt.deltaDisplay)})</small>` : ""}
                    </td>`;
                  })
                  .join("")}
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>
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
      ? `<div class="ds-card ds-empty-state" data-testid="dashboard_metrics_empty">
          <p>${
            lang === "fr"
              ? "Aucune métrique longitudinale brute relevée dans les fiches RCP de ce dossier."
              : "No raw longitudinal metrics found across this patient's MDT forms."
          }</p>
        </div>`
      : "";

  return `<div class="ds-patient-dashboard" data-testid="patient_dashboard_root" data-patient-id="${escapeHtml(dashboard.patientId)}">
    ${renderSummaryCard(dashboard, dashboard.summary, lang)}

    <div class="ds-patient-dashboard__section-header">
      <div>
        <h3 class="ds-patient-dashboard__heading">📈 ${
          lang === "fr"
            ? "Suivi longitudinal brut des métriques cliniques (Multi-années)"
            : "Multi-Year Raw Longitudinal Clinical Metrics Tracking"
        }</h3>
        <p class="ds-patient-dashboard__subheading">
          ${
            lang === "fr"
              ? "Valeurs brutes non lissées (scores entiers, décimaux, ratios type 34/37, bilatéraux D/G et observations qualitatives)."
              : "Unsmoothed raw values (integers, decimals, ratios like 34/37, bilateral D/G scores, and qualitative notes)."
          }
        </p>
      </div>
    </div>

    ${emptyMetricsHtml}

    ${
      numericSeries.length > 0
        ? `<div class="ds-metric-charts-grid" data-testid="patient_dashboard_charts_grid">
            ${numericSeries.map((s) => renderNumericChartCard(s, lang)).join("")}
          </div>`
        : ""
    }

    ${renderQualitativeSwimlanes(qualitativeSeries, lang)}
    ${renderRawMatrixTable(dashboard.metrics, lang)}
  </div>`;
}
