import hashlib
import json
import zipfile

import pytest

from mclauncher.modpack import ModrinthPackError, ModrinthPackImporter, UnsupportedModrinthPack
from mclauncher.installer import MinecraftInstaller


def _pack(path, *, dependency="fabric-loader", file_path="mods/example.jar", payload=b"jar"):
    hashes = {
        "sha1": hashlib.sha1(payload).hexdigest(),
        "sha512": hashlib.sha512(payload).hexdigest(),
    }
    manifest = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": "demo",
        "name": "Demo",
        "dependencies": {"minecraft": "1.21.4", dependency: "0.16.9"},
        "files": [{"path": file_path, "hashes": hashes, "downloads": ["https://cdn.modrinth.com/example.jar"]}],
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("modrinth.index.json", json.dumps(manifest))
        archive.writestr("overrides/config/example.txt", "configured")
    return payload


def test_importer_validates_hashes_and_stages_overrides(tmp_path):
    payload = _pack(tmp_path / "demo.mrpack")
    destination = tmp_path / "instance"
    result = ModrinthPackImporter(
        download=lambda _url: payload,
        loader_resolver=lambda _game, _loader: {"id": "fabric"},
    ).import_archive(tmp_path / "demo.mrpack", destination)

    assert result["provider"] == "modrinth"
    assert result["loader"] == "fabric"
    assert (destination / "mods/example.jar").read_bytes() == payload
    assert (destination / "config/example.txt").read_text() == "configured"

    with pytest.raises(ModrinthPackError, match="Integrity"):
        ModrinthPackImporter(download=lambda _url: b"changed", loader_resolver=lambda *_args: True).import_archive(
            tmp_path / "demo.mrpack", tmp_path / "other"
        )


def test_importer_rejects_unsupported_loader_and_traversal_before_writes(tmp_path):
    _pack(tmp_path / "forge.mrpack", dependency="forge")
    with pytest.raises(UnsupportedModrinthPack, match="not supported"):
        ModrinthPackImporter(download=lambda _url: b"jar").import_archive(tmp_path / "forge.mrpack", tmp_path / "forge")

    _pack(tmp_path / "escape.mrpack", file_path="../outside.jar")
    with pytest.raises(ModrinthPackError, match="inside"):
        ModrinthPackImporter(download=lambda _url: b"jar", loader_resolver=lambda *_args: True).import_archive(
            tmp_path / "escape.mrpack", tmp_path / "escape"
        )
    assert not (tmp_path / "outside.jar").exists()


def test_importer_accepts_forge_only_after_exact_pair_is_resolved(tmp_path):
    payload = _pack(tmp_path / "forge.mrpack", dependency="forge")
    destination = tmp_path / "forge-instance"
    result = ModrinthPackImporter(
        download=lambda _url: payload,
        loader_resolver=lambda game, forge: {"game": game, "forge": forge},
    ).import_archive(tmp_path / "forge.mrpack", destination)

    assert result["loader"] == "forge"
    assert result["loader_version"] == "0.16.9"

    with pytest.raises(UnsupportedModrinthPack, match="cannot be verified"):
        ModrinthPackImporter(download=lambda _url: payload).import_archive(
            tmp_path / "forge.mrpack", tmp_path / "unverified"
        )

    with pytest.raises(UnsupportedModrinthPack, match="unavailable"):
        ModrinthPackImporter(
            download=lambda _url: payload,
            loader_resolver=lambda _game, _forge: None,
        ).import_archive(tmp_path / "forge.mrpack", tmp_path / "unsupported")


def test_installer_checks_exact_forge_pair_and_records_launcher_profile(tmp_path, monkeypatch):
    class Forge:
        def __init__(self):
            self.installs = []

        def get_loader_versions(self, game, stable_only):
            assert (game, stable_only) == ("1.21.4", False)
            return ["47.3.0"]

        def install(self, game, directory, *, loader_version, callback):
            self.installs.append((game, directory, loader_version, callback))
            return "1.21.4-forge-47.3.0"

    forge = Forge()
    monkeypatch.setattr(
        "mclauncher.installer.minecraft_launcher_lib.mod_loader.get_mod_loader",
        lambda loader: forge if loader == "forge" else None,
    )
    monkeypatch.setattr(
        "mclauncher.installer.minecraft_launcher_lib.runtime",
        type("Runtime", (), {"get_version_runtime_information": staticmethod(lambda *_: {"name": "java"})}),
    )

    instance = {"version": "1.21.4"}
    MinecraftInstaller().install_modpack(
        instance,
        tmp_path,
        {"loader": "forge", "game_version": "1.21.4", "loader_version": "47.3.0"},
        lambda *_args: None,
    )
    assert instance["minecraft_version"] == "1.21.4"
    assert instance["version"] == "1.21.4-forge-47.3.0"
    assert forge.installs[0][2] == "47.3.0"

    with pytest.raises(RuntimeError, match="unavailable"):
        MinecraftInstaller().install_modpack(
            {"version": "1.21.4"}, tmp_path,
            {"loader": "forge", "game_version": "1.21.4", "loader_version": "47.3.1"},
            lambda *_args: None,
        )


def test_importer_accepts_exact_neoforge_pair_from_loader_resolver(tmp_path):
    _pack(tmp_path / "neoforge.mrpack", dependency="neoforge")
    calls = []

    def resolve(game, loader, version):
        calls.append((game, loader, version))
        return {"loader": loader, "game_version": game, "loader_version": version}

    result = ModrinthPackImporter(
        download=lambda _url: b"jar", loader_resolver=resolve
    ).import_archive(tmp_path / "neoforge.mrpack", tmp_path / "neoforge")

    assert calls == [("1.21.4", "neoforge", "0.16.9")]
    assert result["loader"] == "neoforge"


def test_importer_fails_closed_when_neoforge_pair_is_unavailable(tmp_path):
    _pack(tmp_path / "neoforge.mrpack", dependency="neoforge")
    with pytest.raises(UnsupportedModrinthPack, match="NeoForge.*unavailable"):
        ModrinthPackImporter(
            download=lambda _url: b"jar", loader_resolver=lambda *_args: None
        ).import_archive(tmp_path / "neoforge.mrpack", tmp_path / "neoforge")
