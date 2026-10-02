def normalize_percentage_score(value: float) -> float:
    """Convert an LLM score in normalized form to the domain percentage scale."""
    if 0 < value <= 1:
        return value * 100
    return value