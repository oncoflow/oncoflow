from os import listdir
from os.path import isfile, join
from argparse import ArgumentParser

from pprint import pprint

import environ
import inquirer

from pymupdf import FileDataError
from pdf2image.exceptions import PDFPageCountError
from pypdf.errors import PdfStreamError
from pdfminer.pdfparser import PDFSyntaxError

from src.application.config import AppConfig
from src.application.reader import DocumentReader
from src.application.app_functions import full_read_file


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
        pprint(rag.ask_in_document(answers["question"]), compact=True)


def all_asked(dir, config):
    for f in listdir(dir):
        try:
            if isfile(join(dir, f)):
                full_read_file(app_conf=config, filename=f, logger=logger)
        except (FileDataError, PDFPageCountError, PdfStreamError, PDFSyntaxError):
                logger.debug("File %s is not a pdf, pass", f)


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
