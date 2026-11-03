from datetime import datetime, timezone
import os
import re
from typing import List
import unicodedata

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from src.application.paths import UnsafePathError, is_safe_filename, safe_path
from src.application.reader import DocumentReader
from src.application.ressources import Ressources
from src.domain.agents import get_domain_agents
from src.models.rcp import ChatResponse
from src.models.resources import (
    ResourceChatRequest,
    ResourceDeleteResponse,
    ResourceIndexedResponse,
    ResourceIndexResponse,
)
from src.routers.dependencies import DomainConfigDep

router = APIRouter(prefix="/resources", tags=["resources"])

MAX_RESOURCE_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


def _get_resources_dir(config) -> str:
    """Resolve the domain clinical reference resources directory from config."""
    data_cfg = getattr(config, "Data", None)
    if data_cfg is not None and getattr(data_cfg, "ressources_path", None) is not None:
        return str(data_cfg.ressources_path)
    return str(config.rcp.additional_path)


def _stat_resource_metadata(base_dir: str, filename: str) -> tuple[int, str | None]:
    """Return `(size_bytes, updated_at_iso)` for `filename` inside `base_dir`."""
    try:
        fpath = safe_path(base_dir, filename)
        st = os.stat(fpath)
        updated_at = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
        return int(st.st_size), updated_at
    except (UnsafePathError, OSError):
        return 0, None


@router.get("", response_model=List[ResourceIndexResponse])
def list_resources(config: DomainConfigDep):
    """List clinical reference resources for the domain and their vector indexing status."""
    manager = Ressources(config)
    try:
        files = manager.list_ressources()
    except Exception as err:
        config.set_logger("oncoflow.api").exception("Failed to list resources")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible de lister les ressources.",
        ) from err

    base_dir = _get_resources_dir(config)
    result = []
    for f in files:
        size_bytes, updated_at = _stat_resource_metadata(base_dir, f)
        result.append(
            {
                "filename": f,
                "is_indexed": manager.is_indexed(f),
                "size_bytes": size_bytes,
                "updated_at": updated_at,
            }
        )
    return result


@router.post("/upload", response_model=ResourceIndexResponse)
def upload_resource(
    config: DomainConfigDep,
    file: UploadFile = File(...),
):
    """Upload a clinical reference PDF into the domain resources directory."""
    raw_name = (file.filename or "").strip()
    filename = os.path.basename(raw_name)
    if (
        not filename
        or not is_safe_filename(filename)
        or not filename.lower().endswith(".pdf")
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seuls les fichiers PDF valides sont acceptés.",
        )

    base_dir = _get_resources_dir(config)
    try:
        target_path = safe_path(base_dir, filename)
    except UnsafePathError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom de fichier invalide.",
        ) from err

    chunks: list[bytes] = []
    total_read = 0
    while True:
        chunk = file.file.read(65536)
        if not chunk:
            break
        total_read += len(chunk)
        if total_read > MAX_RESOURCE_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Fichier trop volumineux (limite : 50 Mo).",
            )
        chunks.append(chunk)
    file_bytes = b"".join(chunks)

    os.makedirs(str(base_dir), exist_ok=True)
    with open(target_path, "wb") as buffer:
        buffer.write(file_bytes)

    size_bytes, updated_at = _stat_resource_metadata(base_dir, filename)
    manager = Ressources(config)
    return {
        "filename": filename,
        "is_indexed": manager.is_indexed(filename),
        "size_bytes": size_bytes or len(file_bytes),
        "updated_at": updated_at,
    }


@router.delete("/{filename}", response_model=ResourceDeleteResponse)
def delete_resource(filename: str, config: DomainConfigDep):
    """Delete a clinical reference PDF from the domain resources directory."""
    if not is_safe_filename(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom de fichier invalide.",
        )
    base_dir = _get_resources_dir(config)
    try:
        file_path = safe_path(base_dir, filename)
    except UnsafePathError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom de fichier invalide.",
        ) from err

    if not os.path.isfile(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La ressource '{filename}' n'a pas été trouvée ({config.domain}).",
        )

    os.remove(file_path)
    return {"deleted": filename}


@router.post("/{filename}/index", response_model=ResourceIndexedResponse)
def index_resource(filename: str, config: DomainConfigDep):
    """Index a scientific clinical reference resource into the domain vector store."""
    try:
        safe_path(config.rcp.additional_path, filename)
    except UnsafePathError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom de fichier invalide.",
        ) from err
    manager = Ressources(config)
    files = manager.list_ressources()
    if filename not in files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La ressource '{filename}' n'a pas été trouvée dans le répertoire des ressources ({config.domain}).",
        )

    try:
        manager.index_ressource(filename)
        return {
            "filename": filename,
            "domain": config.domain,
            "message": "Ressource indexée avec succès.",
        }
    except Exception as err:
        config.set_logger("oncoflow.api").exception(
            "Failed to index resource %s", filename
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de l'indexation de la ressource.",
        ) from err


def _extract_tokens(value: str) -> list[str]:
    """Extract lowercase ASCII alphanumeric tokens (length >= 3) for dynamic file matching."""
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return [
        tok for tok in re.findall(r"[a-z0-9]+", ascii_only.lower()) if len(tok) >= 3
    ]


def _normalize_token(value: str) -> str:
    """Return lowercase ASCII alphanumeric string for fuzzy citation-to-PDF matching."""
    return "".join(_extract_tokens(value))


def _best_token_match(raw_query: str, candidates: list[str]) -> str | None:
    """
    Dynamically score candidate filenames against `raw_query` by token overlap length
    without any hardcoded domain or clinical filenames.
    """
    query_tokens = _extract_tokens(raw_query)
    norm_query = _normalize_token(raw_query)
    if not query_tokens or not candidates:
        return None

    best_file: str | None = None
    best_score = 0
    for filename in candidates:
        stem = os.path.splitext(filename)[0]
        stem_norm = _normalize_token(stem)
        if not stem_norm:
            continue
        if stem_norm == norm_query or (len(stem_norm) >= 4 and stem_norm in norm_query):
            return filename
        score = sum(len(tok) for tok in query_tokens if tok in stem_norm)
        if score > best_score:
            best_score = score
            best_file = filename
    return best_file if best_score >= 3 else None


def _resolve_resource_pdf_path(
    config, raw_name: str, form_file: str | None = None
) -> tuple[str, str] | None:
    """
    Dynamically resolve a citation label or filename against the domain's indexed
    resources directory (`additional_path`) or patient records directory (`rcp.path`).
    """
    cleaned = os.path.basename((raw_name or "").strip().replace("\\", "/"))
    if not cleaned or ".." in raw_name or "\0" in raw_name:
        return None

    base_dir = _get_resources_dir(config)
    try:
        available = [
            f
            for f in os.listdir(base_dir)
            if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(base_dir, f))
        ]
    except OSError:
        available = []
    available.sort()

    # 1. Exact or case-insensitive match in resources directory
    exact_candidates = [cleaned]
    if not cleaned.lower().endswith(".pdf"):
        exact_candidates.append(f"{cleaned}.pdf")
    lower_map = {f.lower(): f for f in available}
    for cand in exact_candidates:
        if cand.lower() in lower_map:
            matched = lower_map[cand.lower()]
            return matched, os.path.join(base_dir, matched)

    # 2. Dynamic token-overlap match against available guideline PDFs in resources directory
    matched_resource = _best_token_match(raw_name, available)
    if matched_resource:
        return matched_resource, os.path.join(base_dir, matched_resource)

    # 3. Check if the citation or fallback `form_file` resolves to a patient PDF in `config.rcp.path`
    rcp_dir = str(config.rcp.path)
    try:
        rcp_files = [
            f
            for f in os.listdir(rcp_dir)
            if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(rcp_dir, f))
        ]
    except OSError:
        rcp_files = []
    rcp_lower_map = {f.lower(): f for f in rcp_files}
    for cand in exact_candidates:
        if cand.lower() in rcp_lower_map:
            matched = rcp_lower_map[cand.lower()]
            return matched, os.path.join(rcp_dir, matched)

    matched_rcp = _best_token_match(raw_name, rcp_files)
    if matched_rcp:
        return matched_rcp, os.path.join(rcp_dir, matched_rcp)

    if form_file:
        clean_form = os.path.basename(form_file.strip().replace("\\", "/"))
        if clean_form and ".." not in form_file and clean_form.lower() in rcp_lower_map:
            matched = rcp_lower_map[clean_form.lower()]
            return matched, os.path.join(rcp_dir, matched)

    return None


@router.get(
    "/{filename}/file",
    response_class=FileResponse,
    responses={200: {"content": {"application/pdf": {}}}},
)
def get_resource_file(
    filename: str,
    config: DomainConfigDep,
    form_file: str | None = None,
):
    """Serve a clinical reference resource PDF inline after validating safe path boundaries."""
    if ".." in filename or "\0" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom de fichier invalide.",
        )

    resolved = _resolve_resource_pdf_path(config, filename, form_file=form_file)
    if resolved is None:
        if not is_safe_filename(filename):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nom de fichier invalide.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La ressource '{filename}' n'a pas été trouvée ({config.domain}).",
        )

    resolved_name, file_path = resolved
    return FileResponse(
        str(file_path),
        media_type="application/pdf",
        filename=resolved_name,
        content_disposition_type="inline",
    )


@router.post("/{filename}/chat", response_model=ChatResponse)
def chat_with_resource_agent(
    filename: str, request: ResourceChatRequest, config: DomainConfigDep
):
    """Chat with the Resource Assistant agent to query a specific indexed clinical resource."""
    try:
        safe_path(config.rcp.additional_path, filename)
    except UnsafePathError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom de fichier invalide.",
        ) from err
    manager = Ressources(config)
    files = manager.list_ressources()
    if filename not in files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La ressource '{filename}' n'a pas été trouvée ({config.domain}).",
        )

    if not manager.is_indexed(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La ressource '{filename}' doit d'abord être indexée.",
        )

    try:
        effective_config = (
            config.model_copy(update={"language": request.language})
            if request.language
            else config
        )
        reader = DocumentReader(
            effective_config, document=filename, document_type="ressource"
        )
        agents = get_domain_agents(effective_config.domain)
        agent_cls = agents.list["Ressource Assistant"]
        agent = agent_cls(config=effective_config, additionnal_readers=[reader])
        resp = agent.ask(request.message)
        return ChatResponse(response=resp.response)
    except Exception as err:
        config.set_logger("oncoflow.api").exception(
            "Resource agent error on %s", filename
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur interne lors de la génération de la réponse.",
        ) from err
