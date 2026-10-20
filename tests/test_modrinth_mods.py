import hashlib
import threading

import pytest

from mclauncher.modrinth_catalog import ModrinthRelease
from mclauncher.modrinth_mods import ModrinthModInstallError, ModrinthModInstaller


def release(project, version, filename, payload, *, dependencies=()):
    return ModrinthRelease(
        version, project, project, version, ("1.21.4",), ("fabric",),
        f"https://cdn.modrinth.com/{filename}", filename,
        hashlib.sha1(payload).hexdigest(), hashlib.sha512(payload).hexdigest(), dependencies,
    )


class Catalog:
    def __init__(self):
        self.main = release("main", "main-v1", "main.jar", b"main", dependencies=(
            {"project_id": "dep", "dependency_type": "required"},
        ))
        self.dep = release("dep", "dep-v1", "dep.jar", b"dep")

    def releases(self, project_id, *, game_version="", loader=""):
        return [self.dep] if project_id == "dep" else []

    def download_release(self, selected):
        return {"main-v1": b"main", "dep-v1": b"dep"}[selected.id]


def test_installer_downloads_required_dependency_and_records_verified_entries(tmp_path):
    instance = {"minecraft_version": "1.21.4", "loader": "fabric", "mods": []}
    entries = ModrinthModInstaller(Catalog()).install(instance, tmp_path / "instance", Catalog().main)

    assert [entry["project_id"] for entry in entries] == ["main", "dep"]
    assert all(entry["metadata_verified"] and entry["compatible"] for entry in entries)
    assert (tmp_path / "instance" / "mods" / "main.jar").read_bytes() == b"main"
    assert (tmp_path / "instance" / "mods" / "dep.jar").read_bytes() == b"dep"


def test_installer_rejects_incompatible_release_without_writing(tmp_path):
    selected = ModrinthRelease(
        "bad", "bad", "Bad", "1", ("1.20.1",), ("forge",),
        "https://cdn.modrinth/bad.jar", "bad.jar", "a", "b",
    )
    with pytest.raises(ModrinthModInstallError, match="not compatible"):
        ModrinthModInstaller(Catalog()).install(
            {"minecraft_version": "1.21.4", "loader": "fabric", "mods": []}, tmp_path / "instance", selected
        )
    assert not (tmp_path / "instance" / "mods").exists()


def test_installer_rejects_hash_mismatch_and_leaves_existing_state(tmp_path):
    catalog = Catalog()
    catalog.download_release = lambda _release: b"tampered"
    instance = {"minecraft_version": "1.21.4", "loader": "fabric", "mods": []}
    with pytest.raises(ModrinthModInstallError, match="Integrity"):
        ModrinthModInstaller(catalog).install(instance, tmp_path / "instance", catalog.main)
    assert instance["mods"] == []
    assert not (tmp_path / "instance" / "mods" / "main.jar").exists()


def test_installer_rejects_duplicate_project_without_writing(tmp_path):
    catalog = Catalog()
    instance = {"minecraft_version": "1.21.4", "loader": "fabric", "mods": [{"project_id": "main"}]}
    with pytest.raises(ModrinthModInstallError, match="already contains"):
        ModrinthModInstaller(catalog).install(instance, tmp_path / "instance", catalog.main)


def test_cancellation_rolls_back_files_already_published(tmp_path, monkeypatch):
    catalog = Catalog()
    cancel = threading.Event()
    import mclauncher.modrinth_mods as module
    original_copy = module.shutil.copy2

    def copy_then_cancel(source, destination):
        original_copy(source, destination)
        cancel.set()

    monkeypatch.setattr(module.shutil, "copy2", copy_then_cancel)
    with pytest.raises(ModrinthModInstallError, match="cancelled"):
        ModrinthModInstaller(catalog).install(
            {"minecraft_version": "1.21.4", "loader": "fabric", "mods": []},
            tmp_path / "instance", catalog.main, cancel_event=cancel,
        )
    assert not list((tmp_path / "instance" / "mods").glob("*.jar"))
