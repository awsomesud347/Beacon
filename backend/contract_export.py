"""Renders the committed contract artifacts. Used by scripts/export_contract.py and tests."""

import json
from pathlib import Path

from backend.contract import Turn
from backend.routes.llm_proxy import sse_chunks

CONTRACT_DIR = Path(__file__).resolve().parent.parent / "contract"
OPENAPI_PATH = CONTRACT_DIR / "openapi.json"
SSE_EXAMPLE_PATH = CONTRACT_DIR / "examples" / "sse_chunks.txt"


def render_openapi() -> str:
    from backend.main import create_app

    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"


def render_sse_example() -> str:
    turn = Turn.model_validate_json((CONTRACT_DIR / "examples" / "turn_anomalies.json").read_text())
    return "".join(sse_chunks(turn.narration, "chatcmpl-example", 1789840800))


def write_all() -> None:
    OPENAPI_PATH.write_text(render_openapi(), encoding="utf-8", newline="\n")
    SSE_EXAMPLE_PATH.write_text(render_sse_example(), encoding="utf-8", newline="\n")
