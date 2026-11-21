"""Regression tests for launcher UI revision 3 (round-2 audit findings)."""

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QWidget

from mclauncher import ui
from mclauncher.app import PACK_DETAILS_PROMPT, LauncherWindow
from review_fixtures import FixtureCatalog, FixtureInstaller, FixturePlayer, make_window, seed_state

COMPACT = (680, 420)
DEFAULT = (920, 560)


def _app():
    return QApplication.instance() or QApplication([])


def _shown(window, size=DEFAULT):
    window.resize(*size)
    window.show()
    window.activateWindow()
    QTest.qWaitForWindowActive(window, 1000)
    _app().processEvents()
    return window


def _wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "timed out waiting for the UI"
        QTest.qWait(10)


def _scroll_area(widget: QWidget) -> QScrollArea | None:
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QScrollArea):
            return parent
        parent = parent.parentWidget()
    return None


def _in_view(widget: QWidget) -> bool:
    """Whole widget inside its enclosing scroll area's viewport (and on screen)."""
    if not widget.isVisible():
        return False
    area = _scroll_area(widget)
    if area is None:
        return True
    viewport = area.viewport()
    top_left = widget.mapTo(viewport, QPoint(0, 0))
    bottom_right = widget.mapTo(viewport, QPoint(widget.width() - 1, widget.height() - 1))
    return viewport.rect().contains(top_left) and viewport.rect().contains(bottom_right)


def _click_row(view, row):
    rect = view.visualItemRect(view.item(row))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, rect.center())
    _app().processEvents()


def _open_mods_for(window, name):
    QTest.mouseClick(window.instances_nav_button, Qt.MouseButton.LeftButton)
    row = next(r for r in range(window.instance_list.count()) if window.instance_list.item(r).text() == name)
    _click_row(window.instance_list, row)
    QTest.mouseClick(window.manage_mods_button, Qt.MouseButton.LeftButton)
    _app().processEvents()


# Mods: two tasks, each fully visible ---------------------------------------------

def test_mods_find_task_shows_search_results_release_and_add_at_both_sizes(tmp_path):
    for size in (DEFAULT, COMPACT):
        window, catalog = make_window(tmp_path / f"data-{size[0]}")
        _shown(window, size)
        _open_mods_for(window, "Fabric Adventure")
        # Nothing installed yet, so the page opens on the task that matters.
        assert window.mods_find_mode_button.isChecked()
        assert window.mods_installed_mode_button.text() == "Installed (0)"
        assert not window.mods_list.isVisible()

        QTest.keyClicks(window.mod_search_input, "sodium")
        QTest.keyClick(window.mod_search_input, Qt.Key.Key_Return)
        _app().processEvents()
        _click_row(window.mod_search_results, 0)
        assert window.mod_release_selector.currentData().id == "mod-sodium-r1"
        for widget in (window.mod_search_input, window.mod_search_results, window.mod_release_selector,
                       window.mod_install_button, window.mod_search_status):
            assert _in_view(widget), (size, widget.objectName())
        first_row = window.mod_search_results.visualItemRect(window.mod_search_results.item(0))
        assert window.mod_search_results.viewport().rect().contains(first_row), size

        QTest.mouseClick(window.mod_install_button, Qt.MouseButton.LeftButton)
        _app().processEvents()
        assert ("download", "mod-sodium-r1") in catalog.calls
        assert window.mods_installed_mode_button.text() == "Installed (1)"
        assert "Installed 1" in window.mod_search_status.text()

        # The other task replaces this one instead of stacking below it.
        QTest.mouseClick(window.mods_installed_mode_button, Qt.MouseButton.LeftButton)
        _app().processEvents()
        assert window.mods_installed_mode_button.isChecked() and not window.mods_find_mode_button.isChecked()
        assert window.mods_list.count() == 1 and _in_view(window.mods_list)
        assert _in_view(window.import_mod_button) and _in_view(window.remove_mod_button)
        assert not window.mod_search_input.isVisible()
        window.close()


def test_setup_with_mods_opens_on_installed_and_search_returns_to_find(tmp_path):
    window, _ = make_window(tmp_path / "data")
    _shown(window)
    fabric = next(i for i in window.state["instances"] if i["name"] == "Fabric Adventure")
    fabric["mods"] = [dict(id="m1", name="Sodium", filename="sodium.jar", enabled=True)]
    _open_mods_for(window, "Fabric Adventure")
    assert window.mods_installed_mode_button.isChecked()
    assert window.mods_list.isVisible() and window.mods_list.count() == 1

    QTest.mouseClick(window.mods_find_mode_button, Qt.MouseButton.LeftButton)
    _app().processEvents()
    assert window.mod_search_input.isVisible() and not window.mods_list.isVisible()
    window.close()


def test_vanilla_switch_action_is_in_the_first_viewport_at_both_sizes(tmp_path):
    for size in (DEFAULT, COMPACT):
        window, _ = make_window(tmp_path / f"data-{size[0]}")
        _shown(window, size)
        _open_mods_for(window, "Survival")
        assert window.mods_vanilla_notice.isVisible()
        assert _in_view(window.mods_switch_setup_button), size
        assert _in_view(window.mods_browse_packs_button), size

        QTest.mouseClick(window.mods_switch_setup_button, Qt.MouseButton.LeftButton)
        _app().processEvents()
        assert window._selected_instance()["name"] == "Fabric Adventure"
        assert window.mods_find_mode_button.isChecked()
        assert window.mod_search_input.hasFocus() and _in_view(window.mod_search_input)
        window.close()


# Real Tab key: every focused control is scrolled into view ----------------------

def _tab_through(window, presses, key=Qt.Key.Key_Tab):
    seen = []
    for _ in range(presses):
        QTest.keyClick(QApplication.focusWidget(), key)
        _app().processEvents()
        focused = QApplication.focusWidget()
        if focused is not None and _scroll_area(focused) is not None and focused.window() is window:
            assert _in_view(focused), focused.objectName() or type(focused).__name__
            seen.append(focused)
    return seen


def test_tab_and_backtab_reveal_focused_actions_in_compact_instances(tmp_path):
    window, _ = make_window(tmp_path / "data")
    _shown(window, COMPACT)
    QTest.mouseClick(window.instances_nav_button, Qt.MouseButton.LeftButton)
    window.instance_list.setFocus(Qt.FocusReason.TabFocusReason)
    tools = window.findChild(QScrollArea, "instanceToolsScroll")
    assert tools.verticalScrollBar().maximum() > 0  # the card really scrolls here

    seen = _tab_through(window, 30)
    assert window.save_log_button in seen or window.open_screenshots_button in seen
    assert tools.verticalScrollBar().value() > 0

    # Shift+Tab from the launch strip enters the card at its bottom.
    tools.verticalScrollBar().setValue(0)
    window.open_folder_button.setFocus(Qt.FocusReason.TabFocusReason)
    _tab_through(window, 30, Qt.Key.Key_Backtab)
    window.close()


def test_tab_reveals_each_focused_action_in_compact_mods(tmp_path):
    window, _ = make_window(tmp_path / "data")
    _shown(window, COMPACT)
    _open_mods_for(window, "Fabric Adventure")
    QTest.keyClicks(window.mod_search_input, "sodium")
    QTest.keyClick(window.mod_search_input, Qt.Key.Key_Return)
    _click_row(window.mod_search_results, 0)
    window.mods_back_button.setFocus(Qt.FocusReason.TabFocusReason)
    seen = _tab_through(window, 12)
    assert window.mod_install_button in seen
    window.close()


def test_focus_set_by_code_inside_a_scrolled_page_is_revealed(tmp_path):
    window, _ = make_window(tmp_path / "data")
    _shown(window, COMPACT)
    QTest.mouseClick(window.instances_nav_button, Qt.MouseButton.LeftButton)
    tools = window.findChild(QScrollArea, "instanceToolsScroll")
    tools.verticalScrollBar().setValue(0)
    assert not _in_view(window.save_log_button) or not window.save_log_button.isEnabled()
    window.save_log_button.setEnabled(True)
    window.save_log_button.setFocus(Qt.FocusReason.TabFocusReason)
    _app().processEvents()
    assert _in_view(window.save_log_button)
    window.close()


# Instances: the library column fits its content ---------------------------------

def test_compact_library_rows_and_badges_fit_after_shrinking_from_default(tmp_path):
    window, _ = make_window(tmp_path / "data")
    _shown(window, DEFAULT)
    QTest.mouseClick(window.instances_nav_button, Qt.MouseButton.LeftButton)
    window.resize(*COMPACT)
    _app().processEvents()

    library = window.findChild(QScrollArea, "instanceLibraryScroll")
    tools = window.findChild(QScrollArea, "instanceToolsScroll")
    assert library.geometry().right() < tools.geometry().left()
    assert library.horizontalScrollBar().maximum() == 0
    assert window.instance_list.horizontalScrollBar().maximum() == 0
    assert _in_view(window.instance_list)
    viewport = window.instance_list.viewport().rect()
    for row in range(window.instance_list.count()):
        assert viewport.contains(window.instance_list.visualItemRect(window.instance_list.item(row))), row
    for widget in (window.instance_name_input, window.create_instance_button, window.import_pack_menu_button):
        assert _in_view(widget), widget.objectName()

    # Without the "New setup" heading, the placeholder is the input's label.
    name = window.instance_name_input
    assert name.placeholderText() == "New setup"
    assert name.fontMetrics().horizontalAdvance(name.placeholderText()) < name.width() - 20
    window.resize(*DEFAULT)
    _app().processEvents()
    assert name.placeholderText() == "New setup name"
    window.close()


# Modpacks: a new search never shows the previous pack ----------------------------

class _GatedCatalog(FixtureCatalog):
    """Fixture answers, but searches wait for a gate and can come back empty or fail."""

    def __init__(self):
        super().__init__()
        self.gate = threading.Event()
        self.gate.set()

    def search(self, query):
        self.gate.wait(5)
        if query == "offline":
            raise OSError("network unreachable")
        return super().search(query) if query != "missing" else []


def _assert_no_stale_pack(window):
    assert window.modrinth_release_selector.count() == 0
    assert not window.modrinth_install_button.isEnabled()
    assert not window._catalog_release_section.isVisible()
    assert "Demo Adventure Pack" not in window.modrinth_pack_details.text()


def test_async_new_search_clears_old_pack_while_running_and_after_empty_or_failed(tmp_path):
    store = seed_state(tmp_path / "data")
    window = LauncherWindow(data_root=store.root, installer=FixtureInstaller(), player=FixturePlayer())
    catalog = _GatedCatalog()
    window.modrinth_catalog = catalog  # not injected: the real worker-thread path
    assert not window._catalog_injected
    _shown(window)
    QTest.mouseClick(window.browse_nav_button, Qt.MouseButton.LeftButton)

    QTest.keyClicks(window.modrinth_search_input, "demo")
    QTest.keyClick(window.modrinth_search_input, Qt.Key.Key_Return)
    _wait_until(lambda: window.modrinth_pack_list.count() == 3)
    _click_row(window.modrinth_pack_list, 0)
    _wait_until(lambda: window.modrinth_install_button.isEnabled())
    assert "Demo Adventure Pack" in window.modrinth_pack_details.text()

    # While the next search is still running, the old pack is already gone.
    catalog.gate.clear()
    window.modrinth_search_input.clear()
    QTest.keyClicks(window.modrinth_search_input, "missing")
    QTest.keyClick(window.modrinth_search_input, Qt.Key.Key_Return)
    _app().processEvents()
    _assert_no_stale_pack(window)
    assert window.modrinth_pack_details.text() == PACK_DETAILS_PROMPT
    assert "Searching" in window.modrinth_catalog_status.text()
    catalog.gate.set()
    _wait_until(lambda: "No Modrinth" in window.modrinth_catalog_status.text())
    _assert_no_stale_pack(window)
    assert window.modrinth_pack_list.placeholder().startswith("No modpacks match “missing”")

    # Failure path, from a selected pack again.
    window.modrinth_search_input.clear()
    QTest.keyClicks(window.modrinth_search_input, "demo")
    QTest.keyClick(window.modrinth_search_input, Qt.Key.Key_Return)
    _wait_until(lambda: window.modrinth_pack_list.count() == 3)
    _click_row(window.modrinth_pack_list, 0)
    _wait_until(lambda: window.modrinth_install_button.isEnabled())
    window.modrinth_search_input.clear()
    QTest.keyClicks(window.modrinth_search_input, "offline")
    QTest.keyClick(window.modrinth_search_input, Qt.Key.Key_Return)
    _wait_until(lambda: "failed" in window.modrinth_catalog_status.text())
    _assert_no_stale_pack(window)
    assert "network unreachable" in window.modrinth_catalog_status.text()
    assert window.modrinth_pack_list.placeholder().startswith("Couldn’t reach Modrinth")
    window.close()


def test_sync_empty_and_failed_searches_clear_the_selected_pack(tmp_path):
    window, catalog = make_window(tmp_path / "data")
    _shown(window)
    QTest.mouseClick(window.browse_nav_button, Qt.MouseButton.LeftButton)
    for query in ("missing", "offline"):
        window.modrinth_search_input.setText("demo")
        QTest.mouseClick(window.modrinth_search_button, Qt.MouseButton.LeftButton)
        _click_row(window.modrinth_pack_list, 0)
        assert window.modrinth_install_button.isEnabled()
        original = catalog.search

        def search(q, original=original):
            if q == "offline":
                raise OSError("network unreachable")
            return [] if q == "missing" else original(q)

        catalog.search = search
        window.modrinth_search_input.setText(query)
        QTest.mouseClick(window.modrinth_search_button, Qt.MouseButton.LeftButton)
        _assert_no_stale_pack(window)
        catalog.search = original
    window.close()


# Copy ---------------------------------------------------------------------------

def test_first_run_copy_names_the_button_the_player_will_see(tmp_path):
    window = LauncherWindow(data_root=tmp_path / "fresh")
    window.show()
    _app().processEvents()
    assert "Install & Play" in window.hero_detail.text()
    window._versions_discovered(["1.21.11", "1.21.8"])
    _app().processEvents()
    assert window.play_button.text().replace("&&", "&").endswith("Install & Play")
    assert "Install & Play" in window.hero_detail.text()
    window.close()
