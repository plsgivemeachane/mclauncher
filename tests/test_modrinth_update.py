from pathlib import Path
import os
import hashlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from mclauncher.modpack import ModrinthPackUpdateError, ModrinthPackUpdater
from mclauncher.app import LauncherWindow


class FakeImporter:
    def __init__(self, *, fail=False):
        self.fail = fail

    def import_archive(self, archive, destination, *, cancel_event=None, on_progress=None):
        if self.fail:
            raise ValueError("integrity check failed")
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "mods").mkdir()
        (destination / "mods" / "pack-new.jar").write_bytes(b"new")
        (destination / "config").mkdir()
        (destination / "config" / "pack.toml").write_text("new", encoding="utf-8")
        return {
            "provider": "modrinth", "format": "mrpack", "game_version": "1.21.4",
            "loader": "fabric", "loader_version": "0.16.9",
            "installed_files": ["mods/pack-new.jar", "config/pack.toml"],
        }


def _instance(root: Path) -> dict:
    (root / "mods").mkdir(parents=True)
    (root / "mods" / "pack-old.jar").write_bytes(b"old")
    (root / "mods" / "local.jar").write_bytes(b"local")
    (root / "config").mkdir()
    (root / "config" / "local.toml").write_text("local", encoding="utf-8")
    (root / "saves").mkdir()
    (root / "saves" / "world.txt").write_text("world", encoding="utf-8")
    return {
        "id": "pack-1", "provider": "modrinth", "installed_files": ["mods/pack-old.jar"],
        "pack_release_id": "old", "ready": True, "install_state": "ready",
    }


def test_update_backs_up_worlds_warns_local_mods_and_publishes_after_stage(tmp_path):
    root = tmp_path / "minecraft"
    instance = _instance(root)
    updater = ModrinthPackUpdater(FakeImporter())

    result = updater.update(instance, root, tmp_path / "new.mrpack", release_id="new", confirm_local_changes=lambda paths: True)

    backup = Path(result["backup"])
    assert (backup / "saves" / "world.txt").read_text(encoding="utf-8") == "world"
    assert (root / "mods" / "pack-new.jar").read_bytes() == b"new"
    assert not (root / "mods" / "pack-old.jar").exists()
    assert (root / "mods" / "local.jar").read_bytes() == b"local"
    assert instance["pack_release_id"] == "new"
    assert instance["install_state"] == "ready"
    assert result["local_files"] == ["config/local.toml", "mods/local.jar"]


def test_journal_is_durable_before_live_tree_publication(tmp_path):
    root = tmp_path / "minecraft"
    instance = _instance(root)
    updater = ModrinthPackUpdater(FakeImporter())
    observed = {}

    def publish(journal, data):
        observed["old_file_present"] = (root / "mods" / "pack-old.jar").is_file()
        observed["journal_parent"] = journal.parent
        assert Path(data["backup"]).is_dir()
        assert not journal.exists()
        ModrinthPackUpdater._publish_journal(journal, data)

    updater._publish_journal = publish
    updater.update(instance, root, tmp_path / "new.mrpack", confirm_local_changes=lambda paths: True)
    assert observed == {"old_file_present": True, "journal_parent": root.parent}


def test_changed_path_sync_flushes_all_ancestor_directories(tmp_path, monkeypatch):
    root = tmp_path / "minecraft"
    changed = root / "config" / "nested" / "settings.toml"
    changed.parent.mkdir(parents=True)
    changed.write_text("new", encoding="utf-8")
    synced = []
    monkeypatch.setattr(ModrinthPackUpdater, "_fsync_file", staticmethod(synced.append))
    ModrinthPackUpdater._durable_paths(root, [changed])
    assert changed in synced
    assert root / "config" / "nested" in synced
    assert root / "config" in synced
    assert root in synced


def test_recovery_syncs_restored_tree_before_journal_unlink(tmp_path, monkeypatch):
    root = tmp_path / "minecraft"
    instance = _instance(root)
    updater = ModrinthPackUpdater(FakeImporter())
    updater.update(instance, root, tmp_path / "new.mrpack", confirm_local_changes=lambda paths: True)
    order = []
    original_tree = updater._durable_tree
    original_unlink = updater._durable_unlink
    monkeypatch.setattr(updater, "_durable_tree", lambda path: (order.append("sync"), original_tree(path))[1])
    monkeypatch.setattr(updater, "_durable_unlink", lambda path: (order.append("unlink"), original_unlink(path))[1])
    updater.recover(instance, root)
    assert order == ["sync"]
    assert (root.parent / "update-journal.json").is_file()


def test_update_declined_local_warning_does_not_publish(tmp_path):
    root = tmp_path / "minecraft"
    instance = _instance(root)
    updater = ModrinthPackUpdater(FakeImporter())

    with pytest.raises(ModrinthPackUpdateError, match="local mod changes"):
        updater.update(instance, root, tmp_path / "new.mrpack", confirm_local_changes=lambda paths: False)
    assert (root / "mods" / "pack-old.jar").read_bytes() == b"old"
    assert not (root / "mods" / "pack-new.jar").exists()


def test_update_warns_when_managed_config_was_modified(tmp_path):
    root = tmp_path / "minecraft"
    instance = _instance(root)
    instance["installed_files"] = ["mods/pack-old.jar", "config/managed.toml"]
    (root / "config" / "managed.toml").write_text("original", encoding="utf-8")
    instance["installed_file_hashes"] = {
        "mods/pack-old.jar": hashlib.sha512(b"old").hexdigest(),
        "config/managed.toml": hashlib.sha512(b"expected").hexdigest(),
    }
    seen = []
    ModrinthPackUpdater(FakeImporter()).update(
        instance, root, tmp_path / "new.mrpack", confirm_local_changes=lambda paths: seen.extend(paths) or True,
    )
    assert "config/managed.toml" in seen


def test_failure_restores_live_tree_and_recovery_restores_backup(tmp_path):
    root = tmp_path / "minecraft"
    instance = _instance(root)
    updater = ModrinthPackUpdater(FakeImporter())

    def cancel(_paths):
        return True

    updater.update(instance, root, tmp_path / "new.mrpack", confirm_local_changes=cancel)
    assert (root.parent / "update-journal.json").is_file()
    (root / "mods" / "pack-new.jar").write_bytes(b"damaged")
    updater.recover(instance, root)
    assert (root / "mods" / "pack-old.jar").read_bytes() == b"old"
    assert not (root / "mods" / "pack-new.jar").exists()
    assert instance["installed_files"] == ["mods/pack-old.jar"]
    assert (root.parent / "update-journal.json").is_file()


def test_update_journal_survives_reopen_until_recovery(tmp_path):
    root = tmp_path / "minecraft"
    instance = _instance(root)
    updater = ModrinthPackUpdater(FakeImporter())
    updater.update(instance, root, tmp_path / "new.mrpack", confirm_local_changes=lambda paths: True)
    journal = root.parent / "update-journal.json"
    journal.write_text('{"backup": "missing"}\n', encoding="utf-8")
    assert journal.is_file()
    instance["update_recovery_required"] = True
    assert instance["ready"] is True
    updater.recover(instance, root)
    assert journal.is_file()


def test_interrupted_update_without_current_journal_does_not_restore_stale_backup(tmp_path):
    root = tmp_path / "minecraft"
    instance = _instance(root)
    stale = tmp_path / "stale-backup"
    stale.mkdir()
    (stale / "mods").mkdir()
    (stale / "mods" / "wrong.jar").write_bytes(b"wrong")
    instance.update(recovery_backup=str(stale), update_recovery_required=True, install_state="interrupted", ready=False)
    ModrinthPackUpdater(FakeImporter()).recover(instance, root)
    assert (root / "mods" / "pack-old.jar").read_bytes() == b"old"
    assert not (root / "mods" / "wrong.jar").exists()
    assert not instance["update_recovery_required"]


def test_active_instance_and_import_failure_are_refused(tmp_path):
    root = tmp_path / "minecraft"
    instance = _instance(root)
    instance["install_state"] = "installing"
    with pytest.raises(ModrinthPackUpdateError, match="active"):
        ModrinthPackUpdater(FakeImporter()).update(instance, root, tmp_path / "pack.mrpack")

    instance["install_state"] = "ready"
    with pytest.raises(ValueError, match="integrity"):
        ModrinthPackUpdater(FakeImporter(fail=True)).update(instance, root, tmp_path / "pack.mrpack")


def test_window_updates_existing_instance_and_reopens_metadata(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    archive = tmp_path / "replacement.mrpack"
    archive.write_bytes(b"fixture")

    class Updater:
        def update(self, instance, root, selected, **kwargs):
            assert selected == archive
            instance.update(pack_release_id="release-2", install_state="ready", ready=True)
            return {"backup": str(tmp_path / "backup")}

        def recover(self, instance, root):
            raise AssertionError("recovery should not run")

    class Player:
        @staticmethod
        def is_ready(instance, root):
            return True

    monkeypatch.setattr(
        "mclauncher.app.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(archive), "Modrinth packs (*.mrpack)"),
    )
    window = LauncherWindow(data_root=tmp_path / "data", modrinth_updater=Updater(), player=Player())
    window.instance_name_input.setText("Pack")
    window.create_instance_button.click()
    instance = window.state["instances"][0]
    instance.update(provider="modrinth", pack_release_id="release-1", ready=True, install_state="ready")
    events = []
    original_save = window.store.save
    monkeypatch.setattr(window.store, "save", lambda state: (events.append("save"), original_save(state))[1])
    monkeypatch.setattr(ModrinthPackUpdater, "_durable_unlink", staticmethod(lambda path: events.append("unlink")))
    window._update_selected_modrinth_pack()
    assert instance["pack_release_id"] == "release-2"
    assert instance["install_state"] == "ready"
    assert events[-2:] == ["save", "unlink"]
    window.close()
    reopened = LauncherWindow(data_root=tmp_path / "data", modrinth_updater=Updater(), player=Player())
    application.processEvents()
    assert reopened.state["instances"][0]["pack_release_id"] == "release-2"
    reopened.close()


def test_window_recovery_saves_metadata_before_removing_journal(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])

    class Updater:
        def recover(self, instance, root):
            instance.update(ready=True, install_state="ready", update_recovery_required=False)

    window = LauncherWindow(data_root=tmp_path / "data", modrinth_updater=Updater())
    window.instance_name_input.setText("Pack")
    window._create_instance()
    instance = window.state["instances"][0]
    instance.update(provider="modrinth", ready=False, install_state="interrupted", update_recovery_required=True)
    window.store.save(window.state)
    journal = window.store.instance_root(instance["id"]) / "update-journal.json"
    journal.write_text("{}\n", encoding="utf-8")
    events = []
    original_save = window.store.save
    monkeypatch.setattr(window.store, "save", lambda state: (events.append("save"), original_save(state))[1])
    original_unlink = ModrinthPackUpdater._durable_unlink
    monkeypatch.setattr(ModrinthPackUpdater, "_durable_unlink", staticmethod(lambda path: (events.append("unlink"), original_unlink(path))[1]))
    window._recover_selected_modrinth_pack()
    assert events[-2:] == ["save", "unlink"]
    assert not journal.exists()
    window.close()
    application.processEvents()


def test_window_recovery_save_failure_keeps_journal(tmp_path, monkeypatch):
    class Updater:
        def recover(self, instance, root):
            instance.update(ready=True, install_state="ready", update_recovery_required=False)

    window = LauncherWindow(data_root=tmp_path / "data", modrinth_updater=Updater())
    window.instance_name_input.setText("Pack")
    window._create_instance()
    instance = window.state["instances"][0]
    instance.update(provider="modrinth", ready=False, install_state="interrupted", update_recovery_required=True)
    window.store.save(window.state)
    journal = window.store.instance_root(instance["id"]) / "update-journal.json"
    journal.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(window.store, "save", lambda _state: (_ for _ in ()).throw(RuntimeError("save failed")))
    with pytest.raises(RuntimeError, match="save failed"):
        window._recover_selected_modrinth_pack()
    assert journal.exists()
    monkeypatch.undo()
    window.close()
