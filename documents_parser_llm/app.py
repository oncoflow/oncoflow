

from argparse import ArgumentParser
from os import listdir, makedirs
from os.path import isfile, join, exists

from datetime import datetime
import pandas as pd

from pprint import pprint

import environ
import inquirer

from pymupdf import FileDataError
from pdf2image.exceptions import PDFPageCountError
from pypdf.errors import PdfStreamError
from pdfminer.pdfparser import PDFSyntaxError

from src.application.config import AppConfig
from src.application.reader import DocumentReader
from src.domain.patient_mdt_oncologic_form import PatientMDTOncologicForm


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
            inquirer.List(
                "file",
                message="What RCP file do you want to use ?",
                choices=[f for f in listdir(dir) if isfile(join(dir, f))],
            ),
            inquirer.Text("question", message="Question for LLM (type quit to quit)?"),
        ]
        answers = inquirer.prompt(questions)

        if answers["question"].lower() == "quit":
            break
        rag = DocumentReader(config, answers["file"], docs_pdf=["tncdchc.pdf"])
        # pprint(rag.ask_in_document(answers["question"]), compact=True)
        

def flatten_json(data, prefix=''):
    result = {}
    for key, value in data.items():
        new_key = f"{prefix}{key}" if prefix else key
        if isinstance(value, dict):
            sub_result = flatten_json(value, new_key + '.')
            result.update(sub_result)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                sub_result = flatten_json(item, f"{new_key}[{i}].")
                result.update(sub_result)
        else:
            result[new_key] = value
    return result

def write_to_csv(data, filename):
    # Vérifier si le fichier CSV existe déjà
    if exists(filename):
        # Charger le CSV existant avec Pandas
        df = pd.read_csv(filename)
        
        # Ajouter la nouvelle ligne et éventuellement les nouvelles colonnes
        new_row = flatten_json(data)
        new_row['horodatage'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        
        # Sauver le CSV mis à jour
        df.to_csv(filename, index=False)
    else:
        # Créer un nouveau CSV avec les données
        new_row = flatten_json(data)
        new_row['horodatage'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df = pd.DataFrame([new_row])
        
        # Sauver le CSV
        df.to_csv(filename, index=False)
        
        
def all_asked(dir, config):
    fiche_rcp = PatientMDTOncologicForm()
    results_dir = join(dir, 'results')
    if not exists(results_dir):
        makedirs(results_dir)

    for f in listdir(dir):
        if isfile(join(dir, f)):
            logger.info(f"Start reading {f} ...")
            total_inferences = int(1)
            actual_inference = int(1)
            if config.rcp.batch_mode:
                total_inferences=int(config.rcp.batch_raw)
                logger.debug("Exporting to csv with %s try",total_inferences)
                
            for actual_inference in range(1, total_inferences + 1):
                logger.debug(f"Try number {actual_inference} of {total_inferences} ")
                try:
                    rag = DocumentReader(config, document=f)
                    for cl in fiche_rcp.basemodel_list:
                        cl_prompt = fiche_rcp.base_prompt.copy()
                        cl_prompt.extend(cl.base_prompt)
                        rag.set_prompt(prompt=cl_prompt)
                        rag.read_additionnal_document(docs_pdf=cl.ressources)

                        logger.info(f"Process {cl.__name__}")
                        logger.info(f"Question : {cl.question}")
                        datas = rag.ask_in_document(query=cl.question,
                                                    class_type=cl, models=cl.models)
                        if datas:
                            # Set first response
                            fiche_rcp.set_datas(cl, datas)
                    if config.rcp.batch_mode:
                        
                        csv_file_name = f.replace(".pdf", ".csv")
                        write_to_csv(fiche_rcp.get_datas(),join(results_dir,csv_file_name))
                    del rag
                except (FileDataError, PDFPageCountError, PdfStreamError, PDFSyntaxError):
                    logger.debug("File %s is not a pdf, pass", f)
                
                
            pprint(fiche_rcp.get_datas(), compact=True)



if __name__ == "__main__":

    parser = ArgumentParser()
    parser.add_argument(
        "-e", "--env-list", dest="envlist", action="store_true", default=False
    )
    args = parser.parse_args()

    if args.envlist:
        print("List of environment Variables :")
        print(environ.generate_help(AppConfig, display_defaults=True))
    else:
        app_conf = environ.to_config(AppConfig)
        logger = app_conf.set_logger("main")

        if app_conf.rcp.manual_query:
            logger.info("Start manual prompting")
            manual_prompt(app_conf.rcp.path, app_conf)
        else:
            logger.info("Start auto prompting")
            all_asked(app_conf.rcp.path, app_conf)
