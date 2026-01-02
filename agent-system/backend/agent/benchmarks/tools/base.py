from abc import ABC, abstractmethod
from typing import List, Dict, Any

class AbstractToolSet(ABC):
    """
    Abstract Interface for Agent Tool Capabilities.
    Defines how an agent perceives and interacts with the world.
    """
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the tool definitions and persona instructions"""
        pass
        
    @abstractmethod
    def parse_tool_calls(self, llm_response: str) -> List[Dict[str, Any]]:
        """Parse raw LLM output into structured tool calls"""
        pass
        
    @abstractmethod
    def execute_tool(self, name: str, params: Dict[str, Any]) -> str:
        """Execute a tool and return the output string"""
        pass
