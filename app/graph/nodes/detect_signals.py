from app.services.ports.llm import LLMProvider
from app.services.signal_detection import detect_signals as detect_signals_service
from app.graph.state import RadarState


async def detect_signals(
    state: RadarState,
    llm_provider: LLMProvider | None = None,
) -> dict[str, object]:
    if state["events"] and llm_provider is None:
        raise ValueError("llm_provider is required when events are present")

    signals = (
        await detect_signals_service(state["events"], llm_provider)
        if state["events"]
        else []
    )
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("detect_signals")
    metadata["execution_trace"] = execution_trace
    return {"signals": signals, "metadata": metadata}


def build_detect_signals_node(llm_provider: LLMProvider | None):
    async def node(state: RadarState) -> dict[str, object]:
        return await detect_signals(state, llm_provider)

    return node