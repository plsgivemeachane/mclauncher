from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import minecraft_launcher_lib
from PySide6.QtCore import QProcess


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


class MinecraftPlayer:
    """Build and start a ready instance without performing network work."""

    def build_command(self, instance: dict, minecraft_directory: Path, username: str, player_uuid: str):
        version = instance.get("version")
        if not version:
            raise RuntimeError("No Minecraft version is pinned; install the instance first")
        version_root = minecraft_directory / "versions" / version
        if not (version_root / f"{version}.json").is_file() or not (version_root / f"{version}.jar").is_file():
            raise RuntimeError("Minecraft files are incomplete; install or retry before playing")
        runtime_info = minecraft_launcher_lib.runtime.get_version_runtime_information(version, minecraft_directory)
        if not runtime_info or not runtime_info.get("name"):
            raise RuntimeError("The managed Java runtime is missing; install or retry before playing")
        executable = minecraft_launcher_lib.runtime.get_executable_path(runtime_info["name"], minecraft_directory)
        if not executable or not os.path.isfile(executable) or not os.access(executable, os.X_OK):
            raise RuntimeError("The managed Java runtime is unavailable; install or retry before playing")
        game_directory = minecraft_directory.parent
        options = {
            "username": username,
            "uuid": player_uuid,
            # minecraft-launcher-lib requires this field even for a local session.
            # An empty token deliberately does not claim authenticated access.
            "token": "",
            "executablePath": executable,
            "gameDirectory": str(game_directory),
            "launcherName": "mclauncher",
            "launcherVersion": "0.1.0",
        }
        return minecraft_launcher_lib.command.get_minecraft_command(version, minecraft_directory, options), game_directory

    def launch(self, instance: dict, minecraft_directory: Path, username: str, player_uuid: str,
               on_started: Callable[[], None], on_finished: Callable[[int, bool], None]) -> QProcess:
        command, game_directory = self.build_command(instance, minecraft_directory, username, player_uuid)
        process = QProcess()
        process.setProgram(command[0])
        process.setArguments(command[1:])
        process.setWorkingDirectory(str(game_directory))
        process.started.connect(on_started)
        process.finished.connect(lambda code, status: on_finished(code, status != QProcess.ExitStatus.NormalExit))
        process.errorOccurred.connect(lambda _error: on_finished(-1, True))
        process.start()
        return process
