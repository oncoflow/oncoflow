import { formatFieldLabel } from "./catalog.js";
import { t, translateValue } from "./i18n.js";
import type {
  CompletenessStatus,
  Language,
  LongitudinalDelta,
  MdtFormCard,
  MdtFormDetail,
  OrientationStatus,
  PriorityLevel,
  WorklistFilter,
  WorklistKpis,
} from "./types.js";

export function normalizePriorityLevel(raw: unknown): PriorityLevel {
  if (!raw) return "none";
  const str = String(raw).trim().toLowerCase();
  if (
    str === "low" ||
    str.includes("not urgent") ||
    str.includes("pas d'urgence") ||
    str.includes("standard") ||
    str.includes("faible") ||
    str.includes("basse")
  ) {
    return "low";
  }
  if (
    str === "medium" ||
    str === "moderate" ||
    str.includes("semi-urgent") ||
    str.includes("semi urgent") ||
    str.includes("soon as possible") ||
    str.includes("modérée") ||
    str.includes("moyen")
  ) {
    return "medium";
  }
  if (
    str === "high" ||
    str === "urgent" ||
    str.includes("urgent") ||
    str.includes("haute") ||
    str.includes("quickly")
  ) {
    return "high";
  }
  return "none";
}

export function priorityRank(level: PriorityLevel): number {
  switch (level) {
    case "high":
      return 1;
    case "medium":
      return 2;
    case "low":
      return 3;
    default:
      return 4;
  }
}

export function derivePriorityBadgeInfo(
  level: PriorityLevel,
  lang: Language = "fr",
  short = false,
): {
  level: PriorityLevel;
  icon: string;
  badgeClass: string;
  label: string;
} {
  const key = short ? `priority.${level}.short` : `priority.${level}`;
  switch (level) {
    case "high":
      return {
        level,
        icon: "ic-priority-high",
        badgeClass: "ds-badge--urgency-high",
        label: t(key, lang),
      };
    case "medium":
      return {
        level,
        icon: "ic-priority-medium",
        badgeClass: "ds-badge--urgency-medium",
        label: t(key, lang),
      };
    case "low":
      return {
        level,
        icon: "ic-priority-low",
        badgeClass: "ds-badge--urgency-low",
        label: t(key, lang),
      };
    default:
      return {
        level: "none",
        icon: "ic-priority-none",
        badgeClass: "ds-badge--urgency-none",
        label: t(key, lang),
      };
  }
}

/**
 * Medico-legal non-prescriptive orientation badge derivation (ML-1, ML-2, ML-3).
 * Never uses red/rose or prescriptive wording.
 */
export function deriveOrientationInfo(
  input: {
    care_adaptation_suggested?: boolean | null;
    proposed_care_type?: string | null;
  },
  lang: Language = "fr",
): {
  status: OrientationStatus;
  icon: string;
  badgeClass: string;
  label: string;
  proposedCareType: string | null;
} {
  if (input.care_adaptation_suggested === true) {
    return {
      status: "adapt",
      icon: "ic-compass",
      badgeClass: "ds-badge--orientation-adapt",
      label: t("orientation.adapt", lang),
      proposedCareType: input.proposed_care_type ?? null,
    };
  }
  if (input.care_adaptation_suggested === false) {
    return {
      status: "standard",
      icon: "ic-check-circle",
      badgeClass: "ds-badge--orientation-standard",
      label: t("orientation.standard", lang),
      proposedCareType: null,
    };
  }
  return {
    status: "pending",
    icon: "ic-clock",
    badgeClass: "ds-badge--orientation-pending",
    label: t("orientation.pending", lang),
    proposedCareType: null,
  };
}

export function deriveCompletenessInfo(
  input: {
    is_complete?: boolean;
    missing_count?: number;
    missing_items?: string[];
  },
  lang: Language = "fr",
): {
  status: CompletenessStatus;
  icon: string;
  badgeClass: string;
  label: string;
  missingCount: number;
  missingItems: string[];
} {
  const missingItems = input.missing_items ?? [];
  const missingCount =
    typeof input.missing_count === "number" ? input.missing_count : missingItems.length;
  const isComplete = input.is_complete === true && missingCount === 0;
  if (isComplete) {
    return {
      status: "complete",
      icon: "ic-check-circle",
      badgeClass: "ds-badge--complete",
      label: t("completeness.complete", lang),
      missingCount: 0,
      missingItems: [],
    };
  }
  const count = Math.max(1, missingCount);
  const suffix = t("completeness.incomplete.short", lang);
  return {
    status: "incomplete",
    icon: "ic-warning",
    badgeClass: "ds-badge--incomplete",
    label: `${count} ${suffix}`,
    missingCount: count,
    missingItems,
  };
}

export function computeWorklistKpis(cards: MdtFormCard[]): WorklistKpis {
  let structuredCount = 0;
  let highPriorityCount = 0;
  let incompleteCount = 0;
  let adaptationSuggestedCount = 0;

  for (const card of cards) {
    if (card.processingStatus === "COMPLETED") {
      structuredCount += 1;
    }
    if (card.priorityLevel === "high") {
      highPriorityCount += 1;
    }
    if (!card.isComplete || card.missingCount > 0) {
      incompleteCount += 1;
    }
    if (card.careAdaptationSuggested === true) {
      adaptationSuggestedCount += 1;
    }
  }

  return {
    structuredCount,
    highPriorityCount,
    incompleteCount,
    adaptationSuggestedCount,
  };
}

export function filterAndSortCards(
  cards: MdtFormCard[],
  filter: WorklistFilter = {},
): MdtFormCard[] {
  const q = (filter.query ?? "").trim().toLowerCase();
  const completeness = filter.completeness ?? "all";
  const priority = filter.priority ?? "all";
  const orientation = filter.orientation ?? "all";
  const domain = filter.domain ?? "all";
  const sortBy = filter.sortBy ?? "priority";
  const sortDir = filter.sortDir ?? "asc";

  const filtered = cards.filter((card) => {
    if (domain !== "all" && card.domain !== domain) return false;
    if (completeness === "complete" && !card.isComplete) return false;
    if (completeness === "incomplete" && card.isComplete) return false;
    if (priority !== "all" && card.priorityLevel !== priority) return false;
    if (orientation === "adapt" && card.careAdaptationSuggested !== true) return false;
    if (orientation === "standard" && card.careAdaptationSuggested !== false) return false;
    if (orientation === "pending" && card.careAdaptationSuggested !== null) return false;

    if (q) {
      const haystack = [
        card.id,
        card.file,
        card.patientId ?? "",
        card.patientName,
        card.summaryText,
        card.proposedCareType ?? "",
        ...card.specialties,
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });

  const dir = sortDir === "desc" ? -1 : 1;
  return [...filtered].sort((a, b) => {
    if (sortBy === "patient") {
      return a.patientName.localeCompare(b.patientName, "fr") * dir;
    }
    if (sortBy === "date") {
      return (b.mdtDate ?? "").localeCompare(a.mdtDate ?? "") * dir;
    }
    // Default: priority high > medium > low > none, then most recent mdtDate
    const rankDiff = (priorityRank(a.priorityLevel) - priorityRank(b.priorityLevel)) * dir;
    if (rankDiff !== 0) return rankDiff;
    return (b.mdtDate ?? "").localeCompare(a.mdtDate ?? "");
  });
}

export function computeLongitudinalDeltas(
  currentForm: MdtFormDetail,
  previousForm: MdtFormDetail | null | undefined,
  lang: Language = "fr",
): LongitudinalDelta[] {
  if (!previousForm) return [];

  const deltas: LongitudinalDelta[] = [];
  const prevDate = previousForm.mdtDate ?? "RCP préc.";

  // Compare key numeric/clinical markers across sections
  const trackedKeys: Array<{
    section: string;
    field: string;
    higherIsWorse: boolean;
  }> = [
    { section: "PatientPerformanceStatus", field: "performance_status", higherIsWorse: true },
    { section: "MotorFunctionStatus", field: "hfmse_score", higherIsWorse: false },
    { section: "MotorFunctionStatus", field: "rulm_score", higherIsWorse: false },
    { section: "MotorFunctionStatus", field: "chop_intend_score", higherIsWorse: false },
    {
      section: "RespiratoryFunction",
      field: "forced_vital_capacity_percent",
      higherIsWorse: false,
    },
    { section: "RespiratoryFunction", field: "daily_ventilation_hours", higherIsWorse: true },
    { section: "OrthopedicAndSpineStatus", field: "scoliosis_cobb_angle", higherIsWorse: true },
  ];

  for (const item of trackedKeys) {
    const curSec = currentForm.sections[item.section];
    const prevSec = previousForm.sections[item.section];
    if (!curSec || !prevSec) continue;

    const curRaw = curSec[item.field];
    const prevRaw = prevSec[item.field];
    if (curRaw === undefined || curRaw === null || prevRaw === undefined || prevRaw === null) {
      continue;
    }

    const curNum = Number(String(curRaw).replace(/[^0-9.-]/g, ""));
    const prevNum = Number(String(prevRaw).replace(/[^0-9.-]/g, ""));
    if (!Number.isNaN(curNum) && !Number.isNaN(prevNum)) {
      const diff = curNum - prevNum;
      if (diff === 0) {
        deltas.push({
          key: item.field,
          label: formatFieldLabel(item.field, lang),
          currentValue: translateValue(curRaw, lang),
          previousValue: translateValue(prevRaw, lang),
          previousDate: prevDate,
          deltaText: lang === "fr" ? "= stable" : "= stable",
          direction: "stable",
          icon: "ic-check",
        });
      } else {
        const sign = diff > 0 ? `+${diff}` : `${diff}`;
        const isWorse = item.higherIsWorse ? diff > 0 : diff < 0;
        deltas.push({
          key: item.field,
          label: formatFieldLabel(item.field, lang),
          currentValue: translateValue(curRaw, lang),
          previousValue: translateValue(prevRaw, lang),
          previousDate: prevDate,
          deltaText: `${sign} vs ${prevDate}`,
          direction: isWorse ? "worse" : "better",
          icon: diff > 0 ? "ic-trend-up" : "ic-trend-down",
        });
      }
    }
  }

  return deltas;
}
