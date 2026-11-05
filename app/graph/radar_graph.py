import inspect
import logging
from collections.abc import Callable

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes.cluster_events import build_cluster_events_node
from app.graph.nodes.collect_sources import build_collect_sources_node
from app.graph.nodes.detect_signals import build_detect_signals_node
from app.graph.nodes.generate_opportunities import build_generate_opportunities_node
from app.graph.nodes.normalize_sources import normalize_sources
from app.graph.nodes.rank_opportunities import rank_opportunities
from app.graph.nodes.validate_evidence import build_validate_evidence_node
from app.graph.state import RadarState
from app.services.ports.llm import LLMProvider
from app.services.ports.source import SourceProvider


logger = logging.getLogger(__name__)


def _instrument_node(name: str, node: Callable):
    if inspect.iscoroutinefunction(node):

        async def async_node(state):
            try:
                return await node(state)
            except Exception:
                logger.exception(
                    "Radar node failed",
                    extra={"run_id": state.get("run_id"), "node": name},
                )
                raise

        return async_node

    def sync_node(state):
        try:
            return node(state)
        except Exception:
            logger.exception(
                "Radar node failed",
                extra={"run_id": state.get("run_id"), "node": name},
            )
            raise

    return sync_node


def build_radar_graph(
    llm_provider: LLMProvider | None = None,
    source_provider: SourceProvider | None = None,
) -> CompiledStateGraph:
    graph = StateGraph(RadarState)

    graph.add_node(
        "collect_sources",
        _instrument_node("collect_sources", build_collect_sources_node(source_provider)),
    )
    graph.add_node("normalize_sources", _instrument_node("normalize_sources", normalize_sources))
    graph.add_node(
        "cluster_events",
        _instrument_node("cluster_events", build_cluster_events_node(llm_provider)),
    )
    graph.add_node(
        "detect_signals",
        _instrument_node("detect_signals", build_detect_signals_node(llm_provider)),
    )
    graph.add_node(
        "validate_evidence",
        _instrument_node("validate_evidence", build_validate_evidence_node(llm_provider)),
    )
    graph.add_node(
        "generate_opportunities",
        _instrument_node(
            "generate_opportunities", build_generate_opportunities_node(llm_provider)
        ),
    )
    graph.add_node("rank_opportunities", _instrument_node("rank_opportunities", rank_opportunities))

    graph.add_edge(START, "collect_sources")
    graph.add_edge("collect_sources", "normalize_sources")
    graph.add_edge("normalize_sources", "cluster_events")
    graph.add_edge("cluster_events", "detect_signals")
    graph.add_edge("detect_signals", "validate_evidence")
    graph.add_edge("validate_evidence", "generate_opportunities")
    graph.add_edge("generate_opportunities", "rank_opportunities")
    graph.add_edge("rank_opportunities", END)

    return graph.compile()