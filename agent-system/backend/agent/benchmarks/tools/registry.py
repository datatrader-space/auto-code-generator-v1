from .base import AbstractToolSet
from .crs_tools import CRSToolSet
from .direct_tools import DirectToolSet

class ToolRegistry:
    """
    Factory for creating ToolSets based on strategy name.
    """
    
    @staticmethod
    def get(strategy: str, repository) -> AbstractToolSet:
        strategy = strategy.lower().strip()
        
        if strategy in ["crs", "crs-only"]:
            return CRSToolSet(repository)
        elif strategy == "direct":
            return DirectToolSet(repository)
        else:
            # Fallback or Error
            raise ValueError(f"Unknown benchmarking strategy: {strategy}")
