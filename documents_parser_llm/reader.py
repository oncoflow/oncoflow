import langchain
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOllama
from langchain.document_loaders import PyMuPDFLoader
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import FAISS

class DocumentReader:
    pdf_reader = LayoutPDFReader
    
    def __init__(self, config):
        self.pdf_reader = LayoutPDFReader(config.getConfig("apiparserurl"))
        
    def readDocument(self, doc_path):
        # Create a PyMuPDFLoader object with file_path
        loader = PyMuPDFLoader(file_path=doc_path)

        # load the PDF file
        doc = loader.load()

        # return the loaded document
    
        return doc
    
    def searchInDocument(self, doc, query):
        index = VectorStoreIndex([])
        for chunk in doc.chunks():
            index.insert(Document(text=chunk.to_context_text(), extra_info={}))
        query_engine = index.as_query_engine()
        
        response = query_engine.query(query)
        
        return response