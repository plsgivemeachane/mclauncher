"""Headless launcher control used by the MCP server (and any other automation).

The controller works on the same data root as the desktop window. Saves go
through ``LauncherStore``, which merges concurrent changes under a file lock,
and game launches claim the same ``GameProcessRegistry`` lock, so the GUI and
this controller can run side by side without clobbering each other.

Long operations (installs and pack imports) run as background jobs so a caller
can start one, poll it with ``job()``, and keep working meanwhile.
"""

from __future__ import annotations

import copy
import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
import zipfile
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .identity import USERNAME_RE, local_identity
from .installer import MinecraftInstaller, MinecraftPlayer, validate_version_id
from .lifecycle import GameProcessRegistry
from .memory import default_memory_gib, validate_memory_gib
from .modpack import CurseForgePackImporter, CurseForgeProvider, ModrinthPackImporter, ModrinthPackUpdater
from .persistence import LauncherStore


class ControlError(RuntimeError):
    """A request the launcher refused; the message is safe to show a user."""


_INSTANCE_SUMMARY_KEYS = (
    "id", "name", "version", "loader", "loader_version", "ready", "install_state",
    "install_error", "automatic", "provider", "pack_source",
)


@dataclass
class Job:
    id: str
    kind: str
    instance_id: str
    status: str = "running"  # running | succeeded | failed
    message: str = ""
    progress_current: int = -1
    progress_maximum: int = -1
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    result: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "instance_id": self.instance_id, "status": self.status,
            "message": self.message, "progress_current": self.progress_current,
            "progress_maximum": self.progress_maximum, "started_at": self.started_at,
            "finished_at": self.finished_at, "result": self.result,
        }


def detect_pack_provider(archive: Path) -> str:
    """Return ``modrinth`` or ``curseforge`` from the archive's manifest."""
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = set(bundle.namelist())
    except (OSError, zipfile.BadZipFile) as error:
        raise ControlError(f"{archive} is not a readable modpack archive: {error}") from error
    if "modrinth.index.json" in names:
        return "modrinth"
    if "manifest.json" in names:
        return "curseforge"
    raise ControlError(
        f"{archive.name} has neither modrinth.index.json nor manifest.json; "
        "only Modrinth .mrpack and CurseForge exported .zip packs are supported"
    )


class LauncherController:
    """Thread-safe, Qt-free operations on launcher instances and the game."""

    def __init__(self, data_root: Path | str | None = None, *, installer=None, player=None,
                 game_registry=None, modrinth_importer=None, curseforge_importer=None,
                 popen: Callable[..., subprocess.Popen] = subprocess.Popen,
                 run_jobs_inline: bool = False) -> None:
        self.store = LauncherStore(data_root)
        self.installer = installer or MinecraftInstaller()
        self.player = player or MinecraftPlayer()
        self.registry = game_registry or GameProcessRegistry(self.store.root)
        self.modrinth_importer = modrinth_importer or ModrinthPackImporter(provider=self.installer)
        self.curseforge_importer = curseforge_importer or CurseForgePackImporter(
            provider=CurseForgeProvider(
                allow_public=lambda: bool(getattr(self, "state", {}).get("curseforge_public_downloads"))
            ),
            loader_resolver=getattr(self.installer, "resolve_loader", None),
        )
        self._popen = popen
        self._run_jobs_inline = run_jobs_inline
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._busy_instances: set[str] = set()
        self._game: subprocess.Popen | None = None
        self._game_instance_id: str | None = None
        self.last_exit: dict[str, Any] | None = None
        self.state = self.store.load()

    # -- state helpers -------------------------------------------------

    def _reload(self) -> dict[str, Any]:
        """Re-read disk so changes made in the GUI are visible before we act."""
        if self.store.recovery_required:
            raise ControlError(self.store.load_error or "Launcher state needs recovery in the desktop app")
        self.state = self.store.load()
        if self.store.recovery_required:
            raise ControlError(self.store.load_error)
        return self.state

    def _find(self, ref: str) -> dict[str, Any]:
        instances = self.state.get("instances", [])
        for instance in instances:
            if instance.get("id") == ref:
                return instance
        lowered = ref.strip().lower()
        matches = [item for item in instances if str(item.get("name", "")).lower() == lowered]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ControlError(f"More than one instance is named {ref!r}; use its id")
        raise ControlError(f"No instance matches {ref!r}")

    def _update_instance(self, instance_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._reload()
            instance = self._find(instance_id)
            instance.update(fields)
            self.store.save(self.state)
            return instance

    def _unique_name(self, requested: str) -> str:
        existing = {str(item.get("name")) for item in self.state.get("instances", [])}
        name, suffix = requested, 2
        while name in existing:
            name = f"{requested} ({suffix})"
            suffix += 1
        return name

    @staticmethod
    def summarize(instance: dict[str, Any]) -> dict[str, Any]:
        return {key: instance.get(key) for key in _INSTANCE_SUMMARY_KEYS if key in instance}

    # -- read-only queries ---------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._reload()
            return {
                "data_root": str(self.store.root),
                "username": self.state.get("username", ""),
                "memory_gib": self.state.get("memory_gib", default_memory_gib()),
                "instance_count": len(self.state.get("instances", [])),
                "game": self.game_status(),
                "active_jobs": [job.as_dict() for job in self._jobs.values() if job.status == "running"],
            }

    def list_instances(self) -> list[dict[str, Any]]:
        with self._lock:
            self._reload()
            return [self.summarize(item) for item in self.state.get("instances", [])]

    def get_instance(self, ref: str) -> dict[str, Any]:
        with self._lock:
            self._reload()
            instance = self._find(ref)
            summary = self.summarize(instance)
            summary["folder"] = str(self.store.instance_root(instance["id"]))
            summary["mods"] = instance.get("mods", [])
            summary["missing_files"] = instance.get("missing_files", [])
            return summary

    def list_versions(self, *, include_snapshots: bool = False, limit: int = 25) -> list[dict[str, Any]]:
        versions = self.installer.discover_versions()
        if not include_snapshots:
            versions = [item for item in versions if item.get("type") == "release"]
        return versions[: max(1, limit)]

    # -- settings ------------------------------------------------------

    def set_username(self, username: str) -> dict[str, Any]:
        username = username.strip()
        if not USERNAME_RE.fullmatch(username):
            raise ControlError("Usernames are 3-16 letters, digits, or underscores")
        with self._lock:
            self._reload()
            self.state["username"] = username
            self.store.save(self.state)
        return {"username": username, "player_uuid": local_identity(username)}

    def set_curseforge_public_downloads(self, enabled: bool) -> dict[str, Any]:
        """Save whether CurseForge packs may download through the keyless public API."""
        with self._lock:
            self._reload()
            self.state["curseforge_public_downloads"] = bool(enabled)
            self.store.save(self.state)
        return {"curseforge_public_downloads": bool(enabled)}

    def set_memory(self, memory_gib: int) -> dict[str, Any]:
        value, error = validate_memory_gib(memory_gib)
        if error:
            raise ControlError(error)
        with self._lock:
            self._reload()
            self.state["memory_gib"] = value
            self.store.save(self.state)
        return {"memory_gib": value}

    # -- instance management -------------------------------------------

    def create_instance(self, name: str, version: str | None = None) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ControlError("Instance name must not be empty")
        if version:
            try:
                validate_version_id(version)
            except ValueError as error:
                raise ControlError(str(error)) from error
        with self._lock:
            self._reload()
            instance = {"id": str(uuid.uuid4()), "name": self._unique_name(name), "version": version or None,
                        "ready": False}
            self.state["instances"].append(instance)
            self.store.create_instance_root(instance["id"])
            self.store.save(self.state)
            return self.summarize(instance)

    def rename_instance(self, ref: str, new_name: str) -> dict[str, Any]:
        new_name = new_name.strip()
        if not new_name:
            raise ControlError("Instance name must not be empty")
        with self._lock:
            self._reload()
            instance = self._find(ref)
            self._refuse_if_busy(instance["id"])
            others = {str(item.get("name")) for item in self.state["instances"] if item is not instance}
            if new_name in others:
                raise ControlError(f"Another instance is already named {new_name!r}")
            instance["name"] = new_name
            self.store.save(self.state)
            return self.summarize(instance)

    def delete_instance(self, ref: str) -> dict[str, Any]:
        """Remove an instance and its folder, as the desktop app's Delete button does."""
        with self._lock:
            self._reload()
            instance = self._find(ref)
            instance_id = str(instance["id"])
            self._refuse_if_busy(instance_id)
            root = self.store.instance_root(instance_id)
            if root.exists():
                try:
                    shutil.rmtree(root)
                except OSError as error:
                    raise ControlError(f"Could not delete instance folder: {error}") from error
            self.state["instances"] = [item for item in self.state["instances"] if item.get("id") != instance_id]
            self.state["automatic_instances"] = {
                version: value for version, value in self.state.get("automatic_instances", {}).items()
                if value != instance_id
            }
            for key in ("selected_instance_id", "selected_setup_id"):
                if self.state.get(key) == instance_id:
                    self.state[key] = ""
            self.store.save(self.state)
        return {"deleted": instance_id, "name": instance.get("name")}

    def _refuse_if_busy(self, instance_id: str) -> None:
        if instance_id in self._busy_instances:
            raise ControlError("That instance already has an install or import running")
        record = self.registry.read()
        if record and record.get("instance_id") == instance_id and self.registry.is_alive(record):
            raise ControlError("That instance is running; stop the game first")

    # -- jobs ----------------------------------------------------------

    def job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise ControlError(f"No job {job_id!r}")
            return job.as_dict()

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [job.as_dict() for job in sorted(self._jobs.values(), key=lambda item: item.started_at)]

    def _start_job(self, kind: str, instance_id: str, work: Callable[[Job], dict[str, Any] | None]) -> dict[str, Any]:
        with self._lock:
            self._refuse_if_busy(instance_id)
            job = Job(id=uuid.uuid4().hex[:12], kind=kind, instance_id=instance_id)
            self._jobs[job.id] = job
            self._busy_instances.add(instance_id)

        def run() -> None:
            try:
                job.result = work(job) or {}
                job.status = "succeeded"
                job.message = job.message or "Done"
            except Exception as error:  # noqa: BLE001 - every failure is reported on the job
                job.status = "failed"
                job.message = str(error) or type(error).__name__
            finally:
                job.finished_at = time.time()
                with self._lock:
                    self._busy_instances.discard(instance_id)

        if self._run_jobs_inline:
            run()
        else:
            threading.Thread(target=run, name=f"mclauncher-{kind}-{job.id}", daemon=True).start()
        return job.as_dict()

    @staticmethod
    def _progress(job: Job) -> Callable[[str, int, int], None]:
        def report(status: str, current: int, maximum: int) -> None:
            if status:
                job.message = status
            if current >= 0:
                job.progress_current = current
            if maximum >= 0:
                job.progress_maximum = maximum
        return report

    def _snapshot(self, instance_id: str) -> dict[str, Any]:
        with self._lock:
            self._reload()
            return copy.deepcopy(self._find(instance_id))

    def _mark_ready(self, instance_id: str, working: dict[str, Any]) -> bool:
        minecraft_root = self.store.instance_minecraft_root(instance_id)
        ready = bool(self.player.is_ready(working, minecraft_root))
        working.update(ready=ready, install_state="ready" if ready else "incomplete",
                       install_error="" if ready else "Required Minecraft or runtime files are incomplete")
        return ready

    # -- install / import ----------------------------------------------

    def install_instance(self, ref: str, *, launch_after: bool = False) -> dict[str, Any]:
        """Download Minecraft (and runtime) for a vanilla instance in the background."""
        with self._lock:
            self._reload()
            instance = self._find(ref)
            if instance.get("loader"):
                raise ControlError("Modpack instances are prepared by import_modpack; re-import to repair")
            instance_id = instance["id"]

        def work(job: Job) -> dict[str, Any]:
            self._prepare_vanilla(job, instance_id)
            result = {"instance": self.summarize(self._snapshot(instance_id))}
            if launch_after:
                result["game"] = self.launch(instance_id)
            return result

        return self._start_job("install", instance_id, work)

    def _prepare_vanilla(self, job: Job, instance_id: str) -> None:
        working = self._snapshot(instance_id)
        if not working.get("version"):
            job.message = "Resolving latest Minecraft release"
            working["version"] = self.installer.resolve_version()
        self._update_instance(instance_id, {"version": working["version"], "install_state": "installing",
                                            "install_error": "", "ready": False})
        try:
            self.installer.install(working, self.store.instance_minecraft_root(instance_id), self._progress(job))
            ready = self._mark_ready(instance_id, working)
        except Exception as error:
            self._update_instance(instance_id, {"ready": False, "install_state": "failed",
                                                "install_error": str(error) or "Installation failed"})
            raise
        self._update_instance(instance_id, {key: working[key] for key in
                                            ("version", "ready", "install_state", "install_error")})
        if not ready:
            raise ControlError(working["install_error"])
        job.message = f"Installed Minecraft {working['version']}"

    def import_modpack(self, archive_path: str, name: str | None = None) -> dict[str, Any]:
        """Create a new instance from a .mrpack or CurseForge .zip and prepare it in the background."""
        archive = Path(archive_path).expanduser()
        if not archive.is_file():
            raise ControlError(f"No file at {archive}")
        archive = archive.resolve()
        provider = detect_pack_provider(archive)
        importer = self.modrinth_importer if provider == "modrinth" else self.curseforge_importer
        display = "Modrinth" if provider == "modrinth" else "CurseForge"
        with self._lock:
            self._reload()
            instance = {
                "id": str(uuid.uuid4()), "name": self._unique_name((name or archive.stem).strip() or f"Imported {display} pack"),
                "version": None, "ready": False, "automatic": False, "provider": provider,
                "pack_source": str(archive), "install_state": "importing", "install_error": "",
            }
            self.state["instances"].append(instance)
            self.store.create_instance_root(instance["id"])
            self.store.save(self.state)
            instance_id = instance["id"]

        def work(job: Job) -> dict[str, Any]:
            minecraft_root = self.store.instance_minecraft_root(instance_id)
            game_root = self.store.instance_game_root(instance_id)
            try:
                metadata = importer.import_archive(archive, game_root, on_progress=self._progress(job))
                working = self._snapshot(instance_id)
                working.update(
                    version=metadata["game_version"], minecraft_version=metadata["game_version"],
                    loader=metadata["loader"], loader_version=metadata["loader_version"],
                    installed_files=metadata["installed_files"], pack_format=metadata["format"],
                    install_state="imported", ready=False, install_error="",
                    installed_file_hashes=ModrinthPackUpdater._file_hashes(
                        game_root, metadata.get("installed_files", [])),
                )
                if not metadata.get("complete", True):
                    missing = metadata.get("missing_files", [])
                    action = metadata.get("recovery_action", "Retry the import to recover missing files")
                    working.update(missing_files=missing, recovery_action=action, install_state="incomplete",
                                   install_error=f"Missing {len(missing)} required {display} file(s). {action}")
                    self._update_instance(instance_id, working)
                    raise ControlError(working["install_error"])
                job.message = f"Installing {metadata['loader']} {metadata['loader_version']}"
                installed = self.installer.install_modpack(working, minecraft_root, metadata, self._progress(job))
                if installed:
                    working["installed_version"] = installed
                ready = self._mark_ready(instance_id, working)
                self._update_instance(instance_id, working)
                if not ready:
                    raise ControlError(working["install_error"])
            except ControlError:
                raise
            except Exception as error:
                self._update_instance(instance_id, {"ready": False, "install_state": "failed",
                                                    "install_error": str(error) or f"{display} pack import failed"})
                raise
            job.message = f"Imported {display} pack for Minecraft {working['version']} ({working['loader']})"
            return {"instance": self.summarize(working)}

        return self._start_job("import_modpack", instance_id, work)

    # -- game ----------------------------------------------------------

    def _log_path(self, instance_id: str) -> Path:
        return self.store.instance_root(instance_id) / "logs" / "minecraft.log"

    def launch(self, ref: str, *, username: str | None = None, memory_gib: int | None = None) -> dict[str, Any]:
        """Start a ready instance. Not-ready instances are installed first, as Play does."""
        with self._lock:
            self._reload()
            instance = self._find(ref)
            if username:
                self.set_username(username)
            name = str(self.state.get("username", "")).strip()
            if not name:
                raise ControlError("Set a username first (set_username)")
            memory = memory_gib if memory_gib is not None else self.state.get("memory_gib", default_memory_gib())
            memory, error = validate_memory_gib(memory)
            if error:
                raise ControlError(error)
            minecraft_root = self.store.instance_minecraft_root(instance["id"])
            if not self.player.is_ready(instance, minecraft_root):
                if instance.get("loader"):
                    raise ControlError("This modpack instance is not ready; re-import the pack")
                return {"launched": False, "job": self.install_instance(instance["id"], launch_after=True),
                        "message": "Instance was not ready; installing first, then launching"}
            if self._game is not None and self._game.poll() is None:
                raise ControlError("A Minecraft game is already running")
            if not self.registry.acquire():
                raise ControlError("A Minecraft game is already running (started from the desktop app)")
            record = self.registry.read()
            if record is not None and self.registry.is_alive(record):
                self.registry.release()
                raise ControlError("A Minecraft game is already running")
            try:
                command, game_directory = self.player.build_command(
                    instance, minecraft_root, name, local_identity(name), memory)
                log_path = self._log_path(instance["id"])
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("ab") as log_file:
                    process = self._popen(command, cwd=str(game_directory), stdin=subprocess.DEVNULL,
                                          stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True)
            except Exception as error:
                self.registry.release()
                raise ControlError(f"Launch failed: {error}") from error
            if self.registry.remember(process.pid, instance["id"]) is None:
                self.registry.release()
                raise ControlError("Launch failed: could not verify the Minecraft process")
            self._game = process
            self._game_instance_id = instance["id"]
            threading.Thread(target=self._watch_game, args=(process, instance["id"]), daemon=True).start()
            return {"launched": True, "pid": process.pid, "instance": self.summarize(instance),
                    "username": name, "memory_gib": memory, "log": str(log_path)}

    def _watch_game(self, process: subprocess.Popen, instance_id: str) -> None:
        exit_code = process.wait()
        with self._lock:
            if self._game is process:
                self._game = None
                self._game_instance_id = None
                self.registry.clear()
                self.registry.release()
            self.last_exit = {"instance_id": instance_id, "exit_code": exit_code, "crashed": exit_code != 0,
                              "finished_at": time.time()}

    def game_status(self) -> dict[str, Any]:
        record = self.registry.read()
        running = bool(record and self.registry.is_alive(record))
        return {
            "running": running,
            "pid": record.get("pid") if running else None,
            "instance_id": record.get("instance_id") if running else None,
            "started_here": running and self._game is not None and self._game.pid == record.get("pid"),
            "last_exit": self.last_exit,
        }

    def stop_game(self, *, force: bool = False) -> dict[str, Any]:
        record = self.registry.read()
        if not record or not self.registry.is_alive(record):
            raise ControlError("No Minecraft game is running")
        pid = int(record["pid"])
        sig = signal.SIGKILL if force else signal.SIGTERM
        try:
            os.killpg(os.getpgid(pid), sig)
        except ProcessLookupError:
            pass
        return {"signalled": True, "pid": pid, "signal": sig.name}

    def read_log(self, ref: str, *, lines: int = 80) -> dict[str, Any]:
        with self._lock:
            self._reload()
            instance = self._find(ref)
        path = self._log_path(instance["id"])
        if not path.is_file():
            return {"log": str(path), "lines": []}
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            tail = deque(stream, maxlen=max(1, min(lines, 2000)))
        return {"log": str(path), "lines": [line.rstrip("\n") for line in tail]}
