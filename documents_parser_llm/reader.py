import uuid

from langchain_community.document_loaders import PyMuPDFLoader
from langchain_community import document_loaders
from langchain_community.chat_models.ollama import ChatOllama
#from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain.prompts import PromptTemplate
from langchain_core.prompts import ChatPromptTemplate

from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser

from langchain_text_splitters import CharacterTextSplitter

from langchain_chroma import Chroma

import chromadb

class DocumentReader:
    document = str
    collectionName = "oncoflowDocs"
    retriever = None
    prompt = PromptTemplate

    def __init__(self, pdf = str):
        self.documentPath = pdf
        self.loadedDocument = None
        self.model = ChatOllama(base_url="http://192.168.0.122:11434", format="json", model="phi3:latest", temperature=0) #json is for better output management, and less verbose, temperature=0 is for reproducibility
        self.prompt = ChatPromptTemplate.from_messages([
    ("system", "Tu es un spécialiste de la cancérologie digestive. Tu dois répondre aux questions concernant le dossier de ce patient : {context}."),
    ("human", "As-tu compris?"),
    ("ai", "Oui, grâce aux éléments je vais pouvoir répondre, si il me manque un élément de réponse je répondrai par : inconnu"),
    ("human", "Que vas-tu répondre si tu n'as pas tous les éléments?"),
    ("ai", "inconnu"),
    ("human", "Es tu prêt à répondre de manière brève et en francais à une question?"),
    ("ai", "Oui, quelle est la question concernant ce patient ?"),
    ("human", "{question}"),
        ])  
        self.readDocument()
        
    def _loadDocument(self, loaderType=None ):
        if loaderType == "PyMuPDFLoader":
            return PyMuPDFLoader(self.documentPath)
        else:
            cla = getattr(document_loaders, loaderType )
            return cla(self.documentPath)
        
    def readDocument(self):
        loader = self._loadDocument("PyMuPDFLoader")
        
        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=10)
        pages = loader.load()
        
        chunked_documents = text_splitter.split_documents(pages)
        self._connectChroma(chunked_documents)
        self.chain = (
                     {"context": self.retriever, "question": RunnablePassthrough()} 
                        | self.prompt
                        | self.model
                        | StrOutputParser()
            )
        
    
    def _connectChroma(self, chunked_documents):
        #chroma_client = chromadb.HttpClient(host = "localhost")
        chroma_client = chromadb.PersistentClient()
        chroma_collection = chroma_client.get_or_create_collection(self.collectionName)

        
        for doc in chunked_documents:
            chroma_collection.add(
                ids=[str(uuid.uuid1())], metadatas=doc.metadata, documents=doc.page_content)
        # https://ollama.com/blog/embedding-models
        embeddings = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
        
        chroma_db4 = Chroma(
            client=chroma_client,
            collection_name=chroma_collection.name,
            embedding_function=embeddings,
        )
        self.retriever = chroma_db4.as_retriever()
        
        return chroma_db4
    
    def askInDocument(self, query):
        print(query)
        print(self.chain.get_prompts())
        return self.chain.invoke(query)