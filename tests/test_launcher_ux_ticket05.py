import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow


class RecoveringInstaller:
    def __init__(self, version="1.21.4"):
        self.version = version
        self.attempts = 0
        self.calls = []

    def discover_versions(self):
        return [{"id": self.version, "type": "release"}]

    def resolve_version(self):
        return self.version

    def install(self, instance, directory, on_progress):
        self.attempts += 1
        self.calls.append((instance["id"], instance["version"], directory))
        on_progress("Preparing Minecraft", -1, -1)
        time.sleep(0.03)
        if self.attempts == 1:
            raise RuntimeError("download interrupted")
        on_progress("Preparing Minecraft", 4, 4)


class ReadyAfterPreparationPlayer:
    def __init__(self):
        self.ready = False
        self.launches = []

    def is_ready(self, _instance, _directory):
        return self.ready

    def launch(self, instance, directory, username, player_uuid, on_started, on_finished, memory_gib=None):
        self.launches.append((instance["id"], instance["version"], username, directory))
        on_started()
        return object()


def test_interrupted_preparation_reopens_to_play_pinned_version(tmp_path):
    application = QApplication.instance() or QApplication([])
    root = tmp_path / "data"
    first = LauncherWindow(data_root=root, installer=RecoveringInstaller(version="1.22.0"))
    first.state["username"] = "Alex"
    first.state["instances"] = [{
        "id": "survival-1214-a1b2c3d4",
        "name": "Survival",
        "version": "1.21.4",
        "ready": False,
        "install_state": "installing",
    }]
    first.state["selected_setup_id"] = "survival-1214-a1b2c3d4"
    first.store.create_instance_root("survival-1214-a1b2c3d4")
    first.store.save(first.state)
    first.close()

    installer = RecoveringInstaller(version="1.22.0")
    installer.attempts = 1
    player = ReadyAfterPreparationPlayer()
    player.ready = True
    window = LauncherWindow(data_root=root, installer=installer, player=player)
    window.show()
    wait_until(application, lambda: window.discovery_worker is None)

    assert window.play_button.isEnabled()
    assert window.state["instances"][0]["version"] == "1.21.4"
    window.play_button.click()
    wait_until(application, lambda: window.install_worker is None)

    assert installer.calls[-1][1] == "1.21.4"
    assert len(player.launches) == 1
    window.close()


def wait_until(application, predicate):
    for _ in range(200):
        application.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    assert predicate()


def test_failed_preparation_retries_from_play_and_launches_pinned_target_once(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = RecoveringInstaller()
    player = ReadyAfterPreparationPlayer()
    window = LauncherWindow(data_root=tmp_path / "data", installer=installer, player=player)
    window.show()
    wait_until(application, lambda: window.discovery_worker is None)
    window.username_input.setText("Alex")
    window.username_input.editingFinished.emit()

    window.play_button.click()
    wait_until(application, lambda: window.install_worker is None)

    assert installer.attempts == 1
    assert window.play_button.isEnabled()
    assert "Retry" in window.play_button.text()
    automatic = window.state["instances"][0]
    assert automatic["version"] == "1.21.4"

    player.ready = True
    window.play_button.click()
    window.play_button.click()
    wait_until(application, lambda: len(player.launches) == 1 and window.install_worker is None)

    assert installer.attempts == 2
    assert len(player.launches) == 1
    assert installer.calls[-1][0] == automatic["id"]
    assert installer.calls[-1][1] == "1.21.4"
    assert "failed" not in window.instance_status_label.text().lower()
    window.close()


def test_ready_marker_does_not_disable_play_when_actual_files_need_preparation(tmp_path):
    application = QApplication.instance() or QApplication([])
    root = tmp_path / "data"
    installer = RecoveringInstaller()
    player = ReadyAfterPreparationPlayer()
    first = LauncherWindow(data_root=root, installer=installer, player=player)
    first.state["username"] = "Alex"
    first.state["instances"] = [{
        "id": "survival-1214-a1b2c3d4",
        "name": "Survival",
        "version": "1.21.4",
        "ready": True,
    }]
    first.store.create_instance_root("survival-1214-a1b2c3d4")
    first.state["selected_setup_id"] = "survival-1214-a1b2c3d4"
    first.store.save(first.state)
    first.close()

    window = LauncherWindow(data_root=root, installer=installer, player=player)
    window.show()
    wait_until(application, lambda: window.discovery_worker is None)

    assert window.play_button.isEnabled()
    window.play_button.click()
    wait_until(application, lambda: window.install_worker is None)
    assert installer.attempts == 1
    assert len(player.launches) == 0
    window.close()


def test_setup_selection_is_locked_until_failed_preparation_finishes(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = RecoveringInstaller()
    player = ReadyAfterPreparationPlayer()
    window = LauncherWindow(data_root=tmp_path / "data", installer=installer, player=player)
    window.show()
    wait_until(application, lambda: window.discovery_worker is None)
    window.username_input.setText("Alex")
    window.username_input.editingFinished.emit()

    window.play_button.click()
    wait_until(application, lambda: window.install_worker is not None)
    assert not window.setup_selector.isEnabled()
    assert not window.setup_search_input.isEnabled()
    wait_until(application, lambda: window.install_worker is None)
    assert window.setup_selector.isEnabled()
    assert window.setup_search_input.isEnabled()
    window.close()


def test_preparation_explains_connectivity_requirement_before_download(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = RecoveringInstaller()
    player = ReadyAfterPreparationPlayer()
    window = LauncherWindow(data_root=tmp_path / "data", installer=installer, player=player)
    window.show()
    wait_until(application, lambda: window.discovery_worker is None)
    window.username_input.setText("Alex")
    window.username_input.editingFinished.emit()

    window.play_button.click()

    assert "connect" in window.diagnostic_hint_label.text().lower()
    assert "prepar" in window.diagnostic_hint_label.text().lower()
    wait_until(application, lambda: window.install_worker is None)
    window.close()


def test_failure_points_to_retry_on_same_play_button_and_clears_after_recovery(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = RecoveringInstaller()
    player = ReadyAfterPreparationPlayer()
    window = LauncherWindow(data_root=tmp_path / "data", installer=installer, player=player)
    window.show()
    wait_until(application, lambda: window.discovery_worker is None)
    window.username_input.setText("Alex")
    window.username_input.editingFinished.emit()

    window.play_button.click()
    wait_until(application, lambda: window.install_worker is None)

    assert "Retry" in window.play_button.text()
    assert "Play" in window.diagnostic_hint_label.text()
    assert "same" in window.diagnostic_hint_label.text().lower()

    player.ready = True
    window.play_button.click()
    wait_until(application, lambda: len(player.launches) == 1 and window.install_worker is None)
    assert window.diagnostic_hint_label.text() == ""
    window.close()


def test_preparation_failure_remains_available_in_diagnostic_export(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    installer = RecoveringInstaller()
    player = ReadyAfterPreparationPlayer()
    window = LauncherWindow(data_root=tmp_path / "data", installer=installer, player=player)
    window.show()
    wait_until(application, lambda: window.discovery_worker is None)
    window.username_input.setText("Alex")
    window.username_input.editingFinished.emit()
    window.play_button.click()
    wait_until(application, lambda: window.install_worker is None)

    output = tmp_path / "diagnostic.log"
    monkeypatch.setattr(
        "mclauncher.app.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(output), "Diagnostic log (*.log)"),
    )
    window._save_diagnostic_log()

    diagnostic = output.read_text(encoding="utf-8")
    assert "Installation error: download interrupted" in diagnostic
    assert "Last event: Installation failed: download interrupted" in diagnostic
    window.close()
