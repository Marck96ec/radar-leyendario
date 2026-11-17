from app.services.ports.llm import LLMProvider
from app.services.signal_detection import detect_signals as detect_signals_service
from app.graph.state import RadarState


async def detect_signals(
    state: RadarState,
    llm_provider: LLMProvider | None = None,
) -> dict[str, object]:
    if state["events"] and llm_provider is None:
        raise ValueError("llm_provider is required when events are present")

    signal_metrics: dict[str, object] = {}
    signals = (
        await detect_signals_service(
            state["events"], llm_provider, metrics=signal_metrics
        )
        if state["events"]
        else []
    )
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("detect_signals")
    metadata["execution_trace"] = execution_trace
    metadata["signal_metrics"] = signal_metrics
    quality_metrics = dict(metadata.get("quality_metrics", {}))
    quality_metrics["signals"] = len(signals)
    quality_metrics["signal_candidates_discarded"] = signal_metrics.get(
        "signals_discarded", 0
    )
    quality_metrics["candidates_discarded"] = sum(
        int(quality_metrics.get(key, 0))
        for key in ("signal_candidates_discarded", "evidence_candidates_discarded")
    )
    metadata["quality_metrics"] = quality_metrics
    return {"signals": signals, "metadata": metadata}


def build_detect_signals_node(llm_provider: LLMProvider | None):
    async def node(state: RadarState) -> dict[str, object]:
        return await detect_signals(state, llm_provider)

    return node