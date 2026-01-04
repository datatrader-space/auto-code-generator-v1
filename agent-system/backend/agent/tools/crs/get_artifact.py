from typing import Dict, Any
from agent.tools.base import BaseTool, ToolMetadata, ToolParameter, ToolPermission, ToolResult, ToolExecutionContext
from agent.crs_tools import CRSTools

class GetArtifactTool(BaseTool):
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="GET_ARTIFACT",
            category="crs",
            description="Retrieve the full definition and context of a specific artifact by its ID.",
            parameters=[
                ToolParameter(
                    name="artifact_id",
                    type="string",
                    description="The exact artifact ID from LIST_ARTIFACTS (e.g., 'django_model:User:auth/models.py:10-50')",
                    required=True
                )
            ],
            permissions=[ToolPermission.READ],
            enabled=True,
            tags=["crs", "context", "read"]
        )

    def execute(self, params: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        if not context.repository:
             return ToolResult(
                success=False,
                error="Repository context required for CRS tools",
                output=""
            )

        crs_tools = CRSTools(context.repository)
        
        legacy_params = {
            "artifact_id": params["artifact_id"]
        }
        
        result_str = crs_tools.execute_tool("GET_ARTIFACT", legacy_params)
        
        return ToolResult(
            success=True,
            output=result_str,
            metadata={"source": "crs_tools"}
        )
