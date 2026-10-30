import os
from datetime import datetime
from pathlib import Path
from typing import Any

from slugify import slugify

from src.application.app_functions import to_naive
from src.application.config import AppConfig
from src.application.paths import UnsafePathError, safe_path
from src.domain.patient import Patient
from src.domain.patient_mdt_form import PatientMDTForm, get_domain_mdt_form_cls
from src.domain.repositories import (
    DocumentCacheRepository,
    PatientMDTFormRepository,
    PatientRepository,
)
from src.infrastructure.documents.mongodb import Mongodb
from src.infrastructure.documents.repositories import (
    MongoDocumentCacheRepository,
    MongoPatientMDTFormRepository,
    MongoPatientRepository,
)


class PatientRecordService:
    """
    Application use-case service orchestrating the lifecycle of `Patient` records
    and their associated `PatientMDTForm` documents.
    Enforces the `Patient` <-> `PatientMDTForm` association invariant at write time.
    """

    def __init__(
        self,
        patient_repo: PatientRepository,
        mdt_form_repo: PatientMDTFormRepository,
        cache_repo: DocumentCacheRepository | None = None,
        queue_broker: Any | None = None,
        mdt_form_storage_path: str | Path | None = None,
        form_cls: type[PatientMDTForm] = PatientMDTForm,
        config: AppConfig | None = None,
    ) -> None:
        self.patient_repo = patient_repo
        self.mdt_form_repo = mdt_form_repo
        self.cache_repo = cache_repo
        self.queue_broker = queue_broker
        self.mdt_form_storage_path = (
            Path(mdt_form_storage_path)
            if mdt_form_storage_path is not None
            else (Path(config.rcp.path) if config is not None else None)
        )
        self.form_cls = form_cls
        self.config = config

    @classmethod
    def from_config(
        cls,
        config: AppConfig,
        db_client: Mongodb | None = None,
        queue_broker: Any | None = None,
    ) -> "PatientRecordService":
        """Build the application service wired with MongoDB repository adapters."""
        client = db_client or Mongodb(config)
        domain_form_cls = get_domain_mdt_form_cls(config.domain)
        return cls(
            patient_repo=MongoPatientRepository(client),
            mdt_form_repo=MongoPatientMDTFormRepository(client),
            cache_repo=MongoDocumentCacheRepository(client),
            queue_broker=queue_broker,
            mdt_form_storage_path=config.rcp.path,
            form_cls=domain_form_cls,
            config=config,
        )

    def synchronize_patient_from_admin(
        self,
        filename: str,
        admin_data: dict[str, Any],
        target_patient_id: str | None = None,
    ) -> tuple[Patient, dict[str, Any]]:
        """
        Synchronize the `Patient` aggregate and the `PatientMDTForm` (`filename`) from
        extracted administrative data or a manually selected `target_patient_id`.
        """
        merged_admin = dict(admin_data or {})
        existing_patient: Patient | None = None

        if target_patient_id:
            existing_patient = self.patient_repo.get_by_id(target_patient_id)
            if existing_patient is not None:
                merged_admin = existing_patient.apply_to_administrative(merged_admin)
                existing_patient.attach_file(filename)
                saved_patient = self.patient_repo.save(
                    existing_patient, filename=filename
                )
                self.mdt_form_repo.upsert_fields(
                    filename,
                    {
                        "patient_id": saved_patient.patient_id,
                        "PatientAdministrative": merged_admin,
                    },
                )
                return saved_patient, merged_admin

        existing_patient = self.patient_repo.find_by_identity(
            first_name=merged_admin.get("first_name"),
            last_name=merged_admin.get("last_name"),
            date_birth=merged_admin.get("date_birth"),
            fallback_file=filename,
        )
        if existing_patient is not None:
            existing_patient.attach_file(filename)
            if (
                existing_patient.date_birth is None
                and merged_admin.get("date_birth") is not None
            ):
                dob = merged_admin.get("date_birth")
                if isinstance(dob, str):
                    try:
                        dob = datetime.fromisoformat(dob)
                    except ValueError:
                        dob = None
                existing_patient.date_birth = dob
            if not existing_patient.born_name and merged_admin.get("born_name"):
                existing_patient.born_name = merged_admin.get("born_name")
            saved_patient = self.patient_repo.save(existing_patient, filename=filename)
        else:
            new_patient = Patient.from_administrative(
                merged_admin,
                filename=filename,
                patient_id=target_patient_id,
            )
            saved_patient = self.patient_repo.save(new_patient, filename=filename)

        self.mdt_form_repo.upsert_fields(
            filename,
            {
                "patient_id": saved_patient.patient_id,
                "PatientAdministrative": merged_admin,
            },
        )
        return saved_patient, merged_admin

    def list_patient_mdt_form_cards(self) -> list[dict[str, Any]]:
        """Return dashboard card metrics for all visible `PatientMDTForm` records."""
        projection = {
            "file": 1,
            "patient_id": 1,
            "ui_date": 1,
            "date_refresh": 1,
            "PatientAdministrative": 1,
            "ExpertAnswer": 1,
            "MTDCompleted": 1,
            "CareOrientationProposal": 1,
            "processing_status": 1,
            "processing_step": 1,
            "processing_progress_pct": 1,
        }
        visible_docs = [
            d
            for d in self.mdt_form_repo.list_all(projection=projection)
            if self.form_cls.is_visible_in_cards(d)
        ]
        cards = [self.form_cls.extract_card_metrics(d) for d in visible_docs]
        cards.sort(
            key=lambda x: x.get("date_refresh") or datetime.min,
            reverse=True,
        )
        return cards

    def _collect_patients_including_unlinked(
        self, all_forms: list[dict[str, Any]]
    ) -> list[Patient]:
        """
        Return all persisted `Patient` aggregates, enriched with synthesized `Patient`
        aggregates for any unlinked `PatientMDTForm` documents that contain `PatientAdministrative`.
        """
        patients_by_id: dict[str, Patient] = {
            p.patient_id: p for p in self.patient_repo.list_all()
        }
        covered_files = {f for p in patients_by_id.values() for f in p.files}

        for doc in all_forms:
            fname = doc.get("file")
            if not fname or fname in covered_files:
                continue
            pid = doc.get("patient_id")
            if pid and pid in patients_by_id:
                patients_by_id[pid].attach_file(fname)
                covered_files.add(fname)
                continue
            admin = doc.get("PatientAdministrative")
            if isinstance(admin, dict) and (
                admin.get("first_name") or admin.get("last_name")
            ):
                synth = Patient.from_administrative(
                    admin, filename=fname, patient_id=pid
                )
                if synth.patient_id in patients_by_id:
                    patients_by_id[synth.patient_id].attach_file(fname)
                else:
                    patients_by_id[synth.patient_id] = synth
                covered_files.add(fname)

        return list(patients_by_id.values())

    def list_patient_cards(self) -> list[dict[str, Any]]:
        """
        Build the list of `PatientRecord` cards summarized from each patient's
        latest analyzed `PatientMDTForm`.
        """
        all_forms = self.mdt_form_repo.list_all()
        forms_by_file = {d["file"]: d for d in all_forms if "file" in d}
        all_patients = self._collect_patients_including_unlinked(all_forms)

        patient_cards: list[dict[str, Any]] = []
        for patient in all_patients:
            patient_forms_map: dict[str, dict[str, Any]] = {}
            for f in patient.files:
                if f in forms_by_file:
                    patient_forms_map[f] = forms_by_file[f]
            for d in all_forms:
                if d.get("patient_id") == patient.patient_id and "file" in d:
                    patient_forms_map[d["file"]] = d

            patient_forms = list(patient_forms_map.values())
            if not patient_forms:
                continue

            latest_doc = self.form_cls.select_latest_analyzed(patient_forms)
            if latest_doc is None:
                continue

            card = self.form_cls.extract_card_metrics(latest_doc)
            latest_file = latest_doc["file"]
            patient_cards.append(
                {
                    "patient_id": patient.patient_id,
                    "patient": patient.full_name,
                    "first_name": patient.first_name,
                    "last_name": patient.last_name,
                    "date_birth": to_naive(patient.date_birth),
                    "rcp_count": len(patient_forms),
                    "file": latest_file,
                    "latest_file": latest_file,
                    "link": f"datas?patient_id={patient.patient_id}&file={latest_file}",
                    "date_refresh": card["date_refresh"],
                    "date": card["date"],
                    "experts": card["experts"],
                    "missing": card["missing"],
                    "urgency": card["urgency"],
                    "urgency_score": card["urgency_score"],
                    "intervention_required": card["intervention_required"],
                    "intervention_type": card["intervention_type"],
                    "processing_status": card.get("processing_status"),
                    "processing_step": card.get("processing_step"),
                    "processing_progress_pct": card.get("processing_progress_pct", 100),
                }
            )

        patient_cards.sort(
            key=lambda x: x.get("date_refresh") or datetime.min,
            reverse=True,
        )
        return patient_cards

    def _get_patient_and_forms(
        self, patient_id: str
    ) -> tuple[Patient | None, list[dict[str, Any]], str | None]:
        """
        Retrieve the `Patient` aggregate, the chronological list (newest first) of its
        `PatientMDTForm` records, and the filename of the latest analyzed `PatientMDTForm`.
        """
        patient = self.patient_repo.get_by_id(patient_id)
        if patient is None:
            all_forms = self.mdt_form_repo.list_all()
            for candidate in self._collect_patients_including_unlinked(all_forms):
                if candidate.patient_id == patient_id:
                    patient = candidate
                    break
        if not patient:
            return None, [], None

        raw_forms = self.mdt_form_repo.list_by_patient(patient_id, files=patient.files)
        dedup_map: dict[str, dict[str, Any]] = {}
        for d in raw_forms:
            if "file" in d:
                dedup_map[d["file"]] = d

        forms_list = list(dedup_map.values())
        forms_list.sort(
            key=lambda d: self.form_cls.extract_mdt_date(d) or datetime.min,
            reverse=True,
        )
        latest_doc = self.form_cls.select_latest_analyzed(forms_list)
        latest_file = (
            latest_doc["file"]
            if latest_doc and "file" in latest_doc
            else (forms_list[0]["file"] if forms_list else None)
        )
        return patient, forms_list, latest_file

    def get_patient_detail(self, patient_id: str) -> dict[str, Any] | None:
        """
        Retrieve the serialized `PatientRecord` detail dictionary for API/UI consumption.
        """
        patient, forms_list, latest_file = self._get_patient_and_forms(patient_id)
        if patient is None:
            return None
        return {
            "patient": patient.model_dump(mode="json"),
            "latest_file": latest_file,
            "rcps": forms_list,
        }

    def resolve_patient_record(
        self,
        patient_id: str | None = None,
        filename: str | None = None,
        *,
        patient_id_param: str | None = None,
        file_param: str | None = None,
    ) -> tuple[Patient | None, list[dict[str, Any]], str | None]:
        """
        Resolve the `PatientRecord`, its chronologically sorted `PatientMDTForm` records,
        and the selected filename from a `patient_id` and/or `filename`.
        """
        effective_pid = patient_id if patient_id is not None else patient_id_param
        effective_file = filename if filename is not None else file_param

        if effective_pid:
            patient, forms_list, latest_file = self._get_patient_and_forms(
                effective_pid
            )
            if patient is not None:
                valid_files = {d.get("file") for d in forms_list}
                selected = (
                    effective_file
                    if (effective_file and effective_file in valid_files)
                    else latest_file
                )
                return patient, forms_list, selected

        if effective_file:
            form_doc = self.mdt_form_repo.get_by_file(effective_file)
            pid = form_doc.get("patient_id") if form_doc else None
            if pid:
                patient, forms_list, _ = self._get_patient_and_forms(pid)
                if patient is not None:
                    return patient, forms_list, effective_file

            all_forms = self.mdt_form_repo.list_all()
            for candidate in self._collect_patients_including_unlinked(all_forms):
                if effective_file in candidate.files:
                    patient, forms_list, _ = self._get_patient_and_forms(
                        candidate.patient_id
                    )
                    return patient, forms_list, effective_file

            return (
                None,
                [form_doc] if form_doc else [{"file": effective_file}],
                effective_file,
            )

        return None, [], None

    def delete_patient_mdt_form_document(
        self,
        filename: str,
        delete_file: bool = True,
        *,
        delete_queue_jobs: bool = True,
        delete_vector_collection: bool = True,
    ) -> None:
        """
        Delete a `PatientMDTForm` document from the queue, vector store, repository,
        and Markdown cache, detach the file from its `Patient`, and remove the PDF from disk.
        """
        if delete_queue_jobs:
            if self.queue_broker is not None:
                try:
                    self.queue_broker.delete_jobs_for_file(filename)
                except Exception:
                    pass
            elif self.config is not None and self.config.queue.enabled:
                try:
                    from src.infrastructure.queue import QueueBroker

                    broker = QueueBroker(self.config)
                    try:
                        broker.delete_jobs_for_file(filename)
                    finally:
                        broker.close()
                except Exception:
                    pass

        if delete_vector_collection and self.config is not None and delete_file:
            try:
                from src.infrastructure.vectorial.client import (
                    VectorialDataBaseClient,
                )

                vecdb = VectorialDataBaseClient(
                    self.config, coll_prefix=slugify(filename, separator="_")
                ).vectordb
                vecdb.delete_collection()
            except Exception:
                pass

        self.mdt_form_repo.delete_by_file(filename)
        if self.cache_repo is not None:
            try:
                self.cache_repo.delete(file_name=filename)
            except Exception:
                pass
        self.patient_repo.remove_file(filename)

        if delete_file and self.mdt_form_storage_path is not None:
            try:
                target_path = safe_path(self.mdt_form_storage_path, filename)
                if os.path.exists(target_path):
                    os.remove(target_path)
                bbox_path = f"{target_path}.bbox"
                if os.path.exists(bbox_path):
                    os.remove(bbox_path)
            except (UnsafePathError, OSError):
                pass

    def delete_patient_record(self, patient_id: str, delete_files: bool = True) -> bool:
        """
        Delete an entire `PatientRecord` along with all its associated `PatientMDTForm` documents.
        """
        patient, forms_list, _ = self._get_patient_and_forms(patient_id)
        if not patient:
            return False

        all_files: list[str] = list(patient.files)
        for doc in forms_list:
            fname = doc.get("file")
            if fname and fname not in all_files:
                all_files.append(fname)

        for fname in all_files:
            self.delete_patient_mdt_form_document(fname, delete_file=delete_files)

        self.patient_repo.delete(patient_id)
        return True
