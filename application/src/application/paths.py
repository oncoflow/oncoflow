"""
Filesystem path safety helpers.

Every user-controlled filename (HTTP path params, uploaded file names, UI
selections, LLM tool arguments) must go through :func:`safe_path` before it
touches the filesystem, to prevent path traversal (``../``, absolute paths,
NUL bytes, ...).
"""

import re
from pathlib import Path

__all__ = ["UnsafePathError", "is_safe_filename", "safe_path"]

# Letters (incl. accents via \w in unicode mode), digits, underscore, dash,
# dot, space and parentheses. No path separators.
_SAFE_FILENAME_RE = re.compile(r"^[\w\-. ()]+$")
_MAX_FILENAME_LENGTH = 255


class UnsafePathError(ValueError):
    """Raised when a filename is unsafe or escapes its base directory."""


def _check_filename(filename: str) -> None:
    if not isinstance(filename, str) or not filename or not filename.strip():
        raise UnsafePathError("Empty filename")
    if len(filename) > _MAX_FILENAME_LENGTH:
        raise UnsafePathError("Filename too long")
    if "\x00" in filename:
        raise UnsafePathError("NUL byte in filename")
    if "/" in filename or "\\" in filename:
        raise UnsafePathError("Path separators are not allowed in filename")
    if filename == "." or ".." in filename:
        # Conservative: rejects '.', '..' and any name containing '..'.
        raise UnsafePathError("Relative path components are not allowed")
    if Path(filename).is_absolute():
        raise UnsafePathError("Absolute paths are not allowed")
    if not _SAFE_FILENAME_RE.match(filename):
        raise UnsafePathError("Filename contains forbidden characters")


def is_safe_filename(name: str) -> bool:
    """Return True if ``name`` is a plain, safe basename (same rules as safe_path)."""
    try:
        _check_filename(name)
    except UnsafePathError:
        return False
    return True


def safe_path(base: Path | str, filename: str) -> Path:
    """
    Join ``filename`` to ``base`` safely.

    Args:
        base: Trusted base directory.
        filename: Untrusted plain file name (no directories).

    Returns:
        The resolved absolute path, guaranteed to be inside ``base``.

    Raises:
        UnsafePathError: if the filename is invalid or escapes ``base``.
    """
    _check_filename(filename)
    base_resolved = Path(base).resolve()
    candidate = (base_resolved / filename).resolve()
    if not candidate.is_relative_to(base_resolved) or candidate == base_resolved:
        raise UnsafePathError("Path escapes base directory")
    return candidate
