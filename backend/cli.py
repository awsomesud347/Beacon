"""python -m backend.cli "what's unusual?" [--bundle] [--narrator template|cloud|local]"""

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask Beacon a question from the terminal.")
    parser.add_argument("question", nargs="+")
    parser.add_argument("--bundle", action="store_true", help="also print the fact bundle")
    parser.add_argument("--narrator", choices=["cloud", "local", "template"])
    parser.add_argument("--discreet", action="store_true")
    parser.add_argument("--dataset", help="CSV path (default: DATASET_PATH)")
    args = parser.parse_args()

    if args.narrator:
        os.environ["NARRATOR"] = args.narrator
    if args.dataset:
        os.environ["DATASET_PATH"] = args.dataset
    os.environ["STUB_MODE"] = "0"

    from backend import service

    turn = service.answer(" ".join(args.question), discreet=args.discreet)
    print(turn.narration)
    print(f"[{turn.intent.value} | {turn.narration_source.value} | guard "
          f"{'passed' if turn.guard.passed else 'blocked ' + ', '.join(turn.guard.rejected_tokens)}"
          f" | {turn.latency_ms.total} ms]", file=sys.stderr)
    if args.bundle and turn.fact_bundle:
        print(turn.fact_bundle.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
