"""The audit journal must let an incident be reconstructed from audit.jsonl alone."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from mclauncher import audit as audit_module
from mclauncher.audit import AuditLog, diff_state
from mclauncher.control import ControlError
from mclauncher.mcp_server import _tool
from mclauncher.persistence import LauncherStore

from test_control import _controller


def _actions(log: AuditLog) -> list[str]:
    return [event["action"] for event in log.read()]


def test_every_save_journals_a_field_level_diff(tmp_path):
    store = LauncherStore(tmp_path)
    state = store.load()
    state["username"] = "Alex"
    state["instances"].append({"id": "a" * 8 + "-0000-4000-8000-" + "0" * 12, "name": "One",
                               "installed_files": [f"mods/{index}.jar" for index in range(500)]})
    store.save(state)
    state["username"] = "Steve"
    state["instances"][0]["installed_files"] = state["instances"][0]["installed_files"][1:]
    store.save(state)
    state["instances"] = []
    store.save(state)

    first, second, third = store.audit.read()
    assert first["action"] == "state_change" and first["source"] == "app"
    assert first["settings"]["username"] == {"before": "", "after": "Alex"}
    assert first["instances_added"][0]["installed_files"] == {"count": 500}
    assert second["settings"]["username"] == {"before": "Alex", "after": "Steve"}
    (changed,) = second["instances_changed"].values()
    files = changed["fields"]["installed_files"]
    assert files["removed"] == ["mods/0.jar"] and files["before_count"] == 500 and files["after_count"] == 499
    assert third["instances_removed"][0]["name"] == "One"


def test_unchanged_save_writes_nothing():
    assert diff_state({"username": "a", "instances": []}, {"username": "a", "instances": []}) == {}


def test_controller_delete_survives_in_the_journal_with_an_inventory(tmp_path):
    control = _controller(tmp_path)
    created = control.create_instance("Gone")
    root = control.store.instance_root(created["id"])
    (root / "saves" / "My World").mkdir(parents=True)
    (root / "saves" / "My World" / "level.dat").write_bytes(b"x" * 10)
    (root / "mods").mkdir()
    (root / "mods" / "sodium.jar").write_bytes(b"jar")

    control.delete_instance("Gone")

    assert not root.exists()
    assert (tmp_path / "data" / "audit.jsonl").is_file()
    events = [event for event in control.audit.read() if event["action"] == "delete_instance"]
    assert [event["phase"] for event in events] == ["started", "folder_removed"]
    folder = events[0]["folder"]
    assert folder["saves"] == ["My World"] and folder["mods"] == ["sodium.jar"]
    assert folder["file_count"] == 2 and folder["total_bytes"] == 13
    assert events[0]["source"] == "control" and events[0]["name"] == "Gone"
    removal = [event for event in control.audit.read() if event.get("instances_removed")]
    assert removal and removal[-1]["instances_removed"][0]["id"] == created["id"]


def test_jobs_and_failures_are_journaled_with_outcome(tmp_path):
    control = _controller(tmp_path)
    control.create_instance("Survival")
    job = control.install_instance("Survival")

    events = control.audit.read()
    started = [event for event in events if event["action"] == "job_started"]
    finished = [event for event in events if event["action"] == "job_finished"]
    assert started[0]["job_id"] == job["id"] == finished[0]["job_id"]
    assert finished[0]["status"] == "succeeded" and finished[0]["seconds"] >= 0


def test_launch_stop_and_exit_are_journaled_and_bannered(tmp_path):
    control = _controller(tmp_path)
    control.set_username("Alex")
    control.create_instance("Survival")
    control.install_instance("Survival")
    launched = control.launch("Survival")
    try:
        control.stop_game(force=True)
        control._game.wait(timeout=10)
    finally:
        if control._game is not None and control._game.poll() is None:
            control._game.kill()
    for _ in range(100):
        if "game_exit" in _actions(control.audit):
            break
        import time
        time.sleep(0.05)

    events = {event["action"]: event for event in control.audit.read()}
    assert events["game_launch"]["pid"] == launched["pid"] and events["game_launch"]["username"] == "Alex"
    assert events["game_stop"]["signal"] == "SIGKILL"
    assert events["game_exit"]["pid"] == launched["pid"]
    log = (tmp_path / "data" / "instances").glob("*/logs/minecraft.log")
    text = next(log).read_text()
    assert "launch source=control" in text and "exit pid=" in text


class _FakeServer:
    def __init__(self):
        self.tools = {}

    def tool(self, **_options):
        def register(function):
            self.tools[function.__name__] = function
            return function
        return register


def test_mcp_calls_are_journaled_including_refusals_but_not_successful_polls(tmp_path):
    log = AuditLog(tmp_path, source="mcp")
    server = _FakeServer()

    @_tool(server, log)
    def delete_instance(instance: str):
        raise ControlError("That instance is running; stop the game first")

    @_tool(server, log)
    def rename_instance(instance: str, name: str):
        return {"name": name}

    @_tool(server, log)
    def get_job(job_id: str):
        return {"status": "running"}

    with pytest.raises(Exception, match="stop the game first"):
        server.tools["delete_instance"](instance="World")
    server.tools["rename_instance"](instance="World", name="New")
    server.tools["get_job"](job_id="abc")

    events = log.read()
    assert [(event["tool"], event["outcome"]) for event in events] == [
        ("delete_instance", "error"), ("rename_instance", "ok")]
    assert events[0]["kwargs"] == {"instance": "World"} and events[0]["source"] == "mcp"
    assert "stop the game first" in events[0]["error"]


def test_rotation_keeps_old_journals(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_module, "MAX_BYTES", 200)
    log = AuditLog(tmp_path)
    for index in range(10):
        log.record("tick", index=index)

    rotated = sorted(tmp_path.glob("audit-*.jsonl"))
    assert rotated, "a full journal is renamed, never truncated"
    lines = sum(len(path.read_text().splitlines()) for path in [*rotated, log.path])
    assert lines == 10


def test_journal_failure_never_breaks_the_save(tmp_path, monkeypatch, capsys):
    store = LauncherStore(tmp_path)
    state = store.load()
    real_open = os.open

    def refuse_audit(path, *args, **kwargs):
        if str(path).endswith("audit.jsonl"):
            raise PermissionError("read-only")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(audit_module.os, "open", refuse_audit)
    state["username"] = "Alex"
    store.save(state)

    assert LauncherStore(tmp_path).load()["username"] == "Alex"
    assert "could not write audit event" in capsys.readouterr().err


def test_desktop_app_journals_mod_changes_and_instance_deletion(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from mclauncher.app import LauncherWindow
    from test_local_mods import write_fabric_mod

    QApplication.instance() or QApplication([])
    jar = tmp_path / "example.jar"
    write_fabric_mod(jar)
    window = LauncherWindow(data_root=tmp_path / "data")
    instance = {"id": "pack-1214-a1b2c3d4", "name": "Pack", "version": "1.21.4",
                "loader": "fabric", "ready": True, "provider": "modrinth", "mods": []}
    window.state["instances"] = [instance]
    root = window.store.create_instance_root(instance["id"])
    (root / "saves" / "Base").mkdir(parents=True)
    window.store.save(window.state)
    window._add_instance_item(instance)
    window.instance_list.setCurrentRow(0)
    monkeypatch.setattr("mclauncher.app.QFileDialog.getOpenFileName", lambda *a, **k: (str(jar), "JAR"))
    monkeypatch.setattr("mclauncher.app.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.Yes)

    window._show_page(2)
    window._import_local_mod()
    window.mods_list.setCurrentRow(0)
    window._toggle_selected_mod()
    window._remove_selected_mod()
    window._delete_selected_instance()
    window.close()

    events = AuditLog(tmp_path / "data").read()
    actions = [event["action"] for event in events]
    assert actions[0] == "app_start" and actions[-1] == "app_close"
    for expected in ("import_local_mod", "toggle_mod", "remove_mod", "delete_instance"):
        assert expected in actions
    removed = next(event for event in events if event["action"] == "remove_mod")
    assert removed["file"]["exists"] is True and removed["mod"]["filename"] == "example.jar"
    deleted = next(event for event in events if event["action"] == "delete_instance")
    assert deleted["folder"]["saves"] == ["Base"] and deleted["name"] == "Pack"
    assert not root.exists()
