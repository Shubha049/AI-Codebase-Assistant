from __future__ import annotations


def confidence(
    scores: list[float],
    *,
    provider_name: str = "mock",
    threshold: float | None = None,
) -> str:
    if not scores:
        return "Low"
    top = max(scores)
    is_mock = provider_name.lower().strip() == "mock"

    if threshold is not None:
        med_thresh = threshold
        high_thresh = max(0.60 if is_mock else 0.75, threshold * 1.5 if is_mock else threshold)
    else:
        med_thresh = 0.08 if is_mock else 0.25
        high_thresh = 0.30 if is_mock else 0.70

    if top >= high_thresh and len(scores) >= 2:
        return "High"
    if top >= med_thresh:
        return "Medium"
    return "Low"

