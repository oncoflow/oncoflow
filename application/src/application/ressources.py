from pathlib import Path
from src.application.config import AppConfig
from src.application.reader import DocumentReader


class Ressources:
    """
    Service class to handle clinical / scientific reference resources.
    Manages listing resource files from the filesystem and inspecting/updating
    their index status within the vectorial database.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.directory = Path(config.rcp.additional_path)

    def list_ressources(self) -> list[str]:
        """
        List all available resource filenames in the additional path directory,
        excluding hidden files/directories.
        """
        if not self.directory.exists():
            return []
        return sorted(
            [
                f.name
                for f in self.directory.iterdir()
                if f.is_file() and not f.name.startswith(".")
            ]
        )

    def is_indexed(self, ressource: str) -> bool:
        """
        Check if a given resource has been indexed in the vector database.
        """
        try:
            reader = DocumentReader(
                self.config, document=ressource, document_type="ressource"
            )
            return reader.is_indexed()
        except Exception:
            return False

    def index_ressource(self, ressource: str) -> None:
        """
        Load, split, and index the selected resource into the vector database.
        """
        reader = DocumentReader(
            self.config, document=ressource, document_type="ressource"
        )
        reader.read_document()
