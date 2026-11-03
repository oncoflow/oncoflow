import type {
  ClinicalDomain,
  MdtAgendaEnrollInput,
  MdtAgendaMoveInput,
  MdtAgendaUpdateInput,
  MdtAgendaView,
} from "../../domain/types.js";
import type { OncoflowApiPort } from "../ports/oncoflow-api.port.js";

export class AgendaUseCase {
  constructor(private readonly api: OncoflowApiPort) {}

  async getAgenda(domain: ClinicalDomain): Promise<MdtAgendaView> {
    return this.api.getMdtAgenda(domain);
  }

  async updateOptions(input: MdtAgendaUpdateInput, domain: ClinicalDomain): Promise<MdtAgendaView> {
    return this.api.updateMdtAgenda(input, domain);
  }

  async enrollPatients(
    input: MdtAgendaEnrollInput,
    domain: ClinicalDomain,
  ): Promise<MdtAgendaView> {
    return this.api.addPatientsToMdtAgenda(input, domain);
  }

  async removePatient(patientId: string, domain: ClinicalDomain): Promise<MdtAgendaView> {
    return this.api.removePatientFromMdtAgenda(patientId, domain);
  }

  async clearAgenda(domain: ClinicalDomain): Promise<MdtAgendaView> {
    return this.api.clearMdtAgenda(domain);
  }

  async movePatient(
    patientId: string,
    input: MdtAgendaMoveInput,
    domain: ClinicalDomain,
  ): Promise<MdtAgendaView> {
    return this.api.movePatientInMdtAgenda(patientId, input, domain);
  }
}
