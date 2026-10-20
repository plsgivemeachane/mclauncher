import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow
from mclauncher.modpack import UnsupportedModrinthPack


class ForgeImporter:
    def import_archive(self, archive, destination, *, on_progress=None):
        return {
            "provider": "modrinth",
            "format": "mrpack",
            "game_version": "1.21.4",
            "loader": "forge",
            "loader_version": "47.3.0",
            "installed_files": [],
        }


class ForgeInstaller:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def install_modpack(self, instance, directory, metadata, on_progress):
        self.calls.append((instance["id"], directory, metadata["loader"], metadata["loader_version"]))
        if self.error:
            raise self.error
        instance["version"] = "1.21.4-forge-47.3.0"


class ReadyPlayer:
    def __init__(self):
        self.launches = []

    def is_ready(self, _instance, _directory):
        return True

    def launch(self, instance, directory, username, player_uuid, on_started, on_finished, memory_gib=None):
        self.launches.append((instance["id"], instance["version"], directory))
        on_started()
        return object()


def test_window_imports_exact_forge_pack_and_reopens_ready_instance(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    archive = tmp_path / "forge-pack.mrpack"
    archive.write_bytes(b"fixture")
    installer = ForgeInstaller()
    player = ReadyPlayer()
    monkeypatch.setattr(
        "mclauncher.app.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(archive), "Modrinth packs (*.mrpack)"),
    )
    window = LauncherWindow(
        data_root=tmp_path / "data", installer=installer, player=player, modpack_importer=ForgeImporter()
    )
    window._import_modrinth_pack()
    application.processEvents()

    instance = window.state["instances"][0]
    assert instance["loader"] == "forge"
    assert instance["loader_version"] == "47.3.0"
    assert instance["version"] == "1.21.4-forge-47.3.0"
    assert instance["ready"] is True
    assert installer.calls[0][2:] == ("forge", "47.3.0")
    window.close()

    reopened = LauncherWindow(
        data_root=tmp_path / "data", installer=ForgeInstaller(), player=ReadyPlayer(), modpack_importer=ForgeImporter()
    )
    application.processEvents()
    assert reopened.state["instances"][0]["loader"] == "forge"
    assert reopened.state["instances"][0]["version"] == "1.21.4-forge-47.3.0"
    reopened.close()


def test_window_reports_unsupported_forge_pair_and_keeps_retryable_instance(tmp_path, monkeypatch):
    archive = tmp_path / "unsupported-forge.mrpack"
    archive.write_bytes(b"fixture")
    monkeypatch.setattr(
        "mclauncher.app.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(archive), "Modrinth packs (*.mrpack)"),
    )
    window = LauncherWindow(
        data_root=tmp_path / "data",
        installer=ForgeInstaller(UnsupportedModrinthPack("Forge 47.3.0 is unavailable for Minecraft 1.21.4")),
        player=ReadyPlayer(),
        modpack_importer=ForgeImporter(),
    )
    window._import_modrinth_pack()

    assert window.state["instances"][0]["ready"] is False
    assert "unavailable" in window.state["instances"][0]["install_error"]
    assert "supported Modrinth" in window.diagnostic_hint_label.text()
    window.close()
