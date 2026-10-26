"""Minimal Claude Messages API client (requests only) with server-side web search support."""
import json
import re
import time

import requests

from . import config as C

API_URL = "https://api.anthropic.com/v1/messages"


class LLMError(RuntimeError):
    pass


def call(system, user, *, web_search=False, max_searches=5, max_tokens=4000, temperature=None):
    """Return (text, sources). `sources` lists {url,title} from any web searches Claude ran."""
    if not C.ANTHROPIC_API_KEY:
        raise LLMError("ANTHROPIC_API_KEY not set")
    headers = {"x-api-key": C.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    messages = [{"role": "user", "content": user}]
    body = {"model": C.CLAUDE_MODEL, "max_tokens": max_tokens, "system": system, "messages": messages}
    if temperature is not None:
        body["temperature"] = temperature
    if web_search:
        body["tools"] = [{"type": C.WEB_SEARCH_TOOL, "name": "web_search", "max_uses": max_searches,
                          "user_location": {"type": "approximate", "country": "IN"}}]

    texts, sources = [], []
    for _ in range(4):  # server tools can return stop_reason=pause_turn; continue the turn
        for attempt in range(3):
            r = requests.post(API_URL, headers=headers, data=json.dumps(body), timeout=300)
            if r.status_code in (429, 500, 502, 503, 529):
                time.sleep(10 * (attempt + 1))
                continue
            break
        if r.status_code >= 300:
            raise LLMError(f"Claude API {r.status_code}: {r.text[:500]}")
        data = r.json()
        for block in data.get("content", []):
            if block.get("type") == "text":
                texts.append(block["text"])
            elif block.get("type") == "web_search_tool_result":
                for res in block.get("content") or []:
                    if isinstance(res, dict) and res.get("url"):
                        sources.append({"url": res["url"], "title": res.get("title", "")})
        if data.get("stop_reason") != "pause_turn":
            break
        messages.append({"role": "assistant", "content": data["content"]})
        body["messages"] = messages
    return "".join(texts), sources


def extract_json(text):
    """Pull the last JSON object/array out of a model response."""
    m = re.findall(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, flags=re.S)
    candidates = m[::-1] if m else []
    # fallback: outermost braces
    if not candidates:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            candidates.append(text[start:end + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    raise LLMError("No valid JSON in model response:\n" + text[-1500:])
