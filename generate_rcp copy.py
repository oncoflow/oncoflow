"""
Generate RCP files randomly
"""
from random import randrange, randint, uniform
from datetime import timedelta, datetime
import io
import os
from copy import deepcopy
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, mm
import yaml

from docx import Document


document = Document('models/FACIL - Trame de fiche RCP CHC.docx')
document.