"""Verified Modrinth mod installation for one launcher instance."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Callable

from .modrinth_catalog import ModrinthCatalog, ModrinthCatalogError, ModrinthRelease


Progress = Callable[[str, int, int], None]


class ModrinthModInstallError(ModrinthCatalogError):
    """A selected mod or required dependency cannot be installed safely."""


class ModrinthModInstaller:
    """Resolve, verify, and publish a selected mod and required dependencies."""

    def __init__(self, catalog: ModrinthCatalog | None = None) -> None:
        self.catalog = catalog or ModrinthCatalog()

    @staticmethod
    def _safe_filename(value: str) -> str:
        path = PurePosixPath(value)
        if not value or "\\" in value or path.is_absolute() or len(path.parts) != 1 or path.name in {".", ".."}:
            raise ModrinthModInstallError("Modrinth supplied an unsafe mod filename")
        return path.name

    @staticmethod
    def _verify(content: bytes, release: ModrinthRelease) -> bool:
        return (
            hashlib.sha1(content).hexdigest().lower() == release.file_sha1.lower()
            and hashlib.sha512(content).hexdigest().lower() == release.file_sha512.lower()
        )

    def _dependencies(self, release: ModrinthRelease, *, game_version: str, loader: str) -> list[ModrinthRelease]:
        resolved = [release]
        seen = {release.id}
        index = 0
        while index < len(resolved):
            current = resolved[index]
            index += 1
            for dependency in current.dependencies:
                if dependency.get("dependency_type", "required") != "required":
                    continue
                version_id = dependency.get("version_id")
                if isinstance(version_id, str) and version_id:
                    candidate = self.catalog.release(version_id)
                else:
                    project_id = dependency.get("project_id")
                    if not isinstance(project_id, str) or not project_id:
                        raise ModrinthModInstallError("A required Modrinth dependency has no authoritative release")
                    releases = self.catalog.releases(project_id, game_version=game_version, loader=loader)
                    candidate = next((item for item in releases if game_version in item.game_versions and loader in item.loaders), None)
                    if candidate is None:
                        raise ModrinthModInstallError(
                            f"No compatible release is available for required dependency {project_id}"
                        )
                if candidate.id not in seen:
                    seen.add(candidate.id)
                    resolved.append(candidate)
        return resolved

    def install(self, instance: dict, instance_root: Path | str, release: ModrinthRelease,
                *, on_progress: Progress | None = None) -> list[dict]:
        game_version = instance.get("minecraft_version") or instance.get("version")
        loader = instance.get("loader")
        if not isinstance(game_version, str) or not game_version or not isinstance(loader, str) or not loader:
            raise ModrinthModInstallError("Select an instance with a pinned Minecraft version and loader first")
        if game_version not in release.game_versions or loader not in release.loaders:
            raise ModrinthModInstallError(
                f"{release.name} is not compatible with Minecraft {game_version} and {loader}"
            )
        releases = self._dependencies(release, game_version=game_version, loader=loader)
        existing = instance.get("mods", [])
        existing_projects = {str(item.get("project_id")) for item in existing if item.get("project_id")}
        selected_projects = {item.project_id for item in releases}
        duplicate = existing_projects & selected_projects
        if duplicate:
            raise ModrinthModInstallError(f"This instance already contains Modrinth mod {sorted(duplicate)[0]}")
        root = Path(instance_root)
        root.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".modrinth-mod-", dir=str(root.parent)))
        progress = on_progress or (lambda *_args: None)
        downloaded: list[tuple[ModrinthRelease, bytes, str]] = []
        try:
            for index, candidate in enumerate(releases, 1):
                if game_version not in candidate.game_versions or loader not in candidate.loaders:
                    raise ModrinthModInstallError(
                        f"Required dependency {candidate.name} is not compatible with Minecraft {game_version} and {loader}"
                    )
                content = self.catalog.download_release(candidate)
                if not isinstance(content, bytes) or not self._verify(content, candidate):
                    raise ModrinthModInstallError(f"Integrity verification failed for {candidate.file_name}")
                filename = self._safe_filename(candidate.file_name)
                destination = stage / filename
                if destination.exists():
                    raise ModrinthModInstallError(f"Competing mod filename {filename} was selected")
                destination.write_bytes(content)
                downloaded.append((candidate, content, filename))
                progress(f"Preparing {filename}", index, len(releases))
            mods_dir = root / "mods"
            mods_dir.mkdir(parents=True, exist_ok=True)
            if any((mods_dir / filename).exists() for _candidate, _content, filename in downloaded):
                raise ModrinthModInstallError("This instance already contains a mod with the selected filename")
            entries = []
            for candidate, _content, filename in downloaded:
                destination = mods_dir / filename
                shutil.copy2(stage / filename, destination)
                entries.append({
                    "id": f"modrinth:{candidate.project_id}:{candidate.id}",
                    "project_id": candidate.project_id,
                    "release_id": candidate.id,
                    "name": candidate.name,
                    "version": candidate.version_number,
                    "filename": filename,
                    "path": str(PurePosixPath("mods") / filename),
                    "enabled": True,
                    "source": "modrinth",
                    "metadata_verified": True,
                    "compatible": True,
                    "compatibility_reason": "Modrinth release matches the selected instance game and loader.",
                })
            return entries
        except OSError as error:
            raise ModrinthModInstallError(f"Could not publish Modrinth mods: {error}") from error
        finally:
            shutil.rmtree(stage, ignore_errors=True)

