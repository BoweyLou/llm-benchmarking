from __future__ import annotations

from typing import Any

PROVENANCE_POLICY_STANDARD = "standard"
PROVENANCE_POLICY_DERIVATIVE_REVIEW = "derivative_review"
PROVENANCE_POLICY_DERIVATIVE_UNVERIFIED = "derivative_unverified"
PROVENANCE_POLICY_LABELS = {
    PROVENANCE_POLICY_STANDARD: "Standard provenance",
    PROVENANCE_POLICY_DERIVATIVE_REVIEW: "Derivative lineage disclosed",
    PROVENANCE_POLICY_DERIVATIVE_UNVERIFIED: "Unverified derivative provenance",
}
PROVENANCE_GAP_LABELS = {
    "unknown_provider": "provider identity is unknown",
    "missing_model_card": "model card link is missing",
    "missing_training_data_summary": "training data summary is missing",
}
PROVENANCE_REVIEW_NOTE = (
    "Derivative model: base model lineage is disclosed, but confirm training provenance, artifact ownership, and security review before production commercial use."
)


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        text_value = _clean_optional_text(value)
        if text_value is not None:
            normalized.append(text_value)
    return normalized


def build_provenance_policy_payload(
    *,
    base_models: Any,
    provider: Any,
    model_card_url: Any,
    training_data_summary: Any,
) -> dict[str, Any]:
    normalized_base_models = _normalize_string_list(base_models)
    derivative_model = bool(normalized_base_models)
    provider_name = _clean_optional_text(provider)
    model_card = _clean_optional_text(model_card_url)
    training_summary = _clean_optional_text(training_data_summary)
    gap_fields: list[str] = []

    if derivative_model:
        if provider_name is None or provider_name.casefold() == "unknown":
            gap_fields.append("unknown_provider")
        if model_card is None:
            gap_fields.append("missing_model_card")
        if training_summary is None:
            gap_fields.append("missing_training_data_summary")

    if not derivative_model:
        policy_class = PROVENANCE_POLICY_STANDARD
        note = None
    elif gap_fields:
        policy_class = PROVENANCE_POLICY_DERIVATIVE_UNVERIFIED
        note = (
            "Unverified derivative provenance: this model is derived from another base model, but "
            f"{_format_gap_labels(gap_fields)}. It is not recommended for production commercial use."
        )
    else:
        policy_class = PROVENANCE_POLICY_DERIVATIVE_REVIEW
        note = PROVENANCE_REVIEW_NOTE

    return {
        "provenance_policy_class": policy_class,
        "provenance_policy_label": PROVENANCE_POLICY_LABELS[policy_class],
        "provenance_policy_note": note,
        "derivative_model": derivative_model,
        "potential_provenance_review": policy_class == PROVENANCE_POLICY_DERIVATIVE_REVIEW,
        "production_provenance_blocked": policy_class == PROVENANCE_POLICY_DERIVATIVE_UNVERIFIED,
        "provenance_gap_fields": gap_fields,
    }


def _format_gap_labels(gap_fields: list[str]) -> str:
    labels = [PROVENANCE_GAP_LABELS.get(field, field.replace("_", " ")) for field in gap_fields]
    if not labels:
        return "required provenance details are incomplete"
    if len(labels) == 1:
        return labels[0]
    return f"{', '.join(labels[:-1])}, and {labels[-1]}"


__all__ = [
    "PROVENANCE_POLICY_DERIVATIVE_REVIEW",
    "PROVENANCE_POLICY_DERIVATIVE_UNVERIFIED",
    "PROVENANCE_POLICY_STANDARD",
    "build_provenance_policy_payload",
]
