from typing import TypedDict, List
from langchain.tools import tool, ToolRuntime

from src.application.reader import DocumentReader


class Context(TypedDict):
    """
    Type definition for the context passed to tools at runtime.
    """
    reader: DocumentReader
    additionnal_readers: List[DocumentReader]


@tool(response_format="content_and_artifact")
def search_on_mtd(runtime: ToolRuntime[Context], query: str):
    """
    Search within the Medical Technical Documents (MTD) / Patient Records.
    
    Args:
        runtime (ToolRuntime): The runtime context containing the document reader.
        query (str): The search query.
        
    Returns:
        tuple: A tuple containing the serialized string of results and the raw artifacts (documents).
    """
    reader: DocumentReader = runtime.context["reader"]
    retrieved_docs = reader.get_retriever().invoke(query)
    
    # Serialize documents for the LLM context
    serialized = "\n\n".join(
        (f"Source: {doc.metadata}\nContent: {doc.page_content}")
        for doc in retrieved_docs
    )
    return serialized, retrieved_docs


@tool(response_format="content_and_artifact")
def search_on_ressources(runtime: ToolRuntime[Context], query: str):
    """
    Search within additional resources (e.g., TNCD, guidelines).
    
    Args:
        runtime (ToolRuntime): The runtime context containing additional readers.
        query (str): The search query.
        
    Returns:
        tuple: A tuple containing the serialized string of results and the raw artifacts.
    """
    # Retrieve retrievers from all additional readers in the context
    retrieved_retrievers = [
        r.get_retriever() for r in runtime.context.get("additionnal_readers", [])
    ]
    
    retrieved_docs = []
    for r in retrieved_retrievers:
        retrieved_docs.extend(r.invoke(query))

    if retrieved_docs:
        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in retrieved_docs
        )
        return serialized, retrieved_docs
    else:
        return "No additionnal ressources provided", []
