import json

from PySide6.QtWidgets import QApplication, QCheckBox, QDialog

from mclauncher.app import LauncherWindow
from mclauncher.persistence import LauncherStore


class VersionInstaller:
    def __init__(self, versions, error=None):
        self.versions = versions
        self.error = error

    def discover_versions(self):
        if self.error:
            raise RuntimeError(self.error)
        return self.versions


class ReadinessPlayer:
    def __init__(self, ready_ids=()):
        self.ready_ids = set(ready_ids)
        self.launches = []

    def is_ready(self, instance, _directory):
        return instance["id"] in self.ready_ids


def _process(application, window):
    for _ in range(100):
        application.processEvents()
        if window.discovery_worker is None:
            return


def _items(window):
    return [(window.setup_selector.itemText(row), window.setup_selector.itemData(row))
            for row in range(window.setup_selector.count())
            if window.setup_selector.itemData(row) is not None]


def test_search_groups_duplicate_named_setups_by_stable_id_and_preserves_selection(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow(data_root=tmp_path / "data", installer=VersionInstaller([
        {"id": "1.21.4", "type": "release"},
    ]))
    window.state["instances"] = [
        {"id": "alpha-1214-a1b2c3d4", "name": "Survival", "version": "1.21.4", "ready": False},
        {"id": "beta-1214-e5f6a7b8", "name": "Survival", "version": "1.21.4", "ready": False},
    ]
    window._add_instance_item(window.state["instances"][0])
    window._add_instance_item(window.state["instances"][1])
    window.show()
    _process(application, window)
    assert _items(window)[-2:] == [
        ("Survival · alpha-1214-a1b2c3d4", "alpha-1214-a1b2c3d4"),
        ("Survival · beta-1214-e5f6a7b8", "beta-1214-e5f6a7b8"),
    ]
    selected = window.setup_selector.findData("beta-1214-e5f6a7b8")
    window.setup_selector.setCurrentIndex(selected)
    window.setup_search_input.setText("does-not-exist")
    assert window.selector_empty_label.isVisible()
    assert window.setup_selector.currentData() == "beta-1214-e5f6a7b8"
    window.close()


def test_downloaded_marker_requires_associated_automatic_instance_readiness(tmp_path):
    application = QApplication.instance() or QApplication([])
    player = ReadinessPlayer({"auto-1214-a1b2c3d4"})
    window = LauncherWindow(data_root=tmp_path / "data", installer=VersionInstaller([
        {"id": "1.21.4", "type": "release"},
    ]), player=player)
    window.state["automatic_instances"] = {"1.21.4": "auto-1214-a1b2c3d4"}
    window.state["instances"] = [
        {"id": "auto-1214-a1b2c3d4", "name": "Minecraft 1.21.4", "version": "1.21.4", "ready": False, "automatic": True},
        {"id": "named-1214-a1b2c3d4", "name": "Named", "version": "1.21.4", "ready": True},
    ]
    window.state["available_version_metadata"] = [{"id": "1.21.4", "type": "release"}]
    window._rebuild_setup_selector()
    version_row = window.setup_selector.findData("version:1.21.4")
    assert window.setup_selector.itemText(version_row).startswith("✓ ")
    window.close()


def test_snapshots_are_opt_in_and_preference_is_saved_automatically(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    installer = VersionInstaller([
        {"id": "1.21.4", "type": "release"},
        {"id": "25w01a", "type": "snapshot"},
    ])
    window = LauncherWindow(data_root=tmp_path / "data", installer=installer)
    _process(application, window)
    assert window.setup_selector.findData("version:25w01a") == -1

    def accept(dialog):
        dialog.findChild(QCheckBox).setChecked(True)
        return 1

    monkeypatch.setattr(QDialog, "exec", accept)
    window._open_settings()
    assert window.state["show_snapshots"] is True
    assert window.store.load()["show_snapshots"] is True
    assert window.setup_selector.findData("version:25w01a") >= 0
    window.close()


def test_cached_metadata_restores_choices_when_discovery_is_offline(tmp_path):
    application = QApplication.instance() or QApplication([])
    root = tmp_path / "data"
    first = LauncherWindow(data_root=root, installer=VersionInstaller([
        {"id": "1.21.4", "type": "release"},
        {"id": "25w01a", "type": "snapshot"},
    ]))
    first.state["show_snapshots"] = True
    first.state["selected_setup_id"] = "version:25w01a"
    first.store.save(first.state)
    _process(application, first)
    first.close()
    second = LauncherWindow(data_root=root, installer=VersionInstaller([], error="offline"))
    _process(application, second)
    assert second.setup_selector.findData("version:25w01a") >= 0
    assert second.setup_selector.currentData() == "version:25w01a"
    second.close()


def test_disabling_snapshots_keeps_existing_pinned_snapshot_setup_visible(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow(data_root=tmp_path / "data", installer=VersionInstaller([
        {"id": "1.21.4", "type": "release"},
        {"id": "25w01a", "type": "snapshot"},
    ]))
    window.state["show_snapshots"] = True
    window.state["available_version_metadata"] = [
        {"id": "1.21.4", "type": "release"}, {"id": "25w01a", "type": "snapshot"}
    ]
    window.state["instances"] = [{
        "id": "auto-25w01a-a1b2c3d4", "name": "Minecraft 25w01a", "version": "25w01a",
        "ready": False, "automatic": True,
    }]
    window.state["automatic_instances"] = {"25w01a": "auto-25w01a-a1b2c3d4"}
    window.state["selected_setup_id"] = "version:25w01a"
    window._rebuild_setup_selector(selected="version:25w01a")
    assert window.setup_selector.findData("version:25w01a") >= 0
    window.state["show_snapshots"] = False
    window._rebuild_setup_selector(selected="version:25w01a")
    assert window.setup_selector.findData("version:25w01a") >= 0
    window.close()


def test_invalid_snapshot_preference_requires_state_recovery(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "state.json").write_text(json.dumps({"username": "Alex", "instances": [], "show_snapshots": "yes"}))
    store = LauncherStore(root)
    state = store.load()
    assert store.recovery_required
    assert state["show_snapshots"] is False
