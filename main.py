import ollama
from ollama import DocumentStore
from ollama.llm import LLM
from ollama.index import SemanticIndex

# Configuration du stockage des documents
document_store = DocumentStore(path="/content/drive/MyDrive/OncoAIFlow")

# Initialisation du LLM avec Ollama
llm = LLM(model_name="mistralai/Mistral-7B-Instruct-v0.1", tokenizer_name="mistralai/Mistral-7B-Instruct-v0.1")

# Création d'un index sémantique
semantic_index = SemanticIndex(document_store=document_store, llm=llm)

# Fonction pour générer un prompt
def generer_prompt():
    # Vos listes de valeurs et génération de prompt aléatoire
    pass

# Fonction pour interroger l'index et afficher les réponses
def query_and_display(prompt):
    response = semantic_index.query(prompt)
    print(response)  # ou afficher dans un format plus approprié pour votre application

# Exemple d'utilisation
for _ in range(5):
    prompt = generer_prompt()
    query_and_display(prompt)
