import os
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from src.application.paths import UnsafePathError, safe_path
from src.application.reader import DocumentReader
from src.application.use_cases import (
    PatientMDTFormExtractionService,
    PatientRecordService,
)
from src.domain.agents import get_domain_agents
from src.domain.patient_mdt_form import (
    NonPatientMDTFormError,
    get_domain_mdt_form_cls,
)
from src.infrastructure.documents.repositories import (
    MongoDocumentCacheRepository,
    MongoPatientMDTFormRepository,
    MongoPatientRepository,
)
from src.models.rcp import (
    ActiveJobsStateResponse,
    AdministrativeUpdateRequest,
    AdministrativeUpdateResponse,
    BatchStatusResponse,
    ChatRequest,
    ChatResponse,
    DomainFormSchemaResponse,
    LinkPatientRequest,
    MessageResponse,
    PatientCardResponse,
    PatientDetailResponse,
    PatientMDTFormDetailResponse,
    PatientMDTFormStatusResponse,
    PatientResolveResponse,
    ProcessRequest,
    ProcessResponse,
    RCPCardResponse,
    SectionUpdateRequest,
    UploadResponse,
)
from src.routers.dependencies import (
    DomainConfigDep,
    get_db,
    require_admin,
    require_db,
)

router = APIRouter(prefix="/patientmdtform", tags=["patientmdtform"])

# --- Helpers & Dependencies ---

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


def _safe_mdt_form_path(base_dir, filename: str) -> str:
    """Resolve `filename` inside `base_dir` or raise HTTP 400."""
    try:
        return str(safe_path(base_dir, filename))
    except UnsafePathError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom de fichier invalide.",
        ) from err


def serialize_mongo_doc(doc: dict) -> dict:
    """Convert a MongoDB document into a JSON-serializable dictionary."""
    if not doc:
        return doc
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))

    for k, v in doc.items():
        if isinstance(v, dict):
            doc[k] = serialize_mongo_doc(v)
        elif isinstance(v, list):
            doc[k] = [
                serialize_mongo_doc(item) if isinstance(item, dict) else item
                for item in v
            ]
    return doc


def get_form_models(domain: str | None = None):
    """Dynamically retrieve the clinical model classes defined in the domain's PatientMDTForm."""
    form_cls = get_domain_mdt_form_cls(domain)
    return form_cls.get_clinical_models()


def _is_queue_enabled(config) -> bool:
    """Return True when the async processing queue and MongoDB persistence are enabled."""
    return bool(config.queue.enabled and config.rcp.display_type == "mongodb")


def _build_record_service(config, db=None) -> PatientRecordService:
    """Instantiate a `PatientRecordService` backed by the given MongoDB client or config."""
    return PatientRecordService.from_config(config, db_client=db)


def _build_extraction_service(
    config, db=None, filename: str | None = None
) -> PatientMDTFormExtractionService:
    """Instantiate a `PatientMDTFormExtractionService` backed by the given config."""
    record_service = _build_record_service(config, db=db)
    return PatientMDTFormExtractionService(
        config=config,
        patient_repo=MongoPatientRepository(config, db_client=db),
        mdt_form_repo=MongoPatientMDTFormRepository(config, db_client=db),
        cache_repo=MongoDocumentCacheRepository(config, db_client=db),
        patient_record_service=record_service,
        filename=filename,
    )


def get_mdt_form_repo(
    config: DomainConfigDep, db=Depends(require_db)
) -> MongoPatientMDTFormRepository:
    """FastAPI dependency providing a domain-scoped `PatientMDTFormRepository`."""
    return MongoPatientMDTFormRepository(config, db_client=db)


def get_record_service(
    config: DomainConfigDep, db=Depends(require_db)
) -> PatientRecordService:
    """FastAPI dependency providing a domain-scoped `PatientRecordService`."""
    return _build_record_service(config, db=db)


def get_extraction_service(
    config: DomainConfigDep, db=Depends(get_db)
) -> PatientMDTFormExtractionService:
    """FastAPI dependency providing a domain-scoped `PatientMDTFormExtractionService`."""
    return _build_extraction_service(config, db=db)


RecordServiceDep = Annotated[PatientRecordService, Depends(get_record_service)]
ExtractionServiceDep = Annotated[
    PatientMDTFormExtractionService, Depends(get_extraction_service)
]


# --- Endpoints ---


@router.get("", response_model=list[RCPCardResponse])
def get_rcp_cards(record_service: RecordServiceDep):
    """Retrieve the summary list of all PatientMDTForm records for the domain."""
    return record_service.list_patient_mdt_form_cards()


@router.get("/patients", response_model=list[PatientCardResponse])
def get_patient_cards(record_service: RecordServiceDep):
    """Retrieve the list of PatientRecord summaries built from their latest analyzed PatientMDTForm."""
    return record_service.list_patient_cards()


@router.get("/patients/{patient_id}", response_model=PatientDetailResponse)
def get_patient_detail(patient_id: str, record_service: RecordServiceDep):
    """Retrieve a PatientRecord and the chronological history of all its PatientMDTForm records."""
    detail = record_service.get_patient_detail(patient_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le dossier patient '{patient_id}' n'a pas été trouvé.",
        )

    return {
        "patient": detail["patient"],
        "latest_file": detail["latest_file"],
        "rcps": [serialize_mongo_doc(d) for d in detail["rcps"]],
    }


@router.get("/schema", response_model=DomainFormSchemaResponse)
def get_domain_form_schema(config: DomainConfigDep):
    """Return the pure domain form schema (sections, editability, agents, and clinical enums)."""
    form_cls = get_domain_mdt_form_cls(config.domain)
    return form_cls.get_domain_schema(config.domain)


@router.get("/resolve", response_model=PatientResolveResponse)
def resolve_patient_record_endpoint(
    config: DomainConfigDep,
    record_service: RecordServiceDep,
    patient_id: Annotated[str | None, Query()] = None,
    file: Annotated[str | None, Query()] = None,
):
    """Resolve a `PatientRecord`, its chronologically ordered `PatientMDTForm` records, and the selected/latest files."""
    if file:
        _safe_mdt_form_path(config.rcp.path, file)

    patient, rcps, selected_file = record_service.resolve_patient_record(
        patient_id_param=patient_id,
        file_param=file,
    )
    latest_doc = record_service.form_cls.select_latest_analyzed(rcps) if rcps else None
    latest_file = (
        latest_doc["file"]
        if latest_doc and "file" in latest_doc
        else (rcps[0].get("file") if rcps else None)
    )
    enriched_rcps = [
        serialize_mongo_doc(record_service.enrich_form_doc(d)) for d in rcps
    ]
    return {
        "patient": patient.model_dump(mode="json") if patient else None,
        "rcps": enriched_rcps,
        "selected_file": selected_file,
        "latest_file": latest_file,
    }


@router.get("/batches/{batch_id}", response_model=BatchStatusResponse)
def get_batch_status_endpoint(
    batch_id: str,
    extraction_service: ExtractionServiceDep,
):
    """Return per-file processing status and progress for an upload `batch_id`."""
    return extraction_service.get_batch_status(batch_id)


@router.delete(
    "/patients/{patient_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_admin)],
)
def delete_patient(patient_id: str, record_service: RecordServiceDep):
    """Delete a PatientRecord and all of its associated PatientMDTForm records (admin required when user headers are present)."""
    deleted = record_service.delete_patient_record(patient_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le dossier patient '{patient_id}' n'existe pas.",
        )

    return {"message": f"Dossier patient '{patient_id}' supprimé avec succès."}


@router.post("/patients/{patient_id}/chat", response_model=ChatResponse)
def chat_with_patient_dossier(
    patient_id: str,
    request: ChatRequest,
    config: DomainConfigDep,
    record_service: RecordServiceDep,
    db=Depends(get_db),
):
    """Chat with an expert agent across the entire PatientRecord (all associated PatientMDTForm records)."""
    detail = record_service.get_patient_detail(patient_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le dossier patient '{patient_id}' n'existe pas.",
        )

    files = list(detail["patient"].get("files") or [])
    for doc in detail["rcps"]:
        if "file" in doc and doc["file"] not in files:
            files.append(doc["file"])

    existing_files = []
    for f in files:
        try:
            candidate = safe_path(config.rcp.path, f)
        except UnsafePathError:
            continue
        if os.path.exists(candidate):
            existing_files.append(f)
    if not existing_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aucun fichier PDF RCP trouvé sur le disque pour le patient '{patient_id}'.",
        )

    agents = get_domain_agents(config.domain)
    available_agents = agents.list
    if request.agent_name not in available_agents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent '{request.agent_name}' non reconnu. Agents valides : {list(available_agents.keys())}",
        )

    try:
        effective_config = (
            config.model_copy(update={"language": request.language})
            if request.language
            else config
        )
        extraction_service = _build_extraction_service(effective_config, db=db)
        patient_readers = extraction_service.build_patient_readers(existing_files)
        agent_cls = available_agents[request.agent_name]
        agent = agent_cls(config=effective_config, patient_readers=patient_readers)
        resp = agent.ask(request.message)
        return ChatResponse(response=resp.response)
    except Exception as err:
        config.set_logger("oncoflow.api").exception(
            "Agent error on patient record %s", patient_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de la communication avec l'agent.",
        ) from err


@router.get("/{filename}", response_model=PatientMDTFormDetailResponse)
def get_rcp_detail(
    filename: str,
    config: DomainConfigDep,
    mdt_repo=Depends(get_mdt_form_repo),
):
    """Retrieve the complete details of a PatientMDTForm record including computed metrics and mdt_date."""
    _safe_mdt_form_path(config.rcp.path, filename)
    data = (
        mdt_repo.get_by_filename(filename)
        if hasattr(mdt_repo, "get_by_filename")
        else mdt_repo.get_by_file(filename)
    )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le dossier RCP '{filename}' n'a pas été trouvé.",
        )

    form_cls = get_domain_mdt_form_cls(config.domain)
    enriched = dict(data)
    enriched["metrics"] = form_cls.extract_card_metrics(data)
    enriched["mdt_date"] = form_cls.extract_mdt_date(data)
    return serialize_mongo_doc(enriched)


@router.get("/{filename}/jobs-state", response_model=ActiveJobsStateResponse)
def get_rcp_jobs_state(
    filename: str,
    config: DomainConfigDep,
    extraction_service: ExtractionServiceDep,
):
    """Return the active processing queue jobs state for a specific `PatientMDTForm` `filename`."""
    _safe_mdt_form_path(config.rcp.path, filename)
    state = extraction_service.get_active_jobs_state(filename)
    return {
        "has_any_job": bool(state.get("has_any_job")),
        "has_full_job": bool(state.get("has_full_job")),
        "active_models": list(state.get("active_models") or []),
        "current_step": state.get("current_step"),
        "jobs": [serialize_mongo_doc(j) for j in state.get("jobs", [])],
    }


@router.get("/{filename}/status", response_model=PatientMDTFormStatusResponse)
def get_rcp_status(
    filename: str,
    config: DomainConfigDep,
    mdt_repo=Depends(get_mdt_form_repo),
):
    """Return lightweight processing status fields for a specific `PatientMDTForm` `filename`."""
    _safe_mdt_form_path(config.rcp.path, filename)
    doc = (
        mdt_repo.get_by_filename(filename)
        if hasattr(mdt_repo, "get_by_filename")
        else mdt_repo.get_by_file(filename)
    )
    if doc is not None:
        status_val = doc.get("processing_status")
        raw_pct = doc.get("processing_progress_pct")
        if raw_pct is None and status_val == "COMPLETED":
            pct_val = 100.0
        elif raw_pct is not None:
            pct_val = float(raw_pct)
        else:
            pct_val = 0.0
        return {
            "filename": filename,
            "processing_status": status_val,
            "processing_step": doc.get("processing_step"),
            "processing_progress_pct": pct_val,
            "processing_error": doc.get("processing_error"),
            "patient_id": doc.get("patient_id"),
        }

    extraction_service = _build_extraction_service(config)
    status_info = extraction_service.get_form_status(filename)
    if status_info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le dossier RCP '{filename}' n'a pas été trouvé.",
        )
    return status_info


@router.delete("/{filename}", response_model=MessageResponse)
def delete_rcp(filename: str, config: DomainConfigDep):
    """Delete a PatientMDTForm record from the database and disk."""
    file_path = _safe_mdt_form_path(config.rcp.path, filename)
    mdt_repo = MongoPatientMDTFormRepository(config)
    if not os.path.exists(file_path):
        exists_in_db = mdt_repo.get_by_filename(filename) is not None
        if not exists_in_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Le dossier RCP '{filename}' n'existe pas.",
            )

    record_service = _build_record_service(config)
    record_service.delete_patient_mdt_form_document(filename)
    return {"message": f"Dossier '{filename}' supprimé avec succès."}


@router.post("/upload", response_model=UploadResponse)
def upload_rcp_file(
    config: DomainConfigDep,
    file: UploadFile = File(),
    patient_id: str | None = Form(default=None),
    run_full_ai: bool = Form(default=True),
    batch_id: str | None = Form(default=None),
):
    """
    Upload a PatientMDTForm PDF file, check for duplicates via SHA-256 hash,
    systematically rename new files, and enqueue it for processing
    (or execute it directly when the queue is disabled).
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seuls les fichiers PDF sont acceptés.",
        )

    try:
        chunks: list[bytes] = []
        total_read = 0
        while True:
            chunk = file.file.read(65536)
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Fichier trop volumineux (limite : 50 Mo).",
                )
            chunks.append(chunk)
        file_bytes = b"".join(chunks)
        if not file_bytes.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le contenu du fichier n'est pas un PDF valide.",
            )
        extraction_service = _build_extraction_service(config)
        filename, is_duplicate = extraction_service.resolve_upload(
            file_bytes, file.filename
        )

        if is_duplicate:
            return {
                "filename": filename,
                "domain": config.domain,
                "is_duplicate": True,
                "batch_id": batch_id,
                "link": f"datas?file={filename}",
                "message": f"Attention : ce fichier existe déjà ('{filename}').",
            }

        target_path = os.path.join(config.rcp.path, filename)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "wb") as buffer:
            buffer.write(file_bytes)

        if _is_queue_enabled(config):
            enqueue_res = extraction_service.enqueue_batch(
                files_payload=[{"filename": filename, "patient_id": patient_id}],
                run_full_ai=run_full_ai,
                batch_id=batch_id,
            )
            return {
                "filename": filename,
                "domain": config.domain,
                "patient_id": patient_id,
                "batch_id": enqueue_res["batch_id"],
                "enqueued_count": enqueue_res["enqueued_count"],
                "already_queued_count": enqueue_res["already_queued_count"],
                "results": [serialize_mongo_doc(r) for r in enqueue_res["results"]],
                "message": "Fichier téléversé et ajouté à la file de traitement.",
            }

        try:
            _, patient_dict = extraction_service.ingest_and_associate(
                filename=filename,
                patient_id=patient_id,
            )
        except NonPatientMDTFormError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(err),
            ) from err

        return {
            "filename": filename,
            "domain": config.domain,
            "is_duplicate": False,
            "batch_id": batch_id,
            "patient_id": patient_dict.get("patient_id")
            if patient_dict
            else patient_id,
            "patient": patient_dict,
            "message": "Fichier téléversé, indexé et associé au patient avec succès.",
        }
    except HTTPException:
        raise
    except Exception as err:
        config.set_logger("oncoflow.api").exception("Failed to upload RCP file")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de l'enregistrement du fichier.",
        ) from err


@router.post("/{filename}/process", response_model=ProcessResponse)
def process_rcp(filename: str, request: ProcessRequest, config: DomainConfigDep):
    """Enqueue a reprocessing job for a specific clinical model or for the complete PatientMDTForm."""
    file_path = _safe_mdt_form_path(config.rcp.path, filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le fichier '{filename}' n'existe pas sur le disque ({config.domain}).",
        )

    try:
        matched_model_name = None
        matched_model = None
        if request.model_name:
            models = get_form_models(config.domain)
            for m in models:
                if m.__name__.lower() == request.model_name.lower():
                    matched_model = m
                    break

            if not matched_model:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Modèle '{request.model_name}' non reconnu pour le domaine '{config.domain}'. Modèles valides : {[m.__name__ for m in models]}",
                )
            matched_model_name = matched_model.__name__

        extraction_service = _build_extraction_service(config, filename=filename)
        if _is_queue_enabled(config):
            res = extraction_service.enqueue_rerun(
                filename=filename,
                model_name=matched_model_name,
                preserve_manual_edits=request.preserve_manual_edits,
            )
            return {
                "filename": filename,
                "domain": config.domain,
                "model_name": matched_model_name,
                "queued": not res.get("already_queued"),
                "already_queued": res["already_queued"],
                "jobs": [serialize_mongo_doc(j) for j in res.get("jobs", [])],
                "message": (
                    "Tâche ajoutée à la file de traitement."
                    if not res.get("already_queued")
                    else "Une tâche est déjà active dans la file de traitement."
                ),
            }

        form_cls = get_domain_mdt_form_cls(config.domain)
        if matched_model_name and matched_model:
            form = extraction_service.form
            if (
                request.preserve_manual_edits
                and form_cls.is_section_manually_edited(form, matched_model_name)
                and matched_model_name in form.sections
            ):
                return {
                    "filename": filename,
                    "domain": config.domain,
                    "model_name": matched_model_name,
                    "message": f"Rubrique '{matched_model_name}' conservée (modifiée manuellement).",
                }
            reader = DocumentReader(config=config, document=filename)
            reader.read_document()
            extraction_service.extract_section(
                form=form,
                reader=reader,
                model_cls=matched_model,
                upsert=True,
                clear_manual_flag=(not request.preserve_manual_edits),
            )
            return {
                "filename": filename,
                "domain": config.domain,
                "model_name": matched_model_name,
                "message": f"Modèle '{matched_model_name}' retraité avec succès pour '{filename}'.",
            }
        else:
            extraction_service.extract_all_sections(
                filename=filename,
                preserve_manual_edits=request.preserve_manual_edits,
            )
            return {"message": f"Dossier complet '{filename}' retraité avec succès."}
    except HTTPException:
        raise
    except Exception as err:
        config.set_logger("oncoflow.api").exception(
            "Failed to process RCP %s", filename
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors du traitement du dossier.",
        ) from err


@router.post("/{filename}/chat", response_model=ChatResponse)
def chat_with_patient_agent(
    filename: str, request: ChatRequest, config: DomainConfigDep
):
    """Chat with an expert agent for a given PatientMDTForm document."""
    file_path = _safe_mdt_form_path(config.rcp.path, filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le fichier '{filename}' n'existe pas ({config.domain}).",
        )

    agents = get_domain_agents(config.domain)
    available_agents = agents.list
    if request.agent_name not in available_agents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent '{request.agent_name}' non reconnu. Agents valides : {list(available_agents.keys())}",
        )

    try:
        effective_config = (
            config.model_copy(update={"language": request.language})
            if request.language
            else config
        )
        reader = DocumentReader(config=effective_config, document=filename)
        reader.read_document()
        agent_cls = available_agents[request.agent_name]
        agent = agent_cls(config=effective_config, mtd=reader)
        resp = agent.ask(request.message)
        return ChatResponse(response=resp.response)
    except Exception as err:
        config.set_logger("oncoflow.api").exception("Agent error on RCP %s", filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de la communication avec l'agent.",
        ) from err


@router.get(
    "/{filename}/pdf",
    response_class=FileResponse,
    responses={200: {"content": {"application/pdf": {}}}},
)
def download_rcp_pdf(
    filename: str,
    config: DomainConfigDep,
    inline: Annotated[
        bool, Query(description="Serve PDF inline instead of attachment")
    ] = False,
    variant: Annotated[
        Literal["plain", "bbox"] | None,
        Query(
            description="PDF variant ('bbox' serves <filename>.bbox if available on disk, falling back to plain PDF)"
        ),
    ] = None,
):
    """Download or serve inline the PDF file (or its highlighted `.bbox` variant) for a PatientMDTForm record."""
    file_path = _safe_mdt_form_path(config.rcp.path, filename)
    bbox_path = f"{file_path}.bbox"
    if variant == "bbox" and os.path.exists(bbox_path):
        target_path = bbox_path
    elif os.path.exists(file_path):
        target_path = file_path
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le fichier '{filename}' n'a pas été trouvé ({config.domain}).",
        )
    if inline:
        return FileResponse(
            target_path,
            media_type="application/pdf",
            filename=filename,
            content_disposition_type="inline",
        )
    return FileResponse(target_path, media_type="application/pdf", filename=filename)


@router.patch(
    "/{filename}/sections/{section_name}",
    response_model=PatientMDTFormDetailResponse,
)
def update_rcp_section(
    filename: str,
    section_name: str,
    request: SectionUpdateRequest,
    config: DomainConfigDep,
    db=Depends(require_db),
):
    """Manually update a clinical, completeness, or decision section on a PatientMDTForm."""
    _safe_mdt_form_path(config.rcp.path, filename)
    record_service = _build_record_service(config, db=db)
    try:
        updated_doc = record_service.update_patient_mdt_form_section(
            filename=filename,
            section_name=section_name,
            section_data=request.section_data,
            edited_by=request.edited_by,
        )
        return serialize_mongo_doc(updated_doc)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.patch(
    "/{filename}/administrative",
    response_model=AdministrativeUpdateResponse,
)
def update_rcp_administrative(
    filename: str,
    request: AdministrativeUpdateRequest,
    config: DomainConfigDep,
    db=Depends(require_db),
):
    """Manually update patient administrative information and synchronize the PatientRecord."""
    _safe_mdt_form_path(config.rcp.path, filename)
    record_service = _build_record_service(config, db=db)
    try:
        patient, updated_doc = record_service.update_patient_administrative(
            filename=filename,
            admin_data={
                "first_name": request.first_name,
                "last_name": request.last_name,
                "born_name": request.born_name,
                "date_birth": request.date_birth,
                "date_rcp": request.date_rcp,
                "gender": request.gender,
            },
            apply_to_all_patient_forms=request.apply_to_all_patient_forms,
            edited_by=request.edited_by,
        )
        return {
            "patient": patient.model_dump(mode="json"),
            "form": serialize_mongo_doc(updated_doc),
        }
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.post(
    "/{filename}/link-patient",
    response_model=AdministrativeUpdateResponse,
)
def link_rcp_to_patient(
    filename: str,
    request: LinkPatientRequest,
    config: DomainConfigDep,
    db=Depends(require_db),
):
    """Link a PatientMDTForm record to an existing PatientRecord."""
    _safe_mdt_form_path(config.rcp.path, filename)
    record_service = _build_record_service(config, db=db)
    try:
        patient, updated_doc = record_service.link_mdt_form_to_patient(
            filename=filename,
            target_patient_id=request.target_patient_id,
            override_date_rcp=request.override_date_rcp,
            edited_by=request.edited_by,
        )
        return {
            "patient": patient.model_dump(mode="json"),
            "form": serialize_mongo_doc(updated_doc),
        }
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
