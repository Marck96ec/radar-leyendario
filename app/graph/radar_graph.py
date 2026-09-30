from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes.cluster_events import cluster_events
from app.graph.nodes.collect_sources import collect_sources
from app.graph.nodes.detect_signals import detect_signals
from app.graph.nodes.generate_opportunities import generate_opportunities
from app.graph.nodes.normalize_sources import normalize_sources
from app.graph.nodes.rank_opportunities import rank_opportunities
from app.graph.nodes.validate_evidence import validate_evidence
from app.graph.state import RadarState


def build_radar_graph() -> CompiledStateGraph:
    graph = StateGraph(RadarState)

    graph.add_node("collect_sources", collect_sources)
    graph.add_node("normalize_sources", normalize_sources)
    graph.add_node("cluster_events", cluster_events)
    graph.add_node("detect_signals", detect_signals)
    graph.add_node("validate_evidence", validate_evidence)
    graph.add_node("generate_opportunities", generate_opportunities)
    graph.add_node("rank_opportunities", rank_opportunities)

    graph.add_edge(START, "collect_sources")
    graph.add_edge("collect_sources", "normalize_sources")
    graph.add_edge("normalize_sources", "cluster_events")
    graph.add_edge("cluster_events", "detect_signals")
    graph.add_edge("detect_signals", "validate_evidence")
    graph.add_edge("validate_evidence", "generate_opportunities")
    graph.add_edge("generate_opportunities", "rank_opportunities")
    graph.add_edge("rank_opportunities", END)

    return graph.compile()