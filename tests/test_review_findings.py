import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow
from mclauncher.installer import DetachedMinecraftProcess, MinecraftPlayer
from mclauncher.persistence import LauncherStore


def test_corrupt_state_is_backed_up_and_requires_explicit_recovery(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "state.json").write_text("{broken", encoding="utf-8")
    store = LauncherStore(root)
    store.load()
    assert store.recovery_required
    assert list(root.glob("state.json.corrupt-*"))
    with __import__("pytest").raises(RuntimeError):
        store.save({"username": "lost", "instances": []})
    store.recover_defaults()
    assert json.loads((root / "state.json").read_text()) == {
        "automatic_instances": {},
        "available_version_metadata": [],
        "available_versions": [],
        "instances": [],
        "selected_instance_id": "",
        "selected_setup_id": "",
        "show_snapshots": False,
        "username": "",
    }


def test_instance_paths_reject_escape_and_symlink(tmp_path):
    store = LauncherStore(tmp_path / "data")
    with __import__("pytest").raises(ValueError):
        store.create_instance_root("../outside")
    external = tmp_path / "external"
    external.mkdir()
    (store.instances_root / "escape").symlink_to(external, target_is_directory=True)
    with __import__("pytest").raises(ValueError):
        store.create_instance_root("escape")


def test_wrong_state_field_type_is_backed_up(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    original = {"username": ["must be text"], "instances": []}
    (root / "state.json").write_text(json.dumps(original), encoding="utf-8")
    store = LauncherStore(root)
    state = store.load()
    assert state == {
        "automatic_instances": {},
        "available_version_metadata": [],
        "available_versions": [],
        "instances": [],
        "selected_instance_id": "",
        "selected_setup_id": "",
        "show_snapshots": False,
        "username": "",
    }
    assert json.loads(next(root.glob("state.json.corrupt-*" )).read_text()) == original


def test_launcher_surfaces_state_recovery_and_does_not_overwrite_backup(tmp_path):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "data"
    root.mkdir()
    original = "{not-json"
    (root / "state.json").write_text(original, encoding="utf-8")
    window = LauncherWindow(data_root=root)
    window.show()
    app.processEvents()
    assert not window.state_recovery_label.isHidden()
    assert window.state_recovery_label.isVisible()
    assert window.recover_state_button.isVisible()
    assert "Recover defaults" in window.state_recovery_label.text()
    assert (root / "state.json").read_text(encoding="utf-8") == original
    window.recover_state_button.click()
    assert window.state_recovery_label.isHidden()
    assert window.recover_state_button.isHidden()
    assert any(path.read_text(encoding="utf-8") == original for path in root.glob("state.json.corrupt-*"))
    window.close()
    app.processEvents()


def test_player_launch_internal_type_error_is_not_retried(tmp_path):
    app = QApplication.instance() or QApplication([])
    class Player:
        def __init__(self): self.calls = 0
        def launch(self, *args, memory_gib=None):
            self.calls += 1
            raise TypeError("internal player error")
    player = Player()
    window = LauncherWindow(data_root=tmp_path / "data", player=player)
    window.username_input.setText("Alex")
    window.save_username_button.click()
    window.instance_name_input.setText("Test")
    window.create_instance_button.click()
    instance = window.state["instances"][0]
    instance.update(version="1.21.4", ready=True)
    window._select_instance(window.instance_list.currentItem(), None)
    window.play_button.click()
    assert player.calls == 1
    window.close()
    app.processEvents()


def test_detached_process_writes_combined_output_to_instance_log(tmp_path):
    seen = []
    process = DetachedMinecraftProcess(
        ["sh", "-c", "printf out; printf err >&2"], tmp_path, lambda code, crashed: seen.append((code, crashed))
    )
    process._process.wait()
    process._poll()
    assert (tmp_path / "logs" / "minecraft.log").read_text() == "outerr"
    assert seen == [(0, False)]


def test_ready_flag_alone_does_not_enable_play(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = LauncherWindow(data_root=tmp_path / "data", player=MinecraftPlayer())
    window.username_input.setText("Alex")
    window.save_username_button.click()
    window.instance_name_input.setText("Test")
    window.create_instance_button.click()
    instance = window.state["instances"][0]
    instance.update(version="1.21.4", ready=True)
    window.store.save(window.state)
    window._select_instance(window.instance_list.currentItem(), None)
    assert not window.play_button.isEnabled()
    window.close()
    app.processEvents()


def test_close_during_install_is_ignored(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = LauncherWindow(data_root=tmp_path / "data")
    window.install_worker = object()
    window.installing_instance = {"id": "x", "name": "x"}
    class Event:
        def __init__(self): self.ignored = False
        def ignore(self): self.ignored = True
    event = Event()
    window.closeEvent(event)
    assert event.ignored
    window.install_worker = None
    window.installing_instance = None
    window.close()
    app.processEvents()
