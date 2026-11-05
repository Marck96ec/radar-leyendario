from app.core.settings import Settings


def test_rss_volume_settings_have_sensible_defaults() -> None:
    settings = Settings()

    assert settings.RSS_MAX_ITEMS_PER_FEED == 10
    assert settings.RSS_MAX_ITEM_AGE_HOURS == 72
    assert settings.RSS_MAX_TOTAL_ITEMS == 50


def test_rss_volume_settings_can_be_overridden_via_environment(monkeypatch) -> None:
    monkeypatch.setenv("RSS_MAX_ITEMS_PER_FEED", "25")
    monkeypatch.setenv("RSS_MAX_ITEM_AGE_HOURS", "48")
    monkeypatch.setenv("RSS_MAX_TOTAL_ITEMS", "120")

    settings = Settings()

    assert settings.RSS_MAX_ITEMS_PER_FEED == 25
    assert settings.RSS_MAX_ITEM_AGE_HOURS == 48
    assert settings.RSS_MAX_TOTAL_ITEMS == 120
