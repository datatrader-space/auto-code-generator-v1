# llm/router.py
"""
LLM Router - Switches between local (Ollama/DeepSeek) and cloud (Anthropic/OpenAI)
Handles fallback, retries, and intelligent routing based on task complexity
"""

import os
import logging
from typing import Dict, Any, List, Optional, Literal
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """LLM configuration"""
    provider: Literal['ollama', 'anthropic', 'openai']
    model: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    max_tokens: int = 4000
    temperature: float = 0.7


class LLMRouter:
    """
    Routes LLM requests to appropriate provider
    
    Strategy:
    1. Try local (DeepSeek) first for speed/privacy
    2. Fall back to cloud for complex reasoning
    3. Allow explicit provider selection
    """
    
    def __init__(self):
        self.local_config = self._get_local_config()
        self.cloud_config = self._get_cloud_config()
        
        # Initialize clients lazily
        self._local_client = None
        self._cloud_client = None
    
    def _get_local_config(self) -> LLMConfig:
        """Get local LLM configuration (Ollama)"""
        return LLMConfig(
            provider='ollama',
            model=os.getenv('LOCAL_LLM_MODEL', 'deepseek-coder:6.7b'),
            base_url=os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'),
            max_tokens=4000,
            temperature=0.7
        )
    
    def _get_cloud_config(self) -> LLMConfig:
        """Get cloud LLM configuration"""
        provider = os.getenv('CLOUD_LLM_PROVIDER', 'anthropic')
        
        if provider == 'anthropic':
            return LLMConfig(
                provider='anthropic',
                model=os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514'),
                api_key=os.getenv('ANTHROPIC_API_KEY'),
                max_tokens=8000,
                temperature=0.7
            )
        elif provider == 'openai':
            return LLMConfig(
                provider='openai',
                model=os.getenv('OPENAI_MODEL', 'gpt-4-turbo-preview'),
                api_key=os.getenv('OPENAI_API_KEY'),
                max_tokens=4000,
                temperature=0.7
            )
        else:
            raise ValueError(f"Unknown cloud provider: {provider}")
    
    @property
    def local_client(self):
        """Lazy-load local client"""
        if self._local_client is None:
            from llm.ollama import OllamaClient
            self._local_client = OllamaClient(self.local_config)
        return self._local_client
    
    @property
    def cloud_client(self):
        """Lazy-load cloud client"""
        if self._cloud_client is None:
            if self.cloud_config.provider == 'anthropic':
                from llm.anthropic_client import AnthropicClient
                self._cloud_client = AnthropicClient(self.cloud_config)
            elif self.cloud_config.provider == 'openai':
                from llm.openai_client import OpenAIClient
                self._cloud_client = OpenAIClient(self.cloud_config)
        return self._cloud_client
    
    def query(
        self,
        messages: List[Dict[str, str]],
        *,
        provider: Optional[str] = None,
        json_mode: bool = False,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Query LLM with automatic routing
        
        Args:
            messages: List of {"role": "user/assistant/system", "content": "..."}
            provider: Force specific provider ('local', 'cloud', None=auto)
            json_mode: Expect JSON response
            max_tokens: Override default
            temperature: Override default
            
        Returns:
            {
                "content": "...",
                "provider": "ollama|anthropic|openai",
                "model": "...",
                "usage": {...}
            }
        """
        
        # Determine which provider to use
        if provider == 'cloud':
            return self._query_cloud(messages, json_mode, max_tokens, temperature)
        elif provider == 'local':
            return self._query_local(messages, json_mode, max_tokens, temperature)
        else:
            # Auto-routing: Try local first, fallback to cloud
            return self._query_auto(messages, json_mode, max_tokens, temperature)
    
    def _query_local(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool,
        max_tokens: Optional[int],
        temperature: Optional[float]
    ) -> Dict[str, Any]:
        """Query local LLM (Ollama)"""
        try:
            logger.info(f"Querying local LLM: {self.local_config.model}")
            
            result = self.local_client.query(
                messages=messages,
                json_mode=json_mode,
                max_tokens=max_tokens or self.local_config.max_tokens,
                temperature=temperature or self.local_config.temperature
            )
            
            result['provider'] = 'local'
            result['model'] = self.local_config.model
            return result
            
        except Exception as e:
            logger.error(f"Local LLM error: {e}")
            raise
    
    def _query_cloud(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool,
        max_tokens: Optional[int],
        temperature: Optional[float]
    ) -> Dict[str, Any]:
        """Query cloud LLM"""
        try:
            logger.info(f"Querying cloud LLM: {self.cloud_config.model}")
            
            result = self.cloud_client.query(
                messages=messages,
                json_mode=json_mode,
                max_tokens=max_tokens or self.cloud_config.max_tokens,
                temperature=temperature or self.cloud_config.temperature
            )
            
            result['provider'] = 'cloud'
            result['model'] = self.cloud_config.model
            return result
            
        except Exception as e:
            logger.error(f"Cloud LLM error: {e}")
            raise
    
    def _query_auto(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool,
        max_tokens: Optional[int],
        temperature: Optional[float]
    ) -> Dict[str, Any]:
        """
        Auto-routing with fallback
        
        Strategy:
        1. Try local first (fast, private)
        2. If local fails or times out, try cloud
        3. If cloud not configured, raise error
        """
        
        # Try local first
        try:
            return self._query_local(messages, json_mode, max_tokens, temperature)
        except Exception as local_error:
            logger.warning(f"Local LLM failed: {local_error}, falling back to cloud")
            
            # Check if cloud is configured
            if not self.cloud_config.api_key:
                raise RuntimeError(
                    "Local LLM failed and cloud LLM not configured. "
                    "Set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable."
                ) from local_error
            
            # Try cloud
            try:
                result = self._query_cloud(messages, json_mode, max_tokens, temperature)
                result['fallback'] = True
                result['local_error'] = str(local_error)
                return result
            except Exception as cloud_error:
                # Both failed
                raise RuntimeError(
                    f"Both local and cloud LLM failed. "
                    f"Local: {local_error}, Cloud: {cloud_error}"
                ) from cloud_error
    
    def parse_json_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse JSON from LLM response
        
        Handles cases where LLM wraps JSON in ```json or adds text
        """
        content = response.get('content', '')
        
        # Remove markdown code blocks if present
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]
        
        content = content.strip()
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}\nContent: {content}")
            raise ValueError(f"Invalid JSON response from LLM: {e}")
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check health of local and cloud LLMs
        
        Returns:
            {
                "local": {"available": bool, "model": str, "error": str},
                "cloud": {"available": bool, "model": str, "error": str}
            }
        """
        result = {
            "local": {"available": False, "model": self.local_config.model},
            "cloud": {"available": False, "model": self.cloud_config.model}
        }
        
        # Check local
        try:
            self.local_client.health_check()
            result['local']['available'] = True
        except Exception as e:
            result['local']['error'] = str(e)
        
        # Check cloud
        try:
            if self.cloud_config.api_key:
                self.cloud_client.health_check()
                result['cloud']['available'] = True
            else:
                result['cloud']['error'] = "API key not configured"
        except Exception as e:
            result['cloud']['error'] = str(e)
        
        return result


# Singleton instance
_router = None

def get_llm_router() -> LLMRouter:
    """Get singleton LLM router instance"""
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router