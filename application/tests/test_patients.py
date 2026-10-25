import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.application.patient import (
    build_patient_from_administrative,
    build_patient_id,
    extract_card_metrics,
    process_patient_association,
    select_latest_analyzed_rcp,
)
from src.domain.common.common_ressources import Gender
from src.domain.common.patient_mdt_common_form import PatientMDTForm


class TestPatientDomainAndLogic(unittest.TestCase):
    def test_build_patient_id_normalizes_accents_and_dates(self):
        pid1 = build_patient_id("Jean-Pierre", "D'Hérémont", datetime(1958, 3, 14))
        pid2 = build_patient_id("  jean pierre ", "d heremont", "1958-03-14T00:00:00")
        self.assertEqual(pid1, "d_heremont_jean_pierre_1958_03_14")
        self.assertEqual(pid1, pid2)

    def test_build_patient_id_without_birth_date(self):
        pid = build_patient_id("Marie", "Curie", None)
        self.assertEqual(pid, "curie_marie")

    def test_from_administrative_and_labels(self):
        admin = PatientMDTForm.PatientAdministrative(
            first_name="Claire",
            last_name="Martin",
            born_name="Bernard",
            age=64,
            date_birth=datetime(1962, 7, 21),
            date_rcp=datetime(2026, 2, 10),
            gender=Gender.female,
        )
        patient = build_patient_from_administrative(admin, filename="rcp_2026_02.pdf")
        self.assertEqual(patient.patient_id, "martin_claire_1962_07_21")
        self.assertEqual(patient.full_name, "Claire Martin")
        self.assertIn("21-07-1962", patient.display_label)
        self.assertEqual(patient.files, ["rcp_2026_02.pdf"])

    def test_select_latest_analyzed_rcp_prefers_analyzed_and_latest_date_rcp(self):
        rcp_old_analyzed = {
            "file": "rcp_2025_01.pdf",
            "ui_date": datetime(2026, 1, 10),
            "PatientAdministrative": {
                "first_name": "Jean",
                "last_name": "Dupont",
                "date_rcp": datetime(2025, 1, 15),
            },
            "ExpertAnswer": {
                "pancreas": {
                    "expert_relevant": True,
                    "patient_priority": "Patient must be treated as soon as possible",
                }
            },
        }
        rcp_new_analyzed = {
            "file": "rcp_2026_03.pdf",
            "ui_date": datetime(2026, 3, 20),
            "PatientAdministrative": {
                "first_name": "Jean",
                "last_name": "Dupont",
                "date_rcp": datetime(2026, 3, 18),
            },
            "ExpertAnswer": {
                "pancreas": {
                    "expert_relevant": True,
                    "patient_priority": "Patient must be treated urgently",
                }
            },
        }
        rcp_unanalyzed_newer_scan = {
            "file": "rcp_2026_04_raw.pdf",
            "ui_date": datetime(2026, 4, 1),
        }

        selected = select_latest_analyzed_rcp(
            [rcp_old_analyzed, rcp_new_analyzed, rcp_unanalyzed_newer_scan]
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected["file"], "rcp_2026_03.pdf")

        card = extract_card_metrics(selected)
        self.assertEqual(card["urgency"], "Urgent")
        self.assertEqual(card["urgency_score"], 2)

    @patch("src.application.patient.Mongodb")
    @patch("src.domain.common.patient_mdt_common_form.DocumentReader.__init__")
    def test_process_patient_association_manual_overrides_identity_keeps_date_rcp(
        self, mock_doc_init, mock_mongodb_cls
    ):
        mock_doc_init.return_value = None
        mock_db = mock_mongodb_cls.return_value
        mock_db.get_document.return_value = {"file": "rcp_scan.pdf"}
        mock_db.get_patient.return_value = {
            "patient_id": "durand_paul_1955_11_02",
            "first_name": "Paul",
            "last_name": "Durand",
            "born_name": None,
            "date_birth": datetime(1955, 11, 2),
            "gender": "male",
            "files": ["rcp_prev.pdf"],
        }
        mock_db.upsert_patient.side_effect = lambda p_data, filename=None: {
            **p_data,
            "files": ["rcp_prev.pdf", filename],
        }

        form = PatientMDTForm.__new__(PatientMDTForm)
        form.config = MagicMock()
        form.config.rcp.display_type = "mongodb"
        form.document = "rcp_scan.pdf"
        form.logger = MagicMock()
        form.mtd_datas = {"file": "rcp_scan.pdf"}
        form.db_client = mock_db

        def fake_read_model(model_cls, upsert=True, callbacks=None):
            form.mtd_datas["PatientAdministrative"] = {
                "first_name": "OCR_Typo_Pol",
                "last_name": "Durant",
                "born_name": None,
                "age": 70,
                "date_birth": None,
                "date_rcp": datetime(2026, 4, 10),
                "gender": "male",
            }
            return form.mtd_datas["PatientAdministrative"]

        form.read_model = MagicMock(side_effect=fake_read_model)

        patient_obj = process_patient_association(
            form=form,
            target_patient_id="durand_paul_1955_11_02",
        )

        form.read_model.assert_called_once()
        # Identity fields are forced from the selected patient while date_rcp and age are preserved
        admin_saved = form.mtd_datas["PatientAdministrative"]
        self.assertEqual(admin_saved["first_name"], "Paul")
        self.assertEqual(admin_saved["last_name"], "Durand")
        self.assertEqual(admin_saved["date_birth"], "1955-11-02")
        self.assertEqual(admin_saved["date_rcp"], datetime(2026, 4, 10))
        self.assertEqual(admin_saved["age"], 70)
        self.assertEqual(form.mtd_datas["patient_id"], "durand_paul_1955_11_02")
        self.assertEqual(patient_obj.patient_id, "durand_paul_1955_11_02")

    def test_build_patients_cards_and_resolve_dossier_for_legacy_rcp(self):
        from src.application.patient import (
            build_patients_cards_data,
            resolve_patient_dossier,
        )

        legacy_doc_1 = {
            "file": "rcp_old.pdf",
            "ui_date": datetime(2025, 1, 10),
            "PatientAdministrative": {
                "first_name": "Marion",
                "last_name": "Roussel",
                "date_birth": datetime(1970, 5, 12),
                "date_rcp": datetime(2025, 1, 10),
            },
        }
        legacy_doc_2 = {
            "file": "rcp_latest.pdf",
            "ui_date": datetime(2026, 2, 15),
            "PatientAdministrative": {
                "first_name": "Marion",
                "last_name": "Roussel",
                "date_birth": datetime(1970, 5, 12),
                "date_rcp": datetime(2026, 2, 15),
            },
            "ExpertAnswer": {
                "pancreas": {
                    "expert_relevant": True,
                    "patient_priority": "Patient must be treated urgently",
                }
            },
        }

        mock_db = MagicMock()
        mock_rcp_col = MagicMock()
        mock_rcp_col.find.return_value = [legacy_doc_1, legacy_doc_2]
        mock_rcp_col.find_one.side_effect = lambda q: (
            legacy_doc_2
            if q.get("file") == "rcp_latest.pdf"
            else legacy_doc_1
            if q.get("file") == "rcp_old.pdf"
            else None
        )
        mock_db.database = {"rcp_info": mock_rcp_col}
        mock_db.get_all_patients.return_value = []
        mock_db.get_patient.return_value = None
        mock_db.find_patient_by_identity.return_value = None

        cards = build_patients_cards_data(mock_db)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["patient_id"], "roussel_marion_1970_05_12")
        self.assertEqual(cards[0]["file"], "rcp_latest.pdf")
        self.assertEqual(cards[0]["rcp_count"], 2)
        self.assertEqual(
            cards[0]["link"],
            "datas?patient_id=roussel_marion_1970_05_12&file=rcp_latest.pdf",
        )

        # Opening the patient dossier by patient_id alone must also resolve both RCPs and select rcp_latest.pdf
        mock_rcp_col.find.side_effect = lambda query=None, proj=None: (
            [] if query and "patient_id" in query else [legacy_doc_1, legacy_doc_2]
        )
        patient_obj, patient_rcps, selected_file = resolve_patient_dossier(
            db_client=mock_db,
            patient_id_param="roussel_marion_1970_05_12",
            file_param=None,
        )
        self.assertIsNotNone(patient_obj)
        self.assertEqual(patient_obj.patient_id, "roussel_marion_1970_05_12")
        self.assertEqual(len(patient_rcps), 2)
        self.assertEqual(selected_file, "rcp_latest.pdf")

    def test_resolve_rcp_upload_hash_and_duplicate_detection(self):
        import os
        import tempfile
        from src.application.app_functions import resolve_rcp_upload

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_conf = MagicMock()
            mock_conf.rcp.path = tmpdir
            mock_conf.rcp.display_type = "stdout"

            bytes_a = b"%PDF-1.4 Patient A RCP Content"
            bytes_b = b"%PDF-1.4 Patient B Different RCP Content"

            # 1. Premier import de "fiche_rcp.pdf" -> renommé avec le hash, pas un doublon
            fname1, is_dup1 = resolve_rcp_upload(mock_conf, bytes_a, "fiche_rcp.pdf")
            self.assertFalse(is_dup1)
            self.assertTrue(fname1.startswith("fiche_rcp_"))
            self.assertTrue(fname1.endswith(".pdf"))

            # On simule l'écriture du fichier sur le disque
            with open(os.path.join(tmpdir, fname1), "wb") as f:
                f.write(bytes_a)

            # 2. Import d'un autre contenu avec le MÊME nom "fiche_rcp.pdf" -> hash différent, pas d'écrasement
            fname2, is_dup2 = resolve_rcp_upload(mock_conf, bytes_b, "fiche_rcp.pdf")
            self.assertFalse(is_dup2)
            self.assertNotEqual(fname1, fname2)

            # 3. Ré-import du même contenu bytes_a -> détecté comme doublon
            fname3, is_dup3 = resolve_rcp_upload(mock_conf, bytes_a, "fiche_rcp.pdf")
            self.assertTrue(is_dup3)
            self.assertEqual(fname3, fname1)
