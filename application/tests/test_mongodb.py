import unittest
from unittest.mock import MagicMock, patch

from src.infrastructure.documents.mongodb import Mongodb, close_all_mongo_clients


class TestMongodbDocumentStore(unittest.TestCase):
    def setUp(self):
        close_all_mongo_clients()
        # Configure a mock config object
        self.mock_config = MagicMock()
        self.mock_config.mongodb.host = "127.0.0.1"
        self.mock_config.mongodb.port = "27017"
        self.mock_config.mongodb.user = "root"
        self.mock_config.mongodb.password = "password"
        self.mock_config.mongodb.database = "TestOncoflow"

        # Mock logger
        self.mock_logger = MagicMock()
        self.mock_config.set_logger.return_value = self.mock_logger

    def tearDown(self):
        close_all_mongo_clients()

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_init_success(self, mock_mongo_client_cls):
        mock_client = mock_mongo_client_cls.return_value
        db = Mongodb(self.mock_config)

        # Asserts connection string & db name
        expected_conn_str = "mongodb://root:password@127.0.0.1:27017"
        mock_mongo_client_cls.assert_called_once_with(expected_conn_str)
        self.assertEqual(db.database, mock_client[self.mock_config.mongodb.database])
        self.mock_logger.info.assert_called_with("Succefully init")

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_close(self, mock_mongo_client_cls):
        mock_client = mock_mongo_client_cls.return_value
        db = Mongodb(self.mock_config)
        db.prepare_insert_doc("rcp_info", {"file": "PDF1.pdf"})
        db.close()
        self.assertEqual(db.documents_to_insert, {})
        mock_client.close.assert_not_called()
        close_all_mongo_clients()
        mock_client.close.assert_called_once()

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_set_uniq_index(self, mock_mongo_client_cls):
        db = Mongodb(self.mock_config)

        mock_collection = MagicMock()
        db.database.__getitem__.return_value = mock_collection

        db.set_uniq_index("rcp_info", "file")
        db.database.__getitem__.assert_called_with("rcp_info")
        mock_collection.create_index.assert_called_once_with("file", unique=True)

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_get_document(self, mock_mongo_client_cls):
        db = Mongodb(self.mock_config)

        mock_collection = MagicMock()
        db.database.__getitem__.return_value = mock_collection
        mock_collection.find_one.return_value = {"file": "PDF1.pdf"}

        result = db.get_document("rcp_info", {"file": "PDF1.pdf"})
        self.assertEqual(result, {"file": "PDF1.pdf"})
        mock_collection.find_one.assert_called_once_with({"file": "PDF1.pdf"})

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_update_doc(self, mock_mongo_client_cls):
        db = Mongodb(self.mock_config)

        mock_collection = MagicMock()
        db.database.__getitem__.return_value = mock_collection

        db.update_doc("rcp_info", {"file": "PDF1.pdf"}, {"age": 67})
        mock_collection.update_one.assert_called_once_with(
            {"file": "PDF1.pdf"}, {"$set": {"age": 67}}, upsert=True
        )

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_insert_docs(self, mock_mongo_client_cls):
        db = Mongodb(self.mock_config)

        mock_collection = MagicMock()
        db.database.__getitem__.return_value = mock_collection

        # Prepare and insert doc
        db.prepare_insert_doc("rcp_info", {"file": "PDF1.pdf"})
        db.insert_docs()

        mock_collection.insert_many.assert_called_once_with([{"file": "PDF1.pdf"}])
        self.assertEqual(db.documents_to_insert, {})

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_delete_docs(self, mock_mongo_client_cls):
        db = Mongodb(self.mock_config)

        mock_collection1 = MagicMock()
        mock_collection2 = MagicMock()
        db.database.__getitem__.side_effect = [mock_collection1, mock_collection2]

        db.delete_docs(["rcp_info", "rcp_metadata"], {"file": "PDF1.pdf"})
        mock_collection1.delete_many.assert_called_once_with({"file": "PDF1.pdf"})
        mock_collection2.delete_many.assert_called_once_with({"file": "PDF1.pdf"})

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_get_document_cache(self, mock_mongo_client_cls):
        db = Mongodb(self.mock_config)
        mock_collection = MagicMock()
        db.database.__getitem__.return_value = mock_collection
        mock_collection.find_one.return_value = {
            "hash": "abc123hash",
            "file": "patient.pdf",
            "markdown": "# Patient Report",
        }

        result = db.get_document_cache("abc123hash")
        mock_collection.find_one.assert_called_once_with({"hash": "abc123hash"})
        self.assertEqual(result["file"], "patient.pdf")
        self.assertEqual(result["markdown"], "# Patient Report")

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_save_document_cache(self, mock_mongo_client_cls):
        db = Mongodb(self.mock_config)
        mock_collection = MagicMock()
        db.database.__getitem__.return_value = mock_collection

        db.save_document_cache(
            file_hash="abc123hash",
            file_name="patient.pdf",
            markdown="# Patient Report",
            document_type="mtd",
        )

        mock_collection.create_index.assert_called_once_with("hash", unique=True)
        mock_collection.update_one.assert_called_once_with(
            {"hash": "abc123hash"},
            {
                "$set": {
                    "hash": "abc123hash",
                    "file": "patient.pdf",
                    "document_type": "mtd",
                    "markdown": "# Patient Report",
                }
            },
            upsert=True,
        )

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_delete_document_cache(self, mock_mongo_client_cls):
        db = Mongodb(self.mock_config)
        mock_collection = MagicMock()
        db.database.__getitem__.return_value = mock_collection

        # Delete by file name
        db.delete_document_cache(file_name="patient.pdf")
        mock_collection.delete_many.assert_called_with({"file": "patient.pdf"})

        # Delete by file hash
        db.delete_document_cache(file_hash="abc123hash")
        mock_collection.delete_many.assert_called_with({"hash": "abc123hash"})

        # Delete all requires explicit clear_all=True
        with self.assertRaises(ValueError):
            db.delete_document_cache()
        db.delete_document_cache(clear_all=True)
        mock_collection.delete_many.assert_called_with({})

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_patient_crud_methods(self, mock_mongo_client_cls):
        db = Mongodb(self.mock_config)
        mock_collection = MagicMock()
        db.database.__getitem__.return_value = mock_collection

        # upsert_patient
        mock_collection.find_one.return_value = {
            "patient_id": "jean_dupont_1960-05-12",
            "files": ["rcp1.pdf"],
        }
        res = db.upsert_patient(
            {
                "patient_id": "jean_dupont_1960-05-12",
                "first_name": "Jean",
                "last_name": "Dupont",
                "files": ["rcp2.pdf"],
            },
            filename="rcp2.pdf",
        )
        mock_collection.create_index.assert_called_with("patient_id", unique=True)
        mock_collection.update_one.assert_called_once()
        self.assertEqual(res["patient_id"], "jean_dupont_1960-05-12")

        # get_patient
        db.get_patient("jean_dupont_1960-05-12")
        mock_collection.find_one.assert_called_with(
            {"patient_id": "jean_dupont_1960-05-12"}
        )

        # remove_file_from_patient when 2 files exist -> updates files list
        mock_collection.find.return_value = [
            {"patient_id": "jean_dupont_1960-05-12", "files": ["rcp1.pdf", "rcp2.pdf"]}
        ]
        db.remove_file_from_patient("rcp1.pdf")
        mock_collection.update_one.assert_called_with(
            {"patient_id": "jean_dupont_1960-05-12"},
            {"$set": {"files": ["rcp2.pdf"]}},
            upsert=True,
        )

        # remove_file_from_patient when last file is removed -> deletes patient doc
        mock_collection.find.return_value = [
            {"patient_id": "jean_dupont_1960-05-12", "files": ["rcp2.pdf"]}
        ]
        db.remove_file_from_patient("rcp2.pdf")
        mock_collection.delete_many.assert_called_once_with(
            {"patient_id": "jean_dupont_1960-05-12"}
        )

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_bug_report_crud_methods(self, mock_mongo_client_cls):
        from datetime import datetime
        from src.domain.bug_report import BugCategory, BugSeverity, BugStatus

        db = Mongodb(self.mock_config)
        mock_collection = MagicMock()
        db.database.__getitem__.return_value = mock_collection

        # create_bug_report
        saved = db.create_bug_report(
            {
                "bug_id": "bug_12345678",
                "title": "Erreur d'extraction date RCP",
                "description": "La date RCP n'est pas extraite sur PDF1.pdf",
                "category": BugCategory.ai_extraction,
                "severity": BugSeverity.high,
                "status": BugStatus.open,
                "page": "Dossier Patient",
                "patient_id": "jean_dupont_1960_05_12",
                "rcp_file": "PDF1.pdf",
                "reporter": "Dr. Martin",
            }
        )
        mock_collection.create_index.assert_called_with("bug_id", unique=True)
        mock_collection.update_one.assert_called_once()
        self.assertEqual(saved["bug_id"], "bug_12345678")
        self.assertEqual(saved["category"], "ai_extraction")
        self.assertEqual(saved["severity"], "high")
        self.assertEqual(saved["status"], "open")

        # get_bug_report
        mock_collection.find_one.return_value = saved
        fetched = db.get_bug_report("bug_12345678")
        mock_collection.find_one.assert_called_with({"bug_id": "bug_12345678"})
        self.assertEqual(fetched["title"], "Erreur d'extraction date RCP")

        # get_all_bug_reports sorts newest first
        older = {**saved, "bug_id": "bug_old", "created_at": datetime(2026, 1, 1)}
        newer = {**saved, "bug_id": "bug_new", "created_at": datetime(2026, 5, 1)}
        mock_collection.find.return_value = [older, newer]
        all_bugs = db.get_all_bug_reports()
        self.assertEqual([b["bug_id"] for b in all_bugs], ["bug_new", "bug_old"])

        # update_bug_report
        mock_collection.find_one.return_value = {**saved, "status": "resolved"}
        updated = db.update_bug_report("bug_12345678", {"status": BugStatus.resolved})
        self.assertEqual(updated["status"], "resolved")

        # delete_bug_report
        db.delete_bug_report("bug_12345678")
        mock_collection.delete_many.assert_called_once_with({"bug_id": "bug_12345678"})

    @patch("scripts.get_bugs.Mongodb")
    @patch("scripts.get_bugs.AppConfig")
    def test_get_bugs_cli_script(self, mock_app_config_cls, mock_mongodb_cls):
        from datetime import datetime
        from scripts.get_bugs import format_bugs_report, main

        sample_bug = {
            "bug_id": "bug_abcd1234",
            "title": "Affichage lent des cartes",
            "description": "Le chargement initial prend 4 secondes",
            "category": "ui",
            "severity": "medium",
            "status": "open",
            "page": "Dossiers Patients",
            "patient_id": None,
            "rcp_file": "PDF1.pdf",
            "steps_to_reproduce": "Ouvrir la page d'accueil",
            "reporter": "admin",
            "created_at": datetime(2026, 10, 18, 17, 0),
        }

        formatted = format_bugs_report([sample_bug])
        self.assertIn("bug_abcd1234", formatted)
        self.assertIn("Affichage lent des cartes", formatted)
        self.assertIn("PDF1.pdf", formatted)

        mock_db = mock_mongodb_cls.return_value
        mock_db.get_all_bug_reports.return_value = [sample_bug]

        exit_code = main(["--status", "open"])
        self.assertEqual(exit_code, 0)
        mock_db.get_all_bug_reports.assert_called_once_with(
            filter_query={"status": "open"}
        )
        mock_db.close.assert_called_once()
