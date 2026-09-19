"""narrate(fact_bundle) -> narration. The only place a language model is called.

cloud = NVIDIA NIM (Nemotron), local = any OpenAI-compatible local server, template = no model.
The model sees only the fact bundle. Its output must pass the numeric guard; one retry, then
the deterministic template.
"""

import logging
import re
from dataclasses import dataclass

from openai import OpenAI

from backend.config import get_settings
from backend.contract import FactBundle, GuardResult, NarrationSource
from backend.narration import guard, prompts, templates

log = logging.getLogger("beacon.narration")
_THINK = re.compile(r"<think>.*?</think>", re.S)
TIMEOUT_S = 8.0


@dataclass
class Narration:
    text: str
    source: NarrationSource
    guard: GuardResult


def _client() -> tuple[OpenAI, str] | None:
    s = get_settings()
    if s.narrator == "cloud" and s.nvidia_api_key and s.nemotron_model:
        return OpenAI(base_url=s.nemotron_base_url, api_key=s.nvidia_api_key,
                      timeout=TIMEOUT_S, max_retries=0), s.nemotron_model
    if s.narrator == "local" and s.local_llm_model:
        return OpenAI(base_url=s.local_llm_base_url, api_key="local",
                      timeout=TIMEOUT_S, max_retries=0), s.local_llm_model
    return None


def _clean(text: str) -> str:
    text = _THINK.sub("", text or "")
    text = re.sub(r"[*_#`]", "", text)
    return " ".join(text.split())


def _complete(client: OpenAI, model: str, messages: list[dict]) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
        max_tokens=220,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    return _clean(resp.choices[0].message.content)


def template(bundle: FactBundle, discreet: bool = False, attempts: int = 0,
             rejected: list[str] | None = None) -> Narration:
    return Narration(
        text=templates.render(bundle, discreet),
        source=NarrationSource.template,
        guard=GuardResult(passed=not rejected, attempts=attempts, rejected_tokens=rejected or []),
    )


def narrate(bundle: FactBundle, discreet: bool = False) -> Narration:
    configured = None if discreet else _client()
    if configured is None:
        return template(bundle, discreet)
    client, model = configured
    intent = bundle.query_type.value
    messages = [
        {"role": "system", "content": prompts.SYSTEM},
        {"role": "user", "content": prompts.user_message(bundle.model_dump_json(), intent)},
    ]
    rejected: list[str] = []
    attempts = 0
    try:
        for attempt in (1, 2):
            text = _complete(client, model, messages)
            attempts = attempt
            result = guard.check(text, bundle)
            guard.record(intent, attempt, result, text)
            if result.passed and text:
                return Narration(text, NarrationSource.model,
                                 GuardResult(passed=True, attempts=attempt))
            rejected += result.rejected
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": prompts.RETRY.format(rejected=", ".join(rejected))},
            ]
    except Exception:
        log.exception("narration model call failed; using template")
    return template(bundle, attempts=attempts, rejected=rejected)
