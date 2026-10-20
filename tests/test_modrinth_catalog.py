import json

import pytest

from mclauncher.modrinth_catalog import ModrinthCatalog, ModrinthCatalogError


def test_catalog_search_details_and_releases_keep_exact_release_identity():
    responses = {
        "/search": {"hits": [{"project_id": "abc", "title": "Demo Pack"}]},
        "/project/abc": {"id": "abc", "slug": "demo", "title": "Demo Pack", "description": "A pack"},
        "/project/abc/version": [{
            "id": "release-2", "project_id": "abc", "name": "2.0", "version_number": "2.0",
            "game_versions": ["1.21.4"], "loaders": ["fabric"],
            "files": [{"url": "https://cdn.modrinth.com/demo.mrpack", "filename": "demo.mrpack",
                       "primary": True, "hashes": {"sha1": "a", "sha512": "b"}}],
        }],
    }

    def request(url):
        return responses[url[url.index("/v2") + 3:].split("?", 1)[0]]

    catalog = ModrinthCatalog(request=request)
    assert catalog.search("demo")[0]["project_id"] == "abc"
    assert catalog.project("abc")["title"] == "Demo Pack"
    release = catalog.releases("abc")[0]
    assert release.id == "release-2"
    assert release.project_id == "abc"
    assert release.file_name == "demo.mrpack"


def test_catalog_rejects_release_without_hashes_or_download():
    with pytest.raises(ModrinthCatalogError, match="hashes"):
        ModrinthCatalog(request=lambda _url: [{"id": "x", "files": [{"url": "https://cdn.modrinth.com/x"}]}]).releases("abc")


def test_catalog_download_uses_selected_release_url():
    seen = []
    catalog = ModrinthCatalog(download=lambda url: seen.append(url) or b"archive")
    release = catalog.__class__.__dict__  # keep the public adapter exercised through API parsing
    parsed = __import__("mclauncher.modrinth_catalog", fromlist=["ModrinthRelease"]).ModrinthRelease(
        "v1", "p1", "Pack", "1", ("1.21.4",), ("fabric",), "https://cdn.modrinth.com/p.mrpack", "p.mrpack", "a", "b"
    )
    assert catalog.download_release(parsed) == b"archive"
    assert seen == [parsed.file_url]
