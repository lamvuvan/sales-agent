"""LLM NLU extractor: raw Vietnamese text -> NluOutput."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from ..api.schemas import NluOutput
from .client import chat_json_schema, load_prompt

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent / "prompts" / "schemas" / "nlu_output.json"

_SYSTEM = "Bạn là module NLU cho trợ lý nhà thuốc Việt Nam. Chỉ trả JSON."


@lru_cache(maxsize=1)
def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def extract_intent_and_payload(raw_text: str) -> NluOutput:
    """Run NLU on raw_text. Raises on LLM or validation failure."""
    prompt = load_prompt("nlu_intent_extract").replace("{raw_text}", raw_text)
    data = chat_json_schema(
        system=_SYSTEM,
        user=prompt,
        schema_name="nlu_output",
        schema=_load_schema(),
    )
    return NluOutput.model_validate(data)
