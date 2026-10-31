import { computeWorklistKpis, filterAndSortCards } from "../../domain/triage.js";
import type {
  ClinicalDomain,
  MdtFormCard,
  WorklistFilter,
  WorklistKpis,
} from "../../domain/types.js";
import type { OncoflowApiPort } from "../ports/oncoflow-api.port.js";

export interface WorklistViewResult {
  kpis: WorklistKpis;
  cards: MdtFormCard[];
  totalUnfiltered: number;
  filter: WorklistFilter;
}

export class WorklistUseCase {
  constructor(private readonly api: OncoflowApiPort) {}

  async execute(domain: ClinicalDomain, filter: WorklistFilter = {}): Promise<WorklistViewResult> {
    const viewMode = filter.viewMode ?? "patients";
    const allCards =
      viewMode === "rcp"
        ? await this.api.listRcpCards(domain)
        : await this.api.listPatientCards(domain);

    const kpis = computeWorklistKpis(allCards);
    const cards = filterAndSortCards(allCards, filter);

    return {
      kpis,
      cards,
      totalUnfiltered: allCards.length,
      filter,
    };
  }

  async deletePatient(patientId: string, domain: ClinicalDomain): Promise<void> {
    await this.api.deletePatient(patientId, domain);
  }

  async deleteForm(filename: string, domain: ClinicalDomain): Promise<void> {
    await this.api.deleteForm(filename, domain);
  }
}
