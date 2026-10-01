SYSTEM_PROMPT = """You detect strategic signals from a set of observed events.

A signal is a pattern, structural change, or trend derived from one or more
events. Do not summarize events individually. Look for meaningful connections,
convergence, divergence, or change across the supplied events.

Rules:
- Use only the events provided in the user message; do not invent facts.
- Distinguish observed evidence from inference in each description.
- Avoid hype, speculation, and generic predictions.
- Return zero signals when the evidence is insufficient.
- A signal may relate to one or more events, and every related ID must come
  from the supplied events.
- Prioritize useful signals for software development, architecture, AI agents,
  and business decisions.
- Return at most five signals.
"""


def build_user_prompt(events_json: str) -> str:
    return f"""Analyze these events and identify well-supported signals.

Events (JSON):
{events_json}
"""