"""Deterministic name normalization with conservative exact matching."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any, Iterable, Mapping

_STRIP_TOKENS = {
    "official",
    "preview",
    "model",
    "release",
    "edition",
    "series",
    "version",
}

_PUNCT_TRANSLATION = str.maketrans(
    {
        "–": "-",
        "—": "-",
        "‑": "-",
        "·": " ",
        "/": " ",
        "_": " ",
        "(": " ",
        ")": " ",
        "[": " ",
        "]": " ",
        "{": " ",
        "}": " ",
        ",": " ",
        ":": " ",
        ";": " ",
        "!": " ",
        "?": " ",
    }
)


@dataclass(frozen=True)
class NormalizedModel:
    model_id: str
    name: str
    provider: str | None
    aliases: tuple[str, ...]


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.translate(_PUNCT_TRANSLATION)
    value = re.sub(r"[^0-9A-Za-z]+", " ", value).lower().strip()
    tokens = [token for token in value.split() if token and token not in _STRIP_TOKENS]
    return " ".join(tokens)


def _compact_text(value: str) -> str:
    return normalize_text(value).replace(" ", "")


def _candidate_strings(model: Mapping[str, Any]) -> tuple[str, ...]:
    candidates: list[str] = []
    for key in ("name",):
        raw = model.get(key)
        if isinstance(raw, str) and raw.strip():
            candidates.append(raw)
    aliases = model.get("aliases")
    if isinstance(aliases, Iterable) and not isinstance(aliases, str):
        for alias in aliases:
            if isinstance(alias, str) and alias.strip():
                candidates.append(alias)
    return tuple(dict.fromkeys(candidates))


def normalize_model_entry(model: Mapping[str, Any]) -> NormalizedModel:
    model_id = str(model["id"])
    name = str(model.get("name", model_id))
    provider = model.get("provider")
    provider_str = str(provider) if isinstance(provider, str) else None
    alias_set = {
        normalized
        for candidate in _candidate_strings(model)
        for normalized in (normalize_text(candidate), _compact_text(candidate))
        if normalized
    }
    aliases = tuple(sorted(alias_set))
    return NormalizedModel(model_id=model_id, name=name, provider=provider_str, aliases=aliases)


def _model_candidates(models: Iterable[Mapping[str, Any]]) -> list[NormalizedModel]:
    return [normalize_model_entry(model) for model in models]


def resolve_model_name(raw_name: str, models: Iterable[Mapping[str, Any]], *, threshold: float = 80.0) -> str | None:
    """Resolve a raw leaderboard label to an existing model id.

    The resolver intentionally prefers false negatives over false positives.
    If a source label is not an exact normalized match for an existing model or
    alias, it should create a new model instead of contaminating a seeded one.
    """

    raw_norm = normalize_text(raw_name)
    raw_compact = raw_norm.replace(" ", "")
    if not raw_norm:
        return None

    candidates = _model_candidates(models)
    exact: list[NormalizedModel] = []

    for candidate in candidates:
        if any(raw_norm == alias or raw_compact == alias for alias in candidate.aliases):
            exact.append(candidate)

    if exact:
        exact.sort(key=lambda candidate: candidate.model_id)
        return exact[0].model_id

    # Threshold is intentionally unused for now. Fuzzy matching created
    # cross-family and cross-generation collapses in live benchmark data.
    _ = threshold
    return None


def build_model_lookup(models: Iterable[Mapping[str, Any]]) -> dict[str, NormalizedModel]:
    return {model["id"]: normalize_model_entry(model) for model in models}


__all__ = [
    "NormalizedModel",
    "build_model_lookup",
    "normalize_model_entry",
    "normalize_text",
    "resolve_model_name",
]
