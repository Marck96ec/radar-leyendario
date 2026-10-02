from datetime import datetime, timedelta, timezone

from app.domain.enums import SourceType
from app.domain.source_item import SourceItem
from scripts.run_real_radar import select_balanced_items


def build_item(source_name: str, index: int) -> SourceItem:
    return SourceItem(
        title=f"{source_name} article {index}",
        url=f"https://example.test/{source_name}/{index}",
        source_name=source_name,
        published_at=datetime(2026, 1, 10, tzinfo=timezone.utc)
        - timedelta(days=index),
        content="Article content.",
        source_type=SourceType.OFFICIAL,
    )


def test_selection_round_robins_sources_and_caps_each_source() -> None:
    items = [
        build_item("AWS", index)
        for index in range(6)
    ] + [
        build_item("Google", index)
        for index in range(4)
    ] + [
        build_item("GitHub", index)
        for index in range(4)
    ] + [
        build_item("NVIDIA", index)
        for index in range(4)
    ]

    selected = select_balanced_items(items)

    assert len(selected) == 8
    assert {item.source_name for item in selected} == {
        "AWS",
        "GitHub",
        "Google",
        "NVIDIA",
    }
    source_counts = {
        source: sum(item.source_name == source for item in selected)
        for source in {item.source_name for item in selected}
    }
    assert source_counts == {
        "AWS": 2,
        "GitHub": 2,
        "Google": 2,
        "NVIDIA": 2,
    }
    assert len({item.url for item in selected}) == len(selected)


def test_selection_fills_from_single_source_when_no_other_source_exists() -> None:
    selected = select_balanced_items([build_item("AWS", index) for index in range(10)])

    assert len(selected) == 8
    assert [item.title for item in selected] == [
        f"AWS article {index}" for index in range(8)
    ]