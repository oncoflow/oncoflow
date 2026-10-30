import os
from typing import TypedDict, List, Optional, Any

from langchain.tools import tool, ToolRuntime

from src.application.reader import DocumentReader

MAX_SEARCH_K_PER_READER = 4


def _normalize_k(k: Any, default: int = 3, max_k: int = MAX_SEARCH_K_PER_READER) -> int:
    """Normalize and clamp `k` against LLM-hallucinated strings or excessive values."""
    if k is None:
        return default
    try:
        val = int(k)
    except (ValueError, TypeError):
        return default
    return max(1, min(val, max_k))


def _sanitize_doc_metadata(metadata: Any) -> Any:
    """
    Strip verbose Docling layout/bounding-box metadata (`dl_meta`, `pk`) before
    serializing retrieved chunks into the LLM prompt or INFO logs, keeping only
    clinically relevant citation fields (`source`, `page`, `pages`, `headings`).
    """
    if not isinstance(metadata, dict):
        return metadata
    if "dl_meta" not in metadata and "pk" not in metadata:
        return metadata

    cleaned: dict[str, Any] = {}
    dl_meta = metadata.get("dl_meta")

    origin_filename = None
    if isinstance(dl_meta, dict):
        origin = dl_meta.get("origin")
        if isinstance(origin, dict):
            origin_filename = origin.get("filename")

    raw_source = origin_filename or metadata.get("source")
    if isinstance(raw_source, str) and raw_source.strip():
        cleaned["source"] = os.path.basename(raw_source.strip())
    elif raw_source is not None:
        cleaned["source"] = raw_source

    pages: list[int] = []
    if "page" in metadata and metadata["page"] is not None:
        cleaned["page"] = metadata["page"]
    elif isinstance(dl_meta, dict):
        for item in dl_meta.get("doc_items") or []:
            if isinstance(item, dict):
                for prov in item.get("prov") or []:
                    if isinstance(prov, dict) and isinstance(prov.get("page_no"), int):
                        if prov["page_no"] not in pages:
                            pages.append(prov["page_no"])
        if len(pages) == 1:
            cleaned["page"] = pages[0]
        elif len(pages) > 1:
            cleaned["pages"] = sorted(pages)

    if isinstance(dl_meta, dict):
        headings = dl_meta.get("headings")
        if isinstance(headings, list) and headings:
            cleaned["headings"] = headings

    for key, value in metadata.items():
        if key in ("pk", "dl_meta", "source", "page"):
            continue
        cleaned[key] = value

    return cleaned


def _format_doc_for_llm(doc: Any) -> str:
    """Serialize a retrieved `Document` with sanitized metadata for the LLM context."""
    meta = _sanitize_doc_metadata(getattr(doc, "metadata", {}))
    content = getattr(doc, "page_content", "")
    return f"Source: {meta}\nContent: {content}"


class Context(TypedDict):
    """
    Type definition for the context passed to single-document PatientMDTForm tools at runtime.
    """

    reader: Optional[DocumentReader]
    additionnal_readers: List[DocumentReader]
    logger: Any


class PatientContext(TypedDict):
    """
    Type definition for the context passed to multi-document PatientRecord tools at runtime.
    """

    patient_readers: List[DocumentReader]
    additionnal_readers: List[DocumentReader]
    logger: Any


@tool(response_format="content")
def get_mtd_markdown(runtime: ToolRuntime[Context]):
    """Get the Medical Technical Documents (MTD) / PatientMDTForm content in Markdown format."""
    runtime.context["logger"].info("tool get_mtd_markdown called")
    reader = runtime.context["reader"]
    if reader is None:
        raise ValueError("No main document reader (mtd) provided in Context.")
    if not getattr(reader, "markdown_exporter", None) and hasattr(
        reader, "read_document"
    ):
        reader.read_document()
    return reader.markdown_exporter[0].page_content


@tool(response_format="content")
def get_patient_mtds_markdown(runtime: ToolRuntime[PatientContext]):
    """Get all Medical Technical Documents (MTD) / PatientMDTForm records of the PatientRecord in Markdown format."""
    runtime.context["logger"].info("tool get_patient_mtds_markdown called")
    patient_readers = runtime.context.get("patient_readers")
    if not patient_readers:
        raise ValueError(
            "No patient document readers (patient_readers) provided in PatientContext."
        )
    for r in patient_readers:
        if not getattr(r, "markdown_exporter", None) and hasattr(r, "read_document"):
            r.read_document()
    return "\n\n".join(
        f"=== FICHE RCP : {r.document} ===\n{r.markdown_exporter[0].page_content}"
        for r in patient_readers
    )


@tool(response_format="content")
def get_patient_ai_history(runtime: ToolRuntime[PatientContext]):
    """Get the chronological history of all AI-extracted clinical, administrative, and expert data across all PatientMDTForm records of the PatientRecord."""
    runtime.context["logger"].info("tool get_patient_ai_history called")
    patient_readers = runtime.context.get("patient_readers")
    if not patient_readers:
        raise ValueError(
            "No patient document readers (patient_readers) provided in PatientContext."
        )
    from src.domain.patient_mdt_form import PatientMDTForm

    entries = [
        (r.document, getattr(r, "sections", None) or {}) for r in patient_readers
    ]
    return PatientMDTForm.format_ai_history_entries(entries)


@tool(response_format="content_and_artifact")
def search_on_mtd(
    runtime: ToolRuntime[Context],
    query: str,
    k: int = 4,
    param: Optional[dict | list[dict]] = None,
    expr: Optional[str] = None,
    timeout: Optional[float] = None,
):
    """Search within the Medical Technical Documents (MTD) / Patient Records.
    This tools use VectoreStore similarity_search options, you can set them as you need

    Args:
        runtime (ToolRuntime): The runtime context containing the document reader.
        query (str): The search query to vectorestore.
        k (int, optional): How many results to return. Defaults to 4.
        param (dict | list[dict], optional): The search params for the index type.
            Defaults to None.
        expr (str, optional): Filtering expression. Defaults to None.
        timeout (int, optional): How long to wait before timeout error.
            Defaults to None.

    Returns:
        tuple: A tuple containing the serialized string of results and the raw artifacts (documents).
    """
    k = _normalize_k(k, default=4, max_k=MAX_SEARCH_K_PER_READER)
    if isinstance(expr, str) and expr.strip().lower() in ("none", "null", ""):
        expr = None
    if isinstance(param, str) and param.strip().lower() in ("none", "null", "{}", ""):
        param = None
    elif isinstance(param, dict) and not param:
        param = None
    if isinstance(timeout, str) and timeout.strip().lower() in ("none", "null", ""):
        timeout = None

    runtime.context["logger"].debug(
        f"tool search_on_mtd called with query : {query} with params :{param}, k: {k}, expr: {expr}, timeout: {timeout}"
    )
    if runtime.context["reader"] is None:
        raise ValueError("No main document reader (mtd) provided in Context.")

    retrieved_docs = runtime.context[
        "reader"
    ].vecdb.clientdb.max_marginal_relevance_search(
        query, k=k, fetch_k=20, param=param, expr=expr, timeout=timeout
    )
    serialized = "\n\n".join(_format_doc_for_llm(doc) for doc in retrieved_docs)
    runtime.context["logger"].debug(
        f"search_on_mtd - serialized : {serialized}, retrieved_docs : {retrieved_docs}"
    )
    return serialized, retrieved_docs


@tool(response_format="content_and_artifact")
def search_on_patient_mtds(
    runtime: ToolRuntime[PatientContext],
    query: str,
    k: int = 4,
    param: Optional[dict | list[dict]] = None,
    expr: Optional[str] = None,
    timeout: Optional[float] = None,
):
    """Search within all Medical Technical Documents (MTD) / PatientMDTForm records of the PatientRecord.
    This tool uses VectorStore similarity_search options across all PatientMDTForm records of the patient.

    Args:
        runtime (ToolRuntime): The runtime context containing the patient document readers.
        query (str): The search query to vectorstore.
        k (int, optional): How many results to return per document. Defaults to 4.
        param (dict | list[dict], optional): The search params for the index type.
            Defaults to None.
        expr (str, optional): Filtering expression. Defaults to None.
        timeout (int, optional): How long to wait before timeout error.
            Defaults to None.

    Returns:
        tuple: A tuple containing the serialized string of results and the raw artifacts (documents).
    """
    k = _normalize_k(k, default=4, max_k=MAX_SEARCH_K_PER_READER)
    if isinstance(expr, str) and expr.strip().lower() in ("none", "null", ""):
        expr = None
    if isinstance(param, str) and param.strip().lower() in ("none", "null", "{}", ""):
        param = None
    elif isinstance(param, dict) and not param:
        param = None
    if isinstance(timeout, str) and timeout.strip().lower() in ("none", "null", ""):
        timeout = None

    runtime.context["logger"].debug(
        f"tool search_on_patient_mtds called with query : {query} with params :{param}, k: {k}, expr: {expr}, timeout: {timeout}"
    )
    patient_readers = runtime.context.get("patient_readers")
    if not patient_readers:
        raise ValueError(
            "No patient document readers (patient_readers) provided in PatientContext."
        )

    retrieved_docs = []
    for r in patient_readers:
        docs = r.vecdb.clientdb.max_marginal_relevance_search(
            query, k=k, fetch_k=20, param=param, expr=expr, timeout=timeout
        )
        retrieved_docs.extend(docs)

    serialized = "\n\n".join(_format_doc_for_llm(doc) for doc in retrieved_docs)
    return serialized, retrieved_docs


@tool(response_format="content_and_artifact")
def search_on_ressources(
    runtime: ToolRuntime[Context | PatientContext],
    query: str,
    k: int = 3,
    param: Optional[dict | list[dict]] = None,
    expr: Optional[str] = None,
    timeout: Optional[float] = None,
):
    """Search within additional resources (e.g., TNCD, PNDS).
    This tools use VectoreStore similarity_search options, you can set them as you need.
    Additional resources can be in french or english.

    Args:
        runtime (ToolRuntime): The runtime context containing additional readers.
        query (str): The search query to vectorestore.
        k (int, optional): How many results to return per resource. Defaults to 3.
        param (dict | list[dict], optional): The search params for the index type.
            Defaults to None.
        expr (str, optional): Filtering expression. Defaults to None.
        timeout (int, optional): How long to wait before timeout error.
            Defaults to None.

    Returns:
        tuple: A tuple containing the serialized string of results and the raw artifacts.
    """
    k = _normalize_k(k, default=3, max_k=MAX_SEARCH_K_PER_READER)
    if isinstance(expr, str) and expr.strip().lower() in ("none", "null", ""):
        expr = None
    if isinstance(param, str) and param.strip().lower() in ("none", "null", "{}", ""):
        param = None
    elif isinstance(param, dict) and not param:
        param = None
    if isinstance(timeout, str) and timeout.strip().lower() in ("none", "null", ""):
        timeout = None

    runtime.context["logger"].debug(
        f"tool search_on_ressources called with query : {query} with params :{param}, k: {k}, expr: {expr}, timeout: {timeout} in {runtime.context['additionnal_readers']}"
    )
    retrieved_docs = []
    for r in runtime.context["additionnal_readers"]:
        docs = r.vecdb.clientdb.max_marginal_relevance_search(
            query, k=k, fetch_k=20, param=param, expr=expr, timeout=timeout
        )
        for doc in docs:
            retrieved_docs.append(doc)

    runtime.context["logger"].info(
        f"search_on_ressources - query={query!r} - retrieved {len(retrieved_docs)} doc(s): "
        f"{[_sanitize_doc_metadata(doc.metadata) for doc in retrieved_docs]}"
    )
    runtime.context["logger"].debug(
        f"search_on_ressources - retrieved_docs : {retrieved_docs}"
    )
    if retrieved_docs:
        serialized = "\n\n".join(_format_doc_for_llm(doc) for doc in retrieved_docs)
        return serialized, retrieved_docs

    return "No additionnal ressources provided", []
