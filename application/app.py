import os
import signal
import atexit


def clean_exit(signum=None, frame=None):
    try:
        # Send SIGKILL to the entire process group to stop all processes instantly
        os.killpg(os.getpgid(0), signal.SIGKILL)
    except Exception:
        os._exit(0)


try:
    signal.signal(signal.SIGINT, clean_exit)
    signal.signal(signal.SIGTERM, clean_exit)
except ValueError:
    atexit.register(clean_exit)

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
os.environ["DOCLING_DEVICE"] = "cpu"

import json
from os import listdir
from os.path import isfile, join
from argparse import ArgumentParser

from pprint import pprint  # noqa: F401


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
        rag = DocumentReader(config, document=answers["file"])  # noqa: F841
        logger.warning(
            "Prompting DocumentReader directly is deprecated. Please use Agents explicitly."
        )
        # pprint(rag.ask_in_document(answers["question"]), compact=True)


def all_asked(dir, config):
    for f in listdir(dir):
        try:
            if isfile(join(dir, f)):
                full_read_file(app_conf=config, filename=f, logger=logger)
        except (FileDataError, PDFPageCountError, PdfStreamError, PDFSyntaxError) as e:
            logger.debug("File %s is not a pdf, pass. Error: %s", f, e)
        except Exception as e:
            logger.exception("Unexpected error when processing file %s: %s", f, e)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "-e", "--env-list", dest="envlist", action="store_true", default=False
    )
    args = parser.parse_args()

    if args.envlist:
        print("List of environment Variables :")
        print(json.dumps(AppConfig.model_json_schema(), indent=2))
    else:
        app_conf = AppConfig()
        logger = app_conf.set_logger("main")

        if app_conf.rcp.manual_query:
            logger.info("Start manual prompting")
            manual_prompt(app_conf.rcp.path, app_conf)
        else:
            logger.info("Start auto prompting")
            all_asked(app_conf.rcp.path, app_conf)
