"""Append-only audit journal for reconstructing what the launcher did.

Every event is one JSON line in ``<data root>/audit.jsonl``. The file lives
beside ``state.json``, outside ``instances/``, so deleting an instance never
deletes the record of that deletion. Lines are only ever appended; when the
file grows past ``MAX_BYTES`` it is renamed to ``audit-<timestamp>.jsonl`` and
a fresh file is started. Rotated files are never removed by the launcher.

Two kinds of events are written:

* ``state_change`` — emitted by ``LauncherStore.save`` with a field-level diff
  of ``state.json`` (before -> after), so every persisted change is covered no
  matter which code path made it.
* explicit events (``delete_instance``, ``remove_mod``, ``game_launch``,
  ``game_exit``, ``mcp_call``, ``pack_update_*``, ``job_finished`` ...) for
  effects on files and processes that ``state.json`` cannot show.

Writing the journal must never break the operation being journaled, so every
failure is swallowed and reported on stderr instead.
"""

from __future__ import annotations

import fcntl
import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_BYTES = 20 * 1024 * 1024
# Values whose JSON form is longer than this are summarized instead of copied.
_MAX_VALUE_CHARS = 2000
# Bulky instance fields: recorded as counts / added / removed, never copied whole.
_BULKY_LIST_FIELDS = {"installed_files", "missing_files", "local_modifications", "available_versions"}
_BULKY_DICT_FIELDS = {"installed_file_hashes"}
_OPAQUE_FIELDS = {"available_version_metadata"}


def _now() -> dict[str, Any]:
    stamp = time.time()
    return {"ts": datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec="milliseconds"), "epoch": stamp}


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


def _small(value: Any) -> Any:
    value = _json_safe(value)
    text = json.dumps(value, sort_keys=True)
    if len(text) <= _MAX_VALUE_CHARS:
        return value
    return {"_truncated": True, "type": type(value).__name__, "json_chars": len(text), "head": text[:_MAX_VALUE_CHARS]}


def _list_delta(before: Any, after: Any) -> dict[str, Any]:
    old = before if isinstance(before, list) else []
    new = after if isinstance(after, list) else []
    old_set = {json.dumps(item, sort_keys=True) for item in old}
    new_set = {json.dumps(item, sort_keys=True) for item in new}
    return {
        "before_count": len(old), "after_count": len(new),
        "added": _small([json.loads(item) for item in sorted(new_set - old_set)]),
        "removed": _small([json.loads(item) for item in sorted(old_set - new_set)]),
    }


def _dict_delta(before: Any, after: Any) -> dict[str, Any]:
    old = before if isinstance(before, dict) else {}
    new = after if isinstance(after, dict) else {}
    return {
        "before_count": len(old), "after_count": len(new),
        "added": _small(sorted(set(new) - set(old))),
        "removed": _small(sorted(set(old) - set(new))),
        "changed": _small(sorted(key for key in set(old) & set(new) if old[key] != new[key])),
    }


def _field_change(key: str, before: Any, after: Any) -> dict[str, Any]:
    if key in _BULKY_LIST_FIELDS:
        return _list_delta(before, after)
    if key in _BULKY_DICT_FIELDS:
        return _dict_delta(before, after)
    if key in _OPAQUE_FIELDS:
        return {"changed": True, "before_count": len(before or []), "after_count": len(after or [])}
    if key == "mods":
        return _list_delta(before, after)
    return {"before": _small(before), "after": _small(after)}


def compact_instance(instance: dict[str, Any]) -> dict[str, Any]:
    """An instance record with bulky fields replaced by their sizes."""
    compact = {}
    for key, value in instance.items():
        if key in _BULKY_LIST_FIELDS or key in _BULKY_DICT_FIELDS:
            compact[key] = {"count": len(value) if hasattr(value, "__len__") else None}
        else:
            compact[key] = _small(value)
    return compact


def diff_state(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Field-level difference between two launcher states; empty when equal."""
    diff: dict[str, Any] = {}
    settings = {}
    for key in sorted(set(before) | set(after)):
        if key == "instances":
            continue
        if before.get(key) != after.get(key):
            settings[key] = _field_change(key, before.get(key), after.get(key))
    if settings:
        diff["settings"] = settings
    old = {item.get("id"): item for item in before.get("instances", []) if isinstance(item, dict)}
    new = {item.get("id"): item for item in after.get("instances", []) if isinstance(item, dict)}
    added = [compact_instance(new[key]) for key in new if key not in old]
    removed = [compact_instance(old[key]) for key in old if key not in new]
    changed = {}
    for key in new:
        if key in old and old[key] != new[key]:
            fields = {
                field: _field_change(field, old[key].get(field), new[key].get(field))
                for field in sorted(set(old[key]) | set(new[key]))
                if old[key].get(field) != new[key].get(field)
            }
            changed[str(key)] = {"name": new[key].get("name"), "fields": fields}
    if added:
        diff["instances_added"] = added
    if removed:
        diff["instances_removed"] = removed
    if changed:
        diff["instances_changed"] = changed
    return diff


def inventory(path: Path, *, max_names: int = 200) -> dict[str, Any]:
    """Describe a folder before it is destroyed: sizes, top-level entries, world names."""
    result: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.is_dir():
        return result
    files = 0
    total = 0
    try:
        for directory, _dirs, names in os.walk(path):
            for name in names:
                files += 1
                try:
                    total += os.lstat(os.path.join(directory, name)).st_size
                except OSError:
                    pass
        result["top_level"] = sorted(entry.name for entry in path.iterdir())[:max_names]
        for worlds in ("saves", "worlds"):
            folder = path / worlds
            if folder.is_dir():
                result[worlds] = sorted(entry.name for entry in folder.iterdir() if entry.is_dir())[:max_names]
        for mods in ("mods", "mods-disabled"):
            folder = path / mods
            if folder.is_dir():
                result[mods] = sorted(entry.name for entry in folder.iterdir())[:max_names]
        backups = path / "backups"
        if backups.is_dir():
            result["backups"] = sorted(entry.name for entry in backups.iterdir())[:max_names]
    except OSError as error:
        result["inventory_error"] = str(error)
    result["file_count"] = files
    result["total_bytes"] = total
    return result


def file_facts(path: Path) -> dict[str, Any]:
    """Size and modification time of a file about to change, if it exists."""
    try:
        stat = path.stat()
    except OSError:
        return {"path": str(path), "exists": False}
    return {"path": str(path), "exists": True, "bytes": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()}


class AuditLog:
    """Durable, append-only JSON-lines journal shared by the app and MCP server."""

    def __init__(self, data_root: Path | str, *, source: str = "app") -> None:
        self.root = Path(data_root)
        self.path = self.root / "audit.jsonl"
        self.lock_path = self.root / "audit.lock"
        self.source = source
        self.host = socket.gethostname()

    def record(self, action: str, **details: Any) -> None:
        event = {**_now(), "source": self.source, "pid": os.getpid(), "host": self.host, "action": action}
        event.update({key: _json_safe(value) for key, value in details.items()})
        try:
            line = json.dumps(event, sort_keys=True, default=repr) + "\n"
        except (TypeError, ValueError) as error:
            line = json.dumps({**_now(), "source": self.source, "action": action,
                               "audit_encoding_error": str(error)}) + "\n"
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open("a+") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    self._rotate_if_needed()
                    descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                    try:
                        os.write(descriptor, line.encode("utf-8"))
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        except OSError as error:
            print(f"mclauncher: could not write audit event {action!r}: {error}", file=sys.stderr)

    def _rotate_if_needed(self) -> None:
        try:
            size = self.path.stat().st_size
        except FileNotFoundError:
            return
        if size < MAX_BYTES:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        os.replace(self.path, self.root / f"audit-{stamp}.jsonl")

    def read(self) -> list[dict[str, Any]]:
        """Every event in the current file, oldest first (for tests and tooling)."""
        if not self.path.is_file():
            return []
        events = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({"unparseable": line})
        return events


def log_banner(log_path: Path, text: str) -> None:
    """Append a launcher-written marker line to a game log, ignoring failures."""
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with log_path.open("ab") as stream:
            stream.write(f"\n===== mclauncher {stamp} {text} =====\n".encode("utf-8"))
    except OSError:
        pass
