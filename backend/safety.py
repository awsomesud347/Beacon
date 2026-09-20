"""The one thing that is not left to the model.

Routing is the planner's job now. But build-spec §1.3 requires the advice refusal to be
hardcoded rather than trusted to a prompt: advice about money, spoken confidently to someone
who cannot check it, is the failure this project least wants. These few patterns run before
the planner and only ever *add* a refusal — they never choose an answer.
"""

import re

ADVICE = re.compile(
    r"\b(should i|shall i|ought i|can i afford|could i afford|do you recommend|"
    r"what do you recommend|give me advice|what should i do|is it worth|worth it|"
    r"will i (be able|have|afford)|what will i (spend|have))\b")


def is_advice(text: str) -> bool:
    return bool(ADVICE.search(re.sub(r"[’`]", "'", text.lower())))
