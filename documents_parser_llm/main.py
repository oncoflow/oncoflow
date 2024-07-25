from os import listdir
from os.path import isfile, join
from optparse import OptionParser

from pprint import pprint

import environ
import inspect

import inquirer

from config import AppConfig
from reader import DocumentReader
from rcp import RcpFiche


from langchain_core.pydantic_v1 import BaseModel
from icecream import ic


def manual_prompt(dir, config):
    """
    Prompt the user for a question and answer it using the LLM.

    Args:
        dir: The directory containing the RCP files.
        config: The AppConfig object.

    Returns:
        None
    """
    while True:
        questions = [
            inquirer.List('file',
                          message="What RCP file do you want to use ?",
                          choices=[f for f in listdir(dir) if isfile(join(dir, f))]),
            inquirer.Text("question",
                          message="Question for LLM (type quit to quit)?")
        ]
        answers = inquirer.prompt(questions)

        if answers["question"].lower() == "quit":
            break
        rag = DocumentReader(
            config,  answers["file"],  docs_pdf=["tncdchc.pdf"])
        pprint(rag.ask_in_document(answers["question"]), compact=True)


def all_asked(dir, config):
    fiche_rcp = RcpFiche()

    for f in listdir(dir):
        if isfile(join(dir, f)):
            print(f"- Start reading {f} ...")
            for cl in fiche_rcp.basemodel_list:
                
                cl_prompt = fiche_rcp.base_prompt
                ic(cl_prompt)
                cl_prompt.extend(cl.base_prompt)
                ic(cl_prompt)
                rag = DocumentReader(config, document=f, docs_pdf=cl.ressources,
                                     prompt=cl_prompt, models=cl.models)
                print(f" -- Process {cl.__name__}")
                print(f" -- Question : {cl.question}")
                pprint(rag.ask_in_document(query=cl.question,
                       class_type=cl, models=cl.models), compact=True)
                del rag


if __name__ == "__main__":

    parser = OptionParser()
    parser.add_option("-e", "--env-list", dest="envlist",
                      action="store_true", default=False)
    (options, args) = parser.parse_args()

    if options.envlist:
        print("List of environment Variables :")
        print(environ.generate_help(AppConfig, display_defaults=True))
    else:
        app_conf = environ.to_config(AppConfig)

        if app_conf.rcp.manual_query:
            manual_prompt(app_conf.rcp.path, app_conf)
        else:
            all_asked(app_conf.rcp.path, app_conf)
