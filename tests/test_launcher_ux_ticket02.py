import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QDialog, QLineEdit, QPushButton, QWidget

from mclauncher.app import LauncherWindow, local_identity


class RunningPlayer:
    def __init__(self, error=None):
        self.error = error
        self.calls = []
        self.process = object()
        self.on_finished = None

    def launch(self, instance, directory, username, player_uuid, on_started, on_finished, memory_gib=None):
        self.calls.append((instance["id"], username, memory_gib))
        if self.error:
            raise RuntimeError(self.error)
        self.on_finished = on_finished
        on_started()
        return self.process

    def finish(self, exit_code=0, crashed=False):
        self.on_finished(exit_code, crashed)


def _ready_window(tmp_path, player):
    window = LauncherWindow(data_root=tmp_path / "launcher-data", player=player)
    window.username_input.setText("Alex")
    window.username_input.editingFinished.emit()
    window.state["instances"] = [{"id": "survival-1214-a1b2c3d4", "name": "Survival", "version": "1.21.4", "ready": True}]
    window.store.create_instance_root("survival-1214-a1b2c3d4")
    window.store.save(window.state)
    window._add_instance_item(window.state["instances"][0])
    window.instance_list.setCurrentRow(0)
    return window


def test_launcher_uses_home_artwork_launch_bar_with_visible_public_controls(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow(data_root=tmp_path / "launcher-data")
    window.show()
    application.processEvents()

    assert window.size().width() == 920
    assert window.size().height() == 560
    assert window.minimumSize().width() <= 680
    assert window.minimumSize().height() <= 420
    assert window.findChild(QLabel, "brandLabel").isVisible()
    assert window.home_artwork.isVisible()
    assert window.home_nav_button.isVisible()
    assert window.instances_nav_button.isVisible()
    assert window.findChild(QWidget, "launchBar").isVisible()
    assert window.username_input.isVisible()
    assert window.setup_selector.isVisible()
    assert window.play_button.isVisible()
    assert window.settings_button.isVisible()
    assert not window.instance_list.isVisible()
    assert not window.install_button.isVisible()
    assert not window.create_instance_button.isVisible()
    assert not window.memory_input.isVisible()

    window.resize(680, 420)
    application.processEvents()
    assert window.width() >= 680
    assert window.height() >= 420
    assert window.username_input.isVisible()
    assert window.setup_selector.isVisible()
    assert window.play_button.isVisible()

    window.close()
    application.processEvents()


def test_existing_named_setups_are_visible_and_selection_is_restored(tmp_path):
    application = QApplication.instance() or QApplication([])
    root = tmp_path / "launcher-data"
    first = LauncherWindow(data_root=root)
    first.state["instances"] = [
        {"id": "survival-1214-a1b2c3d4", "name": "Survival", "version": "1.21.4", "ready": True},
        {"id": "creative-1214-e5f6a7b8", "name": "Creative", "version": "1.21.4", "ready": True},
    ]
    for instance in first.state["instances"]:
        first.store.create_instance_root(instance["id"])
    first.store.save(first.state)
    first.close()

    window = LauncherWindow(data_root=root)
    window.show()
    assert [window.setup_selector.itemText(i) for i in range(window.setup_selector.count())
            if window.setup_selector.itemData(i) is not None] == [
        "Survival · survival-1214-a1b2c3d4", "Creative · creative-1214-e5f6a7b8"
    ]
    window.setup_selector.setCurrentIndex(window.setup_selector.findData("creative-1214-e5f6a7b8"))
    assert window._selected_instance()["name"] == "Creative"
    window.close()
    application.processEvents()
    assert window.store.load()["selected_instance_id"] == "creative-1214-e5f6a7b8"

    reopened = LauncherWindow(data_root=root)
    assert reopened.setup_selector.currentText().startswith("Creative · ")
    reopened.close()
    application.processEvents()


def test_username_is_saved_on_editing_completion_and_identity_is_deterministic(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow(data_root=tmp_path / "launcher-data")
    window.username_input.setText("Alex")
    window.username_input.editingFinished.emit()

    assert window.state["username"] == "Alex"
    assert window.store.load()["username"] == "Alex"
    assert local_identity("Alex") == local_identity("Alex")

    window.username_input.setText(" ")
    window.username_input.editingFinished.emit()
    assert window.store.load()["username"] == "Alex"
    window.close()
    application.processEvents()


def test_play_locks_identity_setup_and_launch_settings_until_game_exit(tmp_path):
    application = QApplication.instance() or QApplication([])
    player = RunningPlayer()
    window = _ready_window(tmp_path, player)

    window.play_button.click()

    assert not window.username_input.isEnabled()
    assert not window.setup_selector.isEnabled()
    assert not window.setup_search_input.isEnabled()
    assert not window.settings_button.isEnabled()
    assert not window.play_button.isEnabled()

    window.username_input.setText("Changed")
    window.username_input.editingFinished.emit()
    assert window.state["username"] == "Alex"

    player.finish()
    assert window.username_input.isEnabled()
    assert window.setup_selector.isEnabled()
    assert window.setup_search_input.isEnabled()
    assert window.settings_button.isEnabled()
    assert window.play_button.isEnabled()
    window.close()
    application.processEvents()


def test_launch_failure_restores_session_controls(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = _ready_window(tmp_path, RunningPlayer(error="runtime unavailable"))

    window.play_button.click()

    assert "runtime unavailable" in window.instance_status_label.text()
    assert window.username_input.isEnabled()
    assert window.setup_selector.isEnabled()
    assert window.settings_button.isEnabled()
    assert window.play_button.isEnabled()
    window.close()
    application.processEvents()


def test_settings_automatically_saves_memory_and_contains_instance_actions(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    root = tmp_path / "launcher-data"
    window = _ready_window(root, RunningPlayer())
    dialogs = []

    def inspect_settings(dialog):
        dialogs.append(dialog)
        memory = dialog.findChild(QLineEdit, "settingsMemoryInput")
        assert memory is not None
        memory.setText("4")
        memory.editingFinished.emit()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", inspect_settings)
    window._open_settings()

    assert len(dialogs) == 1
    assert window.state["memory_gib"] == 4
    assert window.store.load()["memory_gib"] == 4
    labels = {button.text() for button in dialogs[0].findChildren(QPushButton)}
    assert "Open selected setup folder" in labels
    assert "Export diagnostic log" in labels
    assert not window.memory_input.isVisible()
    window.close()
    application.processEvents()
