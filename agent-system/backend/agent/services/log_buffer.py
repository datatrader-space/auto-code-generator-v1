from collections import deque
from datetime import datetime, timezone
import logging
from typing import List, Dict, Any


_LOG_BUFFER = deque(maxlen=500)
_HANDLER_NAME = "agent_in_memory_log_handler"


class InMemoryLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self.format(record),
        }
        _LOG_BUFFER.append(entry)


def attach_log_handler() -> None:
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, "name", None) == _HANDLER_NAME:
            return

    handler = InMemoryLogHandler()
    handler.name = _HANDLER_NAME
    formatter = logging.Formatter("%(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    root.addHandler(handler)


def get_logs(limit: int = 200) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    return list(_LOG_BUFFER)[-limit:]
