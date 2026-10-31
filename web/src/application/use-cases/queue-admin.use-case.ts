import type { ClinicalDomain, QueueJobItem, QueueStats } from "../../domain/types.js";
import type { OncoflowApiPort } from "../ports/oncoflow-api.port.js";

export interface QueueDashboardView {
  stats: QueueStats;
  jobs: QueueJobItem[];
  allDomains: boolean;
}

export class QueueAdminUseCase {
  constructor(private readonly api: OncoflowApiPort) {}

  async getDashboard(domain: ClinicalDomain, allDomains = true): Promise<QueueDashboardView> {
    const [stats, jobs] = await Promise.all([
      this.api.getQueueStats(domain, allDomains),
      this.api.listQueueJobs(domain, allDomains),
    ]);
    return { stats, jobs, allDomains };
  }

  async retryJob(jobId: string, domain: ClinicalDomain): Promise<void> {
    await this.api.retryQueueJob(jobId, domain);
  }

  async cancelOrDeleteJob(jobId: string, domain: ClinicalDomain): Promise<void> {
    await this.api.cancelOrDeleteQueueJob(jobId, domain);
  }

  async cleanQueue(mode: "completed" | "failed" | "all", domain: ClinicalDomain): Promise<number> {
    return this.api.cleanQueue(mode, domain);
  }

  async releaseLocks(domain: ClinicalDomain): Promise<{ released: number }> {
    return this.api.releaseGpuLocks(domain);
  }
}
