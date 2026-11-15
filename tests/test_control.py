import json
import os
import sys
import time
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import anyio
import pytest

from mclauncher.control import ControlError, LauncherController, detect_pack_provider
from mclauncher.identity import local_identity
from mclauncher.lifecycle import GameProcessRegistry
from mclauncher.persistence import LauncherStore


class FakeInstaller:
    def __init__(self):
        self.installed = []

    def resolve_version(self):
        return "1.21.1"

    def discover_versions(self):
        return [{"id": "1.21.1", "type": "release"}, {"id": "24w01a", "type": "snapshot"}]

    def install(self, instance, minecraft_directory, on_progress):
        on_progress("Downloading", 1, 2)
        (minecraft_directory / "ready").write_text(instance["version"])
        self.installed.append(instance["version"])

    def install_modpack(self, instance, minecraft_directory, metadata, on_progress):
        (minecraft_directory / "ready").write_text(metadata["game_version"])
        return f"{metadata['loader']}-{metadata['game_version']}"

    def resolve_loader(self, *_args):
        return {}


class FakePlayer:
    """Ready once FakeInstaller wrote its marker; launches a harmless sleeper."""

    def __init__(self):
        self.commands = []

    def is_ready(self, instance, minecraft_directory):
        return (minecraft_directory / "ready").is_file()

    def build_command(self, instance, minecraft_directory, username, player_uuid, memory_gib=None):
        self.commands.append((instance["id"], username, player_uuid, memory_gib))
        return [sys.executable, "-c", "import time; time.sleep(30)"], minecraft_directory.parent


class FakeImporter:
    def __init__(self, complete=True):
        self.complete = complete

    def import_archive(self, archive, minecraft_root, on_progress=None):
        (minecraft_root / "mods").mkdir(parents=True, exist_ok=True)
        (minecraft_root / "mods" / "a.jar").write_bytes(b"jar")
        return {"game_version": "1.20.1", "loader": "fabric", "loader_version": "0.15.0",
                "installed_files": ["mods/a.jar"], "format": "mrpack", "complete": self.complete,
                "missing_files": [] if self.complete else [{"project_id": 1, "file_id": 2}]}


def _controller(tmp_path, **kwargs):
    return LauncherController(
        tmp_path / "data", installer=FakeInstaller(), player=FakePlayer(),
        modrinth_importer=kwargs.pop("modrinth_importer", FakeImporter()),
        curseforge_importer=kwargs.pop("curseforge_importer", FakeImporter()),
        run_jobs_inline=True, **kwargs,
    )


def _pack(tmp_path, member, name="pack.mrpack"):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr(member, "{}")
    return path


def test_create_and_install_vanilla_instance_persists_for_the_gui(tmp_path):
    control = _controller(tmp_path)
    created = control.create_instance("Survival")
    job = control.install_instance("survival")  # names match case-insensitively

    assert job["status"] == "succeeded", job["message"]
    saved = LauncherStore(tmp_path / "data").load()["instances"]
    assert saved == [dict(saved[0], id=created["id"], name="Survival", version="1.21.1", ready=True,
                          install_state="ready")]


def test_duplicate_names_are_suffixed_like_the_gui(tmp_path):
    control = _controller(tmp_path)
    control.create_instance("Pack")
    assert control.create_instance("Pack")["name"] == "Pack (2)"


def test_failed_install_is_reported_on_job_and_instance(tmp_path):
    control = _controller(tmp_path)

    def broken(*_args):
        raise RuntimeError("network down")

    control.installer.install = broken
    created = control.create_instance("Broken", "1.21.1")
    job = control.install_instance(created["id"])

    assert job["status"] == "failed"
    assert control.job(job["id"])["message"] == "network down"
    assert control.get_instance(created["id"])["install_state"] == "failed"


def test_detects_pack_provider_from_manifest(tmp_path):
    assert detect_pack_provider(_pack(tmp_path, "modrinth.index.json")) == "modrinth"
    assert detect_pack_provider(_pack(tmp_path, "manifest.json", "cf.zip")) == "curseforge"
    with pytest.raises(ControlError):
        detect_pack_provider(_pack(tmp_path, "readme.txt", "other.zip"))


def test_import_modpack_creates_ready_loader_instance(tmp_path):
    control = _controller(tmp_path)
    job = control.import_modpack(str(_pack(tmp_path, "modrinth.index.json", "Cool Pack.mrpack")))

    assert job["status"] == "succeeded", job["message"]
    instance = control.get_instance("Cool Pack")
    assert instance["loader"] == "fabric" and instance["ready"] is True
    assert instance["provider"] == "modrinth"


def test_incomplete_curseforge_import_fails_with_recovery_hint(tmp_path):
    control = _controller(tmp_path, curseforge_importer=FakeImporter(complete=False))
    job = control.import_modpack(str(_pack(tmp_path, "manifest.json", "cf.zip")), name="CF")

    assert job["status"] == "failed"
    assert "Missing 1 required CurseForge file" in job["message"]
    assert control.get_instance("CF")["install_state"] == "incomplete"


def test_launch_requires_username_then_runs_and_stops_game(tmp_path):
    control = _controller(tmp_path)
    created = control.create_instance("Play", "1.21.1")
    control.install_instance(created["id"])
    with pytest.raises(ControlError, match="username"):
        control.launch("Play")

    launched = control.launch("Play", username="Steve", memory_gib=2)
    try:
        assert launched["launched"] is True
        assert control.player.commands[-1] == (created["id"], "Steve", local_identity("Steve"), 2)
        status = control.game_status()
        assert status["running"] and status["instance_id"] == created["id"]
        with pytest.raises(ControlError, match="already running"):
            control.launch("Play")
        with pytest.raises(ControlError, match="running"):
            control.install_instance("Play")
    finally:
        control.stop_game(force=True)
    _wait_for(lambda: control.last_exit is not None)
    assert not control.game_status()["running"]
    assert control.last_exit["crashed"] is True


def test_launch_is_refused_while_the_desktop_app_holds_the_game_lock(tmp_path):
    control = _controller(tmp_path)
    control.create_instance("Play", "1.21.1")
    control.install_instance("Play")
    control.set_username("Alex")
    gui = GameProcessRegistry(tmp_path / "data")
    assert gui.acquire()
    try:
        with pytest.raises(ControlError, match="desktop app"):
            control.launch("Play")
    finally:
        gui.release()


def test_launch_of_unready_vanilla_instance_installs_first(tmp_path):
    control = _controller(tmp_path)
    control.create_instance("Fresh")
    result = control.launch("Fresh", username="Alex")
    try:
        assert result["launched"] is False
        assert result["job"]["status"] == "succeeded"
        assert result["job"]["result"]["game"]["launched"] is True
    finally:
        control.stop_game(force=True)
    _wait_for(lambda: control.last_exit is not None)


def test_changes_made_by_the_gui_are_visible_to_the_controller(tmp_path):
    control = _controller(tmp_path)
    gui_store = LauncherStore(tmp_path / "data")
    gui_state = gui_store.load()
    gui_state["instances"].append({"id": "11111111-1111-4111-8111-111111111111", "name": "From GUI",
                                   "version": "1.20.4", "ready": False})
    gui_store.save(gui_state)

    assert [item["name"] for item in control.list_instances()] == ["From GUI"]


def test_mcp_server_exposes_tools_and_reports_errors(tmp_path):
    pytest.importorskip("mcp")
    from mcp.server.mcpserver.exceptions import ToolError

    from mclauncher.mcp_server import build_server

    server = build_server(_controller(tmp_path))

    async def scenario():
        names = {tool.name for tool in await server.list_tools()}
        assert {"create_instance", "import_modpack", "launch_game", "get_job", "stop_game"} <= names
        result = await server.call_tool("create_instance", {"name": "Via MCP", "version": "1.21.1", "install": True})
        payload = json.loads(result.content[0].text)
        assert payload["job"]["status"] == "succeeded"
        with pytest.raises(ToolError, match="No instance matches 'missing'"):
            await server.call_tool("get_instance", {"instance": "missing"})

    anyio.run(scenario)


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition was not met in time")
        time.sleep(0.02)
