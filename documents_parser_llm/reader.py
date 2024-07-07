from langchain_community import document_loaders
# from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
#from langchain_community.embeddings import SentenceTransformerEmbeddings

#from langchain_core.prompts import ChatPromptTemplate

from langchain.prompts import PromptTemplate
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser

from langchain_text_splitters import CharacterTextSplitter

from config import AppConfig
from llm import llm
from databases import vectorial_db


class DocumentReader:
    document = str
    collectionName = "oncoflowDocs"
    retriever = None

    def __init__(self, config=AppConfig,  pdf=str):
        self.config = config
        self.document_path = str(config.rcp.path) + "/" + pdf
        self.llm = llm(config)
        self.vecdb = vectorial_db(config)

        self.llm.makeDefaultPrompt([
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

        loader = self._loadDocument(config.rcp.doc_type)
        self.text_splitter = CharacterTextSplitter(
            chunk_size=config.rcp.chunk_size, chunk_overlap=config.rcp.chunk_overlap)

        self.readDocument(loader)

    def _loadDocument(self, loader_type=None):
        cla = getattr(document_loaders, loader_type)
        return cla(self.document_path)

    def readDocument(self, loader):
        pages = loader.load()

        chunked_documents = self.text_splitter.split_documents(pages)
        self.vecdb.add_chunked_to_collection(chunked_documents, flush_before=True)

        self.chain = (
            {"context": self.vecdb.get_retreiver(), "question": RunnablePassthrough()}
            | self.llm.default_prompt
            | self.llm.model
            | StrOutputParser()
        )

    def askInDocument(self, query):
        print(query)
        print(self.chain.get_prompts())
        return self.chain.invoke(query)
