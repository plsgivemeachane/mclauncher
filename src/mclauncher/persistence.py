from __future__ import annotations

import json
import os
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

    def load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"username": "", "instances": []}
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"username": "", "instances": []}
        if not isinstance(value, dict):
            return {"username": "", "instances": []}
        value.setdefault("username", "")
        value.setdefault("instances", [])
        return value

    def save(self, state: dict[str, Any]) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.state_path)

    def create_instance_root(self, instance_id: str) -> Path:
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

    def instance_minecraft_root(self, instance_id: str) -> Path:
        return self.create_instance_root(instance_id) / "minecraft"
