from app.graph.state import RadarState
from app.services.evidence_validation import validate_evidence as validate_evidence_service
from app.services.ports.llm import LLMProvider


async def validate_evidence(
    state: RadarState,
    llm_provider: LLMProvider | None = None,
) -> dict[str, object]:
    if state["signals"] and llm_provider is None:
        raise ValueError("llm_provider is required when signals are present")

    evidence = (
        await validate_evidence_service(state["signals"], state["events"], llm_provider)
        if state["signals"]
        else []
    )
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("validate_evidence")
    metadata["execution_trace"] = execution_trace
    metadata["evidence_count"] = len(evidence)
    return {"evidence": evidence, "metadata": metadata}


def build_validate_evidence_node(llm_provider: LLMProvider | None):
    async def node(state: RadarState) -> dict[str, object]:
        return await validate_evidence(state, llm_provider)

    return node