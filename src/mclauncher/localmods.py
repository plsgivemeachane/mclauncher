"""Inspection and safe materialisation of local Minecraft mod JARs."""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path


def _version_tuple(value: str) -> tuple[int, ...] | None:
    match = re.match(r"^(\d+(?:\.\d+)*)(?:[-+].*)?$", value.strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def _matches_version(actual: str, requirement: object) -> bool | None:
    if not isinstance(requirement, str) or not requirement.strip():
        return None
    requirement = requirement.strip()
    if requirement in {"*", ">=0"}:
        return True
    wanted = _version_tuple(actual)
    if wanted is None:
        return actual == requirement
    for expression in requirement.split(","):
        expression = expression.strip()
        operator = "=="
        for candidate in (">=", "<=", ">", "<", "=", "~"):
            if expression.startswith(candidate):
                operator, expression = candidate, expression[len(candidate):].strip()
                break
        expected = _version_tuple(expression)
        if expected is None:
            if expression != actual:
                return False
            continue
        if operator in {"=", "=="} and wanted != expected:
            return False
        if operator == ">=" and wanted < expected:
            return False
        if operator == "<=" and wanted > expected:
            return False
        if operator == ">" and wanted <= expected:
            return False
        if operator == "<" and wanted >= expected:
            return False
        if operator == "~" and wanted[:2] != expected[:2]:
            return False
    return True


def _metadata_from_archive(archive: zipfile.ZipFile) -> tuple[dict, str] | None:
    candidates = (
        ("fabric.mod.json", "fabric"),
        ("quilt.mod.json", "quilt"),
    )
    for name, loader in candidates:
        try:
            data = json.loads(archive.read(name).decode("utf-8"))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        data = data.get("quilt_loader", data) if loader == "quilt" else data
        return data, loader
    for name, loader in (("META-INF/mods.toml", "forge"), ("META-INF/neoforge.mods.toml", "neoforge")):
        try:
            text = archive.read(name).decode("utf-8", errors="replace")
        except KeyError:
            continue
        mod_id = re.search(r"modId\s*=\s*[\"']([^\"']+)", text)
        version = re.search(r"version\s*=\s*[\"']([^\"']+)", text)
        return {"id": mod_id.group(1) if mod_id else Path(name).stem,
                "name": mod_id.group(1) if mod_id else "Unknown mod",
                "version": version.group(1) if version else "unknown",
                "depends": {}}, loader
    return None


def inspect_mod_jar(path: Path | str, *, game_version: str | None, loader: str | None) -> dict:
    """Read supported mod metadata without executing or extracting the JAR."""
    path = Path(path)
    result = {
        "id": path.stem, "name": path.stem, "version": "unknown", "loader": loader or "unknown",
        "metadata_verified": False, "compatible": None,
        "compatibility_reason": "Metadata could not verify compatibility; treat this mod as unverified.",
    }
    try:
        with zipfile.ZipFile(path) as archive:
            found = _metadata_from_archive(archive)
    except (OSError, zipfile.BadZipFile):
        result["compatibility_reason"] = "The selected JAR could not be read; metadata is unverified."
        return result
    if found is None:
        return result
    data, detected_loader = found
    result.update({"id": str(data.get("id", data.get("name", path.stem))),
                   "name": str(data.get("name", data.get("id", path.stem))),
                   "version": str(data.get("version", "unknown")),
                   "loader": detected_loader, "metadata_verified": True})
    depends = data.get("depends", {})
    if not isinstance(depends, dict):
        depends = {}
    game_requirement = depends.get("minecraft")
    loader_requirement = depends.get(f"{loader}loader") or depends.get("loader")
    if game_version and game_requirement is not None and _matches_version(game_version, game_requirement) is False:
        result["compatible"] = False
        result["compatibility_reason"] = f"Known Minecraft version mismatch (requires {game_requirement})."
    elif loader and detected_loader not in {loader, "forge" if loader == "neoforge" else loader}:
        result["compatible"] = False
        result["compatibility_reason"] = f"Known loader mismatch (this mod targets {detected_loader})."
    elif loader_requirement is not None and isinstance(loader_requirement, str) and loader_requirement == "unsupported":
        result["compatible"] = False
        result["compatibility_reason"] = "The mod declares an unsupported loader requirement."
    else:
        result["compatible"] = True
        result["compatibility_reason"] = "Metadata identifies a compatible game and loader."
    return result


def copy_mod_to_instance(source: Path | str, instance_minecraft_root: Path | str, *, enabled: bool = True) -> Path:
    source = Path(source)
    if source.suffix.lower() != ".jar" or not source.is_file():
        raise ValueError("Choose a readable local .jar mod file")
    target_dir = Path(instance_minecraft_root) / ("mods" if enabled else "mods-disabled")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if target.exists():
        target = target_dir / f"{source.stem}-{source.stat().st_size:x}{source.suffix}"
    shutil.copy2(source, target)
    return target
