import pytest

from app.services.score_normalization import normalize_percentage_score


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, 0),
        (0.01, 1),
        (0.5, 50),
        (0.87, 87),
        (1, 100),
        (50, 50),
        (87, 87),
        (100, 100),
    ],
)
def test_normalize_percentage_score(value: float, expected: float) -> None:
    assert normalize_percentage_score(value) == expected