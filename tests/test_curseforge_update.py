import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow
from mclauncher.modpack import ModrinthPackUpdateError, ModrinthPackUpdater


class CurseForgeReplacement:
    def __init__(self, *, complete=True):
        self.complete = complete

    def import_archive(self, archive, destination, *, cancel_event=None, on_progress=None):
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "mods").mkdir()
        (destination / "mods" / "cf-new.jar").write_bytes(b"cf-new")
        if not self.complete:
            return {
                "provider": "curseforge", "complete": False, "missing_files": [{"project_id": 1}],
                "recovery_action": "configure CurseForge access and retry",
            }
        return {
            "provider": "curseforge", "format": "curseforge-export", "complete": True,
            "game_version": "1.20.1", "loader": "forge", "loader_version": "47.2.0",
            "installed_files": ["mods/cf-new.jar"],
        }


def _instance(root: Path) -> dict:
    (root / "mods").mkdir(parents=True)
    (root / "mods" / "cf-old.jar").write_bytes(b"old")
    (root / "saves").mkdir()
    (root / "saves" / "world.dat").write_bytes(b"world")
    return {
        "id": "cf-1", "provider": "curseforge", "installed_files": ["mods/cf-old.jar"],
        "pack_source": "old.zip", "pack_release_id": "old", "ready": True, "install_state": "ready",
    }


def test_curseforge_update_preserves_identity_and_worlds(tmp_path):
    root = tmp_path / "minecraft"
    instance = _instance(root)
    result = ModrinthPackUpdater(CurseForgeReplacement()).update(
        instance, root, tmp_path / "new.zip"
    )
    assert instance["provider"] == "curseforge"
    assert instance["pack_source"] == str(tmp_path / "new.zip")
    assert (root / "mods" / "cf-new.jar").read_bytes() == b"cf-new"
    assert (root / "saves" / "world.dat").read_bytes() == b"world"
    assert Path(result["backup"]).is_dir()


def test_restricted_curseforge_files_never_publish_ready(tmp_path):
    root = tmp_path / "minecraft"
    instance = _instance(root)
    with pytest.raises(ModrinthPackUpdateError, match="incomplete"):
        ModrinthPackUpdater(CurseForgeReplacement(complete=False)).update(instance, root, tmp_path / "new.zip")
    assert instance["pack_release_id"] == "old"
    assert (root / "mods" / "cf-old.jar").exists()


def test_window_updates_curseforge_instance_through_explicit_archive(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    archive = tmp_path / "new.zip"
    archive.write_bytes(b"fixture")

    class Updater:
        def update(self, instance, root, selected, **kwargs):
            assert selected == archive
            instance.update(pack_source=str(selected), install_state="ready", ready=True)
            return {"backup": str(tmp_path / "backup")}

        def recover(self, instance, root):
            raise AssertionError("recovery should not run")

    class Player:
        @staticmethod
        def is_ready(instance, root):
            return True

    monkeypatch.setattr("mclauncher.app.QFileDialog.getOpenFileName", lambda *a, **k: (str(archive), "ZIP"))
    window = LauncherWindow(
        data_root=tmp_path / "data", curseforge_updater=Updater(), player=Player()
    )
    window.instance_name_input.setText("CurseForge pack")
    window.create_instance_button.click()
    instance = window.state["instances"][0]
    instance.update(provider="curseforge", ready=True, install_state="ready")
    window._update_selected_curseforge_pack()
    assert instance["pack_source"] == str(archive)
    assert instance["install_state"] == "ready"
    window.close()
