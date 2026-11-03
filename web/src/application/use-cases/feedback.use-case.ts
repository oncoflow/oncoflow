import type { BugReportItem, ClinicalDomain } from "../../domain/types.js";
import type { OncoflowApiPort } from "../ports/oncoflow-api.port.js";

export interface BugFilter {
  status?: string;
  category?: string;
}

export interface BugListResult {
  items: BugReportItem[];
  counts: {
    total: number;
    open: number;
    inProgress: number;
    resolved: number;
  };
}

export class FeedbackUseCase {
  constructor(private readonly api: OncoflowApiPort) {}

  async listBugs(domain: ClinicalDomain, filter: BugFilter = {}): Promise<BugListResult> {
    const all = await this.api.listBugs(domain);
    const counts = {
      total: all.length,
      open: all.filter((b) => b.status === "open").length,
      inProgress: all.filter((b) => b.status === "in_progress").length,
      resolved: all.filter((b) => b.status === "resolved" || b.status === "closed").length,
    };

    const items = all.filter((b) => {
      if (filter.status && filter.status !== "all" && b.status !== filter.status) {
        return false;
      }
      if (filter.category && filter.category !== "all" && b.category !== filter.category) {
        return false;
      }
      return true;
    });

    return { items, counts };
  }

  async createBug(
    input: Omit<BugReportItem, "id" | "createdAt" | "status">,
  ): Promise<BugReportItem> {
    return this.api.createBug(input);
  }

  async updateStatus(id: string, status: string, domain: ClinicalDomain): Promise<BugReportItem> {
    return this.api.updateBugStatus(id, status, domain);
  }

  async deleteBug(id: string, domain: ClinicalDomain): Promise<void> {
    await this.api.deleteBug(id, domain);
  }
}
