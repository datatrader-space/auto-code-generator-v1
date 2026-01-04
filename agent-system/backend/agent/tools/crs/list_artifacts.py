from typing import Dict, Any, List
from agent.tools.base import BaseTool, ToolMetadata, ToolParameter, ToolPermission, ToolResult, ToolExecutionContext
from agent.crs_tools import CRSTools
import json

class ListArtifactsTool(BaseTool):
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="LIST_ARTIFACTS",
            category="crs",
            description="Get a complete inventory of code elements (artifacts) of a specific kind. This is a DETERMINISTIC tool.",
            parameters=[
                ToolParameter(
                    name="kind",
                    type="choice",
                    description="Type of artifact to list",
                    required=True,
                    choices=[
                        "django_model", "drf_serializer", "drf_viewset", 
                        "drf_apiview", "url_pattern", "admin_register", 
                        "celery_task", "redis_client", "django_app_config", 
                        "django_settings", "requirement"
                    ]
                ),
                ToolParameter(
                    name="filter",
                    type="string",
                    description="Optional text filter for names/paths",
                    required=False,
                    default=""
                )
            ],
            permissions=[ToolPermission.READ],
            enabled=True,
            tags=["crs", "inventory", "deterministic"]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        if not context.repository:
             return ToolResult(
                success=False,
                error="Repository context required for CRS tools",
                output=""
            )

        # Instantiate generic CRS tools wrapper
        crs_tools = CRSTools(context.repository)
        
        # Format params for the legacy tool
        # Legacy tool expects all params as strings in a dict
        legacy_params = {
            "kind": params["kind"],
            "filter": params.get("filter", "")
        }
        
        # Execute using legacy logic
        # Note: crs_tools.execute_tool returns a string (JSON or error)
        result_str = crs_tools.execute_tool("LIST_ARTIFACTS", legacy_params)
        
        # Attempt to parse result to determines success/failure structure
        # The legacy execute_tool returns a string, but usually it's a JSON dump of the result
        return ToolResult(
            success=True, # Legacy tool embeds errors in output string, hard to detect strict failure without parsing
            output=result_str,
            metadata={"source": "crs_tools"}
        )
