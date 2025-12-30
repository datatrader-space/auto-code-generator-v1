"""
CRS Event System for real-time progress streaming
"""
import json
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Callable
from enum import Enum
from collections import defaultdict
from threading import Lock


class EventType(str, Enum):
    """Event types emitted during CRS pipeline execution"""
    STEP_START = "step_start"
    STEP_PROGRESS = "step_progress"
    STEP_LOG = "step_log"
    STEP_COMPLETE = "step_complete"
    STEP_ERROR = "step_error"
    PIPELINE_START = "pipeline_start"
    PIPELINE_COMPLETE = "pipeline_complete"
    PIPELINE_ERROR = "pipeline_error"


class LogLevel(str, Enum):
    """Log levels for step logs"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class CRSEvent:
    """Base event structure"""
    event_type: EventType
    timestamp: float
    run_id: str
    step_name: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

    def to_sse(self) -> str:
        """Convert to Server-Sent Events format"""
        event_dict = asdict(self)
        return f"data: {json.dumps(event_dict)}\n\n"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class CRSEventEmitter:
    """
    Event emitter for CRS pipeline execution
    Captures and broadcasts events during pipeline runs
    """

    def __init__(self, run_id: str, repository_id: Optional[int] = None):
        self.run_id = run_id
        self.repository_id = repository_id
        self.events: List[CRSEvent] = []
        self.callbacks: List[Callable[[CRSEvent], None]] = []
        self._lock = Lock()

    def register_callback(self, callback: Callable[[CRSEvent], None]) -> None:
        """Register a callback to receive events"""
        with self._lock:
            self.callbacks.append(callback)

    def emit(self, event: CRSEvent) -> None:
        """Emit an event"""
        with self._lock:
            self.events.append(event)
            for callback in self.callbacks:
                try:
                    callback(event)
                except Exception as e:
                    print(f"Error in event callback: {e}")

    def emit_pipeline_start(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Emit pipeline start event"""
        event = CRSEvent(
            event_type=EventType.PIPELINE_START,
            timestamp=time.time(),
            run_id=self.run_id,
            data=metadata or {}
        )
        self.emit(event)

    def emit_pipeline_complete(self, summary: Dict[str, Any]) -> None:
        """Emit pipeline complete event"""
        event = CRSEvent(
            event_type=EventType.PIPELINE_COMPLETE,
            timestamp=time.time(),
            run_id=self.run_id,
            data=summary
        )
        self.emit(event)

    def emit_pipeline_error(self, error: str, error_type: str) -> None:
        """Emit pipeline error event"""
        event = CRSEvent(
            event_type=EventType.PIPELINE_ERROR,
            timestamp=time.time(),
            run_id=self.run_id,
            data={"error": error, "error_type": error_type}
        )
        self.emit(event)

    def emit_step_start(self, step_name: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Emit step start event"""
        event = CRSEvent(
            event_type=EventType.STEP_START,
            timestamp=time.time(),
            run_id=self.run_id,
            step_name=step_name,
            data=metadata or {}
        )
        self.emit(event)

    def emit_step_progress(
        self,
        step_name: str,
        current: int,
        total: int,
        message: Optional[str] = None
    ) -> None:
        """Emit step progress event"""
        event = CRSEvent(
            event_type=EventType.STEP_PROGRESS,
            timestamp=time.time(),
            run_id=self.run_id,
            step_name=step_name,
            data={
                "current": current,
                "total": total,
                "percentage": round((current / total * 100) if total > 0 else 0, 2),
                "message": message
            }
        )
        self.emit(event)

    def emit_step_log(
        self,
        step_name: str,
        message: str,
        level: LogLevel = LogLevel.INFO
    ) -> None:
        """Emit step log event"""
        event = CRSEvent(
            event_type=EventType.STEP_LOG,
            timestamp=time.time(),
            run_id=self.run_id,
            step_name=step_name,
            data={"message": message, "level": level.value}
        )
        self.emit(event)

    def emit_step_complete(
        self,
        step_name: str,
        duration: float,
        result: Dict[str, Any]
    ) -> None:
        """Emit step complete event"""
        event = CRSEvent(
            event_type=EventType.STEP_COMPLETE,
            timestamp=time.time(),
            run_id=self.run_id,
            step_name=step_name,
            data={
                "duration": duration,
                "result": result
            }
        )
        self.emit(event)

    def emit_step_error(
        self,
        step_name: str,
        error: str,
        error_type: str,
        traceback: Optional[str] = None
    ) -> None:
        """Emit step error event"""
        event = CRSEvent(
            event_type=EventType.STEP_ERROR,
            timestamp=time.time(),
            run_id=self.run_id,
            step_name=step_name,
            data={
                "error": error,
                "error_type": error_type,
                "traceback": traceback
            }
        )
        self.emit(event)

    def get_events(self) -> List[CRSEvent]:
        """Get all emitted events"""
        with self._lock:
            return list(self.events)


class CRSEventBroadcaster:
    """
    Global event broadcaster for SSE streams
    Manages event queues per repository
    """

    def __init__(self):
        self._queues: Dict[int, List[CRSEvent]] = defaultdict(list)
        self._max_queue_size = 1000
        self._lock = Lock()

    def broadcast(self, repository_id: int, event: CRSEvent) -> None:
        """Broadcast event to repository's queue"""
        with self._lock:
            queue = self._queues[repository_id]
            queue.append(event)
            # Keep queue size limited
            if len(queue) > self._max_queue_size:
                self._queues[repository_id] = queue[-self._max_queue_size:]

    def get_events(
        self,
        repository_id: int,
        since: Optional[float] = None
    ) -> List[CRSEvent]:
        """Get events for a repository since a timestamp"""
        with self._lock:
            events = self._queues.get(repository_id, [])
            if since is not None:
                return [e for e in events if e.timestamp > since]
            return list(events)

    def clear_events(self, repository_id: int) -> None:
        """Clear events for a repository"""
        with self._lock:
            if repository_id in self._queues:
                del self._queues[repository_id]


# Global broadcaster instance
_broadcaster = CRSEventBroadcaster()


def get_broadcaster() -> CRSEventBroadcaster:
    """Get global event broadcaster"""
    return _broadcaster
