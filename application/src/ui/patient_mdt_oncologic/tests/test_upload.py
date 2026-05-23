from unittest.mock import MagicMock
import sys

# To avoid streamlit execution blocking or crashing during tests
from unittest.mock import patch

with patch.dict(sys.modules, {"streamlit": MagicMock()}):
    import src.ui.patient_mdt_oncologic.upload as upload


def test_ui_upload_placeholder(mocker):
    """
    TEST EXPLANATION:
    This test verifies that the `upload.py` module loads successfully.
    Since it consists mostly of Streamlit logic executed on module load,
    we test its ability to be imported without errors when streamlit is mocked.
    """
    assert hasattr(upload, "PAGES_DIR_SRC")
    assert upload.PAGES_DIR_SRC == "src/ui"
