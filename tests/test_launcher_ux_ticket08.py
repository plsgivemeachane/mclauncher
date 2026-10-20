import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog

from mclauncher.app import LauncherWindow


class QuiltImporter:
    def import_archive(self, _archive, _destination, on_progress=None):
        if on_progress:
            on_progress("Preparing Quilt files", 1, 1)
        return {
            "provider": "modrinth",
            "format": "mrpack",
            "game_version": "1.21.4",
            "loader": "quilt",
            "loader_version": "0.20.0-beta.9",
            "installed_files": ["mods/example.jar"],
        }


class QuiltInstaller:
    def __init__(self):
        self.calls = []

    def install_modpack(self, instance, directory, metadata, _on_progress):
        self.calls.append((instance["id"], directory, metadata["loader"], metadata["loader_version"]))
        return "quilt-loader-0.20.0-beta.9-1.21.4"


class ReadyPlayer:
    def __init__(self):
        self.launches = []

    def is_ready(self, _instance, _directory):
        return True

    def launch(self, instance, directory, username, player_uuid, on_started, _on_finished, memory_gib=None):
        self.launches.append((instance["id"], directory, username, player_uuid, memory_gib))
        on_started()
        return object()


def test_quilt_import_reaches_ready_and_play_with_pinned_loader(monkeypatch, tmp_path):
    application = QApplication.instance() or QApplication([])
    archive = tmp_path / "quilt-pack.mrpack"
    archive.write_bytes(b"fixture")
    installer = QuiltInstaller()
    player = ReadyPlayer()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(archive), ""))

    window = LauncherWindow(
        data_root=tmp_path / "data", installer=installer, player=player,
        modpack_importer=QuiltImporter(),
    )
    window.show()
    window.username_input.setText("Alex")
    window.username_input.editingFinished.emit()
    window.import_modpack_button.click()
    application.processEvents()

    instance = window.state["instances"][0]
    assert instance["loader"] == "quilt"
    assert instance["loader_version"] == "0.20.0-beta.9"
    assert instance["installed_version"] == "quilt-loader-0.20.0-beta.9-1.21.4"
    assert instance["ready"] is True

    window.play_button.click()
    application.processEvents()
    assert len(player.launches) == 1
    window.close()
