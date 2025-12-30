# core/llm_client.py
import json
import urllib.request
from typing import Any, Dict, List, Optional


class LocalLLMClient:
    """
    Minimal HTTP client for a local model API.
    You will adapt URL/payload to your server.

    Expected request:
      POST {base_url}/chat
      { "messages": [{"role":"system|user|assistant","content":"..."}] }

    Expected response:
      { "text": "..." }  OR  { "content": "..." }
    """

    def __init__(self, base_url: str):
        self.base_url = (base_url or "").rstrip("/")

    def chat(self, messages: List[Dict[str, str]], *, timeout: int = 120) -> str:
        url = self.base_url + "/chat"
        payload = json.dumps({"messages": messages}).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        obj = json.loads(raw)
        if isinstance(obj, dict):
            if isinstance(obj.get("text"), str):
                return obj["text"]
            if isinstance(obj.get("content"), str):
                return obj["content"]
        return str(obj)
