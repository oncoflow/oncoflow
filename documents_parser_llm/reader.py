import uuid
import ollama

from langchain_community.document_loaders import PyMuPDFLoader
from langchain_community.chat_models.ollama import ChatOllama
#from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

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
    llm_context =[
        "Tu parle uniquement le français",
        "Comporte toi comme un assistant medical",
        "Sur des documents, les cases cochées représente un oui",
        "Sur des documents, les cases vides représente un non"
    ]
    
    def __init__(self, pdf = str):
        self.document = pdf
        self.model = ChatOllama(model="llama2:latest")
        self.prompt = PromptTemplate.from_template(
            """
            [INST]<<SYS>> You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.<</SYS>> 
            Question: {question} 
            Context: {context} 
            Answer: [/INST]
            """
        )
        self.readDocument()
        
    def readDocument(self):
        loader = PyMuPDFLoader(self.document)
        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=10)
        pages = loader.load()
        chunked_documents = text_splitter.split_documents(pages)
        self._connectChroma(chunked_documents)
        self.chain = ({
            "context" : self.retriever,
            "question" : RunnablePassthrough()
                       }
                        | self.prompt
                        | self.model
                        | StrOutputParser()
                       )
        
    
    def _connectChroma(self, chunked_documents):
        chroma_client = chromadb.HttpClient(host = "localhost")
        try:
            chroma_collection = chroma_client.get_collection(self.collectionName)
        except Exception:
            chroma_collection = chroma_client.create_collection(self.collectionName)
        
        for doc in chunked_documents:
            chroma_collection.add(
                ids=[str(uuid.uuid1())], metadatas=doc.metadata, documents=doc.page_content)
        # https://ollama.com/blog/embedding-models
        response = ollama.embeddings(model="mxbai-embed-large", prompt=self.llm_context)
        
        embedding = response["embedding"]
        chroma_db4 = Chroma(
            client=chroma_client,
            collection_name=chroma_collection.name,
            embedding_function=[embedding],
        )
        self.retriever = chroma_db4.as_retriever()
        
        return chroma_db4
    
    def askInDocument(self, query):
        return self.chain.invoke(query)