import os
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth


def main():
    print("--- Oncoflow : Ajouter un nouvel utilisateur ---")

    username = input("Nom d'utilisateur (username) : ").strip()
    if not username:
        print("Erreur : Le nom d'utilisateur ne peut pas être vide.")
        return

    name = input("Nom complet (ex: Dr. Martin) : ").strip()
    email = input("Adresse e-mail : ").strip()
    password = input("Mot de passe : ").strip()

    if not password:
        print("Erreur : Le mot de passe ne peut pas être vide.")
        return

    # Hachage du mot de passe
    print("Génération du hash sécurisé...")
    hashed_password = stauth.Hasher.hash(password)

    # Détermination du chemin du fichier de configuration via AppConfig
    try:
        import sys

        script_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, os.path.abspath(os.path.join(script_dir, "..")))
        from src.application.config import AppConfig

        app_config = AppConfig()
        config_path = app_config.auth_config_path
    except Exception:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.abspath(
            os.path.join(script_dir, "..", "config", "auth_config.yaml")
        )

    if not os.path.exists(config_path):
        print(f"Erreur : Le fichier de configuration {config_path} n'existe pas.")
        return

    # Lecture de la config existante
    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.load(file, Loader=SafeLoader)

    # Initialisation des structures si nécessaire
    if "credentials" not in config or config["credentials"] is None:
        config["credentials"] = {}
    if (
        "usernames" not in config["credentials"]
        or config["credentials"]["usernames"] is None
    ):
        config["credentials"]["usernames"] = {}

    # Ajout/Mise à jour de l'utilisateur
    config["credentials"]["usernames"][username] = {
        "email": email,
        "name": name,
        "password": hashed_password,
    }

    # Écriture dans le fichier config
    with open(config_path, "w", encoding="utf-8") as file:
        yaml.dump(
            config, file, default_flow_style=False, sort_keys=False, allow_unicode=True
        )

    print(
        f"\nSuccès ! L'utilisateur '{username}' a été ajouté/mis à jour dans {config_path}."
    )


if __name__ == "__main__":
    main()
