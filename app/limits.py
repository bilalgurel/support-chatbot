"""Small in-memory rate limiter shared by the web and Telegram channels."""
import threading
import time
from collections import defaultdict, deque

from . import config

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def allow(key: str) -> bool:
    now = time.monotonic()
    with _lock:
        hits = _hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= config.RATE_LIMIT_PER_MINUTE:
            return False
        hits.append(now)
        return True


def reset() -> None:
    with _lock:
        _hits.clear()
