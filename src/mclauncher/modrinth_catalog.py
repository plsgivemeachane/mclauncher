"""Small, injectable adapter for the public Modrinth project API."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class ModrinthCatalogError(RuntimeError):
    """The catalog could not return a usable response."""


@dataclass(frozen=True)
class ModrinthRelease:
    id: str
    project_id: str
    name: str
    version_number: str
    game_versions: tuple[str, ...]
    loaders: tuple[str, ...]
    file_url: str
    file_name: str
    file_sha1: str
    file_sha512: str

    @classmethod
    def from_api(cls, value: dict[str, Any], project_id: str = "") -> "ModrinthRelease":
        files = value.get("files")
        if not isinstance(files, list) or not files:
            raise ModrinthCatalogError("The selected Modrinth release has no downloadable file")
        primary = next((file for file in files if isinstance(file, dict) and file.get("primary")), files[0])
        if not isinstance(primary, dict):
            raise ModrinthCatalogError("The selected Modrinth release has an invalid file")
        hashes = primary.get("hashes") if isinstance(primary.get("hashes"), dict) else {}
        required = (value.get("id"), primary.get("url"), hashes.get("sha1"), hashes.get("sha512"))
        if any(not isinstance(item, str) or not item for item in required):
            raise ModrinthCatalogError("The selected Modrinth release is missing download hashes or URL")
        return cls(
            id=value["id"], project_id=project_id or str(value.get("project_id", "")),
            name=str(value.get("name", value.get("version_number", value["id"]))),
            version_number=str(value.get("version_number", "")),
            game_versions=tuple(str(item) for item in value.get("game_versions", []) if isinstance(item, str)),
            loaders=tuple(str(item) for item in value.get("loaders", []) if isinstance(item, str)),
            file_url=primary["url"], file_name=str(primary.get("filename", "pack.mrpack")),
            file_sha1=hashes["sha1"], file_sha512=hashes["sha512"],
        )


class ModrinthCatalog:
    """Provider boundary used by Browse; all responses can be injected in tests."""

    base_url = "https://api.modrinth.com/v2"

    def __init__(self, request=None, download=None) -> None:
        self._request = request or self._request_json
        self._download = download or self._download_bytes

    @staticmethod
    def _request_json(url: str) -> Any:
        request = urllib.request.Request(url, headers={"User-Agent": "mclauncher/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:
            raise ModrinthCatalogError(f"Modrinth request failed: {error}") from error

    @staticmethod
    def _download_bytes(url: str) -> bytes:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"cdn.modrinth.com", "github.com", "raw.githubusercontent.com", "gitlab.com"}:
            raise ModrinthCatalogError("Modrinth release files must use HTTPS from a supported host")
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read()
        except Exception as error:
            raise ModrinthCatalogError(f"Modrinth release download failed: {error}") from error

    def _get(self, path: str, **params: str) -> Any:
        query = urllib.parse.urlencode({key: value for key, value in params.items() if value})
        return self._request(f"{self.base_url}/{path.lstrip('/')}" + (f"?{query}" if query else ""))

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        value = self._get("search", query=query.strip(), facets='[["project_type:modpack"]]', limit=str(limit))
        hits = value.get("hits") if isinstance(value, dict) else None
        if not isinstance(hits, list):
            raise ModrinthCatalogError("Modrinth returned an invalid search response")
        return [item for item in hits if isinstance(item, dict) and item.get("project_id")]

    def project(self, project_id: str) -> dict[str, Any]:
        value = self._get(f"project/{urllib.parse.quote(project_id, safe='')}")
        if not isinstance(value, dict) or not value.get("id"):
            raise ModrinthCatalogError("Modrinth returned invalid project details")
        return value

    def releases(self, project_id: str, *, game_version: str = "", loader: str = "") -> list[ModrinthRelease]:
        params = {"game_versions": json.dumps([game_version]) if game_version else "", "loaders": json.dumps([loader]) if loader else ""}
        value = self._get(f"project/{urllib.parse.quote(project_id, safe='')}/version", **params)
        if not isinstance(value, list):
            raise ModrinthCatalogError("Modrinth returned an invalid release response")
        return [ModrinthRelease.from_api(item, project_id) for item in value if isinstance(item, dict)]

    def download_release(self, release: ModrinthRelease) -> bytes:
        return self._download(release.file_url)

