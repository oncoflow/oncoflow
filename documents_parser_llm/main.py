from config import ReaderConfig
from reader import DocumentReader

if __name__ == "main":
    conf = ReaderConfig()

rag = DocumentReader("/home/debianllm/Code/oncoflow/oncoflow/samples/RCP2.pdf")

print(rag.askInDocument("Quel est l'âge du patient ?"))