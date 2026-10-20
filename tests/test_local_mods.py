import json
import os
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow
from mclauncher.localmods import inspect_mod_jar


def write_fabric_mod(path, *, game="1.21.4", mod_id="example"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fabric.mod.json", json.dumps({
            "id": mod_id, "name": "Example Mod", "version": "1.0.0",
            "depends": {"minecraft": game, "fabricloader": ">=0.15.0"},
        }))


def test_local_jar_metadata_identifies_compatible_fabric_mod(tmp_path):
    jar = tmp_path / "example.jar"
    write_fabric_mod(jar)

    metadata = inspect_mod_jar(jar, game_version="1.21.4", loader="fabric")

    assert metadata["metadata_verified"] is True
    assert metadata["compatible"] is True
    assert metadata["id"] == "example"


def test_local_jar_metadata_rejects_known_game_mismatch(tmp_path):
    jar = tmp_path / "example.jar"
    write_fabric_mod(jar, game="1.20.1")

    metadata = inspect_mod_jar(jar, game_version="1.21.4", loader="fabric")

    assert metadata["metadata_verified"] is True
    assert metadata["compatible"] is False
    assert "Minecraft" in metadata["compatibility_reason"]


def test_unknown_local_jar_is_allowed_but_explicitly_unverified(tmp_path):
    jar = tmp_path / "unknown.jar"
    with zipfile.ZipFile(jar, "w") as archive:
        archive.writestr("README.txt", "no mod metadata")

    metadata = inspect_mod_jar(jar, game_version="1.21.4", loader="fabric")

    assert metadata["metadata_verified"] is False
    assert metadata["compatible"] is None
    assert "could not verify" in metadata["compatibility_reason"].lower()


def test_mods_page_import_toggle_remove_and_reopen(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    jar = tmp_path / "example.jar"
    write_fabric_mod(jar)
    window = LauncherWindow(data_root=tmp_path / "data")
    instance = {"id": "pack-1214-a1b2c3d4", "name": "Pack", "version": "1.21.4",
                "loader": "fabric", "ready": True, "provider": "modrinth", "mods": []}
    window.state["instances"] = [instance]
    window.store.create_instance_root(instance["id"])
    window.store.save(window.state)
    window._add_instance_item(instance)
    window.instance_list.setCurrentRow(0)
    monkeypatch.setattr("mclauncher.app.QFileDialog.getOpenFileName", lambda *a, **k: (str(jar), "JAR"))

    window._show_page(2)
    window._import_local_mod()
    assert len(window.state["instances"][0]["mods"]) == 1
    assert window.state["instances"][0]["modified"] is True
    assert window.mods_list.count() == 1
    window.mods_list.setCurrentRow(0)
    window._toggle_selected_mod()
    assert window.state["instances"][0]["mods"][0]["enabled"] is False
    window._toggle_selected_mod()
    window._remove_selected_mod()
    assert window.state["instances"][0]["mods"] == []
    window.close()

    reopened = LauncherWindow(data_root=tmp_path / "data")
    reopened._show_page(2)
    reopened.instance_list.setCurrentRow(0)
    assert reopened.mods_list.count() == 0
    reopened.close()
