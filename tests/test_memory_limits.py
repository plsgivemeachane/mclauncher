import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow
from mclauncher.memory import GIB, default_memory_gib, validate_memory_gib


def test_default_memory_policy_is_conservative_for_representative_ram_sizes():
    assert default_memory_gib(4 * GIB) == 1
    assert default_memory_gib(8 * GIB) == 2
    assert default_memory_gib(16 * GIB) == 4
    assert default_memory_gib(64 * GIB) == 8


def test_memory_setting_accepts_whole_gib_within_physical_ram():
    assert validate_memory_gib("4", 16 * GIB) == (4, None)


def test_memory_setting_rejects_invalid_values():
    assert validate_memory_gib("0", 16 * GIB)[0] is None
    assert validate_memory_gib("1.5", 16 * GIB)[0] is None
    assert validate_memory_gib("17", 16 * GIB)[0] is None


def test_memory_setting_persists_and_restores_after_restart(tmp_path):
    application = QApplication.instance() or QApplication([])
    root = tmp_path / "launcher-data"

    first = LauncherWindow(data_root=root)
    first.memory_input.setText("4")
    first.save_memory_button.click()
    assert first.state["memory_gib"] == 4
    first.close()

    second = LauncherWindow(data_root=root)
    assert second.memory_input.text() == "4"
    assert second.state["memory_gib"] == 4
    second.close()
    application.processEvents()


class MemoryRecordingPlayer:
    def __init__(self):
        self.memory_gib = None
        self.calls = 0

    def launch(self, instance, minecraft_directory, username, player_uuid, on_started, on_finished, *, memory_gib):
        self.calls += 1
        self.memory_gib = memory_gib
        on_started()
        return object()


def test_invalid_memory_setting_prevents_launch(tmp_path):
    application = QApplication.instance() or QApplication([])
    player = MemoryRecordingPlayer()
    window = LauncherWindow(data_root=tmp_path / "launcher-data", player=player)
    window.username_input.setText("Alex")
    window.save_username_button.click()
    window.instance_name_input.setText("Survival")
    window.create_instance_button.click()
    instance = window.state["instances"][0]
    instance["version"] = "1.21.4"
    instance["ready"] = True
    window.store.save(window.state)
    window._select_instance(window.instance_list.currentItem(), None)

    window.memory_input.setText("999")
    window.play_button.click()

    assert player.calls == 0
    assert "Memory allocation cannot exceed" in window.instance_status_label.text()
    window.close()
    application.processEvents()


def test_selected_memory_limit_reaches_player_boundary(tmp_path):
    application = QApplication.instance() or QApplication([])
    player = MemoryRecordingPlayer()
    window = LauncherWindow(data_root=tmp_path / "launcher-data", player=player)
    window.username_input.setText("Alex")
    window.save_username_button.click()
    window.instance_name_input.setText("Survival")
    window.create_instance_button.click()
    instance = window.state["instances"][0]
    instance["version"] = "1.21.4"
    instance["ready"] = True
    window.store.save(window.state)
    window._select_instance(window.instance_list.currentItem(), None)

    window.memory_input.setText("4")
    window.play_button.click()

    assert player.memory_gib == 4
    window.close()
    application.processEvents()


def test_player_passes_memory_as_separate_jvm_arguments(tmp_path, monkeypatch):
    import minecraft_launcher_lib
    from mclauncher.installer import MinecraftPlayer

    minecraft_directory = tmp_path / "minecraft"
    version = "1.21.4"
    version_root = minecraft_directory / "versions" / version
    version_root.mkdir(parents=True)
    (version_root / f"{version}.json").write_text("{}", encoding="utf-8")
    (version_root / f"{version}.jar").write_bytes(b"jar")
    executable = tmp_path / "java"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    captured = {}
    monkeypatch.setattr(
        minecraft_launcher_lib.runtime,
        "get_version_runtime_information",
        lambda _version, _directory: {"name": "managed-java"},
    )
    monkeypatch.setattr(
        minecraft_launcher_lib.runtime,
        "get_executable_path",
        lambda _name, _directory: str(executable),
    )
    def fake_get_command(_version, _directory, options):
        captured["options"] = options
        return ["java"]

    monkeypatch.setattr(minecraft_launcher_lib.command, "get_minecraft_command", fake_get_command)

    MinecraftPlayer().build_command(
        {"version": version}, minecraft_directory, "Alex", "uuid", memory_gib=4
    )

    assert captured["options"]["jvmArguments"] == ["-Xmx4G", "-Xms4G"]
