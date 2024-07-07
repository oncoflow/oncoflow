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

from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser

from langchain_text_splitters import CharacterTextSplitter

from config import AppConfig
from llm import Llm
from databases import vectorial_db


class DocumentReader:
    document = str
    collectionName = "oncoflowDocs"
    retriever = None

    def __init__(self, config=AppConfig,  pdf=str):
        self.config = config
        self.document_path = str(config.rcp.path) + "/" + pdf
        self.llm = Llm(config)
        self.vecdb = vectorial_db(config)

        self.llm.make_default_prompt([
            ("system",
             "Tu es un spécialiste de la cancérologie digestive. Tu dois répondre aux questions concernant le dossier de ce patient : {context}."),
            ("human", "As-tu compris?"),
            ("ai", "Oui, grâce aux éléments je vais pouvoir répondre, si il me manque un élément de réponse je répondrai par : inconnu"),
            ("human", "Que vas-tu répondre si tu n'as pas tous les éléments?"),
            ("ai", "inconnu"),
            ("human", "Es tu prêt à répondre de manière brève et en francais à une question?"),
            ("ai", "Oui, quelle est la question concernant ce patient ?"),
            ("human", "{question}"),
        ])

        loader = self._load_document(config.rcp.doc_type)
        self.text_splitter = CharacterTextSplitter(
            chunk_size=config.rcp.chunk_size, chunk_overlap=config.rcp.chunk_overlap)

        self.read_document(loader)

    
    def _load_document(self, loader_type=None):
        """Loads a document from the specified path using the given loader type."""
        cla = getattr(document_loaders, loader_type)
        return cla(self.document_path)

    def read_document(self, loader):
        """
        Reads a document from the specified loader and splits it into chunks.
        Then, adds the chunks to a VectorStore.
        Finally, creates a retrieval chain that allows users to ask questions about the document.
        """
        pages = loader.load()

        chunked_documents = self.text_splitter.split_documents(pages)
        self.vecdb.add_chunked_to_collection(chunked_documents, flush_before=True)

        self.chain = (
            {"context": self.vecdb.get_retriever(), "question": RunnablePassthrough()}
            | self.llm.default_prompt
            | self.llm.model
            | StrOutputParser()
        )

    def ask_in_document(self, query):
        """
        Asks a question about the document and returns the answer.

        Args:
            query: The question to ask about the document.

        Returns:
            The answer to the question.
        """
        print(query)
        print(self.chain.get_prompts())
        return self.chain.invoke(query)
