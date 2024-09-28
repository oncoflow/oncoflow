import edsnlp
import fitz  # import PyMuPDF...for whatever reason it is called fitz
import random
import datetime
from faker import Faker
from dateutil import parser
import re
import csv
import pandas as pd

delta_days = random.randint(-300, 10)

def flags_decomposer(flags):
    """Make font flags human readable."""
    l = []
    if flags & 2 ** 0:
        l.append("superscript")
    if flags & 2 ** 1:
        l.append("italic")
    if flags & 2 ** 2:
        l.append("serifed")
    else:
        l.append("sans")
    if flags & 2 ** 3:
        l.append("monospaced")
    else:
        l.append("proportional")
    if flags & 2 ** 4:
        l.append("bold")
    return ", ".join(l)

# Initialisation de Faker en français
fake = Faker('fr_FR')

# Bibliothèque pour stocker les correspondances de pseudonymes
pseudonym_library = {
    'first_names': {},
    'last_names': {},
    'full_names': {},
    'locations': {},
    'phones': {},
    'zips': {}
}

datelist = []

def generate_random_mail(fake_names):
    # Generate a random email address
    first_names, last_name = pick_fake_name(fake_names)
    first_name = make_first_name(first_names, "Nn")
    last_name = make_last_name(last_name, "Nn")
    first_name = re.sub(f"[{re.escape(string.punctuation) + ' '}]", "", first_name)
    last_name = re.sub(f"[{re.escape(string.punctuation) + ' '}]", "", last_name)
    domain = random.choice(mail_domains)

    # Different types of email formats
    formats = [
        "{first_name}{num1}{sp}{sep}{sp}{last_name}{num2}{sp}@{sp}{domain}",
        "{last_name}{num1}{sp}{sep}{sp}{first_name}{num2}{sp}@{sp}{domain}",
    ]
    sp = "" if random.randint(0, 10) else " "

    # Choose a random format from the formats list
    fake_mail = random.choice(formats).format(
        first_name=first_name.lower()[: random.randint(1, len(first_name))],
        last_name=last_name.lower()[: random.randint(1, len(last_name))],
        domain=domain,
        sep=random.choice(["-", ".", "_", "", ""]),
        num1=random.choice(["", "", random.randint(0, 99)]),
        num2=random.choice(["", "", random.randint(0, 99)]),
        sp=sp,
    )

    if not sp:
        fake_mail = fake_mail.replace(" ", "")
    fake_mail = fake_mail.strip()
    return fake_mail

# Fonction pour générer un pseudonyme pour un prénom
def get_pseudonym_first_name(original_first_name):
    if original_first_name not in pseudonym_library['first_names']:
        pseudonym_library['first_names'][original_first_name] = fake.first_name()
    return pseudonym_library['first_names'][original_first_name]

# Fonction pour générer un pseudonyme pour un nom de famille
def get_pseudonym_last_name(original_last_name):
    if original_last_name not in pseudonym_library['last_names']:
        pseudonym_library['last_names'][original_last_name] = fake.last_name()
    return pseudonym_library['last_names'][original_last_name]

# Fonction pour générer un pseudonyme pour un nom complet
def get_pseudonym_full_name(original_full_name):
    if original_full_name not in pseudonym_library['full_names']:
        # print(original_full_name)
        names = original_full_name.split()
        pseudonym_first_name = get_pseudonym_first_name(" ".join(names[:-1]))
        pseudonym_last_name = get_pseudonym_last_name(names[-1])
        pseudonym_library['full_names'][original_full_name] = f"{pseudonym_first_name} {pseudonym_last_name}"
    return pseudonym_library['full_names'][original_full_name]

# Fonction pour générer un pseudonyme pour un lieu
def get_pseudonym_location(original_location):
    if original_location not in pseudonym_library['locations']:
        pseudonym_library['locations'][original_location] = fake.city()
    return pseudonym_library['locations'][original_location]

# Détection des formats de date
date_patterns = {
    "%d/%m/%Y": re.compile(r"^\d{1,2}/\d{1,2}/\d{4}\s*$"),
    "%d/%m/%Y": re.compile(r"^\d{1,2}/\d{1,2}/\d{2}\s*$"),
    "%d.%m.%Y": re.compile(r"^\d{1,2}\.\d{1,2}/\d{4}\s*$"),
    "%d.%m.%Y": re.compile(r"^\d{1,2}\.\d{1,2}/\d{2}\s*$"),
    "%B %Y": re.compile(r"^[a-zA-Zéâ]+ \d{4}\s*$"),
    "%d/%m": re.compile(r"^\d{1,2}/\d{1,2}\s*$"),

    "%b": re.compile(r"^[a-zA-Zéâ]{3,}\s*$"),
    "%Y": re.compile(r"^\d{4}\s*$")
}


def detect_date_format(date_str):
    for date_format, pattern in date_patterns.items():
        if pattern.match(date_str):
            return date_format
    return None

# Fonction pour convertir des chaînes de caractères en objets datetime
def parse_date(date_str):
    date_format = detect_date_format(date_str)
    if date_format:
        try:
            # print("RE", date_str, date_format, date_patterns[date_format])
            datelist.append([date_str,datetime.datetime.strptime(date_str, date_format).date(), date_format, date_patterns[date_format]])
            return datetime.datetime.strptime(date_str, date_format).date(), date_format
        except ValueError:
            pass
    try:
        # print("PARSER", date_str)
        datelist.append([date_str,parser.parse(date_str).date(), "PARSER", "PARSER"])
        return parser.parse(date_str).date(), "%d/%m/%Y"
    except (ValueError, TypeError):
        # print ("ERROR", date_str)
        datelist.append([date_str,"PARSER", "PARSER", "PARSER"])
        return date_str, None  # Retourner None si aucun format ne correspond


# Fonction pour générer un pseudonyme pour une date
def get_pseudonymized_date(original_date_str):
    
    original_date, date_format = parse_date(original_date_str)
    if date_format is None:
        return str(original_date_str) # Retourner la chaîne originale si la conversion échoue

    pseudonymized_date = original_date + datetime.timedelta(days=delta_days)
    return pseudonymized_date.strftime(date_format)

# Fonction pour générer un pseudonyme pour un numéro de téléphone
def get_pseudonymized_phone(original_phone):
    # Generating a random country code between 1 and 99
    if random.randint(0, 2):
        ctry = 33
    else:
        ctry = random.randint(11, 99)

    if random.randint(0, 2):
        ctry = f"+{ctry:02}"
    else:
        ctry = f"({ctry:02})"

    # Generating a 10-digit phone number
    n = "".join(
        [" " if random.randint(0, 2) else "0"]
        + [str(random.randint(1 if i == 2 else 0, 7)) for i in range(9)]
    )

    # Different types of separators
    s1 = random.choice([" ", "-", ".", "", "", ""])
    s2 = random.choice([" ", ""])

    # Combining country code and number with different formats
    formats = [
        f"0{n[1:2]}{s1}{n[2:4]}{s1}{n[4:6]}{s1}{n[6:8]}{s1}{n[8:10]}",
        f"0{n[1:2]}{s1}{n[2:4]}{s1}{n[4:6]}{s1}{n[6:8]}{s1}{n[8:10]}",
        f"{ctry}{s2}{n[:2].strip()}{s2}{n[2:4]}{s2}{n[4:6]}{s2}{n[6:8]}{s2}{n[8:10]}",
    ]

    # Choosing a random format from the formats list
    fake_phone = random.choice(formats)

    if not random.randint(0, 6):
        fake_phone = " ".join([char for char in fake_phone if char != " "])

    return fake_phone


def generate_french_zipcode():
    # Define metropolitan department codes
    metro_departments = list(range(1, 96))
    metro_departments.remove(20)  # Removing 20 as Corsica is handled separately
    dom_departments = [971, 972, 973, 974, 976]
    corsica_departments = ["2A", "2B"]

    # Randomly choose a department
    choice = random.choice([*(("metro",) * 5), "dom", "corsica"])

    if choice == "metro":
        department = random.choice(metro_departments)
        zipcode = f"{department:02d}{random.randint(0, 999):03d}"

    elif choice == "dom":
        department = random.choice(dom_departments)
        zipcode = f"{department}{random.randint(0, 99):02d}"

    else:  # Corsica
        department = random.choice(corsica_departments)
        zipcode = f"{department}{random.randint(0, 999):03d}"

    # Adding space in the middle for variation
    if random.choice([True, False]):
        zipcode = f"{zipcode[:2]} {zipcode[2:]}"

    return zipcode
# Fonction pour générer un pseudonyme pour un code postal
def get_pseudonymized_zip(original_zip):
    if original_zip not in pseudonym_library['zips']:
        pseudonymized_zip = generate_french_zipcode()
        pseudonym_library['zips'][original_zip] = pseudonymized_zip
    return pseudonym_library['zips'][original_zip]

# Fonction pour détecter le type de nom et respect de la casse
def get_pseudonymized_name(old_name):
    if ' ' in old_name:
        return get_pseudonym_full_name(old_name)
    elif old_name.istitle():
        return get_pseudonym_first_name(old_name)
    elif old_name.isupper():
        return get_pseudonym_last_name(old_name)
    else:
        return get_pseudonym_last_name(old_name)

# Fonction unique pour pseudonymiser un item en fonction de son type
def get_pseudonymized_item(old_item, item_type):
    if item_type == 'NOM':
        return str(get_pseudonymized_name(old_item))
    elif item_type == 'PRENOM':
        return str(get_pseudonym_first_name(old_item))
    elif item_type == 'ADRESSE':
        return str(get_pseudonym_location(old_item))
    elif item_type == 'DATE':
        return str(get_pseudonymized_date(old_item))
    elif item_type == 'TEL':
        return str(get_pseudonymized_phone(old_item))
    elif item_type == 'ZIP':
        return str(get_pseudonymized_zip(old_item))
    else:
        return str(old_item)



docpdf = fitz.open('sandpit\data\pdfs\SINGLE.pdf')  # the file with the text you want to change

# docpdf.delete_page(0)


nlp = edsnlp.blank("eds")

# Some text cleaning
nlp.add_pipe("eds.normalizer")

# Various simple rules
nlp.add_pipe(
    "eds_pseudo.simple_rules",
    config={"pattern_keys": ["TEL", "MAIL", "SECU", "PERSON"]},
)

# Address detection
nlp.add_pipe("eds_pseudo.addresses")

# Date detection
nlp.add_pipe("eds_pseudo.dates")

# Contextual rules (requires a dict of info about the patient)
nlp.add_pipe("eds_pseudo.context")


for page in docpdf:

    text = page.get_text()
    classicalidentifiers = [  'NIORT' , 'POITIERS' , 'GEORGES RENON', 'CHU LA MILETRIE', '3C Vienne, Nord Deux-Sèvres' , 'Châtellerault', 'CHATELLERAULT']
    for identifier in classicalidentifiers:
        found = page.search_for(identifier)  # list of rectangles where to replace
     
        for item in found:
          
            
            page.add_redact_annot(item, '' )  # create redaction for text
            page.apply_redactions()  # apply the redaction now
            page.insert_text(item.bl - (0, 2), text=get_pseudonym_location(identifier), fontsize=9.29688, fontname='helv')

    doctext = nlp(
    text
)
   
    for ent in doctext.ents:
        search_term = str(ent)

        
      
        found = page.search_for(search_term)  # list of rectangles where to replace
        for item in found:
            

            page.add_redact_annot(item, '' )  # create redaction for text
            page.apply_redactions()  # apply the redaction now

            page.insert_text(item.bl - (0, 2), text=get_pseudonymized_item(search_term, ent.label_), fontsize=9.29688, fontname='helv')


dfdate = pd.DataFrame(datelist, columns=["date_str","date_time","format","re"])
dfdate.to_csv("list.csv")

docpdf.save("pdfANNO4.pdf")

