"""Deterministic, offline fixtures for reviewing the Modpacks and Mods flows.

Run a real window seeded with fixture data (no network, no real installs):

    PYTHONPATH=src:tests .venv/bin/python -m review_fixtures            # interactive
    PYTHONPATH=src:tests .venv/bin/python -m review_fixtures --compact  # 680x420
    QT_QPA_PLATFORM=offscreen PYTHONPATH=src:tests .venv/bin/python -m review_fixtures --capture /tmp/review

In the window:
  * Modpacks: search anything (e.g. "demo") -> three packs; pick one -> release
    list -> "Install as new setup" creates a ready Fabric setup instantly.
  * Instances -> "Survival" -> Manage mods: vanilla notice -> "Switch to Fabric
    Adventure" -> search anything (e.g. "sodium") -> pick a mod -> "Add mod" writes a
    verified jar into that setup's mods folder.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from mclauncher.modrinth_catalog import ModrinthRelease
from mclauncher.modrinth_mods import ModrinthModInstaller
from mclauncher.persistence import LauncherStore

VERSIONS = ["1.21.11", "1.21.8", "1.21.4", "1.20.1", "1.19.4"]
LONG_NAME = "Weekend Survival With Friends — Extremely Long Setup Name For Layout Checks"

PACKS = [
    {"project_id": "pack-demo", "title": "Demo Adventure Pack", "author": "fixtures",
     "downloads": 128_400, "description": "Exploration, quests and a few quality-of-life mods."},
    {"project_id": "pack-light", "title": "Lightweight Performance", "author": "fixtures",
     "downloads": 9_870, "description": "Sodium, Lithium and friends for older laptops."},
    {"project_id": "pack-long", "title": "An Unusually Long Modpack Title That Should Elide Cleanly In Narrow Lists",
     "author": "a-very-long-author-name", "downloads": 42,
     "description": "Checks text elision and tooltips in the results list."},
]
MODS = [
    {"project_id": "mod-sodium", "title": "Sodium (fixture)", "author": "fixtures", "downloads": 1_000_000,
     "description": "Rendering speed-ups."},
    {"project_id": "mod-minimap", "title": "Mini Map (fixture)", "author": "fixtures", "downloads": 5_300,
     "description": "A tiny map in the corner."},
]


def _payload(project_id: str) -> bytes:
    return f"fixture jar for {project_id}".encode()


class FixtureCatalog:
    """Stands in for ModrinthCatalog: same method names, canned answers, records calls."""

    def __init__(self):
        self.calls: list[tuple] = []

    # Modpacks page -------------------------------------------------------
    def search(self, query):
        self.calls.append(("search", query))
        return [dict(pack) for pack in PACKS]

    def project(self, project_id):
        pack = next(p for p in PACKS + MODS if p["project_id"] == project_id)
        return {"id": project_id, **pack}

    # Mods page -----------------------------------------------------------
    def search_mods(self, query, *, game_version, loader):
        self.calls.append(("search_mods", query, game_version, loader))
        return [dict(mod) for mod in MODS]

    # Shared ----------------------------------------------------------------
    def releases(self, project_id, *, game_version="", loader=""):
        self.calls.append(("releases", project_id, game_version, loader))
        if project_id.startswith("pack-"):
            return [
                ModrinthRelease(f"{project_id}-2", project_id, "2.0.0", "2.0.0", ("1.21.4",), ("fabric",),
                                f"https://cdn.example.invalid/{project_id}-2.mrpack", f"{project_id}-2.mrpack", "sha1", "sha512"),
                ModrinthRelease(f"{project_id}-1", project_id, "1.0.0", "1.0.0", ("1.20.1",), ("fabric",),
                                f"https://cdn.example.invalid/{project_id}-1.mrpack", f"{project_id}-1.mrpack", "sha1", "sha512"),
            ]
        payload = _payload(project_id)
        version = game_version or "1.20.1"
        return [ModrinthRelease(
            f"{project_id}-r1", project_id, f"{project_id} 1.0", "1.0", (version,), (loader or "fabric",),
            f"https://cdn.example.invalid/{project_id}.jar", f"{project_id}.jar",
            hashlib.sha1(payload).hexdigest(), hashlib.sha512(payload).hexdigest(),
        )]

    def download_release(self, release):
        self.calls.append(("download", release.id))
        if release.project_id.startswith("mod-"):
            return _payload(release.project_id)
        return b"fixture mrpack"


class FixtureImporter:
    def import_archive(self, archive, destination, *, on_progress=None):
        return {"format": "mrpack", "game_version": "1.21.4", "loader": "fabric",
                "loader_version": "0.16.9", "installed_files": []}


class FixtureInstaller:
    """Pretends every install succeeds instantly."""

    def discover_versions(self):
        return list(VERSIONS)

    def resolve_version(self):
        return VERSIONS[0]

    def install_modpack(self, instance, directory, metadata, on_progress):
        instance["version"] = "1.21.4-fabric-0.16.9"

    def install(self, instance, directory, on_progress=None, *args, **kwargs):
        instance["ready"] = True


class FixturePlayer:
    def is_ready(self, instance, directory):
        return bool(instance.get("ready") or instance.get("pack_release_id"))

    def launch(self, instance, directory, username, player_uuid, on_started, on_finished, memory_gib=None):
        on_started()
        on_finished(0, False)
        return object()


def seed_state(root: Path, *, long_name: bool = True) -> LauncherStore:
    """Write a returning-player state: vanilla, Fabric and (optionally) a long-named setup."""
    store = LauncherStore(root)
    state = store.load()
    state.update(username="Alex", memory_gib=4,
                 selected_instance_id="survival-1218-a1b2c3d4", selected_setup_id="survival-1218-a1b2c3d4")
    state["instances"] = [
        dict(id="survival-1218-a1b2c3d4", name="Survival", version="1.21.8", ready=True),
        dict(id="fabric-1201-b2c3d4e5", name="Fabric Adventure", version="1.20.1-fabric-0.16.9",
             minecraft_version="1.20.1", loader="fabric", loader_version="0.16.9", ready=True, mods=[]),
    ]
    if long_name:
        state["instances"].append(dict(id="long-1218-c3d4e5f6", name=LONG_NAME, version="1.21.8", ready=False))
    for instance in state["instances"]:
        store.create_instance_root(instance["id"])
    store.save(state)
    return store


def make_window(root: Path, *, long_name: bool = True, discover: bool = True):
    """Return (window, catalog). All flows run synchronously because the catalog is injected."""
    from PySide6.QtWidgets import QApplication

    from mclauncher.app import LauncherWindow

    QApplication.instance() or QApplication(sys.argv[:1])
    store = seed_state(root, long_name=long_name)
    catalog = FixtureCatalog()
    window = LauncherWindow(
        data_root=store.root, modrinth_catalog=catalog, mod_installer=ModrinthModInstaller(catalog),
        modpack_importer=FixtureImporter(), installer=FixtureInstaller(), player=FixturePlayer(),
    )
    if discover:
        window._versions_discovered(list(VERSIONS))
    return window, catalog


def _capture(window, app, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)

    def shot(widget, name):
        app.processEvents()
        widget.grab().save(str(out / f"{name}.png"))
        print(out / f"{name}.png")

    for size, suffix in (((920, 560), ""), ((680, 420), "-compact")):
        window.resize(*size)
        window._show_page(2)
        window.modrinth_search_input.setText("demo")
        window._search_modrinth_catalog()
        window.modrinth_pack_list.setCurrentRow(0)
        shot(window, f"modpacks-results{suffix}")
        window.instance_list.setCurrentRow(0)
        window._show_page(3)
        shot(window, f"mods-vanilla{suffix}")
        window.mods_switch_setup_button.click()
        window.mod_search_input.setText("sodium")
        window._search_modrinth_mods()
        window.mod_search_results.setCurrentRow(0)
        shot(window, f"mods-results{suffix}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capture", type=Path, help="write PNGs of the seeded flows and exit")
    parser.add_argument("--compact", action="store_true", help="open at the 680x420 minimum")
    parser.add_argument("--data", type=Path, help="keep fixture data here instead of a temp dir")
    args = parser.parse_args(argv)

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    with TemporaryDirectory() as temp:
        root = args.data or Path(temp) / "review"
        window, _catalog = make_window(root)
        window.show()
        if args.capture:
            _capture(window, app, args.capture)
            window.close()
            return 0
        if args.compact:
            window.resize(680, 420)
        return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
