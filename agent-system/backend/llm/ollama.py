# llm/ollama.py
"""
Ollama Client - Minimal implementation for local LLM
"""

import requests
import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class OllamaClient:
    """
    Simple Ollama client
    
    Talks to Ollama API running locally
    """
    
    def __init__(self, config):
        self.model = config.model
        self.base_url = config.base_url.rstrip('/')
        self.max_tokens = config.max_tokens
        self.temperature = config.temperature
    
    def query(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
        max_tokens: int = None,
        temperature: float = None
    ) -> Dict[str, Any]:
        """
        Query Ollama
        
        Args:
            messages: [{"role": "user", "content": "..."}]
            json_mode: Force JSON output
            max_tokens: Override default
            temperature: Override default
            
        Returns:
            {
                "content": "response text",
                "usage": {"prompt_tokens": 100, "completion_tokens": 50}
            }
        """
        
        # Build prompt from messages
        prompt = self._build_prompt(messages, json_mode)
        
        # Call Ollama API
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature or self.temperature,
                "num_predict": max_tokens or self.max_tokens
            }
        }
        
        if json_mode:
            payload["format"] = "json"
        
        try:
            logger.info(f"Querying Ollama: {self.model}")
            
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            
            data = response.json()
            
            return {
                "content": data.get("response", ""),
                "usage": {
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                    "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
                }
            }
        
        except requests.exceptions.Timeout:
            raise RuntimeError("Ollama request timed out (>120s)")
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Cannot connect to Ollama at {self.base_url}. Is it running?")
        except Exception as e:
            raise RuntimeError(f"Ollama error: {e}")
    
    def _build_prompt(self, messages: List[Dict[str, str]], json_mode: bool) -> str:
        """Build prompt from messages"""
        
        parts = []
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        
        prompt = "\n\n".join(parts)
        
        if json_mode:
            prompt += "\n\nAssistant: {"
        else:
            prompt += "\n\nAssistant:"
        
        return prompt
    
    def health_check(self) -> bool:
        """Check if Ollama is accessible"""
        try:
            url = f"{self.base_url}/api/tags"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            
            # Check if our model is available
            data = response.json()
            models = [m['name'] for m in data.get('models', [])]
            
            if self.model not in models:
                logger.warning(f"Model {self.model} not found in Ollama. Available: {models}")
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False