import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow
from mclauncher.modrinth_catalog import ModrinthRelease


class Catalog:
    def __init__(self):
        self.downloaded = []
        self.release = ModrinthRelease(
            "release-2", "pack-1", "2.0", "2.0", ("1.21.4",), ("fabric",),
            "https://cdn.modrinth.com/pack-2.mrpack", "pack-2.mrpack", "sha1", "sha512",
        )

    def search(self, query):
        assert query == "demo"
        return [{"project_id": "pack-1", "title": "Demo Pack", "description": "A demo"}]

    def project(self, project_id):
        assert project_id == "pack-1"
        return {"id": project_id, "title": "Demo Pack", "description": "A demo"}

    def releases(self, project_id):
        assert project_id == "pack-1"
        return [self.release]

    def download_release(self, release):
        self.downloaded.append(release.id)
        return b"archive"


class Importer:
    def import_archive(self, archive, destination, *, on_progress=None):
        return {"format": "mrpack", "game_version": "1.21.4", "loader": "fabric", "loader_version": "0.16.9", "installed_files": []}


class Installer:
    def install_modpack(self, instance, directory, metadata, on_progress):
        instance["version"] = "1.21.4-fabric-0.16.9"


class Player:
    def is_ready(self, instance, directory):
        return True


def test_browse_selects_exact_release_and_installs_independent_instance(tmp_path):
    application = QApplication.instance() or QApplication([])
    catalog = Catalog()
    window = LauncherWindow(
        data_root=tmp_path / "data", installer=Installer(), player=Player(),
        modpack_importer=Importer(), modrinth_catalog=catalog,
    )
    window.modrinth_search_input.setText("demo")
    window._search_modrinth_catalog()
    assert window.modrinth_pack_list.count() == 1
    window.modrinth_pack_list.setCurrentRow(0)
    application.processEvents()
    assert window.modrinth_release_selector.currentData().id == "release-2"
    window._install_modrinth_catalog_release()
    instance = window.state["instances"][0]
    assert catalog.downloaded == ["release-2"]
    assert instance["pack_project_id"] == "pack-1"
    assert instance["pack_release_id"] == "release-2"
    assert instance["ready"] is True
    assert instance["version"] == "1.21.4-fabric-0.16.9"
    assert not list((tmp_path / "data").glob(".modrinth-catalog-*"))
    window.close()


def test_catalog_empty_results_are_reported_without_affecting_existing_instance(tmp_path):
    class Empty(Catalog):
        def search(self, query):
            return []

    window = LauncherWindow(data_root=tmp_path / "data", installer=Installer(), player=Player(), modrinth_catalog=Empty())
    window.modrinth_search_input.setText("missing")
    window._search_modrinth_catalog()
    assert "No Modrinth" in window.modrinth_catalog_status.text()
    assert window.state["instances"] == []
    window.close()
