import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow


class CurseForgeImporter:
    def import_archive(self, archive, destination, *, on_progress=None):
        return {
            "provider": "curseforge",
            "format": "curseforge-export",
            "game_version": "1.20.1",
            "loader": "forge",
            "loader_version": "47.3.0",
            "installed_files": ["config/example.txt"],
            "complete": False,
            "missing_files": [{"project_id": 42, "file_id": 7, "reason": "API key required"}],
            "recovery_action": "Recovery: configure the CurseForge API key and retry",
        }


class Installer:
    def discover_versions(self):
        return []

    def install_modpack(self, *args):
        raise AssertionError("incomplete pack must not prepare a loader")


class Player:
    def is_ready(self, *_args):
        return False


def test_window_imports_incomplete_curseforge_pack_and_disables_play(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    archive = tmp_path / "exported-pack.zip"
    archive.write_bytes(b"fixture")
    monkeypatch.setattr(
        "mclauncher.app.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(archive), "CurseForge packs (*.zip)"),
    )
    window = LauncherWindow(
        data_root=tmp_path / "data",
        installer=Installer(),
        player=Player(),
        curseforge_importer=CurseForgeImporter(),
    )
    window._import_curseforge_pack()
    application.processEvents()

    instance = window.state["instances"][0]
    assert instance["provider"] == "curseforge"
    assert instance["install_state"] == "incomplete"
    assert instance["missing_files"][0]["project_id"] == 42
    assert window.play_button.isEnabled() is False
    assert "recovery" in window.diagnostic_hint_label.text().lower()
    window.close()
