import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel

from mclauncher.app import LauncherWindow, MinecraftHomePanel


def _visible_text(window):
    return "\n".join(
        label.text()
        for label in window.findChildren(QLabel)
        if label.isVisible() and label.text()
    ).lower()


def test_launcher_has_no_news_or_changelog_on_home_or_browse(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow(data_root=tmp_path / "data")
    window.show()
    application.processEvents()

    assert "news" not in _visible_text(window)
    assert "changelog" not in _visible_text(window)
    window.browse_nav_button.click()
    application.processEvents()
    assert "news" not in _visible_text(window)
    assert "changelog" not in _visible_text(window)
    window.close()


def test_legacy_news_state_remains_loadable_without_network(tmp_path):
    application = QApplication.instance() or QApplication([])
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "state.json").write_text(json.dumps({
        "username": "LegacyUser",
        "instances": [],
        "news_items": [{"unexpected": "legacy"}],
        "news_fetched_at": "yesterday",
    }), encoding="utf-8")

    window = LauncherWindow(data_root=data_root)
    window.show()
    application.processEvents()
    assert not window.store.recovery_required
    assert window.state["username"] == "LegacyUser"
    window.close()


def test_packaged_executable_background_is_used_for_home_rendering(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    executable_dir = tmp_path / "usr" / "lib" / "mclauncher"
    asset = executable_dir / "assets" / "minecraft-home.png"
    asset.parent.mkdir(parents=True)
    pixmap = QPixmap(8, 8)
    pixmap.fill("#a6e175")
    assert pixmap.save(str(asset))
    monkeypatch.setattr(sys, "executable", str(executable_dir / "mclauncher"))

    panel = MinecraftHomePanel()
    panel.show()
    application.processEvents()

    assert panel.bundled_background() == asset
    panel.set_background(None)
    rendered = panel.grab().toImage()
    assert rendered.isNull() is False
    assert rendered.pixelColor(4, 4).green() > rendered.pixelColor(4, 4).red()
    panel.close()
