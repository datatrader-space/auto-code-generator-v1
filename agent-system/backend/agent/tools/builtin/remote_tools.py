"""
Remote Tool Implementation
Allows external services to register as tools via HTTP endpoints
"""

import requests
from typing import Dict, Any, Optional
from dataclasses import dataclass
from ..base import BaseTool, ToolMetadata, ToolParameter, ToolExecutionContext, ToolResult


@dataclass
class RemoteToolConfig:
    """Configuration for a remote tool"""
    endpoint_url: str
    method: str = "POST"  # HTTP method
    timeout: int = 30
    headers: Optional[Dict[str, str]] = None
    auth_type: Optional[str] = None  # "bearer", "basic", "api_key", None
    auth_config: Optional[Dict[str, str]] = None


class RemoteTool(BaseTool):
    """
    Tool that proxies execution to a remote HTTP endpoint.

    The remote service should accept POST requests with JSON body:
    {
        "parameters": {...},
        "context": {
            "repository_id": "...",
            "session_id": "...",
            "workspace_path": "..."
        }
    }

    And respond with JSON:
    {
        "success": true/false,
        "output": "...",
        "error": "..." (if success=false),
        "metadata": {...},
        "citations": [...]
    }
    """

    def __init__(self, metadata: ToolMetadata, config: RemoteToolConfig):
        self._metadata = metadata
        self._config = config

    def get_metadata(self) -> ToolMetadata:
        return self._metadata

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        """Execute tool by calling remote HTTP endpoint"""

        # Validate parameters
        self.validate_parameters(params)

        # Prepare request
        headers = self._config.headers or {}
        headers['Content-Type'] = 'application/json'

        # Add authentication if configured
        if self._config.auth_type == "bearer" and self._config.auth_config:
            token = self._config.auth_config.get('token')
            if token:
                headers['Authorization'] = f'Bearer {token}'
        elif self._config.auth_type == "api_key" and self._config.auth_config:
            key_name = self._config.auth_config.get('key_name', 'X-API-Key')
            api_key = self._config.auth_config.get('api_key')
            if api_key:
                headers[key_name] = api_key
        elif self._config.auth_type == "basic" and self._config.auth_config:
            username = self._config.auth_config.get('username')
            password = self._config.auth_config.get('password')
            if username and password:
                import base64
                credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
                headers['Authorization'] = f'Basic {credentials}'

        # Prepare payload
        payload = {
            "parameters": params,
            "context": {
                "repository_id": str(context.repository.id) if context.repository else None,
                "session_id": context.session_id,
                "workspace_path": context.workspace_path,
                "user_id": str(context.user.id) if context.user else None,
            }
        }

        try:
            # Make HTTP request
            response = requests.request(
                method=self._config.method,
                url=self._config.endpoint_url,
                json=payload,
                headers=headers,
                timeout=self._config.timeout
            )

            # Check for HTTP errors
            if response.status_code >= 400:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Remote tool returned HTTP {response.status_code}: {response.text}",
                    metadata={"status_code": response.status_code}
                )

            # Parse response
            try:
                result_data = response.json()
            except ValueError:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Remote tool returned invalid JSON: {response.text[:200]}",
                    metadata={"status_code": response.status_code}
                )

            # Extract result fields
            success = result_data.get('success', True)
            output = result_data.get('output', '')
            error = result_data.get('error', '')
            metadata = result_data.get('metadata', {})
            citations = result_data.get('citations', [])

            return ToolResult(
                success=success,
                output=output,
                error=error,
                metadata=metadata,
                citations=citations
            )

        except requests.Timeout:
            return ToolResult(
                success=False,
                output="",
                error=f"Remote tool timed out after {self._config.timeout}s",
                metadata={"timeout": self._config.timeout}
            )
        except requests.RequestException as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to connect to remote tool: {str(e)}",
                metadata={"error_type": type(e).__name__}
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Unexpected error calling remote tool: {str(e)}",
                metadata={"error_type": type(e).__name__}
            )
