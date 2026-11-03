import type {
  AgentModuleInfo,
  ClinicalDomain,
  Language,
  ResourceDocument,
} from "../../domain/types.js";
import type { ChatReply, OncoflowApiPort } from "../ports/oncoflow-api.port.js";

export interface GuidelinesOverview {
  resources: ResourceDocument[];
  agents: AgentModuleInfo[];
  selectedResource: ResourceDocument | null;
}

export class GuidelinesUseCase {
  constructor(private readonly api: OncoflowApiPort) {}

  async getOverview(
    domain: ClinicalDomain,
    lang: Language,
    selectedFilename?: string,
  ): Promise<GuidelinesOverview> {
    const [resources, agents] = await Promise.all([
      this.api.listResources(domain),
      this.api.listAgents(domain, lang),
    ]);
    const selectedResource =
      resources.find((r) => r.filename === selectedFilename) ?? resources[0] ?? null;

    return {
      resources,
      agents,
      selectedResource,
    };
  }

  async uploadResource(
    filename: string,
    content: Buffer,
    domain: ClinicalDomain,
  ): Promise<ResourceDocument> {
    return this.api.uploadResource(filename, content, domain);
  }

  async reindexResource(filename: string, domain: ClinicalDomain): Promise<void> {
    await this.api.reindexResource(filename, domain);
  }

  async deleteResource(filename: string, domain: ClinicalDomain): Promise<void> {
    await this.api.deleteResource(filename, domain);
  }

  async askGuidelineQuestion(
    question: string,
    domain: ClinicalDomain,
    lang: Language,
    filename?: string,
  ): Promise<ChatReply> {
    return this.api.askGuidelineQuestion(question, domain, lang, filename);
  }
}
