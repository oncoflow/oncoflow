import re
import json
from PyPDF2 import PdfReader

class PDFParser:
    def __init__(self, file_path):
        self.file_path = file_path
        

    def parse_pdf(self):
        # Open the PDF file
        with open(self.file_path, "rb") as file:
            reader = PdfReader(file)

            # Initialize an empty string to store the concatenated text from all pages
            all_text = ""

            # Loop through all the pages
            for page in reader.pages:
                # Extract the text from the page
                text = page.extract_text()

                # Concatenate the text from this page to the overall string
                all_text += text

        return all_text

    def extract_info(self, all_text):
        # Define regex patterns
        # All pattern
        date_rcp_pattern = r"D\s*a\s*t\s*e\s*d\s*e\s*l\s*a\s*R\s*C\s*P\s*:\s*([\d\s]+/\s*[\d\s]+/\s*[\d\s]+)"
        nom_responsable_pattern = r"N\s*o\s*m\s*d\s*u\s*r\s*e\s*s\s*p\s*o\s*n\s*s\s*a\s*b\s*l\s*e\s*d\s*e\s*l\s*a\s*R\s*C\s*P\s*:\s*([A-Za-z\s\.]+)\.\s*\.\s*\."
        sexe_pattern = r"S\s*e\s*x\s*e\s*M\s*/\s*F\s*/\s*A\s*:\s*([MFA])"
        date_naissance_pattern = r"D\s*a\s*t\s*e\s*d\s*e\s*n\s*a\s*i\s*s\s*s\s*a\s*n\s*c\s*e\s*:\s*([\d\s]+-[\d\s]+-[\d\s]+)"

        dossier_passe_RCP_pattern = r"L\s*e\s* \s*p\s*a\s*t\s*i\s*e\s*n\s*t\s* \s*d\s*o\s*i\s*t\s* \s*ê\s*t\s*r\s*e\s* \s*i\s*n\s*f\s*o\s*r\s*m\s*é\s* \s*q\s*u\s*e\s* \s*s\s*o\s*n\s* \s*d\s*o\s*s\s*s\s*i\s*e\s*r\s* \s*v\s*a\s* \s*p\s*a\s*s\s*s\s*e\s*r\s* \s*e\s*n\s* \s*R\s*C\s*P\s*:\s*(☑)"
        cirrhose_documentee_pattern = r"C\s*i\s*r\s*r\s*h\s*o\s*s\s*e\s* \s*d\s*o\s*c\s*u\s*m\s*e\s*n\s*t\s*é\s*e\s*:\s*(☑\s* \s*o\s*u\s*i\s*|\s*☑\s* \s*n\s*o\s*n)"
        gastroscopie_date_pattern = r"G\s*a\s*s\s*t\s*r\s*o\s*s\s*c\s*o\s*p\s*i\s*e\s*:\s*❑\s* \s*o\s*u\s*i\s*,\s* \s*d\s*a\s*t\s*e\s* \s*d\s*e\s* \s*l\s*a\s* \s*d\s*e\s*r\s*n\s*i\s*è\s*r\s*e\s*:\s*([\d\s]+-\s*[\d\s]+-\s*[\d\s]+)"
        gastroscopie_absent_pattern = r"G\s*a\s*s\s*t\s*r\s*o\s*s\s*c\s*o\s*p\s*i\s*e\s*:\s*(☑\s* \s*n\s*o\s*n)"
        varices_present_pattern = r"V\s*a\s*r\s*i\s*c\s*e\s*s\s* \s*œ\s*s\s*o\s*p\s*h\s*a\s*g\s*i\s*e\s*n\s*n\s*e\s*s\s*/\s*g\s*a\s*s\s*t\s*r\s*i\s*q\s*u\s*e\s*s\s*:\s*❑\s* \s*P\s*r\s*é\s*s\s*e\s*n\s*t\s*e\s*s\s*,\s* \s*g\s*r\s*a\s*d\s*e\s* \s*d\s*e\s*s\s* \s*V\s*O\s*:\s*(.+)"
        ascite_level_pattern = r"A\s*s\s*c\s*i\s*t\s*e\s*:\s*(☑\s* \s*A\s*b\s*s\s*e\s*n\s*t\s*e\s*|\s*☑\s* \s*M\s*o\s*d\s*é\s*r\s*é\s*e\s*|\s*☑\s* \s*A\s*b\s*o\s*n\s*d\s*a\s*n\s*t\s*e)"
        encephalopathy_diagnosis_date_pattern = r"E\s*n\s*c\s*é\s*p\s*h\s*a\s*l\s*o\s*p\s*a\s*t\s*h\s*i\s*e\s*:\s*☑\s* \s*o\s*u\s*i\s*\s*S\s*i\s* \s*o\s*u\s*i\s*,\s* \s*d\s*a\s*t\s*e\s* \s*d\s*u\s* \s*d\s*i\s*a\s*g\s*n\s*o\s*s\s*t\s*i\s*c\s*:\s*([\d\s]+/\s*[\d\s]+/\s*[\d\s]+)"
        alcohol_consumption_current_pattern = r"C\s*o\s*n\s*s\s*o\s*m\s*m\s*a\s*t\s*i\s*o\s*n\s* \s*a\s*l\s*c\s*o\s*o\s*l\s*:\s*☑\s* \s*o\s*u\s*i\s*,\s* \s*é\s*v\s*a\s*l\s*u\s*a\s*t\s*i\s*o\s*n\s* \s*\d*\s* \s*(j\s*o\s*u\s*r\s*s\s*/\s*s\s*e\s*m\s*a\s*i\s*n\s*e\s*s\s*/\s\s*o\s*u\s*i\s*n\s*e\s*e\s*n\s*n\s*e\s*s\s*)\s* \s*p\s*a\s*r\s* \s\s*s\s*e\s*m\s*a\s*i\s*n\s*e\s*s\s* \s*à\s* \s*2\s* \s*v\s*o\s*e\s*r\s*r\s*e\s*s\s* \s*p\s*a\s*r\s* \s\s*s\s*e\s*m\s*a\s*i\s*n\s*e\s*s\s*/\s*d\s*e\s*s\s*s\s*i\s*n\s*e\s*s\s*t\s*i\s*o\s*n\s*/\s*\d*\s* \s*(l\s*i\s*t\s*r\s*e\s*s\s* \s*p\s*a\s*r\s* \s\s*s\s*e\s*m\s*a\s*i\s*n\s*e\s*s\s*/\s*d\s*e\s*s\s*s\s*i\s*n\s*e\s*s\s*t\s*i\s*o\s*n\s*/\s*m\s*o\s*i\s*s\s*)\s*\."
        alcohol_consumption_past_pattern = r"C\s*o\s*n\s*s\s*o\s*m\s*m\s*a\s*t\s*i\s*o\s*n\s* \s*a\s*l\s*c\s*o\s*o\s*l\s*:\s*☑\s* \s*n\s*o\s*n"
        treatment_type_pattern = r"T\s*y\s*p\s*e\s* \s*d\s*'\s*i\s*n\s*t\s*e\s*r\s*v\s*e\s*n\s*t\s*i\s*o\s*n\s*:\s*([\w\s]+)"
        number_of_cures_pattern = r"N\s*o\s*m\s*b\s*r\s*e\s* \s*d\s*e\s* \s*c\s*u\s*r\s*e\s*s\s*:\s*(\d+)"
        last_intervention_date_pattern = r"D\s*a\s*t\s*e\s* \s*d\s*e\s* \s*l\s*a\s* \s*d\s*e\s*r\s*n\s*i\s*è\s*r\s*e\s* \s*i\s*n\s*t\s*e\s*r\s*v\s*e\s*n\s*t\s*i\s*o\s*n\s*:\s*([\d\s]+-\s*[\d\s]+-\s*[\d\s]+)"
        location_of_intervention_pattern = r"L\s*o\s*c\s*a\s*l\s*i\s*s\s*a\s*t\s*i\s*o\s*n\s*:\s*([\w\s]+)"
        size_of_tumor_pattern = r"T\s*a\s*i\s*l\s*l\s*e\s*:\s*([\d\s]*\.\s*[\d\s]+)\s* \s*c\s*m"
        additional_info_pattern = r"I\s*n\s*f\s*o\s*r\s*m\s*a\s*t\s*i\s*o\s*n\s* \s*c\s*o\s*m\s*p\s*l\s*é\s*m\s*e\s*n\s*t\s*a\s*i\s*r\s*e\s*:\s*([\w\s]+)"
        bilirubine_total_pattern = r"B\s*i\s*l\s*i\s*r\s*u\s*b\s*i\s*n\s*e\s* \s*t\s*o\s*t\s*a\s*l\s*e\s*:\s*([\d\s]*\.\s*[\d\s]+)\s* \s*µ\s*m\s*o\s*l\s*/\s*L"
        creatinine_level_pattern = r"C\s*r\s*é\s*a\s*t\s*i\s*n\s*i\s*n\s*e\s*:\s*([\d\s]*\.\s*[\d\s]+)\s* \s*µ\s*m\s*o\s*l\s*/\s*L"
        albumin_level_pattern = r"A\s*l\s*b\s*u\s*m\s*i\s*n\s*e\s*:\s*([\d\s]*\.\s*[\d\s]+)\s* \s*g\s*/\s*L"
        platelets_count_pattern = r"P\s*l\s*a\s*q\s*u\s*e\s*t\s*t\s*e\s*s\s*:\s*([\d\s]*\.\s*[\d\s]+)\s* \s*G\s*/\s*L"
        prothrombin_time_pattern = r"T\s*P\s*:\s*([\d\s]*\.\s*[\d\s]+)%"
        factor_v_level_pattern = r"F\s*a\s*c\s*t\s*e\s*u\s*r\s* \s*V\s*:\s*([\d\s]*\.\s*[\d\s]+)%"
        alpha_foetoprotein_level_pattern = r"A\s*l\s*p\s*h\s*a\s*-\s*f\s*o\s*e\s*t\s*o\s*p\s*r\s*o\s*t\s*e\s*i\s*n\s*e\s*:\s*([\d\s]*\.\s*[\d\s]+)\s* \s*n\s*g\s*/\s*m\s*L"



        # Search for matches using regex patterns
        date_rcp_match = re.search(date_rcp_pattern, all_text)
        nom_responsable_match = re.search(nom_responsable_pattern, all_text)
        sexe_match = re.search(sexe_pattern, all_text)
        date_naissance_match = re.search(date_naissance_pattern, all_text)
        dossier_passe_RCP_match = re.search(dossier_passe_RCP_pattern, all_text)
        cirrhose_documentee_match = re.search(cirrhose_documentee_pattern, all_text)
        gastroscopie_date_match = re.search(gastroscopie_date_pattern, all_text)
        gastroscopie_absent_match = re.search(gastroscopie_absent_pattern, all_text)
        varices_present_match = re.search(varices_present_pattern, all_text)
        ascite_level_match = re.search(ascite_level_pattern, all_text)
        encephalopathy_diagnosis_date_match = re.search(encephalopathy_diagnosis_date_pattern, all_text)
        alcohol_consumption_current_match = re.search(alcohol_consumption_current_pattern, all_text)
        treatment_type_match = re.search(treatment_type_pattern, all_text)
        number_of_cures_match = re.search(number_of_cures_pattern, all_text)
        last_intervention_date_match = re.search(last_intervention_date_pattern, all_text)
        location_of_intervention_match = re.search(location_of_intervention_pattern, all_text)
        size_of_tumor_match = re.search(size_of_tumor_pattern, all_text)
        additional_info_match = re.search(additional_info_pattern, all_text)
        bilirubine_total_match = re.search(bilirubine_total_pattern, all_text)
        creatinine_level_match = re.search(creatinine_level_pattern, all_text)
        albumin_level_match = re.search(albumin_level_pattern, all_text)
        platelets_count_match = re.search(platelets_count_pattern, all_text)
        prothrombin_time_match = re.search(prothrombin_time_pattern, all_text)
        factor_v_level_match = re.search(factor_v_level_pattern, all_text)
        alpha_foetoprotein_level_match = re.search(alpha_foetoprotein_level_pattern, all_text)


        # Extracting and cleaning up the results
        date_rcp = date_rcp_match.group(1).replace(" ", "") if date_rcp_match else None
        nom_responsable = ' '.join(nom_responsable_match.group(1).split()) if nom_responsable_match else None
        sexe = sexe_match.group(1) if sexe_match else None
        date_naissance = date_naissance_match.group(1).replace(" ", "") if date_naissance_match else None
        dossier_passe_RCP = dossier_passe_RCP_match.group(1) if dossier_passe_RCP_match else None
        cirrhose_documentee = cirrhose_documentee_match.group(1).strip() if cirrhose_documentee_match else None
        gastroscopie_date = gastroscopie_date_match.group(1).replace(" ", "") if gastroscopie_date_match else None
        gastroscopie_absent = gastroscopie_absent_match.group(1) if gastroscopie_absent_match else None
        varices_present = varices_present_match.group(1).strip() if varices_present_match else None
        ascite_level = ascite_level_match.group(1).strip() if ascite_level_match else None
        encephalopathy_diagnosis_date = encephalopathy_diagnosis_date_match.group(1).replace(" ", "") if encephalopathy_diagnosis_date_match else None
        alcohol_consumption_current = alcohol_consumption_current_match.group(1).replace(" ", "") if alcohol_consumption_current_match else None
        treatment_type = treatment_type_match.group(1).strip() if treatment_type_match else None
        number_of_cures = number_of_cures_match.group(1) if number_of_cures_match else None
        last_intervention_date = last_intervention_date_match.group(1).replace(" ", "") if last_intervention_date_match else None
        location_of_intervention = location_of_intervention_match.group(1) if location_of_intervention_match else None
        size_of_tumor = size_of_tumor_match.group(1).strip() if size_of_tumor_match else None
        additional_info = additional_info_match.group(1).strip() if additional_info_match else None
        bilirubine_total = bilirubine_total_match.group(1).strip() if bilirubine_total_match else None
        creatinine_level = creatinine_level_match.group(1).strip() if creatinine_level_match else None
        albumin_level = albumin_level_match.group(1).strip() if albumin_level_match else None
        platelets_count = platelets_count_match.group(1).strip() if platelets_count_match else None
        prothrombin_time = prothrombin_time_match.group(1).strip() if prothrombin_time_match else None
        factor_v_level = factor_v_level_match.group(1).strip() if factor_v_level_match else None
        alpha_foetoprotein_level = alpha_foetoprotein_level_match.group(1).strip() if alpha_foetoprotein_level_match else None


        return [
    {
        "date": {
            "date_rcp": date_rcp,
            "nom_responsable": nom_responsable,
            "membres": {
                "hepatogastroenterologues": [],
                "oncologues": [],
                "radiologues_interventionnels": [],
                "chirurgiens": [],
                "radiotherapeutes": [],
                "anatomopathologiste": [],
                "radiologue_diagnostique": [],
                "infirmiers": []
            },
            "patient": {
                "sexe": sexe,  
                "date_naissance": date_naissance,
                "coordonnees_medecin_traitant": "string",
                "coordonnees_medecin_adresseur": "string",
                "dossier_passe_RCP": dossier_passe_RCP
            },
            "motif": {
                "1ere_presentation": "bool",
                "dossier_deja_discute_le": "string",
                "motif_presentation": {
                    "decision_traitement": "bool",
                    "avis_diagnostique": "bool",
                    "ajustement_therapeutique": "bool",
                    "surveillance_post_traitement": "bool"
                }
            },
            "atcd": {
                "diabete_cardiovasculaire_comorbidite": "string",
                "traitement_courant": "string"
            }
        },
        "Cirrhose_documentee": cirrhose_documentee,
        "arguments": {
            "clinique": "bool",
            "marqueurs_non_invasifs": "bool",
            "imagerie": "bool",
            "biopsie": "bool"
        },
        "gastroscopie": {
            "oui_date_de_la_derniere": gastroscopie_date,
            "non": gastroscopie_absent,
            "Varices_oesophagiennes_gastriques": {
                "Non_recherchees": "bool",
                "Absentes": "bool",
                "Presentes_grade_des_VO": "string"
            }
        },
        "ascite": {
            "Absente": "bool",
            "Moderee": "bool",
            "Abondante": "bool",
            "Pas_ascite_clinique_mais_visible_en_imagerie": "bool",
            "Pas_ascite_actuellement_mais_ATCD_d_ascite": "bool"
        },
        "encephalopathie": {
            "oui": "bool",
            "non": "bool",
            "Si_oui_date_du_diagnostic": encephalopathy_diagnosis_date
        },
        "alcool": {
            "OUI_depuis_combien_de_temps": "string",
            "NON_consommation_actuelle_d_alcool": alcohol_consumption_current
        },
        "histoire_de_la_maladie": {
            "date_du_diagnostic": "string",
            "Prouve_histologiquement": "bool",
            "traitements_locoregionaux": {
                "intervention_1": {
                    "Type_intervention": "string",
                    "Nombre_de_cures": "int",
                    "Date_derniere_intervention": "string",
                    "Localisation": "string",
                    "Taille": "float",
                    "Information_complementaire": "string"
                },
                "intervention_2": {
                    "Type_intervention": "string",
                    "Nombre_de_cures": "int",
                    "Date_derniere_intervention": "string",
                    "Localisation": "string",
                    "Taille": "float",
                    "Information_complementaire": "string"
                },
                "intervention_3": {
                    "Type_intervention": "string",
                    "Nombre_de_cures": "int",
                    "Date_derniere_intervention": "string",
                    "Localisation": "string",
                    "Taille": "float",
                    "Information_complementaire": "string"
                }
            },
            "traitements_systemiques": [
                {
                    "Nombre_de_lignes": "int",
                    "traitements": [
                        {
                            "type": "string",
                            "Date_de_debut": "string",
                            "Date_de_fin": "string",
                            "Motif_arret": "string"
                        }
                    ],
                    "Soins_de_confort": "bool",
                    "Si_oui_preciser": "string"
                }
            ]
        },
        "imc": {
            "IMC": "float",
            "ECOG": "float"
        },
        "Donnees_Biologique_moins_de_4_semaines": {
            "Bilirubine_totale": {
                "value": bilirubine_total,
                "unit": "µmol/L"
            },
            "Creatinine": {
                "value": creatinine_level,
                "unit": "µmol/L"
            },
            "Albumine": {
                "value": albumin_level,
                "unit": "g/L"
            },
            "Plaquettes": {
                "value": platelets_count,
                "unit": "G/L"
            },
            "TP": {
                "pourcentage": prothrombin_time,
                "AVK_ou_AOD": "bool"
            },
            "Facteur_V": {
                "value": factor_v_level,
                "unit": "%"
            },
            "Alpha_foetoproteine": {
                "value": alpha_foetoprotein_level,
                "unit": "ng/mL"
            }
        },
        "Souhait_prise_en_charge_post_rcp": {
            "accord": "bool",
            "souhait_patient": "string",
            "eligibilite": "bool"
        },
        "Information_patient_post_RCP": {
            "accord_pour_prévenir_prise_en_charge": "bool",
            "comment_informer": "string"
        },
        "Decision_prise_en_charge": {
            "Transplantation": "bool",
            "Radio_embolisation": "bool",
            "Exerese_Chirurgie": {
                "value": "bool",
                "precision": "string"
            },
            "Chimio_Embolisation": "bool",
            "Traitement_systemique": "bool",
            "Essaie_therapeutique": "bool",
            "Radiotherapie": "bool",
            "Soins_de_confort": "bool",
            "Precision_hierarchisation_si_propositions": "string"
        }
    }
]
    
    def create_json(self, data):
    # Convert the data to JSON format
        json_data = json.dumps(data, indent=4)  # Pretty print with indentation of 4 spaces

        # Write the JSON data to a file
        with open("output.json", "w") as json_file:
            json_file.write(json_data)
        
        return json_data



