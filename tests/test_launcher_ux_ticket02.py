import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow, local_identity


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
