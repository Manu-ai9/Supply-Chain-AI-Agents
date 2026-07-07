"""
llm_utils.py
Optional LLM-backed reasoning layer.

Each agent can produce its structured output two ways:
  1. LLM-driven: if ANTHROPIC_API_KEY is set, the agent calls Claude with
     .with_structured_output(<PydanticModel>) so the model's response is
     forced into the exact schema the next agent expects.
  2. Rule-based fallback: if no API key is present, a deterministic
     heuristic produces the same schema, so the whole pipeline still runs
     end-to-end with no external dependency.

This mirrors how real agent systems are built: start with deterministic
logic for the parts you can specify exactly, and layer in LLM reasoning
for the parts that genuinely benefit from open-ended judgment (here:
the natural-language "reasoning" explanations and edge-case calls).
"""

import os
from typing import Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_llm_cache = {}


def llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def get_structured_llm(schema: Type[T]):
    """Returns a Claude client bound to a structured output schema, or None if no API key."""
    if not llm_available():
        return None
    cache_key = schema.__name__
    if cache_key not in _llm_cache:
        from langchain_anthropic import ChatAnthropic
        base = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
        _llm_cache[cache_key] = base.with_structured_output(schema)
    return _llm_cache[cache_key]


def structured_call(prompt: str, schema: Type[T], fallback: T) -> T:
    """
    Try an LLM call constrained to `schema`. If no API key is configured,
    or the call fails for any reason, return the deterministic `fallback`
    instead so the graph never breaks.
    """
    llm = get_structured_llm(schema)
    if llm is None:
        return fallback
    try:
        result = llm.invoke(prompt)
        return result
    except Exception:
        return fallback
