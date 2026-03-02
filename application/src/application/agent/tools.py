from typing import TypedDict, List, Optional, Any

from langchain.tools import tool, ToolRuntime

from src.application.reader import DocumentReader


class Context(TypedDict):
    """
    Type definition for the context passed to tools at runtime.
    """

    reader: DocumentReader
    additionnal_readers: List[DocumentReader]


@tool(response_format="content")
def get_mtd_markdown(runtime: ToolRuntime[Context]):
    """Get the Medical Technical Documents (MTD) / Patient Records in Markdown format."""
    runtime.context["logger"].info("tool get_mtd_markdown called")

    return runtime.context["reader"].markdown_exporter[0].page_content


@tool(response_format="content_and_artifact")
def search_on_mtd(
    runtime: ToolRuntime[Context],
    query: str,
    k: int = 4,
    param: Optional[dict | list[dict]] = None,
    expr: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs: Any,
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
        kwargs: Collection.search() keyword arguments.

    Returns:
        tuple: A tuple containing the serialized string of results and the raw artifacts (documents).
    """
    runtime.context["logger"].info(
        f"tool search_on_mtd called with query : {query} with params :{param}, k: {k}, expr: {expr}, timeout: {timeout}, kwargs: {kwargs}"
    )
    reader: DocumentReader = runtime.context["reader"]

    retrieved_docs = reader.vecdb.clientdb.max_marginal_relevance_search(
        query, k=k, fetch_k=20, param=param, expr=expr, timeout=timeout, **kwargs
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
def search_on_ressources(
    runtime: ToolRuntime[Context],
    query: str,
    k: int = 4,
    param: Optional[dict | list[dict]] = None,
    expr: Optional[str] = None,
    timeout: Optional[float] = None,
    **kwargs: Any,
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
        kwargs: Collection.search() keyword arguments.

    Returns:
        tuple: A tuple containing the serialized string of results and the raw artifacts.
    """
    runtime.context["logger"].debug(
        f"tool search_on_ressources called with query : {query} with params :{param}, k: {k}, expr: {expr}, timeout: {timeout}, kwargs: {kwargs} in {runtime.context['additionnal_readers']}"
    )
    # Retrieve retrievers from all additional readers in the context
    retrieved_docs = []
    for r in runtime.context["additionnal_readers"]:
        docs = r.vecdb.clientdb.max_marginal_relevance_search(
            query, k=k, fetch_k=20, param=param, expr=expr, timeout=timeout, **kwargs
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
