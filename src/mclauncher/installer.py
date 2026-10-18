from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import minecraft_launcher_lib


ProgressCallback = Callable[[str, int, int], None]


class MinecraftInstaller:
    """Application boundary for vanilla installation and managed Java checks."""

    def resolve_version(self) -> str:
        return minecraft_launcher_lib.utils.get_latest_version()["release"]

    def install(
        self,
        instance: dict,
        minecraft_directory: Path,
        on_progress: ProgressCallback,
    ) -> None:
        version = instance.get("version")
        if not version:
            raise RuntimeError("No Minecraft version is pinned for this installation")

        minecraft_directory.mkdir(parents=True, exist_ok=True)

        def set_status(status: str) -> None:
            on_progress(status, -1, -1)

        def set_progress(progress: int) -> None:
            on_progress("", progress, -1)

        def set_maximum(maximum: int) -> None:
            on_progress("", -1, maximum)

        minecraft_launcher_lib.install.install_minecraft_version(
            version,
            minecraft_directory,
            callback={"setStatus": set_status, "setProgress": set_progress, "setMax": set_maximum},
        )
        self._validate_installation(version, minecraft_directory)

    @staticmethod
    def _validate_installation(version: str, minecraft_directory: Path) -> None:
        version_root = minecraft_directory / "versions" / version
        if not (version_root / f"{version}.json").is_file() or not (version_root / f"{version}.jar").is_file():
            raise RuntimeError("Minecraft files are incomplete")

        runtime_info = minecraft_launcher_lib.runtime.get_version_runtime_information(version, minecraft_directory)
        if not runtime_info or not runtime_info.get("name"):
            raise RuntimeError("The managed Java runtime was not recorded")
        executable = minecraft_launcher_lib.runtime.get_executable_path(runtime_info["name"], minecraft_directory)
        if not executable or not os.path.isfile(executable) or not os.access(executable, os.X_OK):
            raise RuntimeError("The managed Java runtime is unavailable")
