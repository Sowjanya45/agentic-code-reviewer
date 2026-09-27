"""Groq LLM client with retry/backoff, including explicit handling of the
free-tier's rate limits (HTTP 429) -- the evaluation harness makes many
calls in a row, so this matters more here than in a one-off review."""
from __future__ import annotations

import os
import threading
import time

from langchain_groq import ChatGroq
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

_client: ChatGroq | None = None

# LangGraph fans checker calls out concurrently (one per hunk x category), but
# Groq's free tier has a low per-minute request cap -- left unthrottled, even
# a single small review floods it and every call gets 429'd. This serializes
# all Groq calls process-wide to at most one every _MIN_INTERVAL_SECONDS,
# turning the concurrent fan-out into an effectively-paced queue.
_MIN_INTERVAL_SECONDS = float(os.environ.get("GROQ_MIN_INTERVAL_SECONDS", "3.0"))
_rate_lock = threading.Lock()
_last_call_started_at = 0.0


def _throttle() -> None:
    global _last_call_started_at
    with _rate_lock:
        now = time.monotonic()
        wait = _last_call_started_at + _MIN_INTERVAL_SECONDS - now
        if wait > 0:
            time.sleep(wait)
        _last_call_started_at = time.monotonic()


def get_llm() -> ChatGroq:
    global _client
    if _client is None:
        _client = ChatGroq(
            model=os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
            api_key=os.environ["GROQ_API_KEY"],
            temperature=0,
        )
    return _client


def _is_retryable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    if status is not None:
        return status == 429 or 500 <= status < 600
    # network/timeout errors from the underlying HTTP client don't always
    # carry a status_code attribute; retry those too rather than failing hard
    return isinstance(exc, (TimeoutError, ConnectionError))


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(6),
    reraise=True,
)
def call_structured(prompt: str, output_schema) -> object:
    """Call the LLM with structured output, retrying on rate limits/5xx."""
    _throttle()
    llm = get_llm().with_structured_output(output_schema)
    return llm.invoke(prompt)
