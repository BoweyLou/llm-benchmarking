"""Read the application release version from the repository root."""

from __future__ import annotations

from pathlib import Path
import re


_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def project_root(start: Path | None = None) -> Path:
    """Locate the source/deployment root which owns the VERSION file."""
    location = (start or Path(__file__)).resolve()
    candidates = (location, *location.parents) if location.is_dir() else location.parents
    for candidate in candidates:
        if (candidate / "VERSION").is_file():
            return candidate
    raise RuntimeError("Could not locate the application VERSION file.")


def read_app_version(version_file: Path | None = None) -> str:
    """Return the single repository SemVer release version or fail clearly."""
    path = version_file or project_root() / "VERSION"
    try:
        version = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Could not read application VERSION file: {path}") from exc
    if not _SEMVER_RE.fullmatch(version):
        raise RuntimeError(f"Invalid application VERSION {version!r}; expected SemVer.")
    return version


__all__ = ["project_root", "read_app_version"]
