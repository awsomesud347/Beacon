"""Hardcoded answers that never go through the model (build-spec §1.3)."""

ADVICE = (
    "I can't give financial advice, but I can tell you what you've spent, where it went, "
    "and what's unusual this month."
)
UNKNOWN = (
    "I don't know that. I can tell you what's unusual, how your month is going, "
    "where your money went, or how it compares to last month."
)
HELP = (
    "You can ask me what's unusual, how you're doing this month, where your money went, "
    "or how this month compares to last month. Say repeat to hear the last answer again."
)
NOTHING_TO_REPEAT = "There's nothing to repeat yet. Try asking what's unusual this month."
NO_DATA = "I don't have any transactions for this month yet."

IDENTITY = (
    "I'm Beacon. I answer questions about this transaction history out loud. Every number I "
    "say is calculated from the data and checked before I speak it. This is a synthetic "
    "demo ledger, not anyone's real account."
)


def unsupported(examples: list[str] | None = None) -> str:
    """Understood the question, but it is outside what we can answer. Never guess."""
    suggestions = examples or ["what's unusual this month", "how much you spent on groceries"]
    return (f"I can't answer that from this transaction history. I can tell you "
            f"{suggestions[0]}, or {suggestions[1]}.")
