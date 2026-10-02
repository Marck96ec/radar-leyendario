from app.graph.state import RadarState
from app.services.opportunity_generation import (
    generate_opportunities as generate_opportunities_service,
)
from app.services.ports.llm import LLMProvider


async def generate_opportunities(
    state: RadarState,
    llm_provider: LLMProvider | None = None,
) -> dict[str, object]:
    if state["signals"] and llm_provider is None:
        raise ValueError("llm_provider is required when signals are present")

    opportunities = (
        await generate_opportunities_service(
            state["signals"], state["evidence"], state["source_items"], llm_provider
        )
        if state["signals"]
        else []
    )
    metadata = dict(state["metadata"])
    execution_trace = list(metadata.get("execution_trace", []))
    execution_trace.append("generate_opportunities")
    metadata["execution_trace"] = execution_trace
    metadata["opportunity_count"] = len(opportunities)
    return {"opportunities": opportunities, "metadata": metadata}


def build_generate_opportunities_node(llm_provider: LLMProvider | None):
    async def node(state: RadarState) -> dict[str, object]:
        return await generate_opportunities(state, llm_provider)

    return node