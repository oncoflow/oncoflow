"""Unit tests for path traversal and filename sanitization helpers."""

from pathlib import Path

import pytest

from src.application.paths import UnsafePathError, is_safe_filename, safe_path


@pytest.mark.parametrize(
    "name",
    [
        "patient_01.pdf",
        "CR_RCP_Éléonore-Dupont (2026).pdf",
        "dossier.rcp.v2.pdf",
    ],
)
def test_is_safe_filename_accepts_valid_names(name: str):
    assert is_safe_filename(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        ".",
        "..",
        "../secret.pdf",
        "../../etc/passwd",
        "/etc/passwd",
        "subdir/file.pdf",
        "subdir\\file.pdf",
        "file\x00.pdf",
    ],
)
def test_is_safe_filename_rejects_traversal_and_separators(name: str):
    assert is_safe_filename(name) is False


def test_safe_path_resolves_inside_base_dir(tmp_path: Path):
    resolved = safe_path(tmp_path, "report.pdf")
    assert resolved == (tmp_path / "report.pdf").resolve()


@pytest.mark.parametrize(
    "bad_name",
    [
        "",
        "..",
        "../outside.pdf",
        "/abs/path.pdf",
        "nested/file.pdf",
        "nested\\file.pdf",
        "bad\x00.pdf",
    ],
)
def test_safe_path_raises_on_unsafe_filename(tmp_path: Path, bad_name: str):
    with pytest.raises(UnsafePathError):
        safe_path(tmp_path, bad_name)


def test_safe_path_rejects_symlink_escaping_base_dir(tmp_path: Path):
    base = tmp_path / "rcp"
    base.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    escape_link = base / "escape.pdf"
    escape_link.symlink_to(outside)

    with pytest.raises(UnsafePathError):
        safe_path(base, "escape.pdf")
