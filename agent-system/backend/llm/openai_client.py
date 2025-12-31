# llm/openai_client.py
"""
OpenAI Client - Minimal implementation
"""

import logging
import json
from typing import Dict, Any, List

import requests

logger = logging.getLogger(__name__)


class OpenAIClient:
    """
    Simple OpenAI chat completions client
    """

    def __init__(self, config):
        self.model = config.model
        self.api_key = config.api_key
        self.base_url = (config.base_url or "https://api.openai.com/v1").rstrip("/")
        self.max_tokens = config.max_tokens
        self.temperature = config.temperature

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")

    def query(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
        max_tokens: int = None,
        temperature: float = None
    ) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature or self.temperature
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return {
                "content": content,
                "usage": data.get("usage", {})
            }
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            raise RuntimeError(f"OpenAI API error: {e}")

    def query_stream(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
        max_tokens: int = None,
        temperature: float = None
    ):
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature or self.temperature,
            "stream": True
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                stream=True,
                timeout=120
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8")
                if not decoded.startswith("data: "):
                    continue
                data = decoded.replace("data: ", "").strip()
                if data == "[DONE]":
                    break
                chunk = None
                try:
                    payload = json.loads(data)
                    chunk = payload["choices"][0]["delta"].get("content")
                except Exception:
                    chunk = None
                if chunk:
                    yield chunk
        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
            raise RuntimeError(f"OpenAI streaming error: {e}")

    def health_check(self) -> bool:
        try:
            self.query(messages=[{"role": "user", "content": "Hi"}], max_tokens=5)
            return True
        except Exception as e:
            logger.error(f"OpenAI health check failed: {e}")
            return False
