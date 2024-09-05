from os import listdir
from os.path import isfile, join
from optparse import OptionParser

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
        # pprint(rag.ask_in_document(answers["question"]), compact=True)


def all_asked(dir, config):
    fiche_rcp = PatientMDTOncologicForm()

    for f in listdir(dir):
        if isfile(join(dir, f)):
            logger.info(f"Start reading {f} ...")
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
                del rag
            except (FileDataError, PDFPageCountError, PdfStreamError, PDFSyntaxError):
                logger.debug("File %s is not a pdf, pass", f)
            
        pprint(fiche_rcp.get_datas(), compact=True)


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
        logger = app_conf.set_logger("main")

        if app_conf.rcp.manual_query:
            logger.info("Start manual prompting")
            manual_prompt(app_conf.rcp.path, app_conf)
        else:
            logger.info("Start auto prompting")
            all_asked(app_conf.rcp.path, app_conf)
