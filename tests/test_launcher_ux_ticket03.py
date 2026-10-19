import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow


class ReleaseInstaller:
    def __init__(self, versions=("1.21.4", "1.21.3"), latest=None):
        self.versions = versions
        self.latest = latest
        self.calls = []
        self.resolve_calls = 0

    def discover_versions(self):
        return [{"id": version, "type": "release"} for version in self.versions]

    def resolve_version(self):
        self.resolve_calls += 1
        return self.latest or self.versions[0]

    def install(self, instance, directory, on_progress):
        self.calls.append((instance["id"], instance["version"], directory))
        on_progress("Downloading Minecraft", -1, -1)


class Player:
    def __init__(self):
        self.calls = []
        self.finished = None

    def launch(self, instance, directory, username, player_uuid, on_started, on_finished, memory_gib=None):
        self.calls.append((instance["id"], instance["version"], username))
        self.finished = on_finished
        on_started()
        return object()

    def finish(self):
        if self.finished:
            callback, self.finished = self.finished, None
            callback(0, False)


class UnreadyPlayer(Player):
    def __init__(self):
        super().__init__()
        self.readiness_checks = 0

    def is_ready(self, instance, directory):
        self.readiness_checks += 1
        return False


class ProgressInstaller(ReleaseInstaller):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unknown_seen = False

    def install(self, instance, directory, on_progress):
        on_progress("Downloading", -1, -1)
        self.unknown_seen = True
        time.sleep(0.05)
        on_progress("Downloading", 2, 5)
        self.calls.append((instance["id"], instance["version"], directory))


class FailingDiscoveryInstaller(ReleaseInstaller):
    def discover_versions(self):
        raise RuntimeError("offline")


def _wait_until(application, predicate):
    for _ in range(100):
        application.processEvents()
        if predicate():
            return
        QTest.qWait(10)


def test_play_creates_automatic_instance_prepares_and_launches_once(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = ReleaseInstaller(("1.21.4",))
    player = Player()
    window = LauncherWindow(data_root=tmp_path / "data", installer=installer, player=player)
    window.show()
    _process(application, window)
    window.username_input.setText("Alex")
    window.username_input.editingFinished.emit()

    window.play_button.click()
    _process(application, window)
    _wait_until(application, lambda: len(installer.calls) == 1 and not window.install_progress.isVisible())

    assert len(installer.calls) == 1
    assert installer.calls[0][1] == "1.21.4"
    assert len(player.calls) == 1
    assert window.state["automatic_instances"]["1.21.4"] == installer.calls[0][0]
    window.close()


def test_discovery_failure_keeps_existing_setup_playable(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = FailingDiscoveryInstaller()
    player = Player()
    window = LauncherWindow(data_root=tmp_path / "data", installer=installer, player=player)
    window.state["username"] = "Alex"
    window.state["instances"] = [{"id": "survival-1214-a1b2c3d4", "name": "Survival", "version": "1.21.4", "ready": True}]
    window.store.create_instance_root("survival-1214-a1b2c3d4")
    window.store.save(window.state)
    window.close()
    window = LauncherWindow(data_root=tmp_path / "data", installer=installer, player=player)
    window.show()
    _process(application, window)
    assert window.setup_selector.itemText(0) == "Survival"
    assert window.play_button.isEnabled()
    window.close()


def test_unknown_progress_is_indeterminate_then_known_totals_restore_range(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = ProgressInstaller(("1.21.4",))
    window = LauncherWindow(data_root=tmp_path / "data", installer=installer)
    window.show()
    _process(application, window)
    window.username_input.setText("Alex")
    window.username_input.editingFinished.emit()
    window.play_button.click()
    _wait_until(application, lambda: installer.unknown_seen)
    _wait_until(application, lambda: window.install_progress.maximum() == 0)
    assert window.install_progress.minimum() == 0
    assert window.install_progress.maximum() == 0
    _wait_until(application, lambda: window.install_progress.maximum() == 5)
    window.close()


def test_auto_launch_requires_actual_player_readiness(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = ReleaseInstaller(("1.21.4",))
    player = UnreadyPlayer()
    window = LauncherWindow(data_root=tmp_path / "data", installer=installer, player=player)
    window.show()
    _process(application, window)
    window.username_input.setText("Alex")
    window.username_input.editingFinished.emit()
    window.play_button.click()
    _wait_until(application, lambda: player.readiness_checks >= 1)
    assert player.readiness_checks >= 1
    assert player.calls == []
    assert window.state["instances"][0]["ready"] is False
    window.close()


def _process(application, window):
    for _ in range(100):
        application.processEvents()
        if window.setup_selector.count() > 0 or "Could not discover" in window.diagnostic_hint_label.text():
            return
        QTest.qWait(10)


def test_stable_releases_are_discovered_into_selector_without_creating_instances(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = ReleaseInstaller()
    window = LauncherWindow(data_root=tmp_path / "data", installer=installer)
    window.show()
    _process(application, window)

    assert [window.setup_selector.itemText(i) for i in range(window.setup_selector.count())] == [
        "Minecraft 1.21.4", "Minecraft 1.21.3"
    ]
    assert window.state["instances"] == []
    assert list((tmp_path / "data" / "instances").iterdir()) == []
    window.close()


def test_first_use_uses_explicit_latest_resolver_and_restores_concrete_selection(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = ReleaseInstaller(("1.21.3", "1.21.4"), latest="1.21.4")
    first = LauncherWindow(data_root=tmp_path / "data", installer=installer)
    first.show()
    _process(application, first)
    assert first.setup_selector.currentData() == "version:1.21.4"
    assert installer.resolve_calls == 1
    first.close()

    second = LauncherWindow(data_root=tmp_path / "data", installer=FailingDiscoveryInstaller())
    second.show()
    _process(application, second)
    assert second.setup_selector.currentData() == "version:1.21.4"
    second.close()


def test_legacy_state_without_selected_setup_keeps_first_named_setup(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = ReleaseInstaller(("1.21.4",))
    window = LauncherWindow(data_root=tmp_path / "data", installer=installer)
    window.state["instances"] = [{"id": "survival-1214-a1b2c3d4", "name": "Survival", "version": "1.21.4", "ready": True}]
    window.store.create_instance_root("survival-1214-a1b2c3d4")
    window.store.save(window.state)
    window.close()
    restored = LauncherWindow(data_root=tmp_path / "data", installer=installer)
    restored.show()
    _process(application, restored)
    assert restored.setup_selector.currentText() == "Survival"
    assert restored.state["selected_setup_id"] == "survival-1214-a1b2c3d4"
    restored.close()


def test_automatic_instances_reuse_version_mapping_and_isolate_second_version(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = ReleaseInstaller(("1.21.4", "1.20.1"))
    player = Player()
    window = LauncherWindow(data_root=tmp_path / "data", installer=installer, player=player)
    window.show()
    _process(application, window)
    window.username_input.setText("Alex")
    window.username_input.editingFinished.emit()
    window.play_button.click()
    _wait_until(application, lambda: len(player.calls) == 1 and not window.install_progress.isVisible())
    first_id = window.state["automatic_instances"]["1.21.4"]
    player.finish()
    second_index = window.setup_selector.findData("version:1.20.1")
    window.setup_selector.setCurrentIndex(second_index)
    window.play_button.click()
    _wait_until(application, lambda: len(player.calls) == 2 and not window.install_progress.isVisible())
    assert window.state["automatic_instances"]["1.20.1"] != first_id
    window.setup_selector.setCurrentIndex(window.setup_selector.findData("version:1.21.4"))
    player.finish()
    window.play_button.click()
    _wait_until(application, lambda: len(player.calls) == 3 and not window.install_progress.isVisible())
    assert window.state["automatic_instances"]["1.21.4"] == first_id
    assert len(window.state["instances"]) == 2
    assert len(installer.calls) == 2
    window.close()


def test_repeated_play_clicks_start_one_install_and_one_launch(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = ReleaseInstaller(("1.21.4",))
    player = Player()
    window = LauncherWindow(data_root=tmp_path / "data", installer=installer, player=player)
    window.show()
    _process(application, window)
    window.username_input.setText("Alex")
    window.username_input.editingFinished.emit()
    window.play_button.click()
    window.play_button.click()
    _wait_until(application, lambda: len(player.calls) == 1 and not window.install_progress.isVisible())
    assert len(installer.calls) == 1
    assert len(player.calls) == 1
    window.close()
