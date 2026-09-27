import unittest
from unittest.mock import MagicMock, patch
from src.application.ressources import Ressources


class TestRessources(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock()
        self.mock_config.rcp.additional_path = "/mock/path/to/ressources"
        self.ressources_manager = Ressources(self.mock_config)

    @patch("src.application.ressources.Path.exists")
    @patch("src.application.ressources.Path.iterdir")
    def test_list_ressources(self, mock_iterdir, mock_exists):
        # Case 1: Directory does not exist
        mock_exists.return_value = False
        self.assertEqual(self.ressources_manager.list_ressources(), [])

        # Case 2: Directory exists with files
        mock_exists.return_value = True

        file1 = MagicMock()
        file1.is_file.return_value = True
        file1.name = "TNCDPANCREAS.pdf"

        file2 = MagicMock()
        file2.is_file.return_value = True
        file2.name = "TNCDOESOPHAGE.pdf"

        hidden_file = MagicMock()
        hidden_file.is_file.return_value = True
        hidden_file.name = ".gitignore"

        dir1 = MagicMock()
        dir1.is_file.return_value = False
        dir1.name = "some_directory"

        mock_iterdir.return_value = [file1, file2, hidden_file, dir1]

        # Should only list normal files, sorted alphabetically
        expected = ["TNCDOESOPHAGE.pdf", "TNCDPANCREAS.pdf"]
        self.assertEqual(self.ressources_manager.list_ressources(), expected)

    @patch("src.application.ressources.DocumentReader")
    def test_is_indexed(self, mock_document_reader_cls):
        mock_reader = MagicMock()
        mock_document_reader_cls.return_value = mock_reader

        # Case 1: Indexed returns True
        mock_reader.is_indexed.return_value = True
        self.assertTrue(self.ressources_manager.is_indexed("TNCDPANCREAS.pdf"))
        mock_document_reader_cls.assert_called_with(
            self.mock_config, document="TNCDPANCREAS.pdf", document_type="ressource"
        )

        # Case 2: Indexed returns False
        mock_reader.is_indexed.return_value = False
        self.assertFalse(self.ressources_manager.is_indexed("TNCDPANCREAS.pdf"))

        # Case 3: Exception raised, should catch and return False
        mock_reader.is_indexed.side_effect = Exception("DB Connection Error")
        self.assertFalse(self.ressources_manager.is_indexed("TNCDPANCREAS.pdf"))

    @patch("src.application.ressources.DocumentReader")
    def test_index_ressource(self, mock_document_reader_cls):
        mock_reader = MagicMock()
        mock_document_reader_cls.return_value = mock_reader

        self.ressources_manager.index_ressource("TNCDPANCREAS.pdf")
        mock_document_reader_cls.assert_called_with(
            self.mock_config, document="TNCDPANCREAS.pdf", document_type="ressource"
        )
        mock_reader.read_document.assert_called_once()
