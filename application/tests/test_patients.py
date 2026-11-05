from datetime import datetime
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from src.application.use_cases import (
    PatientMDTFormExtractionService,
    PatientRecordService,
)
from src.domain.common.common_ressources import Gender
from src.domain.patient import Patient, PractitionerNote
from src.domain.patient_mdt_form import NonPatientMDTFormError, PatientMDTForm
from src.infrastructure.documents.repositories import (
    InMemoryDocumentCacheRepository,
    InMemoryPatientMDTFormRepository,
    InMemoryPatientRepository,
)


class TestPatientDomainAndLogic(unittest.TestCase):
    def test_build_patient_id_normalizes_accents_and_dates(self):
        pid1 = Patient.build_id("Jean-Pierre", "D'Hérémont", datetime(1958, 3, 14))
        pid2 = Patient.build_id("  jean pierre ", "d heremont", "1958-03-14T00:00:00")
        self.assertEqual(pid1, "d_heremont_jean_pierre_1958_03_14")
        self.assertEqual(pid1, pid2)

    def test_build_patient_id_without_birth_date(self):
        pid = Patient.build_id("Marie", "Curie", None)
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
        patient = Patient.from_administrative(admin, filename="rcp_2026_02.pdf")
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

        selected = PatientMDTForm.select_latest_analyzed(
            [rcp_old_analyzed, rcp_new_analyzed, rcp_unanalyzed_newer_scan]
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected["file"], "rcp_2026_03.pdf")

        card = PatientMDTForm.extract_card_metrics(selected)
        self.assertEqual(card["urgency"], "Urgent")
        self.assertEqual(card["urgency_score"], 2)

    def test_process_patient_association_manual_overrides_identity_keeps_date_rcp(
        self,
    ):
        patient_repo = InMemoryPatientRepository()
        mdt_form_repo = InMemoryPatientMDTFormRepository()
        cache_repo = InMemoryDocumentCacheRepository()

        existing_patient = Patient(
            patient_id="durand_paul_1955_11_02",
            first_name="Paul",
            last_name="Durand",
            born_name=None,
            date_birth=datetime(1955, 11, 2),
            gender=Gender.male,
            files=["rcp_prev.pdf"],
        )
        patient_repo.upsert(existing_patient)

        mock_conf = MagicMock()
        mock_conf.domain = "oncology"
        mock_conf.rcp.display_type = "mongodb"

        record_service = PatientRecordService(
            patient_repo=patient_repo,
            mdt_form_repo=mdt_form_repo,
            cache_repo=cache_repo,
            config=mock_conf,
        )
        extraction_service = PatientMDTFormExtractionService(
            config=mock_conf,
            patient_repo=patient_repo,
            mdt_form_repo=mdt_form_repo,
            cache_repo=cache_repo,
            patient_record_service=record_service,
        )

        form = PatientMDTForm(file="rcp_scan.pdf")
        mock_reader = MagicMock()
        mock_reader.document = "rcp_scan.pdf"

        def fake_extract_section(form, reader, model_cls, upsert=True, callbacks=None):
            form.sections["PatientAdministrative"] = {
                "first_name": "OCR_Typo_Pol",
                "last_name": "Durant",
                "born_name": None,
                "age": 70,
                "date_birth": None,
                "date_rcp": datetime(2026, 4, 10),
                "gender": "male",
            }
            return form.sections["PatientAdministrative"]

        extraction_service.extract_section = MagicMock(side_effect=fake_extract_section)

        patient_obj = extraction_service.process_patient_association(
            form=form,
            reader=mock_reader,
            target_patient_id="durand_paul_1955_11_02",
        )

        extraction_service.extract_section.assert_called_once()
        # Identity fields are forced from the selected patient while date_rcp and age are preserved
        admin_saved = form.sections["PatientAdministrative"]
        self.assertEqual(admin_saved["first_name"], "Paul")
        self.assertEqual(admin_saved["last_name"], "Durand")
        self.assertEqual(admin_saved["date_birth"], "1955-11-02")
        self.assertEqual(admin_saved["date_rcp"], datetime(2026, 4, 10))
        self.assertEqual(admin_saved["age"], 70)
        self.assertEqual(form.patient_id, "durand_paul_1955_11_02")
        self.assertEqual(patient_obj.patient_id, "durand_paul_1955_11_02")

    def test_build_patients_cards_and_resolve_record_for_unlinked_forms(self):
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

        patient_repo = InMemoryPatientRepository()
        mdt_form_repo = InMemoryPatientMDTFormRepository([legacy_doc_1, legacy_doc_2])
        record_service = PatientRecordService(
            patient_repo=patient_repo,
            mdt_form_repo=mdt_form_repo,
        )

        cards = record_service.list_patient_cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["patient_id"], "roussel_marion_1970_05_12")
        self.assertEqual(cards[0]["file"], "rcp_latest.pdf")
        self.assertEqual(cards[0]["rcp_count"], 2)
        self.assertEqual(
            cards[0]["link"],
            "datas?patient_id=roussel_marion_1970_05_12&file=rcp_latest.pdf",
        )

        # Opening the PatientRecord by patient_id alone must also resolve both forms and select rcp_latest.pdf
        patient_obj, patient_rcps, selected_file = (
            record_service.resolve_patient_record(
                patient_id_param="roussel_marion_1970_05_12",
                file_param=None,
            )
        )
        self.assertIsNotNone(patient_obj)
        self.assertEqual(patient_obj.patient_id, "roussel_marion_1970_05_12")
        self.assertEqual(len(patient_rcps), 2)
        self.assertEqual(selected_file, "rcp_latest.pdf")

    def test_resolve_upload_hash_and_duplicate_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_conf = MagicMock()
            mock_conf.rcp.path = tmpdir
            mock_conf.rcp.display_type = "stdout"

            extraction_service = PatientMDTFormExtractionService(
                config=mock_conf,
                patient_repo=InMemoryPatientRepository(),
                mdt_form_repo=InMemoryPatientMDTFormRepository(),
                cache_repo=InMemoryDocumentCacheRepository(),
            )

            bytes_a = b"%PDF-1.4 Patient A RCP Content"
            bytes_b = b"%PDF-1.4 Patient B Different RCP Content"

            # 1. First import of "fiche_rcp.pdf" -> renamed with hash, not a duplicate
            fname1, is_dup1 = extraction_service.resolve_upload(
                bytes_a, "fiche_rcp.pdf"
            )
            self.assertFalse(is_dup1)
            self.assertTrue(fname1.startswith("fiche_rcp_"))
            self.assertTrue(fname1.endswith(".pdf"))

            # Simulate writing the file to disk
            with open(os.path.join(tmpdir, fname1), "wb") as f:
                f.write(bytes_a)

            # 2. Import of different content with the SAME name "fiche_rcp.pdf" -> different hash, no overwrite
            fname2, is_dup2 = extraction_service.resolve_upload(
                bytes_b, "fiche_rcp.pdf"
            )
            self.assertFalse(is_dup2)
            self.assertNotEqual(fname1, fname2)

            # 3. Re-import of the same content bytes_a -> detected as duplicate
            fname3, is_dup3 = extraction_service.resolve_upload(
                bytes_a, "fiche_rcp.pdf"
            )
            self.assertTrue(is_dup3)
            self.assertEqual(fname3, fname1)

    def test_verify_patient_mdt_form_accepts_valid_form_and_executes_admin_extraction(
        self,
    ):
        patient_repo = InMemoryPatientRepository()
        mdt_form_repo = InMemoryPatientMDTFormRepository()
        cache_repo = InMemoryDocumentCacheRepository()

        mock_conf = MagicMock()
        mock_conf.domain = "oncology"
        mock_conf.rcp.display_type = "mongodb"

        record_service = PatientRecordService(
            patient_repo=patient_repo,
            mdt_form_repo=mdt_form_repo,
            cache_repo=cache_repo,
            config=mock_conf,
        )
        extraction_service = PatientMDTFormExtractionService(
            config=mock_conf,
            patient_repo=patient_repo,
            mdt_form_repo=mdt_form_repo,
            cache_repo=cache_repo,
            patient_record_service=record_service,
        )

        form = PatientMDTForm(file="valid_rcp.pdf")
        mock_reader = MagicMock()
        mock_reader.document = "valid_rcp.pdf"

        models_called = []

        def fake_extract_section(form, reader, model_cls, upsert=False, callbacks=None):
            models_called.append(model_cls.__name__)
            if model_cls.__name__ == "PatientMDTFormCheck":
                check = PatientMDTForm.PatientMDTFormCheck(
                    is_patient_mdt_form=True,
                    detected_document_type="Fiche RCP",
                    justification="Compte-rendu de réunion de concertation pluridisciplinaire d'oncologie.",
                )
                form.sections["PatientMDTFormCheck"] = check.model_dump()
                return check
            elif model_cls.__name__ == "PatientAdministrative":
                form.sections["PatientAdministrative"] = {
                    "first_name": "Sophie",
                    "last_name": "Lambert",
                    "born_name": None,
                    "age": 58,
                    "date_birth": datetime(1968, 4, 12),
                    "date_rcp": datetime(2026, 5, 10),
                    "gender": "female",
                }
                return form.sections["PatientAdministrative"]

        extraction_service.extract_section = MagicMock(side_effect=fake_extract_section)

        patient_obj = extraction_service.process_patient_association(
            form=form,
            reader=mock_reader,
            verify_patient_mdt_form=True,
        )
        self.assertEqual(
            models_called, ["PatientMDTFormCheck", "PatientAdministrative"]
        )
        self.assertEqual(patient_obj.patient_id, "lambert_sophie_1968_04_12")

    def test_verify_patient_mdt_form_rejects_non_mdt_form_and_cleans_up(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            patient_repo = InMemoryPatientRepository()
            mdt_form_repo = InMemoryPatientMDTFormRepository()
            cache_repo = InMemoryDocumentCacheRepository()

            mock_conf = MagicMock()
            mock_conf.domain = "oncology"
            mock_conf.rcp.path = tmpdir
            mock_conf.rcp.display_type = "mongodb"
            mock_conf.queue.enabled = False

            pdf_file = "facture_hopital.pdf"
            pdf_path = os.path.join(tmpdir, pdf_file)
            with open(pdf_path, "wb") as f:
                f.write(b"%PDF-1.4 Facture")
            mdt_form_repo.update_fields(pdf_file, {"file": pdf_file})

            record_service = PatientRecordService(
                patient_repo=patient_repo,
                mdt_form_repo=mdt_form_repo,
                cache_repo=cache_repo,
                config=mock_conf,
            )
            extraction_service = PatientMDTFormExtractionService(
                config=mock_conf,
                patient_repo=patient_repo,
                mdt_form_repo=mdt_form_repo,
                cache_repo=cache_repo,
                patient_record_service=record_service,
            )

            form = PatientMDTForm(file=pdf_file)
            mock_reader = MagicMock()
            mock_reader.document = pdf_file
            mock_reader.document_path = pdf_path

            models_called = []

            def fake_extract_section(
                form, reader, model_cls, upsert=False, callbacks=None
            ):
                models_called.append(model_cls.__name__)
                if model_cls.__name__ == "PatientMDTFormCheck":
                    check = PatientMDTForm.PatientMDTFormCheck(
                        is_patient_mdt_form=False,
                        detected_document_type="Facture",
                        justification="Il s'agit d'une facture administrative et non d'une fiche RCP.",
                    )
                    form.sections["PatientMDTFormCheck"] = check.model_dump()
                    return check

            extraction_service.extract_section = MagicMock(
                side_effect=fake_extract_section
            )

            with self.assertRaises(NonPatientMDTFormError) as ctx:
                extraction_service.process_patient_association(
                    form=form,
                    reader=mock_reader,
                    verify_patient_mdt_form=True,
                )

            self.assertEqual(models_called, ["PatientMDTFormCheck"])
            self.assertIn("facture_hopital.pdf", str(ctx.exception))
            self.assertIn("Facture", str(ctx.exception))
            mock_reader.vecdb.delete_collection.assert_called_once()
            self.assertFalse(os.path.exists(pdf_path))
            self.assertIsNone(mdt_form_repo.get_by_filename(pdf_file))

    def test_practitioner_note_domain_one_note_per_practitioner_invariant(self):
        patient = Patient(
            patient_id="dupont_jean_1960_01_01",
            first_name="Jean",
            last_name="Dupont",
            date_birth=datetime(1960, 1, 1),
            files=["rcp1.pdf"],
        )
        t1 = datetime(2026, 5, 1, 9, 0, 0)
        note1 = patient.upsert_practitioner_note(
            practitioner_id="dr.martin@chu.fr",
            practitioner_name="Dr S. Martin",
            content="Vérifier clairance créatinine avant cisplatine.",
            now=t1,
        )
        self.assertIsInstance(note1, PractitionerNote)
        self.assertEqual(len(patient.practitioner_notes), 1)
        self.assertEqual(note1.practitioner_id, "dr.martin@chu.fr")
        self.assertEqual(note1.practitioner_name, "Dr S. Martin")
        self.assertEqual(note1.created_at, t1)
        self.assertEqual(note1.updated_at, t1)

        # Same practitioner updates their note -> still 1 note, created_at preserved, updated_at bumped
        t2 = datetime(2026, 5, 1, 9, 15, 0)
        note1_updated = patient.upsert_practitioner_note(
            practitioner_id="  DR.MARTIN@chu.fr ",
            practitioner_name="Dr Sophie Martin",
            content="Clairance OK (78 mL/min), feu vert cisplatine.",
            now=t2,
        )
        self.assertEqual(len(patient.practitioner_notes), 1)
        self.assertEqual(note1_updated.created_at, t1)
        self.assertEqual(note1_updated.updated_at, t2)
        self.assertEqual(note1_updated.practitioner_name, "Dr Sophie Martin")
        self.assertEqual(
            note1_updated.content, "Clairance OK (78 mL/min), feu vert cisplatine."
        )

        # Second practitioner adds a note -> 2 notes sorted by updated_at desc
        t3 = datetime(2026, 5, 1, 9, 30, 0)
        patient.upsert_practitioner_note(
            practitioner_id="dr.bernard",
            practitioner_name="Dr L. Bernard",
            content="Discussion chirurgie après 4 cures.",
            now=t3,
        )
        self.assertEqual(len(patient.practitioner_notes), 2)
        self.assertEqual(patient.practitioner_notes[0].practitioner_id, "dr.bernard")
        self.assertEqual(
            patient.practitioner_notes[1].practitioner_id, "dr.martin@chu.fr"
        )

        # Reject empty note content
        with self.assertRaises(ValueError):
            patient.upsert_practitioner_note(
                practitioner_id="dr.bernard",
                practitioner_name="Dr L. Bernard",
                content="   ",
            )

        # Persistence round-trip preserves notes
        persisted = patient.to_persistence()
        rehydrated = Patient.from_persistence(persisted)
        self.assertEqual(len(rehydrated.practitioner_notes), 2)
        self.assertEqual(
            rehydrated.practitioner_notes[0].content,
            "Discussion chirurgie après 4 cures.",
        )

        # Delete first practitioner's note -> only theirs is removed
        removed = rehydrated.delete_practitioner_note("DR.MARTIN@CHU.FR")
        self.assertTrue(removed)
        self.assertEqual(len(rehydrated.practitioner_notes), 1)
        self.assertEqual(rehydrated.practitioner_notes[0].practitioner_id, "dr.bernard")
        self.assertFalse(rehydrated.delete_practitioner_note("unknown.dr"))

    def test_patient_record_service_practitioner_notes_and_ai_isolation(self):
        patient_repo = InMemoryPatientRepository()
        mdt_form_repo = InMemoryPatientMDTFormRepository(
            [
                {
                    "file": "rcp_session1.pdf",
                    "patient_id": "moreau_alice_1975_08_20",
                    "PatientAdministrative": {
                        "first_name": "Alice",
                        "last_name": "Moreau",
                        "date_birth": datetime(1975, 8, 20),
                        "date_rcp": datetime(2026, 5, 10),
                    },
                    "practitioner_notes": [
                        {
                            "practitioner_id": "dr.leak",
                            "practitioner_name": "Dr Leak",
                            "content": "Note secrète humaine",
                        }
                    ],
                }
            ]
        )
        record_service = PatientRecordService(
            patient_repo=patient_repo,
            mdt_form_repo=mdt_form_repo,
        )

        # Upsert note on an unlinked/synthesized patient materializes the patient and saves the note
        notes_after_first = record_service.upsert_practitioner_note(
            patient_id_or_file="moreau_alice_1975_08_20",
            practitioner_id="dr.onco",
            practitioner_name="Dr Onco",
            content="OMS 1, patiente favorable au protocole FOLFIRINOX.",
        )
        self.assertEqual(len(notes_after_first), 1)
        self.assertEqual(notes_after_first[0].practitioner_id, "dr.onco")

        # Subsequent administrative sync (e.g. Wave 1 AI extraction on a new file) must preserve practitioner_notes
        synced_patient, _ = record_service.synchronize_patient_from_admin(
            filename="rcp_session2.pdf",
            admin_data={
                "first_name": "Alice",
                "last_name": "Moreau",
                "date_birth": datetime(1975, 8, 20),
            },
        )
        self.assertEqual(len(synced_patient.practitioner_notes), 1)
        self.assertEqual(
            synced_patient.practitioner_notes[0].content,
            "OMS 1, patiente favorable au protocole FOLFIRINOX.",
        )

        # AI history formatter must never include practitioner_notes
        history_text = PatientMDTForm.format_ai_history_entries(
            [("rcp_session1.pdf", mdt_form_repo.get_by_file("rcp_session1.pdf"))]
        )
        self.assertNotIn("Note secrète humaine", history_text)
        self.assertNotIn("practitioner_notes", history_text)

        # Delete note via service
        notes_after_delete = record_service.delete_practitioner_note(
            patient_id_or_file="moreau_alice_1975_08_20",
            practitioner_id="dr.onco",
        )
        self.assertEqual(len(notes_after_delete), 0)
