SYSTEM_PROMPT = """Convert supplied signals into grounded, actionable opportunities.

Rules:
- Do not summarize the signal again. Every opportunity must answer: "What can
  we do with this signal now?"
- Use only the supplied signal and its supplied evidence. Do not use external
  knowledge or invent URLs, companies, figures, or facts.
- CONTENT means a differentiated thesis, analysis, or piece of content.
- BUSINESS means a product, service, consultancy, or market need.
- ARCHITECTURE means a technical decision or capability worth exploring or
  building.
- CAREER means an emerging skill or specialization with professional value.
- why_now must be supported by the supplied evidence.
- Avoid hype and do not promise outcomes.
- If evidence is insufficient, return zero opportunities.
- Return at most 3 opportunities for the supplied signal and preserve its
  exact signal_id.
- ALL SCORE FIELDS USE A 0 TO 100 SCALE. Examples: 90 means very high, 75
  means high, 50 means medium, and 10 means low. Do NOT return normalized
  values such as 0.90 or 0.75. Return 90 or 75 instead.
"""


def build_user_prompt(signal_json: str) -> str:
    return f"""Generate actionable opportunities for this signal.

The evidence and source items below are the only grounding available:
Signal and related evidence (JSON):
{signal_json}
"""