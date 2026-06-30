"""Inference location normalization helpers shared by API workflows."""

from __future__ import annotations

import re

REGION_COUNTRY_OVERRIDES = {
    "global": "Global",
    "af-south-1": "South Africa",
    "ap-east-1": "Hong Kong",
    "ap-east-2": "Taiwan",
    "ap-northeast-1": "Japan",
    "ap-northeast-2": "South Korea",
    "ap-northeast-3": "Japan",
    "ap-south-1": "India",
    "ap-south-2": "India",
    "ap-southeast-1": "Singapore",
    "ap-southeast-2": "Australia",
    "ap-southeast-3": "Indonesia",
    "ap-southeast-4": "Australia",
    "ap-southeast-5": "Malaysia",
    "ap-southeast-6": "New Zealand",
    "asia-east1": "Taiwan",
    "asia-east2": "Hong Kong",
    "asia-northeast1": "Japan",
    "asia-northeast2": "Japan",
    "asia-northeast3": "South Korea",
    "asia-south1": "India",
    "asia-south2": "India",
    "asia-southeast1": "Singapore",
    "asia-southeast2": "Indonesia",
    "australiaeast": "Australia",
    "australiasoutheast": "Australia",
    "australia-southeast1": "Australia",
    "australia-southeast2": "Australia",
    "brazilsouth": "Brazil",
    "brazilsoutheast": "Brazil",
    "ca-central-1": "Canada",
    "ca-west-1": "Canada",
    "canadacentral": "Canada",
    "canadaeast": "Canada",
    "centralindia": "India",
    "centralus": "United States",
    "eastasia": "Hong Kong",
    "eastus": "United States",
    "eastus2": "United States",
    "eu-central-1": "Germany",
    "eu-central-2": "Switzerland",
    "eu-north-1": "Sweden",
    "eu-south-1": "Italy",
    "eu-south-2": "Spain",
    "eu-west-1": "Ireland",
    "eu-west-2": "United Kingdom",
    "eu-west-3": "France",
    "europe-central2": "Poland",
    "europe-north1": "Finland",
    "europe-southwest1": "Spain",
    "europe-west1": "Belgium",
    "europe-west2": "United Kingdom",
    "europe-west3": "Germany",
    "europe-west4": "Netherlands",
    "europe-west6": "Switzerland",
    "europe-west8": "Italy",
    "europe-west9": "France",
    "europe-west10": "Germany",
    "europe-west12": "Italy",
    "francecentral": "France",
    "germanynorth": "Germany",
    "germanywestcentral": "Germany",
    "il-central-1": "Israel",
    "israelcentral": "Israel",
    "japaneast": "Japan",
    "japanwest": "Japan",
    "koreacentral": "South Korea",
    "koreasouth": "South Korea",
    "me-central-1": "United Arab Emirates",
    "me-central1": "Qatar",
    "me-south-1": "Bahrain",
    "me-west1": "Israel",
    "mexicocentral": "Mexico",
    "mx-central-1": "Mexico",
    "northamerica-northeast1": "Canada",
    "northamerica-northeast2": "Canada",
    "northcentralus": "United States",
    "northeurope": "Ireland",
    "norwayeast": "Norway",
    "norwaywest": "Norway",
    "polandcentral": "Poland",
    "qatarcentral": "Qatar",
    "sa-east-1": "Brazil",
    "southafricanorth": "South Africa",
    "southafricawest": "South Africa",
    "southcentralus": "United States",
    "southeastasia": "Singapore",
    "southindia": "India",
    "southamerica-east1": "Brazil",
    "southamerica-west1": "Chile",
    "swedencentral": "Sweden",
    "switzerlandnorth": "Switzerland",
    "switzerlandwest": "Switzerland",
    "uaecentral": "United Arab Emirates",
    "uaeeast": "United Arab Emirates",
    "uaenorth": "United Arab Emirates",
    "uksouth": "United Kingdom",
    "ukwest": "United Kingdom",
    "us-central1": "United States",
    "us-east-1": "United States",
    "us-east-2": "United States",
    "us-east1": "United States",
    "us-east4": "United States",
    "us-east5": "United States",
    "us-south1": "United States",
    "us-west-1": "United States",
    "us-west-2": "United States",
    "us-west1": "United States",
    "us-west2": "United States",
    "us-west3": "United States",
    "us-west4": "United States",
    "westcentralus": "United States",
    "westeurope": "Netherlands",
    "westindia": "India",
    "westus": "United States",
    "westus2": "United States",
    "westus3": "United States",
}

REGION_COUNTRY_KEYWORDS = (
    ("australia", "Australia"),
    ("sweden", "Sweden"),
    ("france", "France"),
    ("germany", "Germany"),
    ("switzerland", "Switzerland"),
    ("poland", "Poland"),
    ("norway", "Norway"),
    ("japan", "Japan"),
    ("korea", "South Korea"),
    ("india", "India"),
    ("canada", "Canada"),
    ("mexico", "Mexico"),
    ("brazil", "Brazil"),
    ("israel", "Israel"),
    ("uae", "United Arab Emirates"),
    ("qatar", "Qatar"),
    ("singapore", "Singapore"),
)

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def get_inference_country_from_region(region: str | None) -> str:
    normalized = str(region or "").strip().lower()
    if not normalized:
        return ""

    if normalized in REGION_COUNTRY_OVERRIDES:
        return REGION_COUNTRY_OVERRIDES[normalized]

    for keyword, label in REGION_COUNTRY_KEYWORDS:
        if keyword in normalized:
            return label

    if normalized.startswith("us-gov") or normalized.startswith("us-"):
        return "United States"
    if normalized.startswith("ca-"):
        return "Canada"
    if normalized.startswith("australia-"):
        return "Australia"
    if normalized.startswith("northamerica-northeast"):
        return "Canada"
    if normalized.startswith("southamerica-east"):
        return "Brazil"
    if normalized.startswith("southamerica-west"):
        return "Chile"

    return ""


def inference_location_key(label: str | None) -> str:
    normalized = str(label or "").strip().lower()
    if not normalized:
        return ""
    return _NON_ALNUM_RE.sub("-", normalized).strip("-")


def compare_inference_location_labels(left_value: str | None, right_value: str | None) -> int:
    left = str(left_value or "")
    right = str(right_value or "")
    if left == right:
        return 0
    left_rank = _inference_location_rank(left)
    right_rank = _inference_location_rank(right)
    if left_rank != right_rank:
        return left_rank - right_rank
    return -1 if left < right else 1


def sort_inference_countries(countries: list[str]) -> list[str]:
    unique = sorted({str(country or "").strip() for country in countries if str(country or "").strip()})
    return sorted(unique, key=_sort_key)


def _sort_key(label: str) -> tuple[int, str]:
    return (_inference_location_rank(label), label)


def _inference_location_rank(location: str | None) -> int:
    normalized = str(location or "").strip()
    if not normalized:
        return 3
    if normalized == "Australia":
        return 0
    if normalized == "Global":
        return 2
    return 1


__all__ = [
    "compare_inference_location_labels",
    "get_inference_country_from_region",
    "inference_location_key",
    "sort_inference_countries",
]
