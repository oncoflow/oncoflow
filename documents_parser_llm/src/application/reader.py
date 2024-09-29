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

from langchain_experimental.text_splitter import SemanticChunker

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.output_parsers import PydanticOutputParser, JsonOutputParser

from src.application.config import AppConfig
from src.application.llm import Llm
from src.application.tools import timed

from src.infrastructure.parsers.openparse import OpenParseDocumentLoader
from src.infrastructure.vectorial.database import VectorialDataBase


class DocumentReader:
    """
    A class that reads documents and enables querying them using an LLM.

    Attributes:
        document_path (str): The path to the document.
        llm (Llm): An instance of the Llm class for performing language tasks.
        vecdb (VectorialDataBase): An instance of VectorialDataBase for vector storage and retrieval.
        default_loader (callable): The default loader type for documents.
        logger (Logger): A logger for tracking progress and errors.
    """

    document = str
    collectionName = "oncoflowDocs"
    retriever = None
    additional_pdf = None
    docs_pdf = {}

    def __init__(
        self, config=AppConfig, document=str, docs_pdf=None, prompt=None, models=None
    ):
        self.config = config
        if prompt is None:
            prompt = []
        self.current_model = None
        
        self.document_path = str(config.rcp.path) + "/" + document
        # ic(self.document_path)
        self.llm = Llm(config, embeddings=False, models=models)
        self.vecdb = VectorialDataBase(config)

        self.set_prompt(prompt)

        self.logger = config.set_logger(
            "reader",
            default_context={
                "document": document,
                "ressources": docs_pdf,
                "list_models": list(self.llm.model.keys()),
                "parser": config.rcp.doc_type
            },
        )

        self.metadata = {}
        self.metadata["list_models"] = list(self.llm.model.keys())

        self.default_loader = config.rcp.doc_type

        self.logger.info("Class reader succesfully init, Start reading documents")
        self.embeddings = Llm(config, embeddings=True).embeddings
        self.text_splitter = SemanticChunker(self.embeddings)
        # self.text_splitter = RecursiveCharacterTextSplitter(
        #     chunk_size=config.rcp.chunk_size, chunk_overlap=config.rcp.chunk_overlap
        # )
        self.read_document(self.vecdb, self.document_path)
        self.read_additionnal_document(docs_pdf)

    def set_prompt(self, prompt):
        """
        Set the default prompt for the DocumentReader instance.

        Args:
            prompt (str or list of str): The default prompt(s) to use when querying documents.
                If a single string is provided, it will be used as-is. If a list of strings
                is provided, each prompt will be appended to the list of default prompts.

        Raises:
            TypeError: If `prompt` is not a string or a list of strings.
        """
        if isinstance(prompt, str):
            prompt = [prompt]
        elif not isinstance(prompt, list):
            raise TypeError("Prompt must be a string or a list of strings")
        self.default_prompt = prompt
        self.llm.make_default_prompt(self.default_prompt)

    @timed
    def read_additionnal_document(self, docs_pdf=None):
        """
        Reads additional documents if provided and updates the default prompt accordingly.

        Args:
            docs_pdf (dict or None): A dictionary containing information about additional PDFs to read.
                If None, no additional documents are read, and the default prompt is used.
        """
        if docs_pdf is not None:
            additionnal_prompt = []
            for doc_pdf in docs_pdf:
                pdf_dict = {
                    "vecdb": VectorialDataBase(self.config, coll_prefix="additional"),
                    "path": f"{self.config.rcp.additional_path}/{doc_pdf}",
                    "name": doc_pdf.replace(".", ""),
                }
                self.docs_pdf[doc_pdf] = pdf_dict
                additionnal_prompt.append(("system", f"I'm going to give you a question about a specific topic. Your task is to find the relevant information in our vector database of reference documents using semantic analogy and provide me with the most accurate answer based on that information, the document : {pdf_dict['name']}"))
                self.logger.debug(f"Start reading ressource {doc_pdf}")
                self.read_document(pdf_dict["vecdb"], pdf_dict["path"])
            self.llm.make_default_prompt(additionnal_prompt + self.default_prompt)
        else:
            self.logger.debug("No additionnal ressources, return to default prompt")
            self.llm.make_default_prompt(self.default_prompt)

    def _load_document(self, document=str, loader_type=None):
        """Loads a document from the specified path using the given loader type."""
        if loader_type is None:
            loader_type = self.default_loader
        if loader_type == "openparse":
            cla = OpenParseDocumentLoader
        else:
            cla = getattr(document_loaders, loader_type)
        if isinstance(cla, document_loaders.UnstructuredPDFLoader):
            return cla(document,    
                            chunking_strategy="by_title",
                            max_characters=1000000,
                            include_orig_elements=False,).load()
        else:
            return cla(document).load()
            #return self.text_splitter.split_documents(docs)

    @timed
    def read_document(self, vecdb: VectorialDataBase, document_path: str):
        """
        Reads a document from the specified loader and splits it into chunks.
        Then, adds the chunks to a VectorStore.
        Finally, creates a retrieval chain that allows users to ask questions about the document.
        """
        self.logger.info(f"Start reading document {document_path}")

        chunked_documents = self._load_document(document_path)

        vecdb.add_chunked_to_collection(chunked_documents, flush_before=True)
        self.current_model = vecdb.embeddings.model

    @timed
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

        self.llm.create_chain(
            self.vecdb.get_retriever(),
            [
                {"name": infos["name"], "retriever": infos["vecdb"].get_retriever()}
                for doc_pdf, infos in self.docs_pdf.items()
            ],
            parser,
        )

        response = self.llm.invoke_multimodels_chain(query, parser)
        self.current_model = self.llm.current_model.model
        
        return response
