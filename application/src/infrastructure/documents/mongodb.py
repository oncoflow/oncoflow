import threading
from urllib.parse import quote_plus

from pymongo import MongoClient

from src.application.config import AppConfig

# One MongoClient per connection URI for the whole process.
# MongoClient is thread-safe and owns a connection pool + monitoring threads:
# creating one per request / rerun / job wastes sockets and threads.
_CLIENTS: dict[str, MongoClient] = {}
_CLIENTS_LOCK = threading.Lock()


def build_connection_string(config: AppConfig) -> str:
    """Build the MongoDB URI with URL-escaped credentials."""
    connection_string = "mongodb://"
    if config.mongodb.user:
        connection_string += (
            f"{quote_plus(config.mongodb.user)}:"
            f"{quote_plus(config.mongodb.password or '')}@"
        )
    connection_string += f"{config.mongodb.host}:{config.mongodb.port}"
    return connection_string


def get_mongo_client(config: AppConfig) -> MongoClient:
    """Return the process-wide MongoClient for this configuration (created lazily)."""
    uri = build_connection_string(config)
    client = _CLIENTS.get(uri)
    if client is None:
        with _CLIENTS_LOCK:
            client = _CLIENTS.get(uri)
            if client is None:
                client = MongoClient(uri)
                _CLIENTS[uri] = client
    return client


def close_all_mongo_clients() -> None:
    """Close every shared MongoClient (call once at process shutdown)."""
    with _CLIENTS_LOCK:
        for client in _CLIENTS.values():
            client.close()
        _CLIENTS.clear()


class Mongodb:
    """
    A class for interacting with a MongoDB database using PyMongo.

    This class initializes a connection to a MongoDB database specified by the provided configuration,
    and provides methods for inserting documents into collections, logging information about the
    connection and operations performed, and closing the database connection when done.

    The underlying `MongoClient` is shared per URI (see `get_mongo_client`), so creating
    `Mongodb` instances is cheap and `close()` does not tear down the shared pool.
    """

    def __init__(self, config: AppConfig) -> None:

        self.logger = config.set_logger(
            "mongodb",
            default_context={
                "host": config.mongodb.host,
                "database": config.mongodb.database,
            },
        )
        self.client = get_mongo_client(config)
        self.database = self.client[config.mongodb.database]

        self.documents_to_insert = {}

        self.logger.info("Succefully init")

    def close(self):
        """Release this handle. The shared pool is closed by `close_all_mongo_clients()`."""
        if hasattr(self, "documents_to_insert"):
            self.documents_to_insert.clear()

    def set_uniq_index(self, collection, field):
        collection = self.database[collection]
        collection.create_index(field, unique=True)

    def get_or_create_document(self, collection, document):
        collection = self.database[collection]
        if self.get_document(collection.name, document) is None:
            self.prepare_insert_doc(collection.name, document)
            self.insert_docs()
        return self.get_document(collection.name, document)

    def get_document(self, collection, filter):
        collection = self.database[collection]
        return collection.find_one(filter)

    def prepare_insert_doc(self, collection, document):
        if collection not in self.documents_to_insert:
            self.documents_to_insert[collection] = []
        # if "timestamp" not in document:
        #     document["timestamp"]
        self.documents_to_insert[collection].append(document)

    def update_docs(self, collection, filter, value):
        self.logger.info("Start update documents")
        self.logger.debug("List of document to update : %s", filter)
        collection = self.database[collection]
        collection.update_many(filter=filter, update=value)
        self.logger.info("Success updating documents")

    def update_doc(
        self,
        collection,
        filter: dict,
        upsertable_data: dict | None = None,
    ):
        upsertable_data = upsertable_data or {}
        # Never log `upsertable_data` values: they can contain patient PII (GDPR).
        self.logger.info(
            "Start update document in %s (keys=%s)",
            collection,
            sorted(upsertable_data.keys()),
        )
        self.logger.debug("Filter keys for update : %s", sorted(filter.keys()))
        collection = self.database[collection]
        infos = collection.update_one(
            filter,
            {"$set": upsertable_data},
            upsert=True,
        )
        self.logger.info("Success updating documents : %s", infos)

    def insert_docs(self):
        self.logger.info("Start inserting documents")
        self.logger.debug(
            "Collections to insert : %s",
            {col: len(docs) for col, docs in self.documents_to_insert.items()},
        )
        for collection, documents in self.documents_to_insert.items():
            collection = self.database[collection]
            collection.insert_many(documents)
        self.logger.info("Success inserting documents")
        self.documents_to_insert.clear()

    def delete_docs(self, collections: list, filter):
        self.logger.info(f"Delete documents by filter : {filter}")
        for collection in collections:
            collection = self.database[collection]
            collection.delete_many(filter)
        self.logger.debug("Success deleted documents")

    def get_document_cache(self, file_hash: str) -> dict | None:
        """
        Retrieves a cached parsed document from the document_cache collection using its SHA-256 hash.
        """
        return self.get_document("document_cache", {"hash": file_hash})

    def save_document_cache(
        self,
        file_hash: str,
        file_name: str,
        markdown: str,
        document_type: str = "mtd",
    ) -> None:
        """
        Saves or updates a document markdown parsing in the document_cache collection.
        Ensures a unique index on 'hash' exists.
        """
        self.set_uniq_index("document_cache", "hash")
        self.update_doc(
            collection="document_cache",
            filter={"hash": file_hash},
            upsertable_data={
                "hash": file_hash,
                "file": file_name,
                "document_type": document_type,
                "markdown": markdown,
            },
        )

    def delete_document_cache(
        self,
        file_hash: str | None = None,
        file_name: str | None = None,
        clear_all: bool = False,
    ) -> None:
        """
        Deletes cached documents from document_cache by file_hash, file_name,
        or clears all if ``clear_all=True`` is explicitly passed.
        """
        filter_query = {}
        if file_hash:
            filter_query["hash"] = file_hash
        elif file_name:
            filter_query["file"] = file_name
        elif not clear_all:
            raise ValueError(
                "Refusing to clear the entire document_cache without clear_all=True, file_hash, or file_name."
            )
        self.delete_docs(["document_cache"], filter_query)

    # --- Patient Collection Methods ---

    def get_patient(self, patient_id: str) -> dict | None:
        """Retrieves a patient document from the patients collection by patient_id."""
        return self.get_document("patients", {"patient_id": patient_id})

    def get_all_patients(self) -> list[dict]:
        """Retrieves all patient documents from the patients collection."""
        return list(self.database["patients"].find({}))

    def find_patient_by_identity(
        self,
        first_name: str | None,
        last_name: str | None,
        date_birth=None,
        fallback_file: str | None = None,
    ) -> dict | None:
        """
        Finds an existing patient by normalized identity (last_name + first_name + date_birth),
        with a fallback to (last_name + first_name) if date_birth is missing on either side.
        """
        from src.application.patient import build_name_key, build_patient_id

        exact_id = build_patient_id(
            first_name=first_name,
            last_name=last_name,
            date_birth=date_birth,
            fallback_file=fallback_file,
        )
        found = self.get_patient(exact_id)
        if found is not None:
            return found

        name_key = build_name_key(first_name=first_name, last_name=last_name)
        if not name_key:
            return None

        # If date_birth is missing in the newly extracted RCP, match any existing patient with the same name_key
        if date_birth is None:
            return self.get_document("patients", {"name_key": name_key})

        # If date_birth is present, check if a previous patient record was created without date_birth
        return self.get_document(
            "patients", {"name_key": name_key, "date_birth": None}
        ) or self.get_patient(name_key)

    def upsert_patient(self, patient_data: dict, filename: str | None = None) -> dict:
        """
        Creates or updates a patient document in the patients collection.
        Ensures a unique index on 'patient_id' and maintains the list of associated RCP files.
        """
        from datetime import datetime
        from src.application.patient import build_name_key, build_patient_id

        self.set_uniq_index("patients", "patient_id")

        patient_id = patient_data.get("patient_id")
        if not patient_id:
            patient_id = build_patient_id(
                first_name=patient_data.get("first_name"),
                last_name=patient_data.get("last_name"),
                date_birth=patient_data.get("date_birth"),
                fallback_file=filename,
            )

        existing = self.get_patient(patient_id)
        files: list[str] = []
        if existing and isinstance(existing.get("files"), list):
            for f in existing["files"]:
                if f and f not in files:
                    files.append(f)

        for f in patient_data.get("files", []):
            if f and f not in files:
                files.append(f)

        if filename and filename not in files:
            files.append(filename)

        name_key = build_name_key(
            first_name=patient_data.get("first_name"),
            last_name=patient_data.get("last_name"),
        )

        upsertable = {
            "patient_id": patient_id,
            "name_key": name_key,
            "first_name": patient_data.get("first_name", ""),
            "last_name": patient_data.get("last_name", ""),
            "born_name": patient_data.get("born_name"),
            "date_birth": patient_data.get("date_birth"),
            "gender": (
                patient_data["gender"].value
                if hasattr(patient_data.get("gender"), "value")
                else patient_data.get("gender", "Not_given")
            ),
            "files": files,
            "updated_at": patient_data.get("updated_at") or datetime.now(),
        }

        self.update_doc(
            collection="patients",
            filter={"patient_id": patient_id},
            upsertable_data=upsertable,
        )
        return upsertable

    def remove_file_from_patient(self, filename: str) -> None:
        """
        Removes a deleted RCP filename from any associated patient record,
        and deletes the patient record if no files remain.
        """
        matching_patients = list(self.database["patients"].find({"files": filename}))
        for p in matching_patients:
            pid = p.get("patient_id")
            if not pid:
                continue
            remaining_files = [f for f in p.get("files", []) if f != filename]
            if not remaining_files:
                self.delete_docs(["patients"], {"patient_id": pid})
            else:
                self.update_doc(
                    collection="patients",
                    filter={"patient_id": pid},
                    upsertable_data={"files": remaining_files},
                )

    # --- Bug Reports Collection Methods ---

    def create_bug_report(self, bug_data: dict) -> dict:
        """
        Creates or updates a bug report document in the bug_reports collection.
        Ensures a unique index on 'bug_id'.
        """
        from datetime import datetime
        from src.domain.bug_report import BugReport

        self.set_uniq_index("bug_reports", "bug_id")

        report = BugReport.model_validate(bug_data)
        now = datetime.now()
        upsertable = {
            "bug_id": report.bug_id,
            "title": report.title,
            "description": report.description,
            "category": report.category.value,
            "severity": report.severity.value,
            "status": report.status.value,
            "page": report.page,
            "patient_id": report.patient_id,
            "rcp_file": report.rcp_file,
            "steps_to_reproduce": report.steps_to_reproduce,
            "reporter": report.reporter or "anonymous",
            "created_at": report.created_at or now,
            "updated_at": report.updated_at or now,
        }

        self.update_doc(
            collection="bug_reports",
            filter={"bug_id": report.bug_id},
            upsertable_data=upsertable,
        )
        return upsertable

    def get_bug_report(self, bug_id: str) -> dict | None:
        """Retrieves a bug report from the bug_reports collection by bug_id."""
        return self.get_document("bug_reports", {"bug_id": bug_id})

    def get_all_bug_reports(self, filter_query: dict | None = None) -> list[dict]:
        """
        Retrieves bug reports from the bug_reports collection, sorted by created_at descending.
        """
        from datetime import datetime

        docs = list(self.database["bug_reports"].find(filter_query or {}))
        docs.sort(
            key=lambda d: (
                d.get("created_at")
                if isinstance(d.get("created_at"), datetime)
                else datetime.min
            ),
            reverse=True,
        )
        return docs

    def update_bug_report(self, bug_id: str, update_data: dict) -> dict | None:
        """
        Updates fields of an existing bug report in the bug_reports collection.
        """
        from datetime import datetime

        payload = dict(update_data)
        for enum_field in ("category", "severity", "status"):
            if enum_field in payload and hasattr(payload[enum_field], "value"):
                payload[enum_field] = payload[enum_field].value
        payload["updated_at"] = payload.get("updated_at") or datetime.now()

        self.update_doc(
            collection="bug_reports",
            filter={"bug_id": bug_id},
            upsertable_data=payload,
        )
        return self.get_bug_report(bug_id)

    def delete_bug_report(self, bug_id: str) -> None:
        """Deletes a bug report from the bug_reports collection by bug_id."""
        self.delete_docs(["bug_reports"], {"bug_id": bug_id})
