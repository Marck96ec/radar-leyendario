from typing import TypedDict

from app.domain.event import Event
from app.domain.evidence import Evidence
from app.domain.opportunity import Opportunity
from app.domain.signal import Signal
from app.domain.source_item import SourceItem


class RadarState(TypedDict):
    run_id: str
    source_items: list[SourceItem]
    events: list[Event]
    signals: list[Signal]
    evidence: list[Evidence]
    opportunities: list[Opportunity]
    ranked_opportunities: list[Opportunity]
    errors: list[str]
    metadata: dict[str, object]