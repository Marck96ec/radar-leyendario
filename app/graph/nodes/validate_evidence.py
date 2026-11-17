from app.graph.state import RadarState
from app.services.evidence_validation import validate_evidence as validate_evidence_service
from app.services.ports.llm import LLMProvider


async def validate_evidence(
    state: RadarState,
    llm_provider: LLMProvider | None = None,
) -> dict[str, object]:
    if state["signals"] and llm_provider is None:
        raise ValueError("llm_provider is required when signals are present")

    evidence_metrics: dict[str, object] = {}
    evidence = (
        await validate_evidence_service(
            state["signals"],
            state["events"],
            llm_provider,
            metrics=evidence_metrics,
        )
        if state["signals"]
        else []
    )
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("validate_evidence")
    metadata["execution_trace"] = execution_trace
    metadata["evidence_count"] = len(evidence)
    metadata["evidence_metrics"] = evidence_metrics
    quality_metrics = dict(metadata.get("quality_metrics", {}))
    quality_metrics.update(
        {
            "eligible_sources": evidence_metrics.get("eligible_sources", 0),
            "evidence_proposed": evidence_metrics.get("evidence_proposed", 0),
            "evidence_accepted": len(evidence),
            "evidence_candidates_discarded": evidence_metrics.get(
                "candidates_discarded", 0
            ),
        }
    )
    quality_metrics["candidates_discarded"] = sum(
        int(quality_metrics.get(key, 0))
        for key in ("signal_candidates_discarded", "evidence_candidates_discarded")
    )
    metadata["quality_metrics"] = quality_metrics
    if state["signals"] and not evidence:
        metadata["evidence_warning"] = (
            "No se aceptaron evidencias: ninguna relación propuesta por el modelo "
            "superó la validación estricta de señales y fuentes reales."
        )
    return {"evidence": evidence, "metadata": metadata}


def build_validate_evidence_node(llm_provider: LLMProvider | None):
    async def node(state: RadarState) -> dict[str, object]:
        return await validate_evidence(state, llm_provider)

    return node