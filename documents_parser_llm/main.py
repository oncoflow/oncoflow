from os import listdir
from os.path import isfile, join
from optparse import OptionParser

from pprint import pprint

import environ

import inquirer

from config import AppConfig
from reader import DocumentReader

from langchain_core.exceptions import OutputParserException

from rcp import RcpFiche


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
        rag = DocumentReader(config,  answers["file"],  docs_pdf=["tncdchc.pdf"])
        pprint(rag.ask_in_document(answers["question"]), compact=True)


def all_asked(dir, config):
    fiche_rcp = RcpFiche()
    prompts_list = [
        {"question": "Donne moi les informations patient de la fiche RCP", "class_type": fiche_rcp.Patient},
        {"question": "En te basant sur les documents de références, est-ce qu'un cardialogue est nécessaire ? ", "class_type": fiche_rcp.Cardiologue}]
    # "Est-ce qu'une biopsie avec un résultat anatomopathologique a déja été obtenu ?",
    # "Est-ce qu'il est fait mention d'un traitement par anticoagulants ?",
    # "Quel sont les examens d'imagerie réalisés chez ce patient, je souhaite un format en sortie avec date de réalisation, type d'examen, résultat principal ?",
    # "Quel est le stade OMS du patient ?",
    # "Est-ce qu'un traitement par chimiothérapie à déja été réalisé ?"]
    for f in listdir(dir):
        if isfile(join(dir, f)):
            print(f"- Start reading {f} ...")
            rag = DocumentReader(config, f, docs_pdf=["tncdchc.pdf"])
            for p in prompts_list:
                print(f" -- Question : {p['question']}")
                try:
                    pprint(rag.ask_in_document(p["question"], p["class_type"]),  compact=True)
                except OutputParserException as e:
                    print(f"llm say : {e.llm_output}")
                    print(f"observation : {e.observation}")
                    raise


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
