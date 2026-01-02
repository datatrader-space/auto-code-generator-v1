from typing import List, Dict, Any
from agent.crs_tools import CRSTools as BaseCRSTools
from .base import AbstractToolSet

class CRSToolSet(AbstractToolSet):
    """
    Adapter for the existing CRS Tools to fit the Benchmark ToolSet interface.
    """
    
    def __init__(self, repository):
        self._impl = BaseCRSTools(repository)
        
    def get_system_prompt(self) -> str:
        return self._impl.get_tool_definitions()
        
    def parse_tool_calls(self, llm_response: str) -> List[Dict[str, Any]]:
        return self._impl.parse_tool_calls(llm_response)
        
    def execute_tool(self, name: str, params: Dict[str, Any]) -> str:
        # Pass through to the existing implementation
        # Note: BaseCRSTools.execute_tool expects params as Dict[str, str], 
        # but our interface allows Any. We cast values to str for safety.
        str_params = {k: str(v) for k, v in params.items()}
        return self._impl.execute_tool(name, str_params)
