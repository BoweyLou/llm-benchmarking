"""Canonical model and family identity inference."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .name_resolution import normalize_text

_DATE_TOKEN_RE = re.compile(r"^20\d{6}$")
_YEAR_TOKEN_RE = re.compile(r"^20\d{2}$")
_CONTEXT_TOKEN_RE = re.compile(r"^\d+k$")
_OPENAI_COMPACT_VERSION_RE = re.compile(r"^\d+[a-z]+$")
_OPENAI_SIZE_TOKEN_RE = re.compile(r"^\d+[a-z]+$")
_NOISE_TOKENS = {
    "adaptive",
    "april",
    "august",
    "december",
    "edition",
    "exp",
    "experimental",
    "february",
    "hf",
    "huggingface",
    "january",
    "july",
    "june",
    "latest",
    "march",
    "may",
    "model",
    "models",
    "nebius",
    "november",
    "october",
    "preview",
    "reasoning",
    "release",
    "september",
    "series",
    "thinking",
    "w",
    "with",
    "version",
}
_FAMILY_VARIANT_TOKENS = {
    "chat",
    "codex",
    "flash",
    "haiku",
    "high",
    "instruct",
    "lite",
    "low",
    "max",
    "medium",
    "mini",
    "nano",
    "opus",
    "pro",
    "sonnet",
    "turbo",
    "xhigh",
}
_GENERIC_LEADING_VARIANT_TOKENS = {
    "flash",
    "large",
    "medium",
    "small",
}
_MODEL_BRAND_TOKENS = {
    "claude",
    "deepseek",
    "gemini",
    "gemma",
    "glm",
    "gpt",
    "grok",
    "hunyuan",
    "kimi",
    "llama",
    "ministral",
    "mistral",
    "nemotron",
    "nova",
    "olmo",
    "o1",
    "o3",
    "o4",
    "phi",
    "qwen",
    "reka",
}
_NON_MODEL_PREFIX_TOKENS = {
    "ai",
    "amazon",
    "anthropic",
    "aws",
    "azure",
    "deepmind",
    "google",
    "meta",
    "microsoft",
    "moonshot",
    "nvidia",
    "openai",
    "xai",
    "z",
    "zhipu",
}
_DISPLAY_TOKEN_MAP = {
    "bf16": "BF16",
    "claude": "Claude",
    "codex": "Codex",
    "deepseek": "DeepSeek",
    "flash": "Flash",
    "fp8": "FP8",
    "gemini": "Gemini",
    "gemma": "Gemma",
    "glm": "GLM",
    "gpt": "GPT",
    "grok": "Grok",
    "hf": "HF",
    "haiku": "Haiku",
    "high": "High",
    "instruct": "Instruct",
    "kimi": "Kimi",
    "lite": "Lite",
    "llama": "Llama",
    "low": "Low",
    "max": "Max",
    "medium": "Medium",
    "mini": "Mini",
    "minimax": "MiniMax",
    "nano": "Nano",
    "nova": "Nova",
    "o1": "o1",
    "o3": "o3",
    "o4": "o4",
    "oss": "OSS",
    "opus": "Opus",
    "phi": "Phi",
    "pro": "Pro",
    "qwen": "Qwen",
    "sonnet": "Sonnet",
    "turbo": "Turbo",
    "xhigh": "xhigh",
}


@dataclass(frozen=True)
class ModelIdentity:
    family_id: str
    family_name: str
    canonical_model_id: str
    canonical_model_name: str
    variant_label: str | None = None


def infer_model_identity(name: str, provider: str | None, model_id: str | None = None) -> ModelIdentity:
    provider_norm = normalize_text(provider or "")
    provider_slug = _provider_slug(provider_norm)
    candidate_values = [value for value in (name, model_id) if isinstance(value, str) and value.strip()]
    token_sets = [_prepare_tokens(_tokens(value)) for value in candidate_values]
    token_sets = [tokens for tokens in token_sets if tokens]

    parser = _pick_parser(provider_norm, token_sets)
    for tokens in token_sets:
        parsed = parser(tokens, provider_slug)
        if parsed is not None:
            variant_label = _variant_label(name, parsed.canonical_model_name)
            return ModelIdentity(
                family_id=parsed.family_id,
                family_name=parsed.family_name,
                canonical_model_id=parsed.canonical_model_id,
                canonical_model_name=parsed.canonical_model_name,
                variant_label=variant_label,
            )

    fallback_tokens = token_sets[0] if token_sets else _tokens(name)
    family_tokens = _generic_family_tokens(fallback_tokens)
    canonical_tokens = _generic_canonical_tokens(fallback_tokens)
    family_name = _humanize_tokens(family_tokens)
    canonical_name = _humanize_tokens(canonical_tokens)
    variant_label = _variant_label(name, canonical_name)
    return ModelIdentity(
        family_id=f"{provider_slug}::{_slugify(' '.join(family_tokens)) or 'family'}",
        family_name=family_name,
        canonical_model_id=f"{provider_slug}::{_slugify(' '.join(canonical_tokens)) or 'model'}",
        canonical_model_name=canonical_name,
        variant_label=variant_label,
    )


def _pick_parser(provider_norm: str, token_sets: list[list[str]]):
    providers = provider_norm.split()
    first_tokens = {tokens[0] for tokens in token_sets if tokens}

    if "anthropic" in providers or "claude" in first_tokens:
        return _parse_claude
    if "openai" in providers or {"gpt", "o1", "o3", "o4"}.intersection(first_tokens):
        return _parse_openai
    if "google" in providers or "deepmind" in providers or {"gemini", "gemma"}.intersection(first_tokens):
        return _parse_google
    return _parse_generic


def _parse_claude(tokens: list[str], provider_slug: str) -> ModelIdentity | None:
    if not tokens or tokens[0] != "claude":
        return None

    tier = _first_token(tokens, {"haiku", "sonnet", "opus"})
    version = _extract_version(tokens, brand_token="claude")
    family_tokens = ["claude"] + _version_tokens(version)
    canonical_tokens = family_tokens + ([tier] if tier else [])
    return ModelIdentity(
        family_id=f"{provider_slug}::{_slugify(' '.join(family_tokens)) or 'claude'}",
        family_name=_humanize_claude(family_tokens, tier=None),
        canonical_model_id=f"{provider_slug}::{_slugify(' '.join(canonical_tokens)) or 'claude'}",
        canonical_model_name=_humanize_claude(family_tokens, tier=tier),
    )


def _parse_openai(tokens: list[str], provider_slug: str) -> ModelIdentity | None:
    if not tokens:
        return None

    brand = tokens[0]
    if brand == "gpt":
        family_tokens = _openai_gpt_family_tokens(tokens)
        variant_tokens = _normalize_openai_variant_tokens(
            family_tokens,
            _canonical_variant_tokens(tokens, family_tokens, keep_family_variants=True),
        )
    elif brand in {"o1", "o3", "o4"}:
        family_tokens = [brand]
        variant_tokens = _canonical_variant_tokens(tokens, family_tokens, keep_family_variants=True)
    else:
        return None

    canonical_tokens = family_tokens + variant_tokens
    family_name = _humanize_tokens(family_tokens)
    canonical_name = _humanize_tokens(canonical_tokens)
    return ModelIdentity(
        family_id=f"{provider_slug}::{_slugify(' '.join(family_tokens)) or brand}",
        family_name=family_name,
        canonical_model_id=f"{provider_slug}::{_slugify(' '.join(canonical_tokens)) or brand}",
        canonical_model_name=canonical_name,
    )


def _openai_gpt_family_tokens(tokens: list[str]) -> list[str]:
    if len(tokens) >= 2 and _OPENAI_COMPACT_VERSION_RE.fullmatch(tokens[1]):
        return ["gpt", tokens[1]]

    if len(tokens) >= 2 and tokens[1] == "oss":
        family_tokens = ["gpt", "oss"]
        if len(tokens) >= 3 and _OPENAI_SIZE_TOKEN_RE.fullmatch(tokens[2]):
            family_tokens.append(tokens[2])
        return family_tokens

    version = _extract_version(tokens, brand_token="gpt")
    return ["gpt"] + _version_tokens(version)


def _normalize_openai_variant_tokens(family_tokens: list[str], variant_tokens: list[str]) -> list[str]:
    normalized = list(variant_tokens)

    if family_tokens and family_tokens[-1].endswith("v") and normalized[:1] == ["ision"]:
        normalized = normalized[1:]

    if normalized == ["o"]:
        return []

    return normalized


def _parse_google(tokens: list[str], provider_slug: str) -> ModelIdentity | None:
    if not tokens or tokens[0] not in {"gemini", "gemma"}:
        return None

    brand = tokens[0]
    version = _extract_version(tokens, brand_token=brand)
    family_tokens = [brand] + _version_tokens(version)
    variant_tokens = _canonical_variant_tokens(tokens, family_tokens, keep_family_variants=True)
    canonical_tokens = family_tokens + variant_tokens
    return ModelIdentity(
        family_id=f"{provider_slug}::{_slugify(' '.join(family_tokens)) or brand}",
        family_name=_humanize_tokens(family_tokens),
        canonical_model_id=f"{provider_slug}::{_slugify(' '.join(canonical_tokens)) or brand}",
        canonical_model_name=_humanize_tokens(canonical_tokens),
    )


def _parse_generic(tokens: list[str], provider_slug: str) -> ModelIdentity | None:
    if not tokens:
        return None

    family_tokens = _generic_family_tokens(tokens)
    canonical_tokens = _generic_canonical_tokens(tokens)
    return ModelIdentity(
        family_id=f"{provider_slug}::{_slugify(' '.join(family_tokens)) or 'family'}",
        family_name=_humanize_tokens(family_tokens),
        canonical_model_id=f"{provider_slug}::{_slugify(' '.join(canonical_tokens)) or 'model'}",
        canonical_model_name=_humanize_tokens(canonical_tokens),
    )


def _generic_family_tokens(tokens: list[str]) -> list[str]:
    cleaned = _strip_noise_tokens(tokens)
    if not cleaned:
        return ["model"]
    brand = cleaned[0]
    if (
        len(cleaned) >= 3
        and cleaned[1] in _GENERIC_LEADING_VARIANT_TOKENS
        and re.fullmatch(r"\d+[a-z]?", cleaned[2])
    ):
        return cleaned[:3]
    version = _extract_version(cleaned, brand_token=brand)
    family_tokens = [brand] + _version_tokens(version)
    if family_tokens == [brand]:
        return cleaned[:2]
    return family_tokens


def _generic_canonical_tokens(tokens: list[str]) -> list[str]:
    family_tokens = _generic_family_tokens(tokens)
    variant_tokens = _canonical_variant_tokens(tokens, family_tokens, keep_family_variants=True)
    return family_tokens + variant_tokens


def _canonical_variant_tokens(tokens: list[str], family_tokens: list[str], *, keep_family_variants: bool) -> list[str]:
    cleaned = _strip_noise_tokens(tokens)
    start = 0
    while start < len(cleaned) and start < len(family_tokens) and cleaned[start] == family_tokens[start]:
        start += 1

    variant_tokens = []
    for token in cleaned[start:]:
        if _DATE_TOKEN_RE.fullmatch(token) or _CONTEXT_TOKEN_RE.fullmatch(token):
            continue
        if token in _NOISE_TOKENS:
            continue
        variant_tokens.append(token)
    variant_tokens = _strip_trailing_build_tokens(variant_tokens)

    if keep_family_variants:
        return variant_tokens
    return [token for token in variant_tokens if token not in _FAMILY_VARIANT_TOKENS]


def _strip_noise_tokens(tokens: list[str]) -> list[str]:
    return [
        token
        for token in tokens
        if token
        and not _DATE_TOKEN_RE.fullmatch(token)
        and not _YEAR_TOKEN_RE.fullmatch(token)
        and not _CONTEXT_TOKEN_RE.fullmatch(token)
        and token not in _NOISE_TOKENS
    ]


def _extract_version(tokens: list[str], *, brand_token: str) -> str | None:
    try:
        brand_index = tokens.index(brand_token)
    except ValueError:
        return None

    parts: list[str] = []
    for token in tokens[brand_index + 1:]:
        if token in _NOISE_TOKENS or _DATE_TOKEN_RE.fullmatch(token) or _YEAR_TOKEN_RE.fullmatch(token):
            continue
        if re.fullmatch(r"\d+", token):
            parts.append(token)
            if len(parts) == 2:
                break
            continue
        if parts:
            break
        if token in _FAMILY_VARIANT_TOKENS:
            continue
        break
    if not parts:
        return None
    return ".".join(parts)


def _version_tokens(version: str | None) -> list[str]:
    if not version:
        return []
    return version.split(".")


def _first_token(tokens: list[str], allowed: set[str]) -> str | None:
    for token in tokens:
        if token in allowed:
            return token
    return None


def _tokens(value: str) -> list[str]:
    normalized = normalize_text(value)
    return normalized.split() if normalized else []


def _prepare_tokens(tokens: list[str]) -> list[str]:
    if not tokens:
        return []

    index = 0
    while index < len(tokens) and tokens[index] in _NON_MODEL_PREFIX_TOKENS:
        index += 1
    if 0 < index < len(tokens) and tokens[index] in _MODEL_BRAND_TOKENS:
        return tokens[index:]
    return tokens


def _humanize_claude(family_tokens: list[str], *, tier: str | None) -> str:
    version = ".".join(token for token in family_tokens[1:] if token)
    if tier and version:
        return f"Claude {tier.title()} {version}"
    if tier:
        return f"Claude {tier.title()}"
    if version:
        return f"Claude {version}"
    return "Claude"


def _humanize_tokens(tokens: list[str]) -> str:
    parts = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        next_token = tokens[index + 1] if index + 1 < len(tokens) else None
        if next_token and _should_compact_decimal_pair(token, next_token):
            parts.append(f"{_humanize_atomic_token(token)}.{_humanize_atomic_token(next_token)}")
            index += 2
            continue
        parts.append(_humanize_atomic_token(token))
        index += 1
    return " ".join(parts).strip()


def _should_compact_decimal_pair(token: str, next_token: str) -> bool:
    if re.fullmatch(r"\d+", token) and re.fullmatch(r"\d+[a-z]?", next_token) and len(next_token) <= 2:
        return True
    if re.fullmatch(r"[a-z]+\d+[a-z]?", token) and re.fullmatch(r"\d+[a-z]?", next_token) and len(next_token) <= 2:
        return True
    return False


def _humanize_atomic_token(token: str) -> str:
    if token in _DISPLAY_TOKEN_MAP:
        return _DISPLAY_TOKEN_MAP[token]
    if token.isalpha():
        return token.capitalize()
    if any(ch.isalpha() for ch in token) and any(ch.isdigit() for ch in token):
        return token.upper()
    return token


def _strip_trailing_build_tokens(tokens: list[str]) -> list[str]:
    trimmed = list(tokens)
    while trimmed:
        if len(trimmed) >= 2 and _is_date_pair(trimmed[-2], trimmed[-1]):
            trimmed = trimmed[:-2]
            continue
        if _is_build_stamp(trimmed[-1]):
            trimmed.pop()
            continue
        break
    return trimmed


def _is_build_stamp(token: str) -> bool:
    if re.fullmatch(r"\d{4}", token):
        return _is_mmdd(token) or _is_yymm(token)
    if re.fullmatch(r"20\d{4}", token):
        return _is_yyyymm(token) or _is_yyyymmdd(token)
    return False


def _is_date_pair(left: str, right: str) -> bool:
    if not re.fullmatch(r"\d{2}", left) or not re.fullmatch(r"\d{2}", right):
        return False
    return _is_mmdd(f"{left}{right}") or _is_yymm(f"{left}{right}")


def _is_mmdd(token: str) -> bool:
    month = int(token[:2])
    day = int(token[2:])
    return 1 <= month <= 12 and 1 <= day <= 31


def _is_yymm(token: str) -> bool:
    year = int(token[:2])
    month = int(token[2:])
    return 20 <= year <= 39 and 1 <= month <= 12


def _is_yyyymm(token: str) -> bool:
    year = int(token[:4])
    month = int(token[4:])
    return 2000 <= year <= 2099 and 1 <= month <= 12


def _is_yyyymmdd(token: str) -> bool:
    year = int(token[:4])
    month = int(token[4:6])
    day = int(token[6:])
    return 2000 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _variant_label(raw_name: str, canonical_name: str) -> str | None:
    raw_signature = " ".join(sorted(normalize_text(raw_name).split()))
    canonical_signature = " ".join(sorted(normalize_text(canonical_name).split()))
    if not raw_signature or raw_signature == canonical_signature:
        return None
    return raw_name


def _provider_slug(provider_norm: str) -> str:
    tokens = set(provider_norm.split())
    if "anthropic" in tokens:
        return "anthropic"
    if "openai" in tokens:
        return "openai"
    if "google" in tokens or "deepmind" in tokens:
        return "google"
    if "zhipu" in tokens:
        return "zhipu-ai"
    if "moonshot" in tokens or "kimi" in tokens:
        return "kimi"
    if "xai" in tokens:
        return "xai"
    return _slugify(provider_norm or "unknown") or "unknown"


__all__ = ["ModelIdentity", "infer_model_identity"]
