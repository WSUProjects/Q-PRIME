"""Lightweight LLM inference helper using Ollama (local or remote HTTP API).

Provides a single public function `summarize_short(data, model=None, max_tokens=60)`
that accepts any JSON-serializable Python object and returns a very short
(1-2 sentence) plain-language summary suitable for UI microcopy.

This module keeps the dependency surface minimal (requests).
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("MODEL", "qwen2.5:7b-instruct-q4_K_M")


class OllamaError(Exception):
    pass


def _make_prompt(
    data: Any, nl_query: Optional[str] = None, sql_query: Optional[str] = None
) -> str:
    """Create a short instruction-style prompt for any JSON-like data.

    The prompt is intentionally concise so the model returns a 1-2 sentence
    summary. We include the JSON in compact form and ask for a "very short" summary.
    """
    compact = json.dumps(data, default=str, separators=(",", ":"))
    # Truncate very long payloads to keep request size reasonable
    if len(compact) > 8000:
        compact = compact[:8000] + "..."
    # Include optional hints to help the model focus the summary
    hints = []
    if nl_query:
        hints.append(f"NL query: {nl_query}")
    if sql_query:
        hints.append(f"SQL query: {sql_query}")

    hint_block = "\n".join(hints) + "\n\n" if hints else ""

    return (
        "You are a helpful assistant.\n"
        "Summarize the following data in one or two very short sentences (max ~30 words).\n"
        "Return only plain text, no markdown, no code fences.\n"
        "If an NL or SQL query hint is provided, use it to focus the summary.\n\n"
        f"{hint_block}Data: {compact}"
    )


def call_ollama_chat(
    prompt: str, model: Optional[str] = None, timeout: int = 30
) -> str:
    model = model or DEFAULT_MODEL
    url = f"{OLLAMA_HOST}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 60,
        "stream": False,
    }
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        j = r.json()
        # Ollama returns choices -> message -> content
        return {
            "ok": True,
            "text": j["choices"][0]["message"]["content"].strip(),
        }

    except Exception as e:
        raise OllamaError(f"Ollama request failed: {e}")


# Local deterministic summarizer used as fallback when LLM is unavailable
def _local_event_summary(
    d: Any,
    fallback: Optional[str] = None,
) -> str:
    try:
        items = d if isinstance(d, list) else [d]
        persons = [
            str(x.get("person", "")).strip() for x in items if isinstance(x, dict)
        ]
        persons_clean = [
            p for p in persons if p and p.lower() not in ("unknown", "unknown person")
        ]
        uniq_people = len(set(persons_clean))
        from collections import Counter

        top = Counter(persons_clean).most_common(3)
        intruder_count = sum(
            1
            for x in items
            if isinstance(x, dict) and x.get("event") and "intruder" in x.get("event")
        )
        parts = []
        if uniq_people > 0:
            parts.append(f"{uniq_people} unique people seen")
        else:
            parts.append("No known people seen")
        parts.append(f"{intruder_count} intruder events")
        if top:
            parts.append("Top: " + ", ".join(f"{n} ({c})" for n, c in top))
        return "; ".join(parts) + "."
    except Exception:
        return fallback or ""


def summarize_short(
    data: Any,
    nl_query: Optional[str] = None,
    sql_query: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Summarize `data` in a very short single-line (1-2 sentences).

    - `data` may be any JSON-serializable Python object (dict, list, scalar).
    - Returns plain text summary. Raises OllamaError on failure.
    """
    prompt = _make_prompt(data, nl_query=nl_query, sql_query=sql_query)
    return call_ollama_chat(prompt, model=model)


def summarize_short_safe(
    data: Any,
    sql_query: str = "",
    nl_query: str = "",
    model: Optional[str] = None,
    timeout: int = 30,
    fallback: Optional[str] = None,
    raise_on_error: bool = False,
) -> str:
    """Safe wrapper around summarize_short.

    - `timeout` is forwarded to the HTTP call.
    - If the call fails and `raise_on_error` is False, returns `fallback` or an empty string.
    """

    # If input is a JSON string, try to parse it
    original = data
    try:
        if isinstance(data, str):
            parsed = json.loads(data)
            data = parsed
    except Exception:
        # leave data as-is
        data = original

    # If the payload is a large list, pass only a deterministic, minimal-field subset to the model
    reduced_data = data
    try:
        if isinstance(data, list):
            total = len(data)
            # Be conservative: smaller subset by default to avoid large prompts
            MAX_ITEMS = 75
            if total > MAX_ITEMS:
                # deterministic subset: head, sampled middle, tail
                head = min(20, MAX_ITEMS // 4)
                tail = min(20, MAX_ITEMS // 4)
                remaining = MAX_ITEMS - head - tail
                mid_start = head
                mid_end = total - tail
                middle = []
                if remaining > 0 and mid_end > mid_start:
                    span = mid_end - mid_start
                    step = max(1, span // remaining)
                    idxs = list(range(mid_start, mid_end, step))[:remaining]
                    middle = [data[i] for i in idxs]

                subset = data[:head] + middle + data[-tail:]

                # Reduce each item to minimal fields to shrink prompt size (only event/person/ts)
                def _minify(item):
                    if not isinstance(item, dict):
                        return item
                    return {
                        "event": item.get("event"),
                        "person": item.get("person"),
                        "ts": item.get("ts") or item.get("timestamp"),
                    }

                reduced_data = [_minify(x) for x in subset]
                nl_query = (
                    f"(Showing {len(reduced_data)}/{total} entries - subset) "
                    + nl_query
                ).strip()
                print(
                    f"[LLMInference] Payload trimmed: passing {len(reduced_data)}/{total} minimal items to LLM"
                )
    except Exception:
        reduced_data = data

    # Call the LLM with the reduced payload
    print(reduced_data if isinstance(reduced_data, list) else str(reduced_data)[:1000])
    try:
        prompt = _make_prompt(reduced_data, nl_query=nl_query, sql_query=sql_query)
        plen = len(prompt)
        print("\nGenerated prompt length:", plen)
        # If prompt is still too large, skip LLM and return a local summary
        if plen > 8000:
            print(
                f"[LLMInference] Prompt too long ({plen} chars) — using local summary"
            )
            return fallback or _local_event_summary(data, fallback)
        print("\nGenerated prompt for LLM:\n", prompt[:4000])
        return call_ollama_chat(prompt, model=model, timeout=timeout)
    except OllamaError as e:
        print(f"[LLMInference] OllamaError: {e}")
        if raise_on_error:
            raise
        # Fallback to local deterministic summary
        return fallback or _local_event_summary(data, fallback)


__all__ = ["summarize_short", "summarize_short_safe", "call_ollama_chat", "OllamaError"]


if __name__ == "__main__":
    # Quick CLI demo: read JSON from stdin and print a one-line summary.
    import sys

    try:
        raw = sys.stdin.read()
        if not raw.strip():
            print("Usage: echo '{\"key\": 123}' | python nlp/LLMInference.py")
            sys.exit(1)
        data = json.loads(raw)
    except Exception:
        # fallback: treat stdin as plain string
        data = raw.strip()

    try:
        s = summarize_short(data)
        print(s)
    except OllamaError as e:
        print(f"Error: {e}")
        sys.exit(2)
