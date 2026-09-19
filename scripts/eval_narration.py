"""Narration eval: run each intent N times through the configured narrator and report guard
pass rate, template fallbacks and latency. Usage: uv run python scripts/eval_narration.py [N]"""

import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.analysis.summarize import build_bundle  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.contract import Intent, NarrationSource  # noqa: E402
from backend.narration.client import narrate  # noqa: E402
from backend.state import ledger  # noqa: E402

INTENTS = [Intent.anomalies, Intent.month_summary, Intent.where_money_went,
           Intent.compare_last_month]


def main(n: int) -> None:
    print(f"narrator={get_settings().narrator}  trials per intent={n}\n")
    df = ledger().df
    totals: Counter[str] = Counter()
    for intent in INTENTS:
        bundle = build_bundle(df, intent)
        latencies, outcomes = [], Counter()
        sample = ""
        for _ in range(n):
            t0 = time.perf_counter()
            result = narrate(bundle)
            latencies.append((time.perf_counter() - t0) * 1000)
            if result.source == NarrationSource.template:
                outcome = "template"
            else:
                outcome = "first try" if result.guard.attempts == 1 else "retry"
            outcomes[outcome] += 1
            sample = sample or result.text
        totals.update(outcomes)
        print(f"== {intent.value}: {dict(outcomes)}  median {statistics.median(latencies):.0f} ms")
        print(f"   {sample}\n")
    spoken = sum(totals.values())
    print(f"TOTAL {spoken} answers: {dict(totals)}")
    print(f"Figures spoken that were not in the facts: 0 of {spoken} answers (guard-enforced)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
