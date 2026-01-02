import time
import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from pathlib import Path

@dataclass
class TraceStep:
    """A single atomic event in the agent's execution timeline"""
    timestamp: float
    kind: str  # 'THOUGHT', 'TOOL_CALL', 'TOOL_RESULT', 'ERROR', 'SYSTEM'
    content: Any
    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

@dataclass
class BenchmarkTrace:
    """Complete record of a benchmark run"""
    trace_id: str
    scenario_id: str
    strategy: str  # 'crs' or 'direct'
    start_time: float
    end_time: float = 0.0
    steps: List[TraceStep] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration(self) -> float:
        end = self.end_time if self.end_time > 0 else time.time()
        return end - self.start_time

class BenchmarkObserver:
    """
    Observer Pattern that records execution events.
    Can be injected into AgentRunner.
    """
    def __init__(self, scenario_id: str, strategy: str, trace_id: Optional[str] = None):
        self.trace = BenchmarkTrace(
            trace_id=trace_id or str(uuid.uuid4()),
            scenario_id=scenario_id,
            strategy=strategy,
            start_time=time.time()
        )
        self._active = True

    def log(self, kind: str, content: Any):
        if not self._active:
            return
        
        step = TraceStep(
            timestamp=time.time(),
            kind=kind,
            content=content
        )
        self.trace.steps.append(step)

    def finish(self, metadata: Dict[str, Any] = None):
        self.trace.end_time = time.time()
        if metadata:
            self.trace.metadata.update(metadata)
        self._active = False

    def save(self, directory: str) -> str:
        """Save trace to JSON file"""
        Path(directory).mkdir(parents=True, exist_ok=True)
        filename = f"trace_{self.trace.scenario_id}_{self.trace.strategy}_{self.trace.trace_id}.json"
        path = Path(directory) / filename
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(asdict(self.trace), f, indent=2)
            
        return str(path)
