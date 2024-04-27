import json
import pandas as pd
from faker import Faker
import random
from datetime import datetime

# Initialisation de Faker pour la génération de données fictives
faker = Faker()

# Chargement du modèle JSON
with open('modele.json', 'r') as file:
    modele = json.load(file)

# Fonction pour générer des données en fonction du modèle
def generate_data(model, num_records):
    data = []
    for _ in range(num_records):
        record = {}
        for key, dtype in model.items():
            if dtype == 'int':
                record[key] = faker.random_int(min=1, max=1000)
            elif dtype == 'string':
                record[key] = faker.random_element(elements=["Cœur", "Rein", "Foie", "Poumon"])
            elif dtype == 'date':
                record[key] = faker.date_between(start_date='-10y', end_date='today')
            elif dtype == 'float':
                record[key] = round(random.uniform(0.0, 100.0), 2)
        data.append(record)
    return pd.DataFrame(data)

# Génération des données
df = generate_data(modele, 100)

# Sauvegarde des données dans un fichier CSV
df.to_csv('dataset_factice.csv', index=False)
