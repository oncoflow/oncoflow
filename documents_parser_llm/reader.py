"""
This code defines a DocumentReader class that performs the following tasks:

- Loads a document from a specified path.
- Splits the document into chunks using a CharacterTextSplitter.
- Adds the chunks to a VectorStore.
- Creates a retrieval chain that allows users to ask questions about the document.

The code also defines a configuration class (AppConfig) and an Llm class (which is not shown in the code).

Usage:

1. Create an instance of the DocumentReader class.
2. Call the askInDocument() method to ask a question about the document.

Example:

```python
# Create an instance of the DocumentReader class
reader = DocumentReader(pdf="patient_file.pdf")

# Ask a question about the document
answer = reader.askInDocument("What is the patient's age?")

# Print the answer
print(answer)
"""

from langchain_community import document_loaders

from langchain_text_splitters import CharacterTextSplitter
from langchain_core.output_parsers import PydanticOutputParser, JsonOutputParser
# import pymupdf4llm
# from langchain.text_splitter import MarkdownTextSplitter

from config import AppConfig
from llm import Llm
from databases import VectorialDataBase






class DocumentReader:
    document = str
    collectionName = "oncoflowDocs"
    retriever = None
    additional_pdf = None
    docs_pdf = {}

    def __init__(self, config=AppConfig,  document=str, docs_pdf=None, prompt = [], models = None):
        self.config = config
        self.document_path = str(config.rcp.path) + "/" + document
        # ic(self.document_path)
        self.llm = Llm(config, embeddings=False, models=models)
        self.vecdb = VectorialDataBase(config)

        default_prompt = []

        if docs_pdf is not None:
            for doc_pdf in docs_pdf:
                pdf_dict = {
                    "vecdb": VectorialDataBase(config, coll_prefix="additional"),
                    "path": str(config.rcp.additional_path) + "/" + doc_pdf,
                    "name": doc_pdf.replace(".", "")
                }
                self.docs_pdf.update({doc_pdf: pdf_dict})
                default_prompt.extend(
                    [("system", "Apprend les éléments de ce document de référence : {" + pdf_dict["name"] + "}")])
        default_prompt.extend(prompt)
        self.logger = config.set_logger("reader", default_context={
            "document": document,
            "ressources": docs_pdf,
            "list_models": models})

        self.llm.make_default_prompt(default_prompt)
        self.default_loader = config.rcp.doc_type
        
        self.logger.info("Class reader succesfully init, Start reading documents")
        self.text_splitter = CharacterTextSplitter(
            chunk_size=config.rcp.chunk_size, chunk_overlap=config.rcp.chunk_overlap)
        self.read_document()

    def _load_document(self, document=str, loader_type=None):
        """Loads a document from the specified path using the given loader type."""
        if loader_type is None:
            loader_type = self.default_loader

        cla = getattr(document_loaders, loader_type)
        return cla(document)

    def read_document(self):
        """
        Reads a document from the specified loader and splits it into chunks.
        Then, adds the chunks to a VectorStore.
        Finally, creates a retrieval chain that allows users to ask questions about the document.
        """
        self.logger.info("Start reading document")
        loader = self._load_document(self.document_path)   
        pages = loader.load()

        chunked_documents = self.text_splitter.split_documents(pages)

        self.vecdb.add_chunked_to_collection(
            chunked_documents, flush_before=True)

        for doc_pdf, infos in self.docs_pdf.items():
            self.logger.debug("Start reading ressource %s", doc_pdf )
            loader = self._load_document(infos["path"])
            pages = loader.load()
            chunked_documents = self.text_splitter.split_documents(pages)
            infos["vecdb"].add_chunked_to_collection(
                chunked_documents, flush_before=True)
    
    def ask_in_document(self, query, class_type=None, models=None):
        """
        Asks a question about the document and returns the answer.

        Args:
            query: The question to ask about the document.

        Returns:
            The answer to the question.
        """
        if class_type is not None:
            parser = PydanticOutputParser(pydantic_object=class_type)

        else:
            parser = JsonOutputParser()

        self.llm.create_chain(self.vecdb.get_retriever(), [
                              {"name":  infos["name"], "retriever": infos["vecdb"].get_retriever()} for doc_pdf, infos in self.docs_pdf.items()], parser)

        return self.llm.invoke_chain(query, parser)
