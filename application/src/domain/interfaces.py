from typing import Protocol, Any, List


class IVectorDatabaseClient(Protocol):
    vectordb: Any


class IVectorDatabase(Protocol):
    def add_chunked_to_collection(
        self, chunks: List[Any], flush_before: bool = False
    ) -> None: ...

    def get_retriever(self) -> Any: ...


class ILlmClient(Protocol):
    embedding: Any
