from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class VerificationSpec:
    """Defines how to verify the scenario success"""
    type: str # 'file_exists', 'grep', 'run_test', 'custom_script'
    target: str
    pattern: Optional[str] = None
    
@dataclass
class BenchmarkScenario:
    """
    Defines a reproducible task for an agent.
    """
    id: str
    title: str
    description: str
    
    # Context
    repository: str # name of repo to use
    
    # Task
    instruction: str # The prompt to the agent
    
    # Validation
    verification_suite: Dict[str, Any] # Passed to VerificationEngine
    
    # Meta
    difficulty: str = "medium"
    tags: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "instruction": self.instruction,
            "verification_suite": self.verification_suite
        }
