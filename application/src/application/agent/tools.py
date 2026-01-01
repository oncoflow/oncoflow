from dataclasses import dataclass
from typing import TypedDict
from langchain.tools import tool, ToolRuntime

from src.application.reader import DocumentReader


@dataclass
class Context(TypedDict):
    reader: DocumentReader


@tool(response_format="content_and_artifact")
def search_on_mtd(runtime: ToolRuntime[Context], query: str):
    """
    Get all the patient record may the agent can used to answer questions
    """
    reader: DocumentReader = runtime.context["reader"]
    retrieved_docs = reader.get_retriever().invoke(query)
    serialized = "\n\n".join(
        (f"Source: {doc.metadata}\nContent: {doc.page_content}")
        for doc in retrieved_docs
    )
    return serialized, retrieved_docs


@tool(response_format="content_and_artifact")
def search_on_ressources(runtime: ToolRuntime[Context], query: str):
    """
    Get all the additionnals ressources may the agent can used to answer questions like TNCD
    """

    retrieved_retrievers = [
        r.get_retriever() for r in runtime.context["additionnal_readers"]
    ]
    if len(retrieved_retrievers) > 0:
        serialized = "\n\n"
        retrieved_docs = []
        for r in retrieved_retrievers:
            retrieved_docs.append(r.invoke(query))
            serialized = serialized.join(
                (f"Source: {doc.metadata}\nContent: {doc.page_content}")
                for doc in retrieved_docs
                if "metadata" in doc and "page_content" in doc
            )
        return serialized, retrieved_docs
    else:
        return "No additionnal ressources provided", []
