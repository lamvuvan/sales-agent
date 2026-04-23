"""OpenAI client wrapper: chat completions + embeddings."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from openai import OpenAI

from ..config import get_settings

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    s = get_settings()
    return OpenAI(api_key=s.openai_api_key, timeout=s.llm_timeout_s)


@lru_cache(maxsize=16)
def load_prompt(name: str) -> str:
    """Load a prompt template from sales_agent/llm/prompts/<name>.md."""
    return (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")


def chat(
    system: str,
    user: str,
    *,
    model: str | None = None,
    temperature: float = 0.2,
) -> str:
    """Call chat completions and return the assistant message content."""
    s = get_settings()
    model = model or s.llm_model
    resp = get_client().chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def embed(texts: list[str], *, model: str | None = None) -> list[list[float]]:
    """Return embeddings for a batch of texts."""
    if not texts:
        return []
    s = get_settings()
    model = model or s.embedding_model
    resp = get_client().embeddings.create(model=model, input=texts)
    return [d.embedding for d in resp.data]


def embed_one(text: str, *, model: str | None = None) -> list[float]:
    return embed([text], model=model)[0]
