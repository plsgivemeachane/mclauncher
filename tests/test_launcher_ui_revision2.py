"""Regression tests for launcher UI revision 2 (round-1 audit findings)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit, QPushButton, QScrollArea

from mclauncher import ui
from mclauncher.app import LauncherWindow
from review_fixtures import LONG_NAME, make_window


def _app():
    return QApplication.instance() or QApplication([])


def _shown(window, size=(920, 560)):
    window.resize(*size)
    window.show()
    window.activateWindow()
    QTest.qWaitForWindowActive(window, 1000)
    _app().processEvents()
    return window


def _marked(window):
    return [w for w in window.findChildren(QPushButton) + [window.setup_selector]
            if w.property("focusVisible")]


# Focus rings ---------------------------------------------------------------

def test_mouse_navigation_never_shows_focus_ring_but_real_tab_keypresses_do(tmp_path):
    window, _ = make_window(tmp_path / "data")
    _shown(window)

    QTest.mouseClick(window.instances_nav_button, Qt.MouseButton.LeftButton)
    _app().processEvents()
    assert window.content_stack.currentIndex() == 1
    assert not ui.focus_visible(window.instances_nav_button)
    assert not _marked(window), "focus handed over from hidden Home controls must stay quiet"

    QTest.mouseClick(window.home_nav_button, Qt.MouseButton.LeftButton)
    QTest.mouseClick(window.browse_nav_button, Qt.MouseButton.LeftButton)
    _app().processEvents()
    assert not _marked(window)

    # A real keypress switches to keyboard modality: the ring follows Tab.
    QTest.keyClick(window.focusWidget() or window, Qt.Key.Key_Tab)
    _app().processEvents()
    focused = QApplication.focusWidget()
    assert focused is not None and focused.property("focusVisible") is True
    QTest.keyClick(focused, Qt.Key.Key_Tab)
    _app().processEvents()
    assert QApplication.focusWidget() is not focused
    assert QApplication.focusWidget().property("focusVisible") is True
    assert focused.property("focusVisible") is False

    # Back to the pointer: the next click clears the ring again.
    QTest.mouseClick(window.home_nav_button, Qt.MouseButton.LeftButton)
    _app().processEvents()
    assert not ui.focus_visible(window.home_nav_button)
    window.close()


def test_focus_visibility_rules():
    rules = ui.FocusVisibility()
    reason = Qt.FocusReason
    assert rules.visible_for(reason.OtherFocusReason)  # programmatic focus before any input
    assert not rules.visible_for(reason.MouseFocusReason)
    rules.modality = "pointer"
    assert not rules.visible_for(reason.TabFocusReason)  # focus moved off a hidden widget
    rules.modality = "keyboard"
    assert rules.visible_for(reason.TabFocusReason)
    assert not rules.visible_for(reason.MouseFocusReason)


# Install / recommended action ----------------------------------------------

def test_tools_card_states_recommended_action_and_ready_state(tmp_path):
    window, _ = make_window(tmp_path / "data")
    window._show_page(1)
    ids = [i["id"] for i in window.state["instances"]]

    window.instance_list.setCurrentRow(ids.index("survival-1218-a1b2c3d4"))
    assert window.install_button.text() == "Repair files"
    assert window.install_button.property("role") != "primary"
    assert window.selected_instance_state.text() == "● Ready to play"
    assert window.selected_instance_state.property("tone") == "good"

    window.instance_list.setCurrentRow(ids.index("long-1218-c3d4e5f6"))
    assert window.install_button.text() == "Install Minecraft"
    assert window.install_button.property("role") == "primary"
    assert window.selected_instance_state.text() == "● Not installed"

    window.state["instances"][ids.index("long-1218-c3d4e5f6")]["install_error"] = "download interrupted"
    window._refresh_install_button()
    assert window.install_button.text() == "Retry installation"
    assert window.install_button.property("role") == "primary"
    assert window.selected_instance_state.property("tone") == "warn"
    window.close()


# First run copy -------------------------------------------------------------

def test_first_run_loading_copy_states_now_and_one_next_action(tmp_path):
    window = LauncherWindow(data_root=tmp_path / "fresh")
    title = window.home_title.text() if hasattr(window, "home_title") else ""
    detail = " ".join(label.text() for label in window.findChildren(QLabel) if label.isVisibleTo(window))
    assert "two steps" not in detail
    assert "Fetching Minecraft versions" in detail
    # One next action, named as the button that will appear ("Install & Play").
    assert "press Play" not in detail
    assert detail.count("Install & Play") == 1
    assert "pick a version" in detail
    assert "Welcome" in title or "Welcome" in detail
    window.close()


# Compact layout --------------------------------------------------------------

def test_compact_library_shows_three_full_rows_and_folds_imports_into_menu(tmp_path):
    window, _ = make_window(tmp_path / "data")
    _shown(window, (680, 420))
    window._show_page(1)
    _app().processEvents()

    viewport = window.instance_list.viewport().rect()
    for row in range(3):
        assert viewport.contains(window.instance_list.visualItemRect(window.instance_list.item(row))), row
    assert window.import_pack_menu_button.isVisible()
    assert not window.import_modpack_button.isVisible()
    assert not window.import_curseforge_button.isVisible()
    actions = [a.text() for a in window.import_pack_menu_button.menu().actions()]
    assert any(".mrpack" in a for a in actions) and any("CurseForge" in a for a in actions)
    assert window.open_folder_button.accessibleName() == "Open folder"

    window.resize(920, 560)
    _app().processEvents()
    assert not window.import_pack_menu_button.isVisible()
    assert window.import_modpack_button.isVisible()
    window.close()


def test_compact_picker_keeps_full_title_by_shrinking_badge(tmp_path):
    window, _ = make_window(tmp_path / "data")
    window.setup_selector.setCurrentIndex(window.setup_selector.findData("survival-1218-a1b2c3d4"))
    _shown(window)
    window.setup_selector.grab()
    assert window.setup_selector.badge_compact is False

    window.resize(680, 420)
    _app().processEvents()
    window.setup_selector.grab()
    assert window.setup_selector.badge_compact is False  # short title still fits beside the pill
    assert "Survival" in window.setup_selector.toolTip()
    assert "Ready" in window.setup_selector.toolTip()
    window.close()


def test_long_setup_name_elides_without_breaking_minimum_window(tmp_path):
    window, _ = make_window(tmp_path / "data")
    window.setup_selector.setCurrentIndex(window.setup_selector.findData("long-1218-c3d4e5f6"))
    _shown(window, (680, 420))
    window.setup_selector.grab()
    assert window.width() == 680 and window.height() == 420
    assert window.setup_selector.badge_compact is True  # pill shrinks to a dot before the name does
    assert LONG_NAME in window.setup_selector.toolTip()
    assert window.play_button.isVisible()
    assert window.setup_selector.geometry().right() < window.play_button.geometry().left()
    window.close()


# Version picker ------------------------------------------------------------------

def test_version_picker_opens_with_top_group_heading_visible(tmp_path):
    window, _ = make_window(tmp_path / "data")
    _shown(window)
    window.setup_selector.showPopup()
    _app().processEvents()
    popup_list = window.setup_selector.popup.list
    first = popup_list.item(0)
    assert not first.flags() & Qt.ItemFlag.ItemIsSelectable  # a group heading
    assert popup_list.verticalScrollBar().value() == 0
    assert popup_list.viewport().rect().contains(popup_list.visualItemRect(first))
    assert popup_list.viewport().rect().contains(popup_list.visualItemRect(popup_list.currentItem()))
    window.setup_selector.hidePopup()
    window.close()


# Mods page -------------------------------------------------------------------------

def test_vanilla_mods_page_shows_one_truthful_state_and_routes_to_compatible_setup(tmp_path):
    window, catalog = make_window(tmp_path / "data")
    _shown(window)
    window.instance_list.setCurrentRow(0)  # Survival, vanilla
    window._show_page(3)
    _app().processEvents()
    assert window.mods_vanilla_notice.isVisible()
    assert not window._mods_online_section.isVisible()
    assert not window.mod_search_input.isVisible()
    assert "Search" not in window.mods_list.placeholder_detail if hasattr(window.mods_list, "placeholder_detail") else True
    assert window.mods_switch_setup_button.text() == "Switch to Fabric Adventure"

    QTest.mouseClick(window.mods_switch_setup_button, Qt.MouseButton.LeftButton)
    _app().processEvents()
    assert window._selected_instance()["name"] == "Fabric Adventure"
    assert window.content_stack.currentIndex() == 3
    assert window._mods_online_section.isVisible()
    assert not window.mods_vanilla_notice.isVisible()
    assert window.mod_search_input.isEnabled() and window.mod_search_input.hasFocus()

    # Real keyboard path: type a query and press Enter.
    QTest.keyClicks(window.mod_search_input, "sodium")
    QTest.keyClick(window.mod_search_input, Qt.Key.Key_Return)
    _app().processEvents()
    assert ("search_mods", "sodium", "1.20.1", "fabric") in catalog.calls
    assert window.mod_search_results.count() == 2
    window.close()


def test_vanilla_notice_without_modded_setup_points_to_modpacks(tmp_path):
    window, _ = make_window(tmp_path / "data")
    window.state["instances"] = [i for i in window.state["instances"] if i.get("loader") != "fabric"]
    window.instance_list.setCurrentRow(0)
    window._show_page(3)
    window._refresh_mods_panel()
    assert window.mods_switch_setup_button.isHidden()
    assert window.mods_browse_packs_button.property("role") == "primary"
    window.mods_browse_packs_button.click()
    assert window.content_stack.currentIndex() == 2
    window.close()


def test_fixture_mod_flow_select_release_and_install(tmp_path):
    window, catalog = make_window(tmp_path / "data")
    fabric = next(i for i in window.state["instances"] if i["name"] == "Fabric Adventure")
    window.instance_list.setCurrentRow(window.state["instances"].index(fabric))
    window._show_page(3)
    assert not window.mod_install_button.isEnabled()
    window.mod_search_input.setText("sodium")
    window._search_modrinth_mods()
    item = window.mod_search_results.item(0)
    assert item.data(ui.ROW_INFO_ROLE).detail == "by fixtures · 1.0M downloads"
    window.mod_search_results.setCurrentRow(0)
    _app().processEvents()
    assert window.mod_release_selector.count() == 1
    assert window.mod_install_button.isEnabled()
    window.mod_install_button.click()
    assert [m["filename"] for m in fabric["mods"]] == ["mod-sodium.jar"]
    assert (tmp_path / "data" / "instances" / fabric["id"] / "mods" / "mod-sodium.jar").is_file()
    assert window.mods_list.count() == 1

    # Switching setups drops results filtered for the previous one.
    window.instance_list.setCurrentRow(0)
    window._refresh_mods_panel()
    assert window.mod_search_results.count() == 0
    assert window.mod_release_selector.count() == 0
    assert window.mod_search_status.text() == ""
    window.close()


def test_fixture_modpack_flow_two_line_rows_select_and_install(tmp_path):
    window, catalog = make_window(tmp_path / "data")
    _shown(window)
    window._show_page(2)
    QTest.keyClicks(window.modrinth_search_input, "demo")
    QTest.keyClick(window.modrinth_search_input, Qt.Key.Key_Return)
    _app().processEvents()
    assert window.modrinth_pack_list.count() == 3
    info = window.modrinth_pack_list.item(0).data(ui.ROW_INFO_ROLE)
    assert (info.title, info.detail) == ("Demo Adventure Pack", "by fixtures · 128k downloads")
    assert window.modrinth_pack_list.item(2).toolTip().startswith("Checks text elision")

    window.modrinth_pack_list.setCurrentRow(0)
    _app().processEvents()
    assert window.modrinth_release_selector.count() == 2
    assert window.modrinth_release_selector.currentData().id == "pack-demo-2"
    assert window.modrinth_install_button.isEnabled()
    before = len(window.state["instances"])
    window.modrinth_install_button.click()
    assert len(window.state["instances"]) == before + 1
    created = window.state["instances"][-1]
    assert created["pack_release_id"] == "pack-demo-2"
    assert created["loader"] == "fabric" and created["ready"] is True
    assert ("download", "pack-demo-2") in catalog.calls
    window.close()


# Settings -------------------------------------------------------------------------

def test_settings_fits_minimum_window_and_corrects_errors_by_keyboard(tmp_path, monkeypatch):
    window, _ = make_window(tmp_path / "data")
    _shown(window, (680, 420))
    seen = {}

    def drive(dialog):
        dialog.show()
        QTest.qWaitForWindowExposed(dialog, 1000)
        _app().processEvents()
        seen["height"] = dialog.height()
        assert dialog.maximumHeight() <= 400
        assert dialog.findChild(QScrollArea, "settingsScroll") is not None
        memory = dialog.findChild(QLineEdit, "settingsMemoryInput")
        error = dialog.findChild(QLabel, "settingsError")
        memory.setFocus()
        QTest.keyClick(memory, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(memory, "0")
        QTest.keyClick(memory, Qt.Key.Key_Tab)
        _app().processEvents()
        assert error.isVisible() and error.text()
        assert memory.property("invalid") is True
        assert memory.accessibleDescription() == error.text()
        assert window.state["memory_gib"] == 4
        memory.setFocus()
        QTest.keyClick(memory, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(memory, "3")
        QTest.keyClick(memory, Qt.Key.Key_Tab)
        _app().processEvents()
        assert not error.isVisible()
        assert memory.property("invalid") is False
        seen["saved"] = window.state["memory_gib"]
        dialog.close()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", drive)
    window._open_settings()
    assert seen["height"] <= 400 < 420
    assert seen["saved"] == 3
    window.close()
