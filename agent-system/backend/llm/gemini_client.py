# llm/gemini_client.py
"""
Google Gemini Client - Minimal implementation
"""

import logging
from typing import Dict, Any, List

import requests

logger = logging.getLogger(__name__)


class GeminiClient:
    """
    Simple Gemini generateContent client
    """

    def __init__(self, config):
        self.model = config.model
        self.api_key = config.api_key
        self.base_url = (config.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        self.max_tokens = config.max_tokens
        self.temperature = config.temperature

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")

    def _build_prompt(self, messages: List[Dict[str, str]]) -> str:
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
            else:
                parts.append(f"User: {content}")
        return "\n\n".join(parts)

    def query(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
        max_tokens: int = None,
        temperature: float = None
    ) -> Dict[str, Any]:
        prompt = self._build_prompt(messages)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens or self.max_tokens,
                "temperature": temperature or self.temperature
            }
        }

        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        try:
            response = requests.post(
                f"{self.base_url}/models/{self.model}:generateContent",
                params={"key": self.api_key},
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            data = response.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            usage = data.get("usageMetadata", {})
            self.last_usage = usage
            return {
                "content": content,
                "usage": usage
            }
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            raise RuntimeError(f"Gemini API error: {e}")

    def query_stream(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
        max_tokens: int = None,
        temperature: float = None
    ):
        self.last_usage = None
        result = self.query(messages, json_mode=json_mode, max_tokens=max_tokens, temperature=temperature)
        yield result.get("content", "")

    def health_check(self) -> bool:
        try:
            self.query(messages=[{"role": "user", "content": "Hi"}], max_tokens=5)
            return True
        except Exception as e:
            logger.error(f"Gemini health check failed: {e}")
            return False
