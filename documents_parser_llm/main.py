from os import listdir
from os.path import isfile, join
from optparse import OptionParser

import environ

import inquirer

from config import AppConfig
from reader import DocumentReader

def manual_prompt(dir, config):
    while True:
        questions = [
            inquirer.List('file', 
                        message="What RCP file do you want to use ?",
                        choices = [f for f in listdir(dir) if isfile(join(dir, f))]),
            inquirer.Text("question",
                        message="Question for LLM (type quit to quit)?")
        ]
        answers = inquirer.prompt(questions)
        
        if answers["question"].lower() == "quit":
            break
        rag = DocumentReader(config,  answers["file"])
        print(rag.askInDocument(answers["question"]))
    


if __name__ == "__main__":
    
    parser = OptionParser()
    parser.add_option("-e", "--env-list", dest="envlist", action="store_true", default=False)
    (options, args) = parser.parse_args()
    
    if options.envlist :
        print ("List of environment Variables :")
        print(environ.generate_help(AppConfig, display_defaults=True))
    else:
        app_conf = environ.to_config(AppConfig)
        
        if app_conf.rcp.manual_query:
            manual_prompt(app_conf.rcp.path, app_conf)
            

