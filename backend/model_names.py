"""Small, display-only model-name normalizers.

These helpers intentionally do not normalize provider IDs, repository IDs, or
raw source labels.  They are safe to use only at catalogue display boundaries.
"""

from __future__ import annotations

import re
from typing import Any


_TRAILING_FREE_SUFFIX_RE = re.compile(r"\s*\(\s*free\s*\)\s*$", re.IGNORECASE)


def remove_trailing_free_suffix(value: Any) -> str:
    """Remove one trailing ``(free)`` display suffix, preserving all other text."""
    text = str(value or "")
    return _TRAILING_FREE_SUFFIX_RE.sub("", text).rstrip()


__all__ = ["remove_trailing_free_suffix"]
