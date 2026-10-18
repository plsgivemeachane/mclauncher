import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow


def test_player_can_save_identity_create_instance_and_restore_after_restart(tmp_path):
    application = QApplication.instance() or QApplication([])

    first = LauncherWindow(data_root=tmp_path / "launcher-data")
    first.show()
    first.username_input.setText("Alex")
    first.save_username_button.click()
    first.instance_name_input.setText("Survival")
    first.create_instance_button.click()

    assert first.username_input.text() == "Alex"
    assert first.identity_label.text().startswith("Local player identity:")
    assert first.instance_list.count() == 1
    assert first.instance_list.item(0).text() == "Survival"
    identity = first.identity_label.text()
    first.close()

    second = LauncherWindow(data_root=tmp_path / "launcher-data")
    second.show()
    assert second.username_input.text() == "Alex"
    assert second.identity_label.text() == identity
    assert second.instance_list.count() == 1
    assert second.instance_list.item(0).text() == "Survival"
    second.close()
    application.processEvents()


def test_changed_username_requires_warning_then_changes_local_identity(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow(data_root=tmp_path / "launcher-data")
    window.show()
    window.username_input.setText("Alex")
    window.save_username_button.click()
    original_identity = window.identity_label.text()

    window.username_input.setText("Sam")
    window.save_username_button.click()

    assert window.username_warning.isVisible()
    assert window.identity_label.text() == original_identity

    window.confirm_username_change_button.click()
    assert not window.username_warning.isVisible()
    assert window.username_input.text() == "Sam"
    assert window.identity_label.text() != original_identity
    window.close()
    application.processEvents()


def test_instance_selection_and_storage_are_launcher_scoped(tmp_path):
    application = QApplication.instance() or QApplication([])
    launcher_root = tmp_path / "launcher-data"
    external_minecraft = tmp_path / ".minecraft"
    external_minecraft.mkdir()
    marker = external_minecraft / "options.txt"
    marker.write_text("existing", encoding="utf-8")

    window = LauncherWindow(data_root=launcher_root)
    window.show()
    window.instance_name_input.setText("Creative")
    window.create_instance_button.click()
    window.instance_name_input.setText("Survival")
    window.create_instance_button.click()
    window.instance_list.setCurrentRow(0)

    assert window.instance_status_label.text() == "Selected instance: Creative"
    assert sorted(path.name for path in (launcher_root / "instances").iterdir())
    assert marker.read_text(encoding="utf-8") == "existing"
    assert not (external_minecraft / "state.json").exists()
    window.close()
    application.processEvents()

