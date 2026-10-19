from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any


class LauncherStore:
    """Persist launcher-owned data below one dedicated data root."""

    def __init__(self, data_root: Path | str | None = None) -> None:
        if data_root is None:
            data_root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "mclauncher"
        self.root = Path(data_root).expanduser()
        self.state_path = self.root / "state.json"
        self.instances_root = self.root / "instances"
        self.root.mkdir(parents=True, exist_ok=True)
        self.instances_root.mkdir(parents=True, exist_ok=True)
        self.recovery_required = False
        self.load_error = ""
        self.recovery_backup: Path | None = None

    @staticmethod
    def _defaults() -> dict[str, Any]:
        return {
            "username": "",
            "instances": [],
            "selected_instance_id": "",
            "selected_setup_id": "",
            "automatic_instances": {},
            "available_versions": [],
            "available_version_metadata": [],
            "show_snapshots": False,
        }

    def _backup_corrupt_state(self) -> Path | None:
        if not self.state_path.exists():
            return None
        backup = self.state_path.with_name(f"state.json.corrupt-{time.time_ns()}")
        try:
            shutil.copy2(self.state_path, backup)
        except OSError:
            return None
        return backup

    def _invalid_state(self, reason: str) -> dict[str, Any]:
        backup = self._backup_corrupt_state()
        suffix = f" Backup: {backup.name}." if backup else ""
        self.recovery_required = True
        self.recovery_backup = backup
        self.load_error = f"Launcher state could not be loaded: {reason}.{suffix} Review the backup, then choose Recover defaults."
        return self._defaults()

    def load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return self._defaults()
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except OSError as error:
            return self._invalid_state(str(error))
        except json.JSONDecodeError as error:
            return self._invalid_state(f"invalid JSON ({error.msg})")
        if not isinstance(value, dict):
            return self._invalid_state("the top-level value must be an object")
        if not isinstance(value.get("username", ""), str) or not isinstance(value.get("instances", []), list):
            return self._invalid_state("username must be text and instances must be a list")
        if not isinstance(value.get("selected_instance_id", ""), str):
            return self._invalid_state("selected_instance_id must be text")
        if not isinstance(value.get("selected_setup_id", ""), str):
            return self._invalid_state("selected_setup_id must be text")
        if not isinstance(value.get("available_versions", []), list) or any(
            not isinstance(version, str) for version in value.get("available_versions", [])
        ):
            return self._invalid_state("available_versions must be a list of text version ids")
        if not isinstance(value.get("automatic_instances", {}), dict) or any(
            not isinstance(version, str) or not isinstance(instance_id, str)
            for version, instance_id in value.get("automatic_instances", {}).items()
        ):
            return self._invalid_state("automatic_instances must map text versions to text instance ids")
        if not isinstance(value.get("available_version_metadata", []), list) or any(
            not isinstance(entry, dict)
            or not isinstance(entry.get("id"), str)
            or not isinstance(entry.get("type", "release"), str)
            for entry in value.get("available_version_metadata", [])
        ):
            return self._invalid_state("available_version_metadata must contain version records")
        if not isinstance(value.get("show_snapshots", False), bool):
            return self._invalid_state("show_snapshots must be a boolean")
        if "memory_gib" in value and (isinstance(value["memory_gib"], bool) or not isinstance(value["memory_gib"], int)):
            return self._invalid_state("memory_gib must be an integer")
        for instance in value.get("instances", []):
            if not isinstance(instance, dict) or not isinstance(instance.get("id"), str) or not isinstance(instance.get("name"), str):
                return self._invalid_state("every instance must have text id and name fields")
            if not self._is_safe_instance_id(instance["id"]):
                return self._invalid_state(f"unsafe instance id {instance['id']!r}")
        value.setdefault("username", "")
        value.setdefault("instances", [])
        value.setdefault("selected_instance_id", "")
        value.setdefault("selected_setup_id", value.get("selected_instance_id", ""))
        value.setdefault("automatic_instances", {})
        value.setdefault("available_versions", [])
        value.setdefault("available_version_metadata", [])
        value.setdefault("show_snapshots", False)
        return value

    def save(self, state: dict[str, Any]) -> None:
        if self.recovery_required:
            raise RuntimeError("State recovery is required before saving launcher data")
        temporary = self.state_path.with_name(f"state.json.tmp-{uuid.uuid4().hex}")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.state_path)

    def create_instance_root(self, instance_id: str) -> Path:
        if not self._is_safe_instance_id(instance_id):
            raise ValueError("instance id must resolve under the managed instances directory")
        instance_root = self.instances_root / instance_id
        for directory in (
            instance_root,
            instance_root / "minecraft",
            instance_root / "worlds",
            instance_root / "settings",
            instance_root / "screenshots",
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return instance_root

    def _is_safe_instance_id(self, instance_id: str) -> bool:
        legacy_id = re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{8}", instance_id or "")
        try:
            uuid_id = uuid.UUID(instance_id) if isinstance(instance_id, str) else None
        except ValueError:
            uuid_id = None
        valid_id = bool(legacy_id or (uuid_id and uuid_id.version == 4 and str(uuid_id) == instance_id))
        if not valid_id or Path(instance_id).name != instance_id:
            return False
        try:
            return self.instances_root.resolve() in (self.instances_root / instance_id).resolve().parents
        except OSError:
            return False

    def recover_defaults(self) -> None:
        if self.recovery_backup is None or not self.recovery_backup.is_file():
            raise RuntimeError("The original launcher state was not backed up; recovery was refused")
        self.recovery_required = False
        self.load_error = ""
        self.save(self._defaults())

    def instance_minecraft_root(self, instance_id: str) -> Path:
        return self.create_instance_root(instance_id) / "minecraft"

    def instance_root(self, instance_id: str) -> Path:
        return self.create_instance_root(instance_id)
