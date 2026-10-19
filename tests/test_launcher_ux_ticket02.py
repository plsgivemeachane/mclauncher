import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QWidget

from mclauncher.app import LauncherWindow, local_identity


def test_launcher_uses_landscape_launch_bar_layout_with_visible_public_controls(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow(data_root=tmp_path / "launcher-data")
    window.show()
    application.processEvents()

    assert window.size().width() == 920
    assert window.size().height() == 560
    assert window.minimumSize().width() <= 680
    assert window.minimumSize().height() <= 420
    assert window.findChild(QLabel, "brandLabel").isVisible()
    assert window.findChild(QWidget, "landscapePanel").isVisible()
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
    assert [window.setup_selector.itemText(i) for i in range(window.setup_selector.count())] == [
        "Survival", "Creative"
    ]
    window.setup_selector.setCurrentIndex(1)
    assert window._selected_instance()["name"] == "Creative"
    window.close()
    application.processEvents()
    assert window.store.load()["selected_instance_id"] == "creative-1214-e5f6a7b8"

    reopened = LauncherWindow(data_root=root)
    assert reopened.setup_selector.currentText() == "Creative"
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
