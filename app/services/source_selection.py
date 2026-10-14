from collections import Counter

from app.domain.source_item import SourceItem


MAX_ANALYSIS_ITEMS = 12
MAX_ITEMS_PER_SOURCE = 2


def select_balanced_items(
    source_items: list[SourceItem],
    max_items: int = MAX_ANALYSIS_ITEMS,
    max_per_source: int = MAX_ITEMS_PER_SOURCE,
) -> list[SourceItem]:
    items_by_category: dict[str, dict[str, list[SourceItem]]] = {}
    for item in source_items:
        category = item.category or "UNCATEGORIZED"
        items_by_category.setdefault(category, {}).setdefault(item.source_name, []).append(item)

    for sources in items_by_category.values():
        for items in sources.values():
            items.sort(key=lambda item: item.published_at, reverse=True)

    category_names = sorted(
        items_by_category,
        key=lambda category: max(
            item.published_at
            for items in items_by_category[category].values()
            for item in items
        ),
        reverse=True,
    )
    source_positions: dict[tuple[str, str], int] = {
        (category, source_name): 0
        for category, sources in items_by_category.items()
        for source_name in sources
    }
    selected: list[SourceItem] = []
    selected_urls: set[str] = set()
    selected_per_source: Counter[str] = Counter()

    while len(selected) < max_items:
        added_in_round = False
        for category in category_names:
            sources = items_by_category[category]
            source_names = sorted(
                sources,
                key=lambda source_name: sources[source_name][0].published_at,
                reverse=True,
            )
            for source_name in source_names:
                if selected_per_source[source_name] >= max_per_source:
                    continue
                items = sources[source_name]
                position_key = (category, source_name)
                while source_positions[position_key] < len(items):
                    item = items[source_positions[position_key]]
                    source_positions[position_key] += 1
                    if item.url in selected_urls:
                        continue
                    selected.append(item)
                    selected_urls.add(item.url)
                    selected_per_source[source_name] += 1
                    added_in_round = True
                    break
                if len(selected) == max_items:
                    return selected
        if not added_in_round:
            break

    return selected
