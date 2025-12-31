# llm/anthropic_client.py
"""
Anthropic Client - Minimal implementation
"""

import os
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic package not installed. Run: pip install anthropic")


class AnthropicClient:
    """
    Simple Anthropic/Claude client
    """
    
    def __init__(self, config):
        if not ANTHROPIC_AVAILABLE:
            raise RuntimeError("anthropic package not installed")
        
        self.model = config.model
        self.api_key = config.api_key
        self.max_tokens = config.max_tokens
        self.temperature = config.temperature
        
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
    
    def query(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
        max_tokens: int = None,
        temperature: float = None
    ) -> Dict[str, Any]:
        """
        Query Claude
        
        Args:
            messages: [{"role": "user/assistant", "content": "..."}]
            json_mode: Request JSON output (via system prompt)
            max_tokens: Override default
            temperature: Override default
            
        Returns:
            {
                "content": "response text",
                "usage": {"input_tokens": 100, "output_tokens": 50}
            }
        """
        
        # Separate system message from conversation
        system_msg = ""
        conv_messages = []
        
        for msg in messages:
            if msg.get("role") == "system":
                system_msg += msg.get("content", "") + "\n"
            else:
                conv_messages.append({
                    "role": msg.get("role"),
                    "content": msg.get("content")
                })
        
        # Add JSON instruction to system if needed
        if json_mode:
            system_msg += "\nYou must respond with valid JSON only. No markdown, no other text."
        
        try:
            logger.info(f"Querying Claude: {self.model}")
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens or self.max_tokens,
                temperature=temperature or self.temperature,
                system=system_msg if system_msg else None,
                messages=conv_messages
            )
            
            content = response.content[0].text
            self.last_usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens
            }
            
            return {
                "content": content,
                "usage": self.last_usage
            }
        
        except Exception as e:
            logger.error(f"Anthropic error: {e}")
            raise RuntimeError(f"Claude API error: {e}")

    def query_stream(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
        max_tokens: int = None,
        temperature: float = None
    ):
        result = self.query(
            messages=messages,
            json_mode=json_mode,
            max_tokens=max_tokens,
            temperature=temperature
        )
        yield result.get("content", "")
    
    def health_check(self) -> bool:
        """Check if API key works"""
        try:
            # Simple test query
            self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            return True
        except Exception as e:
            logger.error(f"Anthropic health check failed: {e}")
            return False
