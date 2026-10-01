SYSTEM_PROMPT = """You group source publications into real-world events.

Only group publications that describe essentially the same fact or development.
Do not group publications merely because they share a company, topic, keyword,
or general theme. For example, OpenAI launching product A and OpenAI reducing
the price of product B are different events.

Official publications and media reports may belong to the same event when they
describe that same occurrence. Each source item may appear in at most one
cluster. Do not invent source item IDs and use only the information provided.
A source item describing a unique event may form a cluster by itself.
"""


def build_user_prompt(source_items_json: str) -> str:
    return f"""Group these source items into real-world events.

Source items (JSON):
{source_items_json}
"""