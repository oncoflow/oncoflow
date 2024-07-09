from config import ReaderConfig
from reader import DocumentReader


class chainTest ():

    def __init__(self):
       
    
        self.rag = DocumentReader('/home/debianllm/Code/oncoflow/oncoflow/samples/RCP2.pdf')
        self.promptsList = ["Quel est l'âge du patient ?",
                            "Est-ce qu'une biopsie avec un résultat anatomopathologique a déja été obtenu ?",
                            "Est-ce qu'il est fait mention d'un traitement par anticoagulants ?",
                           "Quel sont les examens d'imagerie réalisés chez ce patient, je souhaite un format en sortie avec date de réalisation, type d'examen, résultat principal ?",
                           "Quel est le stade OMS du patient ?",
                           "Est-ce qu'un traitement par chimiothérapie à déja été réalisé ?"]
        self.responsesList = []

    def runTest(self):

        while True:
             for i in self.promptsList:
                  ## fonction timer à ce moment pour le temps d'inférence ?
                  
                  response = self.rag.ask_in_document(i)
                  ## timer stop 

                  self.responsesList.append(response)
        ## a ce moment on peut ajouter un enregistrement dans un csv ou xls peut être en prenant en variables également les parametres
        return self.responsesList
    
test1=chainTest()

test1.runTest()

