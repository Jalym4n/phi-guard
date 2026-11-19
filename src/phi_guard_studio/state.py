"""In-memory session state: the token vault, idle timer and batch jobs.

The vault (token -> original value) lives only in this process's memory.
It is cleared when the user clicks "Start over", when the app exits, when
the protection key changes, and after ``idle_timeout`` seconds without any
API activity.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from phi_guard.batch import BatchItem
from phi_guard.redactor import Redactor

__all__ = ["BatchJob", "SessionState"]


@dataclass
class BatchJob:
    id: str
    total: int
    items: list[BatchItem] = field(default_factory=list)
    status: str = "running"  # running | done | error
    zip_bytes: bytes = b""

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "status": self.status,
            "total": self.total,
            "processed": len(self.items),
            "items": [it.to_dict() for it in self.items],
        }


class SessionState:
    def __init__(self, key: bytes, idle_timeout: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._lock = threading.RLock()
        self._clock = clock
        self.idle_timeout = idle_timeout
        self.redactor = Redactor(key=key)
        self.jobs: dict[str, BatchJob] = {}
        self.last_activity = clock()
        self.cleared_for_idle = False

    def touch(self) -> None:
        with self._lock:
            self.check_idle()
            self.last_activity = self._clock()
            self.cleared_for_idle = False

    def seconds_remaining(self) -> float:
        return max(0.0, self.idle_timeout - (self._clock() - self.last_activity))

    def check_idle(self) -> bool:
        """Clear the vault if the session has been idle too long.  Returns True if it cleared."""
        with self._lock:
            if self.seconds_remaining() <= 0 and (self.redactor.vault_size or self.jobs):
                self.clear()
                self.cleared_for_idle = True
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self.redactor.forget()
            self.jobs.clear()

    def set_key(self, key: bytes) -> None:
        """A new key makes every existing code meaningless, so the vault is cleared."""
        with self._lock:
            self.redactor = Redactor(key=key)
            self.jobs.clear()
