from copy import deepcopy
from datetime import datetime
from typing import Any

from src.application.config import AppConfig
from src.domain.bug_report import BugReport, BugStatus
from src.domain.patient import Patient
from src.domain.worker.queue_job import RCPProcessingStatus
from src.infrastructure.documents.mongodb import Mongodb


class InMemoryPatientRepository:
    """In-memory adapter for `PatientRepository` (used in isolated DDD/TDD unit tests)."""

    def __init__(self, initial_patients: list[Patient] | None = None) -> None:
        self._patients: dict[str, Patient] = {}
        for p in initial_patients or []:
            self.save(p)

    def get_by_id(self, patient_id: str) -> Patient | None:
        p = self._patients.get(patient_id)
        return p.model_copy(deep=True) if p else None

    def find_by_identity(
        self,
        first_name: str | None,
        last_name: str | None,
        date_birth: datetime | str | None = None,
        fallback_file: str | None = None,
    ) -> Patient | None:
        exact_id = Patient.build_id(
            first_name=first_name,
            last_name=last_name,
            date_birth=date_birth,
            fallback_file=fallback_file,
        )
        if exact_id in self._patients:
            return self._patients[exact_id].model_copy(deep=True)

        name_key = Patient.build_name_key(first_name=first_name, last_name=last_name)
        if not name_key:
            return None

        if date_birth is None:
            for p in self._patients.values():
                if p.name_key == name_key:
                    return p.model_copy(deep=True)
            return None

        for p in self._patients.values():
            if p.name_key == name_key and p.date_birth is None:
                return p.model_copy(deep=True)
        return self.get_by_id(name_key)

    def list_all(self) -> list[Patient]:
        return [p.model_copy(deep=True) for p in self._patients.values()]

    def save(self, patient: Patient, filename: str | None = None) -> Patient:
        existing = self._patients.get(patient.patient_id)
        files: list[str] = []
        if existing:
            for f in existing.files:
                if f and f not in files:
                    files.append(f)
        for f in patient.files:
            if f and f not in files:
                files.append(f)
        if filename and filename not in files:
            files.append(filename)

        updated = patient.model_copy(
            update={
                "files": files,
                "name_key": Patient.build_name_key(
                    patient.first_name, patient.last_name
                ),
                "updated_at": patient.updated_at or datetime.now(),
            },
            deep=True,
        )
        self._patients[updated.patient_id] = updated
        return updated.model_copy(deep=True)

    def upsert(self, patient: Patient, filename: str | None = None) -> Patient:
        """Persist or update a `Patient` aggregate."""
        return self.save(patient, filename=filename)

    def remove_file(self, filename: str) -> None:
        to_delete: list[str] = []
        for pid, p in self._patients.items():
            if filename in p.files:
                p.detach_file(filename)
                if not p.files:
                    to_delete.append(pid)
        for pid in to_delete:
            self._patients.pop(pid, None)

    def delete(self, patient_id: str) -> None:
        self._patients.pop(patient_id, None)


class InMemoryPatientMDTFormRepository:
    """In-memory adapter for `PatientMDTFormRepository`."""

    def __init__(self, initial_docs: list[dict[str, Any]] | None = None) -> None:
        self._forms: dict[str, dict[str, Any]] = {}
        for doc in initial_docs or []:
            if "file" in doc:
                self._forms[doc["file"]] = deepcopy(doc)

    def get_by_file(self, filename: str) -> dict[str, Any] | None:
        doc = self._forms.get(filename)
        return deepcopy(doc) if doc is not None else None

    def get_by_filename(self, filename: str) -> dict[str, Any] | None:
        """Retrieve a `PatientMDTForm` persistence dictionary by its filename."""
        return self.get_by_file(filename)

    def list_all(
        self, projection: dict[str, int] | None = None
    ) -> list[dict[str, Any]]:
        return [deepcopy(d) for d in self._forms.values()]

    def list_by_patient(
        self, patient_id: str, files: list[str] | None = None
    ) -> list[dict[str, Any]]:
        file_set = set(files or [])
        result: list[dict[str, Any]] = []
        for fname, doc in self._forms.items():
            if doc.get("patient_id") == patient_id or fname in file_set:
                result.append(deepcopy(doc))
        return result

    def list_by_files(
        self, filenames: list[str], projection: dict[str, int] | None = None
    ) -> list[dict[str, Any]]:
        file_set = set(filenames)
        return [
            deepcopy(doc) for fname, doc in self._forms.items() if fname in file_set
        ]

    def list_by_filenames(
        self, filenames: list[str], projection: dict[str, int] | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve `PatientMDTForm` persistence dictionaries matching `filenames`."""
        return self.list_by_files(filenames, projection=projection)

    def list_unfinished(self) -> list[dict[str, Any]]:
        terminal = {
            RCPProcessingStatus.COMPLETED.value,
            RCPProcessingStatus.FAILED.value,
        }
        return [
            deepcopy(doc)
            for doc in self._forms.values()
            if doc.get("processing_status") not in terminal
        ]

    def save_full(
        self, filename: str, payload: dict[str, Any], replace: bool = True
    ) -> None:
        data = deepcopy(payload)
        data["file"] = filename
        if replace or filename not in self._forms:
            self._forms[filename] = data

    def upsert_fields(
        self,
        filename: str,
        fields: dict[str, Any],
        set_on_insert: dict[str, Any] | None = None,
    ) -> None:
        is_new = filename not in self._forms
        doc = self._forms.setdefault(filename, {"file": filename})
        if is_new and set_on_insert:
            for k, v in set_on_insert.items():
                doc.setdefault(k, deepcopy(v))
        for k, v in fields.items():
            doc[k] = deepcopy(v)
        doc["file"] = filename

    def update_fields(
        self,
        filename: str,
        fields: dict[str, Any],
        set_on_insert: dict[str, Any] | None = None,
    ) -> None:
        """Upsert specific fields on a `PatientMDTForm` persistence dictionary."""
        self.upsert_fields(filename, fields, set_on_insert=set_on_insert)

    def delete_by_file(self, filename: str) -> None:
        self._forms.pop(filename, None)

    def delete_by_filename(self, filename: str) -> None:
        """Remove a `PatientMDTForm` persistence dictionary by its filename."""
        self.delete_by_file(filename)


class InMemoryDocumentCacheRepository:
    """In-memory adapter for `DocumentCacheRepository`."""

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}

    def get_by_hash(self, file_hash: str) -> dict[str, Any] | None:
        entry = self._cache.get(file_hash)
        return deepcopy(entry) if entry is not None else None

    def save(
        self,
        file_hash: str,
        file_name: str,
        markdown: str,
        document_type: str = "mtd",
    ) -> None:
        self._cache[file_hash] = {
            "hash": file_hash,
            "file": file_name,
            "document_type": document_type,
            "markdown": markdown,
        }

    def delete(
        self,
        file_hash: str | None = None,
        file_name: str | None = None,
        clear_all: bool = False,
    ) -> None:
        if file_hash:
            self._cache.pop(file_hash, None)
        elif file_name:
            to_drop = [h for h, v in self._cache.items() if v.get("file") == file_name]
            for h in to_drop:
                self._cache.pop(h, None)
        elif clear_all:
            self._cache.clear()
        else:
            raise ValueError(
                "Refusing to clear the entire document_cache without clear_all=True, file_hash, or file_name."
            )

    def delete_cache(
        self,
        file_hash: str | None = None,
        file_name: str | None = None,
        clear_all: bool = False,
    ) -> None:
        """Delete cached Markdown entries by hash, filename, or all."""
        self.delete(file_hash=file_hash, file_name=file_name, clear_all=clear_all)


class InMemoryBugReportRepository:
    """In-memory adapter for `BugReportRepository`."""

    def __init__(self) -> None:
        self._reports: dict[str, BugReport] = {}

    def save(self, report: BugReport) -> BugReport:
        now = datetime.now()
        stored = report.model_copy(
            update={
                "created_at": report.created_at or now,
                "updated_at": report.updated_at or now,
            },
            deep=True,
        )
        self._reports[stored.bug_id] = stored
        return stored.model_copy(deep=True)

    def create(self, report: BugReport | dict[str, Any]) -> dict[str, Any]:
        """Persist a new bug report and return its dictionary representation."""
        obj = (
            report
            if isinstance(report, BugReport)
            else BugReport.model_validate(report)
        )
        saved = self.save(obj)
        return saved.model_dump(mode="python")

    def get_by_id(self, bug_id: str) -> BugReport | None:
        b = self._reports.get(bug_id)
        return b.model_copy(deep=True) if b else None

    def list_all(
        self,
        status: str | None = None,
        severity: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        items: list[BugReport] = []
        for b in self._reports.values():
            if status and b.status.value != status:
                continue
            if severity and b.severity.value != severity:
                continue
            if category and b.category.value != category:
                continue
            items.append(b.model_copy(deep=True))
        items.sort(
            key=lambda x: x.created_at or datetime.min,
            reverse=True,
        )
        return [b.model_dump(mode="python") for b in items]

    def update_status(self, bug_id: str, status: BugStatus | str) -> BugReport | None:
        existing = self._reports.get(bug_id)
        if not existing:
            return None
        resolved_status = status if isinstance(status, BugStatus) else BugStatus(status)
        updated = existing.model_copy(
            update={
                "status": resolved_status,
                "updated_at": datetime.now(),
            },
            deep=True,
        )
        self._reports[bug_id] = updated
        return updated.model_copy(deep=True)

    def update(self, bug_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        """Update fields on an existing bug report and return its dictionary representation."""
        existing = self._reports.get(bug_id)
        if not existing:
            return None
        merged = existing.model_dump(mode="python")
        merged.update(fields)
        merged["updated_at"] = datetime.now()
        updated = BugReport.model_validate(merged)
        self._reports[bug_id] = updated
        return updated.model_dump(mode="python")

    def delete(self, bug_id: str) -> bool:
        return self._reports.pop(bug_id, None) is not None


# --- MongoDB Repository Implementations ---


def _resolve_mongo_client(
    client_or_config: Mongodb | AppConfig | None,
    db_client: Mongodb | None = None,
) -> Mongodb:
    """Resolve a `Mongodb` client from either a `Mongodb` instance or an `AppConfig`."""
    if isinstance(db_client, Mongodb) or (
        db_client is not None and hasattr(db_client, "database")
    ):
        return db_client
    if isinstance(client_or_config, Mongodb) or (
        client_or_config is not None and hasattr(client_or_config, "database")
    ):
        return client_or_config  # type: ignore[return-value]
    if isinstance(client_or_config, AppConfig) or client_or_config is not None:
        return Mongodb(client_or_config)  # type: ignore[arg-type]
    return Mongodb(AppConfig())


class MongoPatientRepository:
    """MongoDB adapter for `PatientRepository`."""

    def __init__(
        self,
        client_or_config: Mongodb | AppConfig | None = None,
        db_client: Mongodb | None = None,
    ) -> None:
        self.db_client = _resolve_mongo_client(client_or_config, db_client=db_client)

    def get_by_id(self, patient_id: str) -> Patient | None:
        raw = self.db_client.get_patient(patient_id)
        return Patient.from_persistence(raw) if raw else None

    def find_by_identity(
        self,
        first_name: str | None,
        last_name: str | None,
        date_birth: datetime | str | None = None,
        fallback_file: str | None = None,
    ) -> Patient | None:
        raw = self.db_client.find_patient_by_identity(
            first_name=first_name,
            last_name=last_name,
            date_birth=date_birth,
            fallback_file=fallback_file,
        )
        return Patient.from_persistence(raw) if raw else None

    def list_all(self) -> list[Patient]:
        docs = self.db_client.get_all_patients()
        return [Patient.from_persistence(d) for d in docs]

    def save(self, patient: Patient, filename: str | None = None) -> Patient:
        raw = self.db_client.upsert_patient(patient.to_persistence(), filename=filename)
        return Patient.from_persistence(raw)

    def upsert(self, patient: Patient, filename: str | None = None) -> Patient:
        """Persist or update a `Patient` aggregate in MongoDB."""
        return self.save(patient, filename=filename)

    def remove_file(self, filename: str) -> None:
        self.db_client.remove_file_from_patient(filename)

    def delete(self, patient_id: str) -> None:
        self.db_client.delete_docs(["patients"], {"patient_id": patient_id})


class MongoPatientMDTFormRepository:
    """MongoDB adapter for `PatientMDTFormRepository`."""

    def __init__(
        self,
        client_or_config: Mongodb | AppConfig | None = None,
        collection_name: str = "rcp_info",
        db_client: Mongodb | None = None,
    ) -> None:
        self.db_client = _resolve_mongo_client(client_or_config, db_client=db_client)
        self.collection_name = collection_name

    def get_by_file(self, filename: str) -> dict[str, Any] | None:
        col = self.db_client.database[self.collection_name]
        return col.find_one({"file": filename})

    def get_by_filename(self, filename: str) -> dict[str, Any] | None:
        """Retrieve a `PatientMDTForm` MongoDB document by its filename."""
        return self.get_by_file(filename)

    def list_all(
        self, projection: dict[str, int] | None = None
    ) -> list[dict[str, Any]]:
        col = self.db_client.database[self.collection_name]
        if projection is not None:
            return list(col.find({}, projection))
        return list(col.find({}))

    def list_by_patient(
        self, patient_id: str, files: list[str] | None = None
    ) -> list[dict[str, Any]]:
        col = self.db_client.database[self.collection_name]
        results: dict[str, dict[str, Any]] = {}
        for f in files or []:
            doc = col.find_one({"file": f})
            if doc and "file" in doc:
                results[doc["file"]] = doc
        for doc in col.find({"patient_id": patient_id}):
            if "file" in doc:
                results[doc["file"]] = doc
        return list(results.values())

    def list_by_files(
        self, filenames: list[str], projection: dict[str, int] | None = None
    ) -> list[dict[str, Any]]:
        if not filenames:
            return []
        col = self.db_client.database[self.collection_name]
        query = {"file": {"$in": filenames}}
        if projection is not None:
            return list(col.find(query, projection))
        return list(col.find(query))

    def list_by_filenames(
        self, filenames: list[str], projection: dict[str, int] | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve `PatientMDTForm` MongoDB documents matching `filenames`."""
        return self.list_by_files(filenames, projection=projection)

    def list_unfinished(self) -> list[dict[str, Any]]:
        col = self.db_client.database[self.collection_name]
        return list(
            col.find(
                {
                    "processing_status": {
                        "$in": [
                            RCPProcessingStatus.PENDING_ADMIN.value,
                            RCPProcessingStatus.PROCESSING_ADMIN.value,
                            RCPProcessingStatus.PENDING_CLINICAL.value,
                            RCPProcessingStatus.PROCESSING_CLINICAL.value,
                        ]
                    }
                }
            )
        )

    def save_full(
        self, filename: str, payload: dict[str, Any], replace: bool = True
    ) -> None:
        data = dict(payload)
        data["file"] = filename
        try:
            self.db_client.set_uniq_index(self.collection_name, "file")
        except Exception:
            pass
        if replace:
            self.db_client.update_doc(
                collection=self.collection_name,
                filter={"file": filename},
                upsertable_data=data,
            )
        elif self.get_by_file(filename) is None:
            self.db_client.prepare_insert_doc(self.collection_name, data)
            self.db_client.insert_docs()

    def upsert_fields(
        self,
        filename: str,
        fields: dict[str, Any],
        set_on_insert: dict[str, Any] | None = None,
    ) -> None:
        try:
            self.db_client.set_uniq_index(self.collection_name, "file")
        except Exception:
            pass
        col = self.db_client.database[self.collection_name]
        update_op: dict[str, Any] = {"$set": dict(fields)}
        if set_on_insert:
            clean_on_insert = {
                k: v for k, v in set_on_insert.items() if k not in fields
            }
            if clean_on_insert:
                update_op["$setOnInsert"] = clean_on_insert
        col.update_one({"file": filename}, update_op, upsert=True)

    def update_fields(
        self,
        filename: str,
        fields: dict[str, Any],
        set_on_insert: dict[str, Any] | None = None,
    ) -> None:
        """Upsert specific fields on a `PatientMDTForm` MongoDB document."""
        self.upsert_fields(filename, fields, set_on_insert=set_on_insert)

    def delete_by_file(self, filename: str) -> None:
        self.db_client.delete_docs([self.collection_name], {"file": filename})

    def delete_by_filename(self, filename: str) -> None:
        """Remove a `PatientMDTForm` MongoDB document by its filename."""
        self.delete_by_file(filename)


class MongoDocumentCacheRepository:
    """MongoDB adapter for `DocumentCacheRepository`."""

    def __init__(
        self,
        client_or_config: Mongodb | AppConfig | None = None,
        db_client: Mongodb | None = None,
    ) -> None:
        self.db_client = _resolve_mongo_client(client_or_config, db_client=db_client)

    def get_by_hash(self, file_hash: str) -> dict[str, Any] | None:
        return self.db_client.get_document_cache(file_hash)

    def save(
        self,
        file_hash: str,
        file_name: str,
        markdown: str,
        document_type: str = "mtd",
    ) -> None:
        self.db_client.save_document_cache(
            file_hash=file_hash,
            file_name=file_name,
            markdown=markdown,
            document_type=document_type,
        )

    def delete(
        self,
        file_hash: str | None = None,
        file_name: str | None = None,
        clear_all: bool = False,
    ) -> None:
        self.db_client.delete_document_cache(
            file_hash=file_hash, file_name=file_name, clear_all=clear_all
        )

    def delete_cache(
        self,
        file_hash: str | None = None,
        file_name: str | None = None,
        clear_all: bool = False,
    ) -> None:
        """Delete cached Markdown documents in MongoDB."""
        self.delete(file_hash=file_hash, file_name=file_name, clear_all=clear_all)


class MongoBugReportRepository:
    """MongoDB adapter for `BugReportRepository`."""

    def __init__(
        self,
        client_or_config: Mongodb | AppConfig | None = None,
        db_client: Mongodb | None = None,
    ) -> None:
        self.db_client = _resolve_mongo_client(client_or_config, db_client=db_client)

    def save(self, report: BugReport) -> BugReport:
        raw = self.db_client.create_bug_report(report.model_dump())
        return BugReport.model_validate(raw)

    def create(self, report: BugReport | dict[str, Any]) -> dict[str, Any]:
        """Create a bug report in MongoDB and return its dictionary representation."""
        payload = report.model_dump() if isinstance(report, BugReport) else dict(report)
        return self.db_client.create_bug_report(payload)

    def get_by_id(self, bug_id: str) -> BugReport | None:
        raw = self.db_client.get_bug_report(bug_id)
        if not raw:
            return None
        clean = {k: v for k, v in raw.items() if k != "_id"}
        return BugReport.model_validate(clean)

    def list_all(
        self,
        status: str | None = None,
        severity: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        if severity:
            query["severity"] = severity
        if category:
            query["category"] = category
        return self.db_client.get_all_bug_reports(query)

    def update_status(self, bug_id: str, status: BugStatus | str) -> BugReport | None:
        val = status.value if isinstance(status, BugStatus) else status
        raw = self.db_client.update_bug_report(bug_id, {"status": val})
        if not raw:
            return None
        clean = {k: v for k, v in raw.items() if k != "_id"}
        return BugReport.model_validate(clean)

    def update(self, bug_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        """Update fields on a bug report in MongoDB."""
        return self.db_client.update_bug_report(bug_id, fields)

    def delete(self, bug_id: str) -> bool:
        return bool(self.db_client.delete_bug_report(bug_id))


def build_repositories(
    config: AppConfig, db_client: Mongodb | None = None
) -> tuple[
    MongoPatientRepository,
    MongoPatientMDTFormRepository,
    MongoDocumentCacheRepository,
    MongoBugReportRepository,
    Mongodb,
]:
    """Instantiate the MongoDB repository adapters for a given application configuration."""
    client = db_client or Mongodb(config)
    return (
        MongoPatientRepository(client),
        MongoPatientMDTFormRepository(client),
        MongoDocumentCacheRepository(client),
        MongoBugReportRepository(client),
        client,
    )
