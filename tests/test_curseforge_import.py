import hashlib
import json
import zipfile

import pytest

from mclauncher.modpack import CurseForgePackError, CurseForgePackImporter


def _archive(path, *, file_entry=None, loader="forge-47.3.0", override=True):
    manifest = {
        "manifestType": "minecraftModpack",
        "manifestVersion": 1,
        "name": "Exported pack",
        "minecraft": {"version": "1.20.1", "modLoaders": [{"id": loader, "primary": True}]},
        "files": [file_entry] if file_entry else [],
        "overrides": "overrides",
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        if override:
            archive.writestr("overrides/config/example.txt", "configured")


class Provider:
    def __init__(self, payload=b"mod jar", *, available=True):
        self.payload = payload
        self.available = available

    def resolve_file(self, project_id, file_id):
        if not self.available:
            return None
        return {
            "project_id": project_id,
            "file_id": file_id,
            "url": "https://edge.forgecdn.net/files/1/2/example.jar",
            "sha1": hashlib.sha1(self.payload).hexdigest(),
            "sha512": hashlib.sha512(self.payload).hexdigest(),
            "filename": "example.jar",
        }

    def download_file(self, metadata):
        return self.payload


def test_importer_materializes_manifest_files_and_overrides(tmp_path):
    archive = tmp_path / "pack.zip"
    _archive(archive, file_entry={"projectID": 42, "fileID": 7, "required": True})

    result = CurseForgePackImporter(
        provider=Provider(),
        loader_resolver=lambda game, loader, version: {"game": game, "loader": loader, "version": version},
    ).import_archive(archive, tmp_path / "instance")

    assert result["provider"] == "curseforge"
    assert result["format"] == "curseforge-export"
    assert result["loader"] == "forge"
    assert result["loader_version"] == "47.3.0"
    assert result["game_version"] == "1.20.1"
    assert result["complete"] is True
    assert (tmp_path / "instance" / "mods" / "example.jar").read_bytes() == b"mod jar"
    assert (tmp_path / "instance" / "config" / "example.txt").read_text() == "configured"


def test_importer_returns_actionable_incomplete_result_without_provider_access(tmp_path):
    archive = tmp_path / "pack.zip"
    _archive(archive, file_entry={"projectID": 42, "fileID": 7, "required": True})

    result = CurseForgePackImporter(
        provider=Provider(available=False),
        loader_resolver=lambda *_args: True,
    ).import_archive(archive, tmp_path / "instance")

    assert result["complete"] is False
    assert result["missing_files"][0]["project_id"] == 42
    assert "recovery" in result["recovery_action"].lower()
    assert (tmp_path / "instance" / "config" / "example.txt").is_file()


def test_importer_rejects_bad_archive_and_traversal_before_publishing(tmp_path):
    archive = tmp_path / "bad.zip"
    _archive(archive, override=False)
    with zipfile.ZipFile(archive, "a") as value:
        value.writestr("overrides/../outside.txt", "escape")
    with pytest.raises(CurseForgePackError, match="inside|manifest"):
        CurseForgePackImporter(provider=Provider()).import_archive(archive, tmp_path / "instance")
    assert not (tmp_path / "outside.txt").exists()


def test_replacement_must_match_authoritative_file_hashes(tmp_path):
    payload = b"authoritative"
    provider = Provider(payload=payload, available=True)
    importer = CurseForgePackImporter(provider=provider)
    replacement = tmp_path / "replacement.jar"
    replacement.write_bytes(payload)

    assert importer.verify_replacement(replacement, {"projectID": 42, "fileID": 7}) is True
    replacement.write_bytes(b"unknown replacement")
    with pytest.raises(CurseForgePackError, match="integrity|verified"):
        importer.verify_replacement(replacement, {"projectID": 42, "fileID": 7})


def test_missing_api_key_is_explicit_and_does_not_claim_download_access(tmp_path, monkeypatch):
    monkeypatch.delenv("CURSEFORGE_API_KEY", raising=False)
    archive = tmp_path / "pack.zip"
    _archive(archive, file_entry={"projectID": 42, "fileID": 7, "required": True})

    result = CurseForgePackImporter(loader_resolver=lambda *_args: True).import_archive(
        archive, tmp_path / "instance"
    )
    assert result["complete"] is False
    assert "API key" in result["recovery_action"]


class _Response:
    def __init__(self, body, final_url):
        self.body, self.final_url = body, final_url

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self):
        return self.body

    def geturl(self):
        return self.final_url


def _public_opener(payload, *, length=None, cdn_host="edge.forgecdn.net"):
    def opener(request, timeout=None):
        url = request.full_url
        if url.endswith("/download"):
            return _Response(payload, f"https://{cdn_host}/files/7/1/example.jar")
        data = {"id": 7, "fileName": "example.jar", "fileLength": len(payload) if length is None else length}
        return _Response(json.dumps({"data": data}).encode(), url)
    return opener


def _keyless_import(tmp_path, monkeypatch, opener, *, allowed=True):
    from mclauncher.modpack import CurseForgeProvider

    monkeypatch.delenv("CURSEFORGE_API_KEY", raising=False)
    archive = tmp_path / "pack.zip"
    _archive(archive, file_entry={"projectID": 42, "fileID": 7, "required": True})
    provider = CurseForgeProvider(opener=opener, allow_public=lambda: allowed)
    return CurseForgePackImporter(provider=provider, loader_resolver=lambda *_args: True).import_archive(
        archive, tmp_path / "instance"
    )


def test_keyless_preference_downloads_size_checked_file_from_curseforge_cdn(tmp_path, monkeypatch):
    result = _keyless_import(tmp_path, monkeypatch, _public_opener(b"mod jar"))

    assert result["complete"] is True
    assert (tmp_path / "instance" / "mods" / "example.jar").read_bytes() == b"mod jar"


def test_keyless_download_rejects_wrong_length(tmp_path, monkeypatch):
    result = _keyless_import(tmp_path, monkeypatch, _public_opener(b"mod jar", length=999))

    assert result["complete"] is False
    assert "integrity" in result["missing_files"][0]["reason"]


def test_keyless_download_rejects_redirect_off_curseforge_cdn(tmp_path, monkeypatch):
    result = _keyless_import(tmp_path, monkeypatch, _public_opener(b"mod jar", cdn_host="evil.example"))

    assert result["complete"] is False
    assert "unexpected host" in result["missing_files"][0]["reason"]


def test_keyless_downloads_stay_off_without_the_preference(tmp_path, monkeypatch):
    def opener(*_args, **_kwargs):
        raise AssertionError("no network access without a key or the preference")

    result = _keyless_import(tmp_path, monkeypatch, opener, allowed=False)

    assert result["complete"] is False
    assert "API key" in result["missing_files"][0]["reason"]


def test_hashless_metadata_from_keyed_api_is_still_rejected():
    assert CurseForgePackImporter._verify(b"jar", {"fileLength": 3}) is False
