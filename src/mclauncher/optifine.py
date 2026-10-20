"""Prepare a player-selected OptiFine jar for a verified local instance.

OptiFine does not publish an unattended installer contract.  This module only
accepts a local jar and a caller supplied compatibility record gathered from
the official OptiFine downloads table.  It never downloads or scrapes a jar.
"""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping


class OptiFineError(ValueError):
    """The selected artifact cannot be prepared safely."""


class UnsupportedOptiFine(OptiFineError):
    """The official compatibility evidence does not support this setup."""


@dataclass(frozen=True)
class OptiFineCompatibility:
    game_version: str
    optifine_version: str
    forge_version: str | None = None


_VERSION_RE = re.compile(r"(?:OptiFine[_-])?([0-9]+(?:\.[0-9]+){1,2}_[A-Za-z0-9_.-]+)")


def _manifest_value(raw: bytes, key: str) -> str | None:
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if line.lower().startswith(key.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return None


def inspect_optifine_jar(path: Path | str) -> dict[str, str]:
    """Read the identity of an official local OptiFine jar without executing it."""
    jar = Path(path)
    if not jar.is_file() or jar.suffix.lower() != ".jar":
        raise OptiFineError("Choose an existing OptiFine .jar file")
    try:
        with zipfile.ZipFile(jar) as archive:
            names = set(archive.namelist())
            if "net/optifine/Config.class" not in names:
                raise OptiFineError("The selected jar is not an OptiFine client jar")
            manifest = archive.read("META-INF/MANIFEST.MF") if "META-INF/MANIFEST.MF" in names else b""
    except (OSError, zipfile.BadZipFile) as error:
        raise OptiFineError(f"The selected OptiFine jar could not be read: {error}") from error
    version = _manifest_value(manifest, "Implementation-Version") or _manifest_value(manifest, "OptiFine-Version")
    if not version:
        match = _VERSION_RE.search(jar.stem)
        version = match.group(1) if match else None
    if not version:
        raise OptiFineError("The OptiFine jar does not declare an identifiable release")
    return {"path": str(jar), "optifine_version": version}


class OptiFineInstaller:
    """Copy a verified local OptiFine artifact into a vanilla or Forge instance."""

    def __init__(self, compatibility: Mapping[tuple[str, str], OptiFineCompatibility | Mapping] | None = None):
        self.compatibility = dict(compatibility or {})

    def _evidence(self, game: str, optifine_version: str) -> OptiFineCompatibility:
        value = self.compatibility.get((game, optifine_version))
        if isinstance(value, OptiFineCompatibility):
            return value
        if isinstance(value, Mapping):
            return OptiFineCompatibility(
                game_version=game,
                optifine_version=optifine_version,
                forge_version=value.get("forge_version"),
            )
        raise UnsupportedOptiFine(
            f"OptiFine {optifine_version} has no verified compatibility record for Minecraft {game}"
        )

    def prepare(
        self,
        instance: dict,
        minecraft_directory: Path | str,
        jar_path: Path | str,
        on_progress: Callable[[str, int, int], None] | None = None,
        cancel_event=None,
    ) -> dict:
        progress = on_progress or (lambda *_args: None)
        identity = inspect_optifine_jar(jar_path)
        game = instance.get("minecraft_version") or instance.get("version")
        if not isinstance(game, str) or not game:
            raise UnsupportedOptiFine("Install the exact Minecraft version before adding OptiFine")
        evidence = self._evidence(game, identity["optifine_version"])
        loader = instance.get("loader")
        if loader not in (None, "", "forge"):
            raise UnsupportedOptiFine("OptiFine is only supported for standalone vanilla or verified Forge instances")
        if loader == "forge":
            forge_version = instance.get("loader_version")
            if not evidence.forge_version or forge_version != evidence.forge_version:
                raise UnsupportedOptiFine(
                    f"OptiFine {identity['optifine_version']} is not verified for Forge {forge_version or 'this instance'}"
                )
        if cancel_event is not None and cancel_event.is_set():
            raise OptiFineError("OptiFine preparation cancelled")
        root = Path(minecraft_directory)
        root.mkdir(parents=True, exist_ok=True)
        if loader == "forge":
            destination = root / "mods" / Path(jar_path).name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(jar_path, destination)
            launch_version = instance.get("launch_version") or instance.get("version")
        else:
            base_root = root / "versions" / game
            base_json = base_root / f"{game}.json"
            base_jar = base_root / f"{game}.jar"
            if not base_json.is_file() or not base_jar.is_file():
                raise UnsupportedOptiFine("The standalone Minecraft version is not installed")
            launch_version = f"{game}-OptiFine-{identity['optifine_version']}"
            version_root = root / "versions" / launch_version
            version_root.mkdir(parents=True, exist_ok=True)
            profile = json.loads(base_json.read_text(encoding="utf-8"))
            profile.update({"id": launch_version, "inheritsFrom": game})
            (version_root / f"{launch_version}.json").write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
            shutil.copy2(jar_path, version_root / f"{launch_version}.jar")
        progress(f"Installed OptiFine {identity['optifine_version']}", 1, 1)
        instance["optifine_version"] = identity["optifine_version"]
        instance["optifine_path"] = str(Path(jar_path).name)
        instance["launch_version"] = launch_version
        return {"optifine_version": identity["optifine_version"], "game_version": game,
                "loader": loader or "vanilla", "launch_version": launch_version,
                "path": str(Path(jar_path).name)}
