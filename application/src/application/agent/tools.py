from typing import TypedDict, List, Optional, Any

from langchain.tools import tool, ToolRuntime

from src.application.reader import DocumentReader


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
    # Defensive cleanup of parameters against LLM hallucinated string representations of empty values
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
    # Serialize documents for the LLM context
    serialized = "\n\n".join(
        (f"Source: {doc.metadata}\nContent: {doc.page_content}")
        for doc in retrieved_docs
    )
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

    serialized = "\n\n".join(
        (f"Source: {doc.metadata}\nContent: {doc.page_content}")
        for doc in retrieved_docs
    )
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
    """Search within additional resources (e.g., TNCD).
    This tools use VectoreStore similarity_search options, you can set them as you need
    Try many time with different query.
    Additional resources can be in french or english

    Args:
        runtime (ToolRuntime): The runtime context containing additional readers.
        query (str): The search query to vectorestore.
        k (int, optional): How many results to return. Defaults to 4.
        param (dict | list[dict], optional): The search params for the index type.
            Defaults to None.
        expr (str, optional): Filtering expression. Defaults to None.
        timeout (int, optional): How long to wait before timeout error.
            Defaults to None.

    Returns:
        tuple: A tuple containing the serialized string of results and the raw artifacts.
    """
    # Defensive cleanup of parameters against LLM hallucinated string representations of empty values
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
    # Retrieve retrievers from all additional readers in the context
    retrieved_docs = []
    for r in runtime.context["additionnal_readers"]:
        docs = r.vecdb.clientdb.max_marginal_relevance_search(
            query, k=k, fetch_k=20, param=param, expr=expr, timeout=timeout
        )
        for doc in docs:
            retrieved_docs.append(doc)
    runtime.context["logger"].info(
        f"search_on_ressources - retrieved_docs : {retrieved_docs}"
    )
    if retrieved_docs:
        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in retrieved_docs
        )
        return serialized, retrieved_docs

    return "No additionnal ressources provided", []
