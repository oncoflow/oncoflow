import uuid

from langchain_community.document_loaders import PyMuPDFLoader
from langchain_community.chat_models.ollama import ChatOllama
#from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

from langchain.embeddings import SentenceTransformerEmbeddings
from langchain.prompts import PromptTemplate
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser

from langchain_text_splitters import CharacterTextSplitter

from langchain_chroma import Chroma

import chromadb

class DocumentReader:
    document = str
    collectionName = "oncowflowDocs"
    retriever = None
    prompt = PromptTemplate

    def __init__(self, pdf = str):
        self.document = pdf
        self.model = ChatOllama(model="llama3:latest")
        self.prompt = PromptTemplate.from_template(
            """
            Tu parle uniquement le français et comporte toi comme un assistant medical,\
            sur des documents, les cases cochées représente un oui et les cases vides représente un non, \
            répond à la question sur le context suivant:
            {context}
            
            Question: {question} 
            """
        )
        self.readDocument()
        
    def readDocument(self):
        loader = PyMuPDFLoader(self.document)
        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=10)
        pages = loader.load()
        print(pages)
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
        return self.chain.invoke(query)