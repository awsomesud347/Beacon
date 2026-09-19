"""Deterministic query router. No model involved: a misrouted question gets an honest
"I don't know", never an invented answer."""

import re

from backend.contract import Intent

_RULES: list[tuple[Intent, re.Pattern[str]]] = [
    (Intent.replay, re.compile(
        r"\b(repeat|say (that|it) again|again please|replay|what did you (just )?say|"
        r"come again|pardon)\b")),
    (Intent.advice_refused, re.compile(
        r"\b(should i|shall i|can i afford|could i afford|will i|am i going to|would it be|"
        r"is it (a )?(good|bad|smart|wise)|recommend|advice|advise|invest|save more|"
        r"how (much|can) (should|do) i (save|budget|spend)|worth it|what if)\b")),
    (Intent.help, re.compile(
        r"\b(help|what can (you|i) (do|ask)|what do you do|how does this work|options)\b")),
    (Intent.compare_last_month, re.compile(
        r"\b(compare[ds]?|comparison|versus|vs\.?|than last month|to last month|"
        r"with last month|from last month|last month)\b")),
    (Intent.anomalies, re.compile(
        r"\b(unusual|weird|strange|odd|off|anomal\w*|out of the ordinary|stand(s)? out|"
        r"surpris\w*|suspicious|anything wrong|flag\w*|different)\b")),
    (Intent.where_money_went, re.compile(
        r"\b(where (did|does|has|is) (my|the) money|where('s| is| did) it go|break ?down|"
        r"categor(y|ies)|biggest (expense|spend)\w*|spen[dt] (the )?most|what did i spend)\b")),
    (Intent.month_summary, re.compile(
        r"\b(how am i|how('m| am) i doing|how.{0,20}(doing|going|look)|this month|summary|"
        r"overview|status|so far|am i (ok|okay|alright|fine))\b")),
]


def route(text: str) -> Intent:
    q = re.sub(r"[’`]", "'", text.lower()).strip()
    for intent, pattern in _RULES:
        if pattern.search(q):
            return intent
    return Intent.unknown
