import os
import sys

# Redirection vers add_user.py pour ajouter l'utilisateur directement
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from add_user import main  # noqa: E402

if __name__ == "__main__":
    main()
