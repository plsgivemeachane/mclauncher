import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QScrollArea

from mclauncher.app import LauncherWindow


def _window(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(LauncherWindow, "_start_version_discovery", lambda self: None)
    window = LauncherWindow(data_root=tmp_path / "launcher-data")
    window.show()
    application.processEvents()
    return application, window


def _create_instance(window, name):
    window.instance_name_input.setText(name)
    window.create_instance_button.click()
    return window.state["instances"][-1]


def test_open_folder_button_is_available_on_home_and_instances_and_matches_play_size(tmp_path, monkeypatch):
    application, window = _window(tmp_path, monkeypatch)

    assert window.open_folder_button.isVisible()
    assert window.open_folder_button.minimumHeight() == window.play_button.minimumHeight()
    assert window.open_folder_button.minimumHeight() >= 47
    assert window.open_folder_button.minimumWidth() >= 120
    assert window.open_folder_button.width() >= 120

    window.instances_nav_button.click()
    application.processEvents()

    assert window.open_folder_button.isVisible()
    assert window.open_folder_button.width() >= 120
    window.close()


def test_open_folder_targets_selected_instance_game_directory_and_follows_selection(tmp_path, monkeypatch):
    application, window = _window(tmp_path, monkeypatch)
    first = _create_instance(window, "Survival")
    second = _create_instance(window, "Creative")
    first_game = window.store.instance_game_root(first["id"])
    second_game = window.store.instance_game_root(second["id"])
    screenshot = first_game / "screenshots" / "spawn.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_bytes(b"png")
    opened = []
    monkeypatch.setattr("mclauncher.app.QDesktopServices.openUrl", lambda url: opened.append(url) or True)

    window.instance_list.setCurrentRow(0)
    window.open_folder_button.click()
    window.instance_list.setCurrentRow(1)
    window.open_folder_button.click()

    assert [url.toLocalFile() for url in opened] == [str(first_game), str(second_game)]
    assert screenshot.is_file()
    window.close()


def test_open_folder_is_disabled_without_selected_instance(tmp_path, monkeypatch):
    application, window = _window(tmp_path, monkeypatch)

    assert window.instance_list.currentRow() == -1
    assert not window.open_folder_button.isEnabled()
    window.close()


def test_open_screenshots_button_creates_and_opens_selected_instance_screenshots(tmp_path, monkeypatch):
    application, window = _window(tmp_path, monkeypatch)
    instance = _create_instance(window, "Screenshots")
    screenshots = window.store.instance_game_root(instance["id"]) / "screenshots"
    if screenshots.exists():
        screenshots.rmdir()
    opened = []
    monkeypatch.setattr("mclauncher.app.QDesktopServices.openUrl", lambda url: opened.append(url) or True)

    window.instances_nav_button.click()
    application.processEvents()
    assert window.open_screenshots_button.isVisible()
    window.open_screenshots_button.click()

    assert screenshots.is_dir()
    assert opened[-1].toLocalFile() == str(screenshots)
    window.close()


def test_instances_tools_fit_small_window_without_orphan_settings_labels(tmp_path, monkeypatch):
    application, window = _window(tmp_path, monkeypatch)
    _create_instance(window, 'Survival')
    window.instances_nav_button.click()
    window.resize(680, 420)
    application.processEvents()

    assert not any(label.isVisible() and label.text() in ('Local username', 'Game memory (GiB)')
                   for label in window.findChildren(QLabel))
    assert window.minimumSizeHint().height() <= 420
    assert window.play_button.isVisible()
    assert window.open_folder_button.isVisible()
    assert window.rect().contains(window.open_folder_button.mapTo(window, window.open_folder_button.rect().bottomRight()))
    window.close()


def test_all_instance_tools_remain_reachable_by_scrolling_small_window(tmp_path, monkeypatch):
    application, window = _window(tmp_path, monkeypatch)
    _create_instance(window, "Survival")
    window.instances_nav_button.click()
    window.resize(680, 420)
    for _ in range(3):
        application.processEvents()

    tools = window.findChild(QScrollArea, "instanceToolsScroll")
    tools.ensureWidgetVisible(window.install_optifine_button)
    library = window.findChild(QScrollArea, "instanceLibraryScroll")
    library.ensureWidgetVisible(window.create_instance_button)
    application.processEvents()
    for scroll, button in ((tools, window.install_optifine_button),
                           (library, window.create_instance_button)):
        top_left = button.mapTo(scroll.viewport(), button.rect().topLeft())
        bottom_right = button.mapTo(scroll.viewport(), button.rect().bottomRight())
        assert scroll.viewport().rect().contains(top_left)
        assert scroll.viewport().rect().contains(bottom_right)
    assert window.open_folder_button.isVisible()
    assert window.play_button.isVisible()
    window.close()


def test_folder_open_failure_reports_selected_directory(tmp_path, monkeypatch):
    application, window = _window(tmp_path, monkeypatch)
    instance = _create_instance(window, "Survival")
    monkeypatch.setattr("mclauncher.app.QDesktopServices.openUrl", lambda url: False)
    window.open_folder_button.click()
    assert "Could not open instance folder" in window.diagnostic_hint_label.text()
    assert str(window.store.instance_game_root(instance["id"])) in window.diagnostic_hint_label.text()
    window.close()
