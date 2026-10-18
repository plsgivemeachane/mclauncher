from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any


class GameProcessRegistry:
    """Own the cross-launcher claim and identity of the managed game."""

    def __init__(self, data_root: Path | str) -> None:
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.root / "game.lock"
        self.record_path = self.root / "running-game.json"
        self._lock_file = None

    def acquire(self) -> bool:
        if self._lock_file is not None:
            return True
        lock_file = self.lock_path.open("a+")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.close()
            return False
        self._lock_file = lock_file
        return True

    def release(self) -> None:
        if self._lock_file is None:
            return
        fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
        self._lock_file.close()
        self._lock_file = None

    def read(self) -> dict[str, Any] | None:
        try:
            value = json.loads(self.record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def write(self, record: dict[str, Any]) -> None:
        temporary = self.record_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.record_path)

    def clear(self) -> None:
        try:
            self.record_path.unlink()
        except FileNotFoundError:
            pass

    @staticmethod
    def process_identity(pid: int) -> dict[str, Any] | None:
        """Capture Linux PID identity; PID alone is deliberately insufficient."""
        try:
            proc = Path("/proc") / str(int(pid))
            stat = (proc / "stat").read_text(encoding="utf-8")
            close_paren = stat.rfind(")")
            fields = stat[close_paren + 2 :].split()
            executable = os.path.realpath(proc / "exe")
            cmdline = (proc / "cmdline").read_bytes().split(b"\0")
            cmdline = [part.decode("utf-8", errors="replace") for part in cmdline if part]
            return {
                "pid": int(pid),
                "start_time": fields[19],  # /proc/<pid>/stat field 22
                "executable": executable,
                "cmdline": cmdline,
            }
        except (OSError, ValueError, IndexError):
            return None

    @classmethod
    def is_alive(cls, record: dict[str, Any] | None) -> bool:
        if not record or not isinstance(record.get("pid"), int):
            return False
        current = cls.process_identity(record["pid"])
        if current is None:
            return False
        return all(current.get(key) == record.get(key) for key in ("start_time", "executable", "cmdline"))

    def remember(self, pid: int, instance_id: str) -> dict[str, Any] | None:
        identity = self.process_identity(pid)
        if identity is None:
            return None
        identity["instance_id"] = instance_id
        self.write(identity)
        return identity

    def adopt(self) -> dict[str, Any] | None:
        record = self.read()
        if self.is_alive(record):
            return record
        if record is not None:
            self.clear()
        return None
