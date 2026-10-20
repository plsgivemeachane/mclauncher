from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Callable

import minecraft_launcher_lib
from PySide6.QtCore import QObject, QTimer

VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

def validate_version_id(version: str) -> str:
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise ValueError("Minecraft version id is invalid")
    return version


ProgressCallback = Callable[[str, int, int], None]


class MinecraftInstaller:
    """Application boundary for vanilla installation and managed Java checks."""

    def resolve_version(self) -> str:
        return validate_version_id(minecraft_launcher_lib.utils.get_latest_version()["release"])

    def discover_versions(self) -> list[dict]:
        """Return concrete release and snapshot choices at the installation boundary."""
        return [
            {"id": item["id"], "type": item.get("type", "release")}
            for item in minecraft_launcher_lib.utils.get_version_list()
            if item.get("type") in {"release", "snapshot"}
        ]

    def install(
        self,
        instance: dict,
        minecraft_directory: Path,
        on_progress: ProgressCallback,
    ) -> None:
        version = instance.get("version")
        if not version:
            raise RuntimeError("No Minecraft version is pinned for this installation")
        validate_version_id(version)

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

    def build_command(
        self,
        instance: dict,
        minecraft_directory: Path,
        username: str,
        player_uuid: str,
        memory_gib: int | None = None,
    ):
        version = instance.get("version")
        if not version:
            raise RuntimeError("No Minecraft version is pinned; install the instance first")
        validate_version_id(version)
        version_root = minecraft_directory / "versions" / version
        if not self.is_ready(instance, minecraft_directory):
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
        if memory_gib is not None:
            options["jvmArguments"] = [f"-Xmx{memory_gib}G", f"-Xms{memory_gib}G"]
        return minecraft_launcher_lib.command.get_minecraft_command(version, minecraft_directory, options), game_directory

    @staticmethod
    def is_ready(instance: dict, minecraft_directory: Path) -> bool:
        version = instance.get("version")
        if not version:
            return False
        try:
            validate_version_id(version)
        except ValueError:
            return False
        version_root = minecraft_directory / "versions" / version
        if not (version_root / f"{version}.json").is_file() or not (version_root / f"{version}.jar").is_file():
            return False
        runtime_info = minecraft_launcher_lib.runtime.get_version_runtime_information(version, minecraft_directory)
        if not runtime_info or not runtime_info.get("name"):
            return False
        executable = minecraft_launcher_lib.runtime.get_executable_path(runtime_info["name"], minecraft_directory)
        return bool(executable and os.path.isfile(executable) and os.access(executable, os.X_OK))

    def launch(self, instance: dict, minecraft_directory: Path, username: str, player_uuid: str,
               on_started: Callable[[], None], on_finished: Callable[[int, bool], None],
               memory_gib: int | None = None) -> "DetachedMinecraftProcess":
        command, game_directory = self.build_command(
            instance, minecraft_directory, username, player_uuid, memory_gib
        )
        process = DetachedMinecraftProcess(command, game_directory, on_finished)
        on_started()
        return process


class DetachedMinecraftProcess(QObject):
    """Track a detached game without making its lifetime depend on the window."""

    def __init__(self, command, working_directory: Path, on_finished: Callable[[int, bool], None]) -> None:
        super().__init__()
        try:
            log_directory = working_directory / "logs"
            log_directory.mkdir(parents=True, exist_ok=True)
            self._log_file = (log_directory / "minecraft.log").open("ab")
            try:
                self._process = subprocess.Popen(
                    command,
                    cwd=str(working_directory),
                    stdin=subprocess.DEVNULL,
                    stdout=self._log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except OSError:
                self._log_file.close()
                raise
        except OSError:
            raise
        self._on_finished = on_finished
        self._finished_reported = False
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()

    def processId(self) -> int:
        return self._process.pid

    def _poll(self) -> None:
        return_code = self._process.poll()
        if return_code is None or self._finished_reported:
            return
        self._finished_reported = True
        self._poll_timer.stop()
        self._log_file.close()
        self._on_finished(return_code, return_code != 0)
