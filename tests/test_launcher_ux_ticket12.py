import hashlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow
from mclauncher.modrinth_catalog import ModrinthRelease
from mclauncher.modrinth_mods import ModrinthModInstaller


class Catalog:
    def __init__(self):
        payload = b"remote mod"
        self.release = ModrinthRelease(
            "release-1", "project-1", "Example Mod", "1.0", ("1.21.4",), ("fabric",),
            "https://cdn.modrinth.com/example.jar", "example.jar",
            hashlib.sha1(payload).hexdigest(), hashlib.sha512(payload).hexdigest(),
        )
        self.payload = payload

    def search_mods(self, query, *, game_version, loader):
        assert (query, game_version, loader) == ("example", "1.21.4", "fabric")
        return [{"project_id": "project-1", "title": "Example Mod", "description": "demo"}]

    def releases(self, project_id, *, game_version="", loader=""):
        assert (project_id, game_version, loader) == ("project-1", "1.21.4", "fabric")
        return [self.release]

    def download_release(self, release):
        assert release.id == "release-1"
        return self.payload


def test_modrinth_search_and_install_stays_on_selected_instance(tmp_path):
    application = QApplication.instance() or QApplication([])
    catalog = Catalog()
    window = LauncherWindow(
        data_root=tmp_path / "data", modrinth_catalog=catalog,
        mod_installer=ModrinthModInstaller(catalog),
    )
    instance = {
        "id": "pack-1214-a1b2c3d4", "name": "Pack A", "version": "1.21.4-fabric-0.16.9", "minecraft_version": "1.21.4",
        "loader": "fabric", "loader_version": "0.16.9", "ready": True, "provider": "modrinth", "mods": [],
    }
    other = {**instance, "id": "pack-1214-b1b2c3d4", "name": "Pack B", "mods": []}
    window.state["instances"] = [instance, other]
    for item in window.state["instances"]:
        window.store.create_instance_root(item["id"])
        window._add_instance_item(item)
    window.instance_list.setCurrentRow(0)
    window._show_page(3)
    window.mod_search_input.setText("example")
    window._search_modrinth_mods()
    window.mod_search_results.setCurrentRow(0)
    application.processEvents()
    assert window.mod_release_selector.count() == 1
    window._install_selected_modrinth_mod()

    assert len(window.state["instances"][0]["mods"]) == 1
    assert window.state["instances"][1]["mods"] == []
    assert (tmp_path / "data" / "instances" / "pack-1214-a1b2c3d4" / "mods" / "example.jar").is_file()
    assert window.state["instances"][0]["modified"] is True
    assert "curated" in window.mods_warning_label.text().lower()
    window.close()
