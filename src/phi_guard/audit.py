"""Append-only, hash-chained audit log in JSON Lines format.

Each line is a JSON object.  ``hash`` is SHA-256 over the canonical JSON of
the entry (without ``hash``) and includes ``prev_hash``, the previous line's
hash.  Editing, deleting, or reordering any line breaks every hash after it,
and ``verify()`` reports the first broken line.

Limits: a hash chain proves the log is *internally consistent*.  Someone who
can rewrite the whole file can recompute the whole chain.  Anchoring the
latest hash somewhere else (printed report, separate system) closes that gap.

Entries must never contain raw PHI: callers log counts and kinds only.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["GENESIS_HASH", "AuditLog"]

GENESIS_HASH = "0" * 64


def _canonical(entry: dict[str, Any]) -> bytes:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _hash(entry: dict[str, Any]) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(_canonical(body)).hexdigest()


class AuditLog:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def _last(self) -> tuple[int, str]:
        if not self.path.exists():
            return 0, GENESIS_HASH
        last_line = ""
        count = 0
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last_line = line
                    count += 1
        if not last_line:
            return 0, GENESIS_HASH
        try:
            return count, str(json.loads(last_line)["hash"])
        except (ValueError, KeyError):
            return count, GENESIS_HASH

    def append(self, event: str, **fields: Any) -> dict[str, Any]:
        """Append an event.  ``fields`` must be JSON-serializable and PHI-free."""
        with self._lock:
            seq, prev = self._last()
            entry: dict[str, Any] = {
                "seq": seq + 1,
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "event": event,
                **fields,
                "prev_hash": prev,
            }
            entry["hash"] = _hash(entry)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            return entry

    def entries(self) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)

    def verify(self) -> tuple[bool, int | None]:
        """Check the whole chain.  Returns ``(True, None)`` or ``(False, line_number)`` (1-based)."""
        if not self.path.exists():
            return True, None
        prev = GENESIS_HASH
        lineno = 0
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                lineno += 1
                try:
                    entry = json.loads(line)
                except ValueError:
                    return False, lineno
                if not isinstance(entry, dict) or entry.get("prev_hash") != prev or entry.get("hash") != _hash(entry):
                    return False, lineno
                prev = entry["hash"]
        return True, None
