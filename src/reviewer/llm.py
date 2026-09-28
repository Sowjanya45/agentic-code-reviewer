"""Groq LLM client with retry/backoff, including explicit handling of the
free-tier's rate limits (HTTP 429).

Every call takes an explicit `api_key` -- there is no shared/global key,
since different callers (different logged-in users on the hosted server)
each bring their own Groq account and their own rate-limit budget.
"""
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

_DEFAULT_MODEL = "openai/gpt-oss-120b"

_clients: dict[tuple[str, str], ChatGroq] = {}
_clients_lock = threading.Lock()

# LangGraph fans checker calls out concurrently (one per hunk x category), but
# Groq's free tier has a low per-minute request cap -- left unthrottled, even
# a single small review floods it and every call gets 429'd. This serializes
# calls made with the SAME api_key to at most one every _MIN_INTERVAL_SECONDS;
# different users' keys have independent rate-limit budgets on Groq's side,
# so they are paced independently rather than sharing one global queue.
_MIN_INTERVAL_SECONDS = float(os.environ.get("GROQ_MIN_INTERVAL_SECONDS", "3.0"))
_rate_lock = threading.Lock()
_last_call_started_at: dict[str, float] = {}


def _throttle(api_key: str) -> None:
    with _rate_lock:
        now = time.monotonic()
        last = _last_call_started_at.get(api_key, 0.0)
        wait = last + _MIN_INTERVAL_SECONDS - now
        if wait > 0:
            time.sleep(wait)
        _last_call_started_at[api_key] = time.monotonic()


def get_llm(api_key: str, model: str | None = None) -> ChatGroq:
    model = model or os.environ.get("GROQ_MODEL", _DEFAULT_MODEL)
    cache_key = (api_key, model)
    with _clients_lock:
        client = _clients.get(cache_key)
        if client is None:
            client = ChatGroq(model=model, api_key=api_key, temperature=0)
            _clients[cache_key] = client
        return client


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
def call_structured(prompt: str, output_schema, api_key: str, model: str | None = None) -> object:
    """Call the LLM with structured output, retrying on rate limits/5xx.

    Uses json_mode rather than forced tool-calling: this model reliably
    fails forced tool-calls when the correct answer is "no findings" (it
    either refuses to call the tool at all, or hallucinates a nonexistent
    tool name) -- json_mode has no such failure mode.
    """
    _throttle(api_key)
    llm = get_llm(api_key, model).with_structured_output(output_schema, method="json_mode")
    return llm.invoke(prompt)
