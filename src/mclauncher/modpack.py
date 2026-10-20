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
import time
import urllib.request
import inspect
from urllib.parse import urlparse
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping


class ModrinthPackError(ValueError):
    """A pack cannot be safely or meaningfully imported."""


class UnsupportedModrinthPack(ModrinthPackError):
    """The archive is valid enough to inspect but needs an unsupported loader."""


class CurseForgePackError(ModrinthPackError):
    """A CurseForge export is invalid, unavailable, or cannot be verified."""


class CurseForgeAccessError(CurseForgePackError):
    """The CurseForge provider requires access that is not configured."""


Progress = Callable[[str, int, int], None]
Download = Callable[[str], bytes]
LoaderResolver = Callable[..., object]

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
        supported_loaders = {
            "fabric-loader": "fabric",
            "forge": "forge",
            "neoforge": "neoforge",
            "quilt-loader": "quilt",
        }
        loader_names = {"fabric-loader": "Fabric", "forge": "Forge", "neoforge": "NeoForge", "quilt-loader": "Quilt"}
        if loader not in supported_loaders or not isinstance(version, str) or not version:
            raise UnsupportedModrinthPack(f"Modrinth loader {loader!r} is not supported yet")
        if loader == "forge" and self.loader_resolver is None:
            raise UnsupportedModrinthPack(
                f"Forge {version} is not supported: cannot be verified from official metadata for Minecraft {game}"
            )
        if loader == "neoforge" and self.loader_resolver is None:
            raise UnsupportedModrinthPack(
                f"{loader_names[loader]} {version} is unavailable for Minecraft {game}; exact support metadata is required"
            )
        resolver = self.loader_resolver
        if resolver is None and loader in {"fabric-loader", "quilt-loader"}:
            resolver = lambda selected_game, selected_loader: resolve_official_loader_profile(
                supported_loaders[loader], selected_game, selected_loader
            )
        if resolver is not None:
            try:
                # Keep the pre-NeoForge two-argument injection seam working while
                # allowing the resolver to distinguish loader families.
                parameters = inspect.signature(resolver).parameters
                positional = [p for p in parameters.values() if p.kind in (
                    inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD
                )]
                accepts_loader = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in parameters.values()) or len(positional) >= 3
                profile = resolver(game, loader, version) if accepts_loader else resolver(game, version)
            except Exception as error:
                name = loader_names[loader]
                raise UnsupportedModrinthPack(
                    f"{name} {version} is unavailable for Minecraft {game}: {error}"
                ) from error
            if profile is False or profile is None:
                name = loader_names[loader]
                raise UnsupportedModrinthPack(f"{name} {version} is unavailable for Minecraft {game}")
        return game, version, supported_loaders[loader]

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
                game, loader_version, loader_id = self._validate_loader(manifest)
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
                "loader": loader_id,
                "loader_version": loader_version,
                "installed_files": sorted(set(installed)),
                "manifest": manifest,
            }
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    # Provider-facing name kept alongside the archive-oriented API for callers
    # that model the operation as importing a pack release.
    import_pack = import_archive


class ModrinthPackUpdateError(ModrinthPackError):
    """An update could not be committed or safely recovered."""


class ModrinthPackUpdater:
    """Stage a replacement pack, back up the live instance, then publish atomically."""

    def __init__(self, importer: ModrinthPackImporter):
        self.importer = importer

    @staticmethod
    def _copy_tree(source: Path, destination: Path) -> None:
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)

    @staticmethod
    def _fsync_file(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @classmethod
    def _durable_tree(cls, root: Path) -> None:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                cls._fsync_file(path)
        for path in sorted((path for path in root.rglob("*") if path.is_dir()), key=lambda item: len(item.parts), reverse=True):
            cls._fsync_file(path)
        cls._fsync_file(root)
        if root.parent.is_dir():
            cls._fsync_file(root.parent)

    @classmethod
    def _durable_paths(cls, root: Path, paths) -> None:
        directories = {root}
        for path in paths:
            candidate = Path(path)
            if candidate.is_file():
                cls._fsync_file(candidate)
            directory = candidate.parent
            while directory != root and root in directory.parents:
                directories.add(directory)
                directory = directory.parent
            directories.add(root)
        for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
            if directory.is_dir():
                cls._fsync_file(directory)

    @classmethod
    def _durable_unlink(cls, path: Path) -> None:
        path.unlink(missing_ok=True)
        cls._fsync_file(path.parent)

    @classmethod
    def _publish_journal(cls, journal: Path, data: dict) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=journal.parent, prefix=".update-journal-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, journal)
            cls._fsync_file(journal.parent)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _file_hashes(root: Path, paths) -> dict[str, str]:
        hashes = {}
        for relative in paths:
            if not isinstance(relative, str):
                continue
            candidate = _inside(root, _safe_relative_path(relative, label="installed file"))
            if candidate.is_file():
                digest = hashlib.sha512()
                with candidate.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                hashes[relative] = digest.hexdigest()
        return hashes

    def update(
        self,
        instance: dict,
        minecraft_directory: Path | str,
        archive_path: Path | str,
        *,
        release_id: str = "",
        on_progress: Progress | None = None,
        confirm_local_changes: Callable[[list[str]], bool] | None = None,
        cancel_event=None,
        replacements=None,
    ) -> dict:
        if instance.get("install_state") == "installing" or instance.get("active"):
            raise ModrinthPackUpdateError("This instance is active; finish preparation or exit the game before updating")
        root = Path(minecraft_directory)
        if not root.is_dir():
            raise ModrinthPackUpdateError("The selected Modrinth instance has no usable data directory")
        progress = on_progress or (lambda *_args: None)
        stage = Path(tempfile.mkdtemp(prefix=".modrinth-update-", dir=str(root.parent)))
        backup_root = root.parent / "backups"
        backup = backup_root / f"{instance.get('id', 'instance')}-{time.time_ns()}"
        journal = root.parent / "update-journal.json"
        old_files = {str(path) for path in instance.get("installed_files", []) if isinstance(path, str)}
        previous_instance = dict(instance)
        try:
            import_kwargs = {"cancel_event": cancel_event, "on_progress": progress}
            if replacements is not None:
                import_kwargs["replacements"] = replacements
            metadata = self.importer.import_archive(archive_path, stage, **import_kwargs)
            if not metadata.get("complete", True):
                missing = metadata.get("missing_files", [])
                raise ModrinthPackUpdateError(
                    f"The replacement pack is incomplete: {len(missing)} required file(s) are unavailable; "
                    f"{metadata.get('recovery_action', 'recover provider access and retry')}"
                )
            if cancel_event is not None and cancel_event.is_set():
                raise ModrinthPackUpdateError("Modrinth pack update cancelled")
            local_files = sorted(
                path for directory in (root / "mods", root / "config")
                if directory.is_dir() for path in directory.rglob("*")
                if path.is_file() and path.relative_to(root).as_posix() not in old_files
            )
            local_names = [path.relative_to(root).as_posix() for path in local_files]
            declared_local = instance.get("local_modifications", [])
            if isinstance(declared_local, list):
                local_names.extend(str(path) for path in declared_local if isinstance(path, str))
            local_names = sorted(set(local_names))
            managed_hashes = instance.get("installed_file_hashes", {})
            if isinstance(managed_hashes, dict):
                local_names.extend(
                    path for path in old_files
                    if path in managed_hashes and self._file_hashes(root, [path]).get(path) != managed_hashes[path]
                )
            local_names = sorted(set(local_names))
            if local_names and confirm_local_changes is not None and not confirm_local_changes(local_names):
                raise ModrinthPackUpdateError("Update cancelled because local mod changes were not confirmed")
            backup_root.mkdir(parents=True, exist_ok=True)
            self._copy_tree(root, backup)
            journal_data = {
                "provider": metadata.get("provider", instance.get("provider", "modrinth")),
                "instance_id": instance.get("id", ""), "backup": str(backup),
                "archive": str(archive_path), "phase": "backed_up",
                "previous_instance": previous_instance,
            }
            self._durable_tree(backup)
            self._fsync_file(backup_root)
            self._publish_journal(journal, journal_data)
            progress("Backed up current instance", 0, 1)
            if cancel_event is not None and cancel_event.is_set():
                raise ModrinthPackUpdateError("Modrinth pack update cancelled")
            changed_paths = []
            for relative in old_files - set(metadata.get("installed_files", [])):
                destination = _inside(root, _safe_relative_path(relative, label="installed file"))
                if destination.is_file():
                    destination.unlink()
                changed_paths.append(destination)
            for source in sorted(stage.rglob("*")):
                if source.is_file():
                    relative = PurePosixPath(source.relative_to(stage).as_posix())
                    destination = _inside(root, relative)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                    changed_paths.append(destination)
            if cancel_event is not None and cancel_event.is_set():
                raise ModrinthPackUpdateError("Modrinth pack update cancelled")
            self._durable_paths(root, changed_paths)
            instance.update(
                provider=metadata.get("provider", instance.get("provider", "modrinth")), pack_source=str(archive_path),
                game_version=metadata["game_version"], loader=metadata["loader"],
                loader_version=metadata["loader_version"], installed_files=metadata["installed_files"],
                pack_format=metadata["format"], install_state="ready", ready=True,
                install_error="", recovery_backup=str(backup), update_recovery_required=False,
                installed_file_hashes=self._file_hashes(root, metadata.get("installed_files", [])),
            )
            if release_id:
                instance["pack_release_id"] = release_id
            return {"metadata": metadata, "backup": str(backup), "local_files": local_names}
        except Exception as error:
            if backup.is_dir():
                try:
                    self._copy_tree(backup, root)
                    self._durable_tree(root)
                except OSError as recovery_error:
                    raise ModrinthPackUpdateError(
                        f"Update failed and recovery failed: {recovery_error}"
                    ) from error
                self._durable_unlink(journal)
            if isinstance(error, ModrinthPackError):
                raise
            raise ModrinthPackUpdateError(f"Modrinth pack update failed: {error}") from error
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def recover(self, instance: dict, minecraft_directory: Path | str) -> None:
        backup = Path(str(instance.get("recovery_backup", "")))
        root = Path(minecraft_directory)
        journal = root.parent / "update-journal.json"
        if instance.get("update_recovery_required") and not journal.is_file():
            instance["install_state"] = "ready"
            instance["ready"] = True
            instance["install_error"] = ""
            instance["update_recovery_required"] = False
            instance.pop("recovery_backup", None)
            return
        if not backup.is_dir():
            if journal.is_file():
                raise ModrinthPackUpdateError("The recorded Modrinth update backup is unavailable")
            # Cancellation can happen while replacement files are staged,
            # before a backup journal is published. The live tree is intact.
            instance["install_state"] = "ready"
            instance["ready"] = True
            instance["install_error"] = ""
            instance["update_recovery_required"] = False
            return
        try:
            journal_data = json.loads(journal.read_text(encoding="utf-8")) if journal.is_file() else {}
        except (OSError, json.JSONDecodeError):
            journal_data = {}
        self._copy_tree(backup, root)
        self._durable_tree(root)
        previous_instance = journal_data.get("previous_instance") if isinstance(journal_data, dict) else None
        if isinstance(previous_instance, dict):
            instance.clear()
            instance.update(previous_instance)
        instance["install_state"] = "ready"
        instance["ready"] = True
        instance["install_error"] = ""
        instance["update_recovery_required"] = False


class CurseForgeProvider:
    """Small, credentialed adapter for CurseForge file metadata and downloads.

    CurseForge file references are not download URLs.  The API resolves a
    project/file pair to authoritative metadata and a temporary URL, so the
    importer never constructs a CDN URL or treats an unverified replacement
    as the declared file.
    """

    base_url = "https://api.curseforge.com/v1"

    def __init__(self, api_key: str | None = None, *, opener=None) -> None:
        self.api_key = api_key or os.environ.get("CURSEFORGE_API_KEY")
        self.opener = opener or urllib.request.urlopen

    def _request(self, url: str) -> dict:
        if not self.api_key:
            raise CurseForgeAccessError(
                "CurseForge file access requires an API key; configure CURSEFORGE_API_KEY and retry"
            )
        request = urllib.request.Request(url, headers={"x-api-key": self.api_key, "Accept": "application/json"})
        try:
            with self.opener(request, timeout=30) as response:
                value = json.loads(response.read().decode("utf-8"))
        except Exception as error:
            raise CurseForgePackError(f"CurseForge provider access failed: {error}") from error
        if not isinstance(value, dict) or value.get("data") is None:
            raise CurseForgePackError("CurseForge provider returned no authoritative file metadata")
        return value["data"]

    def resolve_file(self, project_id: int, file_id: int) -> dict:
        value = self._request(f"{self.base_url}/mods/{project_id}/files/{file_id}/download-url")
        if not isinstance(value, str) or not value.startswith("https://"):
            raise CurseForgePackError("CurseForge returned an invalid file download URL")
        metadata = self._request(f"{self.base_url}/mods/{project_id}/files/{file_id}")
        if not isinstance(metadata, dict):
            raise CurseForgePackError("CurseForge returned invalid file metadata")
        metadata = dict(metadata)
        metadata["url"] = value
        metadata["project_id"] = project_id
        metadata["file_id"] = file_id
        return metadata

    def download_file(self, metadata: Mapping[str, object]) -> bytes:
        url = metadata.get("url")
        if not isinstance(url, str) or urlparse(url).scheme.lower() != "https":
            raise CurseForgePackError("CurseForge returned an invalid secure file URL")
        if not self.api_key:
            raise CurseForgeAccessError(
                "CurseForge file access requires an API key; configure CURSEFORGE_API_KEY and retry"
            )
        request = urllib.request.Request(url, headers={"x-api-key": self.api_key})
        try:
            with self.opener(request, timeout=30) as response:
                return response.read()
        except Exception as error:
            raise CurseForgePackError(f"CurseForge file download failed: {error}") from error


class CurseForgePackImporter:
    """Safely import a CurseForge exported Minecraft pack.

    Missing provider files produce a persisted incomplete result.  This lets
    the launcher explain the missing artifact and offer a permitted retry or
    player replacement without enabling Play prematurely.
    """

    def __init__(self, provider=None, loader_resolver: LoaderResolver | None = None) -> None:
        self.provider = provider or CurseForgeProvider()
        self.loader_resolver = loader_resolver

    @staticmethod
    def _manifest(archive: zipfile.ZipFile) -> dict:
        names = archive.namelist()
        if "manifest.json" not in names:
            raise CurseForgePackError("This archive has no root manifest.json CurseForge manifest")
        try:
            value = json.loads(archive.read("manifest.json").decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CurseForgePackError(f"The CurseForge manifest is invalid: {error}") from error
        if not isinstance(value, dict) or value.get("manifestType") != "minecraftModpack":
            raise CurseForgePackError("This archive is not a CurseForge Minecraft exported pack")
        if value.get("manifestVersion") != 1 or not isinstance(value.get("minecraft"), dict):
            raise CurseForgePackError("The CurseForge manifest version or Minecraft section is invalid")
        minecraft = value["minecraft"]
        if not isinstance(minecraft.get("version"), str) or not minecraft["version"]:
            raise CurseForgePackError("The CurseForge manifest does not declare a Minecraft version")
        if not isinstance(value.get("files"), list) or not isinstance(value.get("overrides"), str):
            raise CurseForgePackError("The CurseForge manifest is missing files or overrides")
        try:
            _safe_relative_path(value["overrides"], label="overrides directory")
        except ModrinthPackError as error:
            raise CurseForgePackError(str(error)) from error
        return value

    @staticmethod
    def _loader(manifest: dict) -> tuple[str, str, str]:
        loaders = manifest["minecraft"].get("modLoaders")
        if not isinstance(loaders, list) or len(loaders) != 1 or not isinstance(loaders[0], dict):
            raise CurseForgePackError("The CurseForge pack must declare exactly one supported mod loader")
        identifier = loaders[0].get("id")
        if not isinstance(identifier, str) or "-" not in identifier:
            raise CurseForgePackError("The CurseForge pack declares an invalid mod loader")
        for prefix, name in (("neoforge-", "neoforge"), ("forge-", "forge"),
                             ("fabric-loader-", "fabric"), ("fabric-", "fabric"),
                             ("quilt-loader-", "quilt"), ("quilt-", "quilt")):
            if identifier.startswith(prefix) and identifier[len(prefix):]:
                return name, identifier[len(prefix):], name
        raise CurseForgePackError(f"CurseForge loader {identifier!r} is not supported")

    @staticmethod
    def _copy_overrides(archive: zipfile.ZipFile, stage: Path, prefix: str) -> list[str]:
        installed = []
        for member in sorted(archive.namelist()):
            if member == prefix or not member.startswith(prefix + "/"):
                continue
            if member.endswith("/"):
                continue
            relative = _safe_relative_path(member[len(prefix) + 1:], label="override path")
            destination = _inside(stage, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
            installed.append(str(relative))
        return installed

    def _resolve(self, project_id: object, file_id: object) -> dict:
        if isinstance(project_id, bool) or not isinstance(project_id, int) or isinstance(file_id, bool) or not isinstance(file_id, int):
            raise CurseForgePackError("CurseForge file references must contain numeric projectID and fileID")
        resolver = getattr(self.provider, "resolve_file", None)
        if not callable(resolver):
            raise CurseForgeAccessError("No permitted CurseForge file provider is configured; retry with provider access")
        metadata = resolver(project_id, file_id)
        if not isinstance(metadata, dict) or not isinstance(metadata.get("url"), str):
            raise CurseForgePackError("CurseForge returned incomplete authoritative file metadata")
        return metadata

    def _download(self, metadata: Mapping[str, object]) -> bytes:
        downloader = getattr(self.provider, "download_file", None)
        if not callable(downloader):
            raise CurseForgeAccessError("No permitted CurseForge downloader is configured; retry with provider access")
        content = downloader(metadata)
        if not isinstance(content, bytes):
            raise CurseForgePackError("CurseForge provider returned an invalid file body")
        return content

    @staticmethod
    def _verify(content: bytes, metadata: Mapping[str, object]) -> bool:
        sha1 = metadata.get("sha1") or metadata.get("hash")
        sha512 = metadata.get("sha512")
        hashes = metadata.get("hashes")
        if isinstance(hashes, list):
            for item in hashes:
                if not isinstance(item, dict) or not isinstance(item.get("value"), str):
                    continue
                algorithm = item.get("algo")
                if algorithm in (1, "1", "sha1"):
                    sha1 = item["value"]
                elif algorithm in (2, "2", "sha512"):
                    sha512 = item["value"]
        if isinstance(sha1, str) and hashlib.sha1(content).hexdigest().lower() != sha1.lower():
            return False
        if isinstance(sha512, str) and hashlib.sha512(content).hexdigest().lower() != sha512.lower():
            return False
        return isinstance(sha1, str) or isinstance(sha512, str)

    def verify_replacement(self, replacement: Path | str, entry: Mapping[str, object]) -> bool:
        metadata = self._resolve(entry.get("projectID"), entry.get("fileID"))
        try:
            content = Path(replacement).read_bytes()
        except OSError as error:
            raise CurseForgePackError(f"Replacement file is unavailable: {error}") from error
        if not self._verify(content, metadata):
            raise CurseForgePackError("Replacement file failed authoritative integrity verification")
        return True

    def prepare_replacements(self, archive_path: Path | str, directory: Path | str) -> dict[tuple[int, int], Path]:
        """Map user-selected files to manifest references after authoritative lookup."""
        root = Path(directory)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                manifest = self._manifest(archive)
        except (OSError, zipfile.BadZipFile) as error:
            raise CurseForgePackError(f"The selected CurseForge archive is invalid: {error}") from error
        replacements = {}
        for entry in manifest["files"]:
            key = (entry.get("projectID"), entry.get("fileID"))
            metadata = self._resolve(*key)
            filename = metadata.get("fileName") or metadata.get("filename")
            if isinstance(filename, str) and (root / filename).is_file():
                replacements[key] = root / filename
        return replacements

    def import_archive(self, archive_path: Path | str, instance_root: Path | str, *, cancel_event=None,
                       on_progress: Progress | None = None, replacements: Mapping[object, Path | str] | None = None) -> dict:
        archive_path = Path(archive_path)
        root = Path(instance_root)
        if not archive_path.is_file():
            raise CurseForgePackError("The selected CurseForge pack file does not exist")
        root.mkdir(parents=True, exist_ok=True)
        progress = on_progress or (lambda *_args: None)
        stage = Path(tempfile.mkdtemp(prefix=".curseforge-", dir=str(root.parent)))
        replacements = replacements or {}
        try:
            with zipfile.ZipFile(archive_path) as archive:
                manifest = self._manifest(archive)
                game, loader_version, loader_id = self._loader(manifest)
                for name in archive.namelist():
                    if not name.endswith("/"):
                        try:
                            _safe_relative_path(name, label="archive entry")
                        except ModrinthPackError as error:
                            raise CurseForgePackError(str(error)) from error
                if self.loader_resolver is None:
                    raise CurseForgePackError(
                        f"{loader_id.title()} {loader_version} cannot be verified for Minecraft {game}"
                    )
                if self.loader_resolver is not None:
                    try:
                        parameters = inspect.signature(self.loader_resolver).parameters
                        positional = [p for p in parameters.values() if p.kind in (
                            inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD
                        )]
                        accepts_loader = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in parameters.values()) or len(positional) >= 3
                        profile = self.loader_resolver(game, loader_id, loader_version) if accepts_loader else self.loader_resolver(game, loader_version)
                    except Exception as error:
                        raise CurseForgePackError(f"{loader_id.title()} {loader_version} is unavailable for Minecraft {game}: {error}") from error
                    if profile is False or profile is None:
                        raise CurseForgePackError(f"{loader_id.title()} {loader_version} is unavailable for Minecraft {game}")
                installed = self._copy_overrides(archive, stage, manifest["overrides"])
                missing = []
                entries = manifest["files"]
                for index, entry in enumerate(entries, 1):
                    if cancel_event is not None and cancel_event.is_set():
                        raise CurseForgePackError("CurseForge pack preparation cancelled")
                    if not isinstance(entry, dict):
                        raise CurseForgePackError("The CurseForge manifest contains an invalid file entry")
                    required = entry.get("required", True) is not False
                    key = (entry.get("projectID"), entry.get("fileID"))
                    try:
                        metadata = self._resolve(*key)
                        replacement = replacements.get(key)
                        content = Path(replacement).read_bytes() if replacement is not None else self._download(metadata)
                        if not self._verify(content, metadata):
                            raise CurseForgePackError("file failed authoritative integrity verification")
                        filename = metadata.get("fileName") or metadata.get("filename")
                        if not isinstance(filename, str) or not filename:
                            filename = f"file-{key[0]}-{key[1]}.jar"
                        filename = _safe_relative_path(filename, label="provider filename").name
                        destination = _inside(stage, PurePosixPath("mods") / filename)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(content)
                        installed.append(str(PurePosixPath("mods") / filename))
                    except (CurseForgeAccessError, CurseForgePackError, OSError) as error:
                        if not required:
                            continue
                        missing.append({"project_id": key[0], "file_id": key[1], "reason": str(error)})
                    progress(f"Preparing CurseForge file {index}", index, len(entries))
            for source in sorted(stage.rglob("*")):
                if source.is_file():
                    relative = PurePosixPath(source.relative_to(stage).as_posix())
                    destination = _inside(root, relative)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
            complete = not missing
            return {
                "provider": "curseforge", "format": "curseforge-export", "game_version": game,
                "loader": loader_id, "loader_version": loader_version, "installed_files": sorted(set(installed)),
                "missing_files": missing, "complete": complete,
                "recovery_action": "Recovery: retry after configuring the CurseForge API key (CURSEFORGE_API_KEY) or provide each missing file for authoritative verification",
                "manifest": manifest,
            }
        except zipfile.BadZipFile as error:
            raise CurseForgePackError(f"The selected CurseForge archive is invalid: {error}") from error
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    import_pack = import_archive
