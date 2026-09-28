import logging
import sys
from collections import deque
from datetime import datetime, timezone


class RingBufferHandler(logging.Handler):
    """Keeps the last `capacity` log records in memory so the admin panel
    has something real to show without needing a log file or external
    aggregator wired up in this deployment."""

    def __init__(self, capacity: int = 500) -> None:
        super().__init__()
        self.capacity = capacity
        self.records: deque[dict] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append({
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        })

    def snapshot(self, level: str | None = None, limit: int = 200) -> list[dict]:
        records = list(self.records)
        if level:
            records = [r for r in records if r["level"] == level.upper()]
        return records[-limit:]


log_ring_buffer = RingBufferHandler()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), log_ring_buffer],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
