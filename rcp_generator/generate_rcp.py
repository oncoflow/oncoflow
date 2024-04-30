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

PDF_SRC = "models/rcp_model.pdf"
PDF_DEST = "files/test.pdf"
DATA_YAML = "models/rcp_data.yaml"
DAY_BETWEEN_1 = datetime.strptime('1/1/2020 1:30 PM', '%m/%d/%Y %I:%M %p')
DAY_BETWEEN_2 = datetime.today()
PACKET = io.BytesIO()
MEMORY = {}
NB_FILES = 10


def random_date(start, end):
    """
    This function will return a random datetime between two datetime 
    objects.
    """
    delta = end - start
    int_delta = (delta.days * 24 * 60 * 60) + delta.seconds
    random_second = randrange(int_delta)
    date = start + timedelta(seconds=random_second)

    return date.strftime("%d-%m-%Y")


def set_elem(element):
    """setting element in calq

    Args:
        element (dict): element data type
    """
    draw_info = deepcopy(element)

    if "name" in element:
        if element["name"] not in MEMORY:
            MEMORY[element["name"]] = {}

    if element["type"] == "list":
        if "zero_value" in element and element["zero_value"]:
            cont = randint(0, 1) == 1
        else:
            cont = True
        if cont:
            number = randint(0, len(draw_info["values"])-1)
            draw_info = element["values"][number]
            draw_info["value"] = "x"
            draw_info["textSize"] = 10

    elif element["type"] == "list_many":
        number = randint(0, len(draw_info["values"])-1)
        draw_info = draw_info["values"][number]
        draw_info["value"] = "x"
        draw_info["textSize"] = 10
        if "number" not in MEMORY[element["name"]]:
            MEMORY[element["name"]].update({"number": 1})
        MEMORY.update(
            {element["name"] + str(MEMORY[element["name"]]["number"] - 1): element["values"][number]["name"]})
        if randint(0, 1) == 1 and MEMORY[element["name"]]["number"] < element["number_max"]:
            if "elem" not in draw_info:
                draw_info["elem"] = []
            element["values"].pop(number)
            draw_info["elem"].append(element)
            MEMORY[element["name"]]["number"] = MEMORY[element["name"]]["number"] + 1

    elif element["type"] == "string":
        if "value_ref" in draw_info:
            print(f"!!!! {element['value_ref']}")
            print(f"!!!! {MEMORY[element['value_ref']]}")
            draw_info["value"] = MEMORY[element["value_ref"]]
        else:
            number = randint(0, len(element["values"])-1)
            draw_info["value"] = element["values"][number]
        draw_info["textSize"] = 7

    elif element["type"] == "date":
        if "after" in draw_info:
            date_begin = datetime.strptime(
                MEMORY[draw_info["after"]]["value"], "%d-%m-%Y")
        else:
            date_begin = DAY_BETWEEN_1
        draw_info["value"] = random_date(date_begin, DAY_BETWEEN_2)
        draw_info["textSize"] = 7

    elif element["type"] == "int":
        draw_info["value"] = str(
            randint(element["between"][0], element["between"][1])) + " " + draw_info["unit"]
        draw_info["textSize"] = 7

    elif element["type"] == "float":
        draw_info["value"] = str(
            round(uniform(float(element["between"][0]), float(element["between"][1])), 2)) + " " + draw_info["unit"]
        draw_info["textSize"] = 7

    elif element["type"] == "lines":
        line_tpl = draw_info["values"]
        draw_info['elem'] = []
        if "number_ref" in draw_info:
            rand = range(MEMORY[draw_info["number_ref"]]["number"])
        else:
            rand = range(
                randint(draw_info["between"][0], draw_info["between"][1]))
        for cpt in rand:
            elem = deepcopy(line_tpl)
            print(f" ---- {elem}")

            for k, l in enumerate(elem["elem"]):
                if "value_ref" in l:
                    elem["elem"][k]["value_ref"] = l["value_ref"] + str(cpt)
                print(f"--------- {l}")
            print(f" ---- {elem}")
            draw_info['elem'].append(elem)
            for k, l in enumerate(line_tpl["elem"]):
                line_tpl["elem"][k]["position"]["y"] = float(
                    l["position"]["y"]) - float(draw_info["height"])
        print(f" --- {draw_info}")

    elif element["type"] == "line":
        print(draw_info)

    if "name" in element and "value" in draw_info:
        MEMORY[element["name"]].update(
            {"value": draw_info["value"], "name": draw_info["name"]})

    return draw_info


def deep_write_calq(can, draw):
    """Deep write with infinite elem

    Args:
        draw (dict): dict of rcp_data
    """
    for elems in draw["elem"]:
        draw = set_elem(elems)
        if "value" in draw:
            can.setFont(psfontname="Helvetica", size=draw["textSize"])
            # 210*mm,297*mm
            # print(f"draw ! {draw}")
            can.drawString(float(draw["position"]
                                 ["x"])*10.0*mm, float(draw
                                                       ["position"]["y"])*10.0*mm, str(draw["value"]))
        if "elem" in draw:
            deep_write_calq(can, draw)


def write_calq(datas):
    """
    write calq
    """
    PACKET = io.BytesIO()
    can = canvas.Canvas(PACKET, pagesize=A4)
    for k, v in datas.items():
        print(f"---- {k}")
        draw = v
        deep_write_calq(can, draw)

    can.save()

    PACKET.seek(0)
    new_pdf = PdfReader(PACKET)

    return new_pdf


def write_pdf(output, dest):
    """
    write to pdf
    """
    output_stream = open(dest, "wb")
    output.write(output_stream)
    output_stream.close()


def load_datas(yaml_file):
    """load yaml datas

    Args:
        yaml_file (string): yaml path

    Returns:
        _type_: dict
    """
    with open(yaml_file, 'r', encoding="UTF-8") as file:
        dict_data = yaml.safe_load(file)
    return dict_data


if __name__ == "__main__":
    datas = load_datas(DATA_YAML)

    for nb in range(NB_FILES):
        existing_pdf = PdfReader(PDF_SRC)
        
        output = PdfWriter()
        for page_nb, page_datas in datas["pages"].items():
            pdf = write_calq(page_datas)

            page = existing_pdf.pages[page_nb-1]
            page.merge_page(pdf.pages[0])
            print(pdf.pages[0])
            output.add_page(page)

        filename, file_extension = os.path.splitext(PDF_DEST)
        write_pdf(output, f"{filename}_{nb}{file_extension}")
        PACKET.truncate(0)
