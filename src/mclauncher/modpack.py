"""Safe client-side import of Modrinth ``.mrpack`` archives.

The importer deliberately owns archive validation and materialisation.  It never
extracts directly into a live instance: all files are checked and staged first,
then copied into the instance directory while leaving worlds and settings alone.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from urllib.parse import urlparse
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable


class ModrinthPackError(ValueError):
    """A pack cannot be safely or meaningfully imported."""


class UnsupportedModrinthPack(ModrinthPackError):
    """The archive is valid enough to inspect but needs an unsupported loader."""


Progress = Callable[[str, int, int], None]
Download = Callable[[str], bytes]
LoaderResolver = Callable[[str, str], object]

_LOADER_NAMES = {
    "fabric-loader": "fabric",
    "quilt-loader": "quilt",
}


def resolve_official_loader_profile(loader: str, game_version: str, loader_version: str) -> dict:
    """Return the upstream profile only when that exact game/loader pair exists."""
    if loader not in {"fabric", "quilt"}:
        raise UnsupportedModrinthPack(f"Loader {loader!r} has no supported profile metadata")
    host = "meta.fabricmc.net" if loader == "fabric" else "meta.quiltmc.org"
    prefix = "/v2" if loader == "fabric" else "/v3"
    versions_url = f"https://{host}{prefix}/versions/loader/{game_version}"
    profile_url = f"{versions_url}/{loader_version}/profile/json"
    try:
        with urllib.request.urlopen(versions_url, timeout=15) as response:
            versions = json.loads(response.read().decode("utf-8"))
        supported = {
            item.get("loader", {}).get("version") or item.get("version")
            for item in versions if isinstance(item, dict)
        }
        if loader_version not in supported:
            raise UnsupportedModrinthPack(
                f"{loader.title()} {loader_version} is unavailable for Minecraft {game_version}"
            )
        with urllib.request.urlopen(profile_url, timeout=15) as response:
            profile = json.loads(response.read().decode("utf-8"))
    except UnsupportedModrinthPack:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UnsupportedModrinthPack(
            f"Could not verify {loader.title()} {loader_version} for Minecraft {game_version}: {error}"
        ) from error
    if not isinstance(profile, dict) or not isinstance(profile.get("id"), str):
        raise UnsupportedModrinthPack(f"{loader.title()} returned an invalid launcher profile")
    return profile


def _safe_relative_path(value: object, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ModrinthPackError(f"{label} is not a safe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or value.startswith(("/", "\\")) or ":" in path.parts[0]:
        raise ModrinthPackError(f"{label} must stay inside the instance")
    if any(part in ("", ".", "..") for part in path.parts):
        raise ModrinthPackError(f"{label} must stay inside the instance")
    return path


def _inside(root: Path, relative: PurePosixPath) -> Path:
    destination = (root / Path(*relative.parts)).resolve()
    if root.resolve() not in destination.parents:
        raise ModrinthPackError("archive entry escapes the instance")
    return destination


def _hashes_match(content: bytes, hashes: object) -> bool:
    if not isinstance(hashes, dict) or not isinstance(hashes.get("sha1"), str) or not isinstance(hashes.get("sha512"), str):
        return False
    return (
        hashlib.sha1(content).hexdigest().lower() == hashes["sha1"].lower()
        and hashlib.sha512(content).hexdigest().lower() == hashes["sha512"].lower()
    )


class ModrinthPackImporter:
    """Validate, prepare, and import a client Modrinth pack."""

    def __init__(self, download: Download | None = None, loader_resolver: LoaderResolver | None = None,
                 provider=None) -> None:
        if provider is not None:
            download = download or getattr(provider, "download_file", None) or getattr(provider, "download", None)
            loader_resolver = loader_resolver or getattr(provider, "resolve_loader", None)
        self.download = download or self._download
        self.loader_resolver = loader_resolver

    @staticmethod
    def _download(url: str) -> bytes:
        allowed_hosts = {"cdn.modrinth.com", "github.com", "raw.githubusercontent.com", "gitlab.com"}
        parsed = urlparse(url) if isinstance(url, str) else None
        if parsed is None or parsed.scheme.lower() != "https" or parsed.hostname not in allowed_hosts:
            raise ModrinthPackError("Modrinth file URLs must use HTTPS from a supported file host")
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read()

    @staticmethod
    def _read_manifest(archive: zipfile.ZipFile) -> dict:
        names = archive.namelist()
        if "modrinth.index.json" not in names:
            raise ModrinthPackError("This archive has no root modrinth.index.json manifest")
        try:
            value = json.loads(archive.read("modrinth.index.json").decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ModrinthPackError(f"The Modrinth manifest is invalid: {error}") from error
        if not isinstance(value, dict) or value.get("formatVersion") != 1 or value.get("game") != "minecraft":
            raise ModrinthPackError("Only Modrinth Minecraft formatVersion 1 packs are supported")
        if not isinstance(value.get("files"), list) or not isinstance(value.get("dependencies"), dict):
            raise ModrinthPackError("The Modrinth manifest is missing files or dependencies")
        return value

    def _validate_loader(self, manifest: dict) -> tuple[str, str, str]:
        dependencies = manifest["dependencies"]
        game = dependencies.get("minecraft")
        if not isinstance(game, str) or not game:
            raise ModrinthPackError("The pack does not declare a Minecraft version")
        loaders = [(key, value) for key, value in dependencies.items() if key != "minecraft"]
        if len(loaders) != 1:
            raise UnsupportedModrinthPack("The pack must declare exactly one supported client loader")
        loader, version = loaders[0]
        if loader not in _LOADER_NAMES or not isinstance(version, str) or not version:
            raise UnsupportedModrinthPack(f"Modrinth loader {loader!r} is not supported yet")
        loader_name = _LOADER_NAMES[loader]
        resolver = self.loader_resolver or (
            lambda selected_game, selected_loader: resolve_official_loader_profile(
                loader_name, selected_game, selected_loader
            )
        )
        if resolver is not None:
            try:
                profile = resolver(game, version)
            except Exception as error:
                raise UnsupportedModrinthPack(
                    f"{loader_name.title()} {version} is unavailable for Minecraft {game}: {error}"
                ) from error
            if profile is False or profile is None:
                raise UnsupportedModrinthPack(f"{loader_name.title()} {version} is unavailable for Minecraft {game}")
        return game, loader_name, version

    def import_archive(
        self,
        archive_path: Path | str,
        instance_root: Path | str,
        *,
        cancel_event=None,
        on_progress: Progress | None = None,
    ) -> dict:
        archive_path = Path(archive_path)
        root = Path(instance_root)
        if not archive_path.is_file():
            raise ModrinthPackError("The selected pack file does not exist")
        root.mkdir(parents=True, exist_ok=True)
        progress = on_progress or (lambda *_args: None)
        stage = Path(tempfile.mkdtemp(prefix=".mrpack-", dir=str(root.parent)))
        try:
            with zipfile.ZipFile(archive_path) as archive:
                manifest = self._read_manifest(archive)
                game, loader, loader_version = self._validate_loader(manifest)
                members = set(archive.namelist())
                for name in members:
                    if name.endswith("/"):
                        continue
                    _safe_relative_path(name, label="archive entry")
                entries = manifest["files"]
                total = len(entries)
                installed = []
                for index, entry in enumerate(entries, 1):
                    if cancel_event is not None and cancel_event.is_set():
                        raise ModrinthPackError("Modpack preparation cancelled")
                    if not isinstance(entry, dict):
                        raise ModrinthPackError("The Modrinth manifest contains an invalid file entry")
                    path = _safe_relative_path(entry.get("path"), label="manifest path")
                    env = entry.get("env", {})
                    if isinstance(env, dict) and env.get("client") == "unsupported":
                        continue
                    if isinstance(env, dict) and env.get("client") not in (None, "required", "optional"):
                        raise ModrinthPackError(f"Unsupported client environment for {path}")
                    url = entry.get("downloads")
                    if not isinstance(url, list) or not url or not isinstance(url[0], str):
                        raise ModrinthPackError(f"No client download is declared for {path}")
                    content = self.download(url[0])
                    if not _hashes_match(content, entry.get("hashes")):
                        raise ModrinthPackError(f"Integrity check failed for {path}")
                    destination = _inside(stage, path)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(content)
                    installed.append(str(path))
                    progress(f"Preparing {path}", index, total)
                for prefix in ("overrides", "client-overrides"):
                    for member in sorted(name for name in members if name.startswith(prefix + "/")):
                        relative = _safe_relative_path(member[len(prefix) + 1 :], label="override path")
                        source = archive.open(member)
                        destination = _inside(stage, relative)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with source, destination.open("wb") as target:
                            shutil.copyfileobj(source, target)
                        installed.append(str(relative))
            for source in sorted(stage.rglob("*")):
                if source.is_file():
                    relative = source.relative_to(stage)
                    destination = _inside(root, PurePosixPath(relative.as_posix()))
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(source, destination) if not destination.exists() else shutil.copy2(source, destination)
            return {
                "provider": "modrinth",
                "format": "mrpack",
                "game_version": game,
                "loader": loader,
                "loader_version": loader_version,
                "installed_files": sorted(set(installed)),
                "manifest": manifest,
            }
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    # Provider-facing name kept alongside the archive-oriented API for callers
    # that model the operation as importing a pack release.
    import_pack = import_archive
