import hashlib
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow
from mclauncher.modrinth_catalog import ModrinthRelease


def test_held_catalog_preparation_keeps_timer_responsive_and_close_bounded(tmp_path):
    application = QApplication.instance() or QApplication([])
    payload = b"archive"
    release = ModrinthRelease(
        "release-1", "project-1", "Pack", "1", ("1.21.4",), ("fabric",),
        "https://cdn.modrinth.test/pack.mrpack", "pack.mrpack",
        hashlib.sha1(payload).hexdigest(), hashlib.sha512(payload).hexdigest(),
    )

    class HeldCatalog:
        def download_release(self, selected):
            time.sleep(1.0)
            return payload

    class HeldImporter:
        def import_archive(self, *args, **kwargs):
            time.sleep(1.0)
            raise RuntimeError("held request released")

    window = LauncherWindow(data_root=tmp_path / "data", installer=object(), modrinth_catalog=HeldCatalog(), modpack_importer=HeldImporter())
    window._catalog_injected = False
    window._catalog_releases = [release]
    window.modrinth_release_selector.addItem("1", release)
    window.modrinth_pack_list.addItem("Pack")
    window.modrinth_pack_list.setCurrentRow(0)
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start(100)
    window._install_modrinth_catalog_release()
    deadline = time.monotonic() + 0.35
    while time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.01)
    started = time.monotonic()
    window.close()
    elapsed = time.monotonic() - started
    timer.stop()
    assert ticks
    assert elapsed <= 1.0
    time.sleep(2.1)
    application.processEvents()
    assert not any(item.get("ready") for item in window.state.get("instances", []))


def test_async_mod_release_result_is_discarded_after_instance_changes(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow(data_root=tmp_path / "data")
    window.instance_name_input.setText("First")
    window._create_instance()
    first = window.state["instances"][0]
    first.update(minecraft_version="1.21.4", loader="fabric")
    window.instance_name_input.setText("Second")
    window._create_instance()
    second = window.state["instances"][1]
    second.update(minecraft_version="1.21.4", loader="fabric")
    window.instance_list.setCurrentRow(1)
    release = ModrinthRelease(
        "mod-release", "mod-project", "Mod", "1", ("1.21.4",), ("fabric",),
        "https://cdn.modrinth.test/mod.jar", "mod.jar", "sha1", "sha512",
    )
    window._mod_query_request = 1
    window._mod_releases_completed(1, first["id"], "1.21.4", "fabric", [release])
    assert window.mod_release_selector.count() == 0
    window.close()
    application.processEvents()
