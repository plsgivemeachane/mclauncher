import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit, QListWidget, QPushButton, QWidget

from mclauncher.app import LauncherWindow
from mclauncher.persistence import LauncherStore


def _app():
    return QApplication.instance() or QApplication([])


def _returning_window(tmp_path):
    store = LauncherStore(tmp_path / "data")
    state = store.load()
    state.update(username="Alex", memory_gib=4,
                 selected_instance_id="survival-1218-a1b2c3d4", selected_setup_id="survival-1218-a1b2c3d4")
    state["instances"] = [
        dict(id="survival-1218-a1b2c3d4", name="Survival", version="1.21.8", ready=True),
        dict(id="fabric-1201-b2c3d4e5", name="Fabric Adventure", version="1.20.1", loader="fabric", ready=False),
    ]
    for instance in state["instances"]:
        store.create_instance_root(instance["id"])
    store.save(state)
    window = LauncherWindow(data_root=tmp_path / "data")
    window.show()
    _app().processEvents()
    return window


def test_first_run_hero_welcomes_and_explains_install_and_play(tmp_path):
    application = _app()
    window = LauncherWindow(data_root=tmp_path / "fresh")
    window.show()
    application.processEvents()

    assert window.hero_eyebrow.text() == "Welcome"
    assert window.hero_title.text()
    # Names the button the player will actually see, and keeps version choice open.
    assert "Install & Play" in window.hero_detail.text()
    assert "pick a version" in window.hero_detail.text()
    assert not window.play_button.isEnabled()
    assert window.play_button.toolTip() == "The version list hasn’t loaded yet"

    window._versions_discovered(["1.21.11", "1.21.8"])
    application.processEvents()

    # "&&" renders as a literal ampersand on the button.
    assert window.play_button.text() == "⬇  Install && Play"
    assert "Not downloaded yet" in window.hero_detail.text()
    assert window.instance_status_label.text() == "Minecraft 1.21.11 selected"
    # Home already says what is selected, so the strip does not repeat it.
    assert not window.instance_status_label.isVisible()


def test_returning_player_is_greeted_and_ready_setup_says_play(tmp_path):
    window = _returning_window(tmp_path)

    assert window.hero_eyebrow.text() == "Welcome back, Alex"
    assert window.hero_title.text() == "Survival"
    assert window.play_button.text() == "▶  Play"
    assert window.username_input.accessibleName() == "Player name"
    assert window.setup_selector.accessibleName() == "Version or setup"
    assert window.setup_selector.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_secondary_pages_keep_a_quiet_one_line_launch_strip(tmp_path):
    application = _app()
    window = _returning_window(tmp_path)

    window.instances_nav_button.click()
    application.processEvents()

    assert window.play_button.property("subdued") is True
    assert window.instance_status_label.isVisible()
    assert window.instance_status_label.text() == "Ready: Survival (1.21.8)"
    assert not window.setup_selector.isVisible()
    assert window.play_button.minimumHeight() == window.open_folder_button.minimumHeight() >= 47

    window.home_nav_button.click()
    application.processEvents()
    assert window.play_button.property("subdued") is False
    assert not window.instance_status_label.isVisible()


def test_modpacks_tab_matches_page_and_mods_page_has_a_way_back(tmp_path):
    application = _app()
    window = _returning_window(tmp_path)

    assert window.browse_nav_button.text() == "Modpacks"
    window.manage_mods_button.click()
    application.processEvents()
    assert window.content_stack.currentIndex() == 3
    assert window.instances_nav_button.property("active") is True
    assert window.mods_back_button.isVisible()
    window.mods_back_button.click()
    application.processEvents()
    assert window.content_stack.currentIndex() == 1


def test_lists_explain_empty_and_no_result_states(tmp_path):
    application = _app()
    window = _returning_window(tmp_path)

    assert window.modrinth_pack_list.placeholder().splitlines()[0] == "Find a modpack"
    window._catalog_last_query = "zzz"
    window._catalog_placeholder_empty()
    assert "zzz" in window.modrinth_pack_list.placeholder().splitlines()[0]
    window._catalog_placeholder_failed()
    assert window.modrinth_pack_list.placeholder().splitlines()[0] == "Couldn’t reach Modrinth"

    window._show_page(3)
    application.processEvents()
    assert window.mods_list.placeholder().splitlines()[0] == "No mods installed yet"
    # Survival is vanilla, so there is nothing to search for.
    assert not window.mod_search_input.isEnabled()

    fabric_row = next(row for row in range(window.instance_list.count())
                      if window.instance_list.item(row).text() == "Fabric Adventure")
    window.instance_list.setCurrentRow(fabric_row)
    application.processEvents()
    assert window.mod_search_input.isEnabled()
    assert "Find mods" in window.mods_list.placeholder()


def test_discovery_failure_offers_retry_and_keeps_cached_setups(tmp_path):
    application = _app()
    window = _returning_window(tmp_path)

    window._version_discovery_failed("Network unavailable")
    application.processEvents()

    assert "Could not discover" in window.diagnostic_hint_label.text()
    assert "still work" in window.diagnostic_hint_label.text()
    assert window.retry_discovery_button.isVisible()
    assert window.setup_selector.currentText()

    window._versions_discovered(["1.21.8"])
    application.processEvents()
    assert not window.retry_discovery_button.isVisible()
    assert not window.diagnostic_hint_label.isVisible()


def test_version_picker_lists_setups_first_and_resets_an_empty_search(tmp_path):
    application = _app()
    window = _returning_window(tmp_path)
    window._versions_discovered(["1.21.11", "1.21.8"])
    popup = window.setup_selector.popup

    window.setup_selector.showPopup()
    application.processEvents()
    selectable = [popup.list.item(row) for row in range(popup.list.count())
                  if popup.list.item(row).flags() & Qt.ItemFlag.ItemIsSelectable]
    assert selectable[0].text() == "Survival"

    window.setup_search_input.setText("no-such-version")
    application.processEvents()
    assert popup.reset_button.isVisible()
    popup.reset_button.click()
    application.processEvents()
    assert window.setup_search_input.text() == ""
    assert not popup.reset_button.isVisible()

    QTest.keyClick(window.setup_search_input, Qt.Key.Key_Escape)
    application.processEvents()
    assert not popup.isVisible()


def test_settings_group_sections_and_state_memory_range(tmp_path, monkeypatch):
    application = _app()
    window = _returning_window(tmp_path)
    seen = {}

    def inspect(dialog):
        memory = dialog.findChild(QLineEdit, "settingsMemoryInput")
        seen["note"] = dialog.findChild(QLabel, "settingsSavedNote").text()
        seen["hint"] = dialog.findChild(QLabel, "settingsMemoryHint").text()
        seen["sections"] = [label.text() for label in dialog.findChildren(QLabel)
                            if label.property("role") == "sectionTitle"]
        memory.setText("invalid")
        memory.editingFinished.emit()
        seen["invalid"] = memory.property("invalid")
        seen["error"] = dialog.findChild(QLabel, "settingsError").text()
        return 0

    monkeypatch.setattr(QDialog, "exec", inspect)
    window._open_settings()

    assert seen["note"] == "Changes are saved automatically."
    assert "GiB" in seen["hint"] and "from 1 to" in seen["hint"]
    assert seen["sections"] == ["Game", "Versions", "Appearance", "Troubleshooting"]
    assert seen["invalid"] is True
    assert "Not saved" in seen["error"]
    assert window.state["memory_gib"] == 4
