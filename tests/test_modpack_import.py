import hashlib
import json
import zipfile

import pytest

from mclauncher.modpack import ModrinthPackError, ModrinthPackImporter, UnsupportedModrinthPack


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
