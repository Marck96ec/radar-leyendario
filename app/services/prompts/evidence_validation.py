SYSTEM_PROMPT = """You validate evidence for supplied signals using only supplied source items.

Rules:
- Evaluate only the signals and source items in the user message; use no
  external knowledge.
- A source may SUPPORTINGly support a signal or COUNTER contradict or weaken it.
- Use only the exact signal_id and source_item_id values supplied. Never invent
  either ID.
- A source is not evidence merely because it shares words with a signal.
- The explanation must state why the source specifically supports or weakens
  that signal.
- Avoid false certainty. Confidence is confidence in the evidence-signal
  relationship, not the general quality of the article.
- Return no evidence when the supplied sources are insufficient; do not invent
  evidence.
- ALL SCORE FIELDS USE A 0 TO 100 SCALE. Examples: 90 means very high, 75
  means high, 50 means medium, and 10 means low. Do NOT return normalized
  values such as 0.90 or 0.75. Return 90 or 75 instead.
"""


def build_user_prompt(signals_and_sources_json: str) -> str:
    return f"""Assess the evidence relationships for these signals and their eligible sources.

The sources listed under each signal are the only candidates for that signal.
Do not use sources listed under another signal.

Signals and eligible source items (JSON):
{signals_and_sources_json}
"""