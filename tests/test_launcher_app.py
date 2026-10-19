import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow, local_identity
from mclauncher.installer import MinecraftPlayer


class FakeInstaller:
    def __init__(self, *, version="1.21.4", error=None):
        self.version = version
        self.error = error
        self.calls = []
        self.observed_versions = []
        self.resolve_calls = 0

    def install(self, instance, minecraft_directory, on_progress):
        self.calls.append((instance["id"], minecraft_directory))
        self.observed_versions.append(instance.get("version"))
        on_progress("Downloading Minecraft", 2, 4)
        if self.error:
            raise RuntimeError(self.error)
        on_progress("Installing managed Java", 4, 4)

    def resolve_version(self):
        self.resolve_calls += 1
        return self.version


class RecoveringInstaller(FakeInstaller):
    def __init__(self, *, version="1.21.4"):
        super().__init__(version=version)
        self.attempt = 0

    def install(self, instance, minecraft_directory, on_progress):
        self.attempt += 1
        super().install(instance, minecraft_directory, on_progress)
        if self.attempt == 1:
            raise RuntimeError("download interrupted")


class FakePlayer:
    def __init__(self, error=None):
        self.error = error
        self.calls = []
        self.process = None
        self.on_finished = None

    def launch(self, instance, minecraft_directory, username, player_uuid, on_started, on_finished, memory_gib=None):
        self.calls.append((instance["id"], minecraft_directory, username, player_uuid))
        if self.error:
            raise RuntimeError(self.error)
        self.process = object()
        self.on_finished = on_finished
        on_started()
        return self.process

    def finish(self, exit_code=0, crashed=False):
        assert self.process is not None
        self.process = None
        self.on_finished(exit_code, crashed)


def wait_for_install(application, window):
    for _ in range(100):
        application.processEvents()
        if window.install_worker is None:
            return
        QTest.qWait(50)


def test_player_can_save_identity_create_instance_and_restore_after_restart(tmp_path):
    application = QApplication.instance() or QApplication([])

    first = LauncherWindow(data_root=tmp_path / "launcher-data")
    first.show()
    first.username_input.setText("Alex")
    first.save_username_button.click()
    first.instance_name_input.setText("Survival")
    first.create_instance_button.click()

    assert first.username_input.text() == "Alex"
    assert first.identity_label.text().startswith("Local player identity:")
    assert first.instance_list.count() == 1
    assert first.instance_list.item(0).text() == "Survival"
    identity = first.identity_label.text()
    first.close()

    second = LauncherWindow(data_root=tmp_path / "launcher-data")
    second.show()
    assert second.username_input.text() == "Alex"
    assert second.identity_label.text() == identity
    assert second.instance_list.count() == 1
    assert second.instance_list.item(0).text() == "Survival"
    second.close()
    application.processEvents()


def test_changed_username_saves_and_warns_without_confirmation(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow(data_root=tmp_path / "launcher-data")
    window.show()
    window.username_input.setText("Alex")
    window.username_input.editingFinished.emit()
    original_identity = window.identity_label.text()

    window.username_input.setText("Sam")
    window.username_input.editingFinished.emit()

    assert window.username_warning.isVisible()
    assert window.store.load()["username"] == "Sam"
    assert window.username_input.text() == "Sam"
    assert window.identity_label.text() == f"Local player identity: {local_identity('Sam')}"
    assert window.identity_label.text() != original_identity
    assert not window.confirm_username_change_button.isVisible()
    window.close()
    application.processEvents()


def test_instance_selection_and_storage_are_launcher_scoped(tmp_path):
    application = QApplication.instance() or QApplication([])
    launcher_root = tmp_path / "launcher-data"
    external_minecraft = tmp_path / ".minecraft"
    external_minecraft.mkdir()
    marker = external_minecraft / "options.txt"
    marker.write_text("existing", encoding="utf-8")

    window = LauncherWindow(data_root=launcher_root)
    window.show()
    window.instance_name_input.setText("Creative")
    window.create_instance_button.click()
    window.instance_name_input.setText("Survival")
    window.create_instance_button.click()
    window.instance_list.setCurrentRow(0)

    assert window.instance_status_label.text() == "Selected instance: Creative"
    assert sorted(path.name for path in (launcher_root / "instances").iterdir())
    assert marker.read_text(encoding="utf-8") == "existing"
    assert not (external_minecraft / "state.json").exists()
    window.close()
    application.processEvents()


def test_player_can_request_install_and_instance_becomes_ready_after_validation(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = FakeInstaller()
    window = LauncherWindow(data_root=tmp_path / "launcher-data", installer=installer)
    window.show()
    window.instance_name_input.setText("Survival")
    window.create_instance_button.click()

    window.install_button.click()
    wait_for_install(application, window)

    assert installer.calls
    assert installer.observed_versions == ["1.21.4"]
    assert window.state["instances"][0]["version"] == "1.21.4"
    assert window.state["instances"][0]["ready"] is True
    assert window.instance_status_label.text() == "Ready: Survival (1.21.4)"
    assert window.install_progress.value() == 4
    window.close()
    application.processEvents()


def test_install_failure_is_readable_and_does_not_mark_instance_ready(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = FakeInstaller(error="managed Java could not be verified")
    window = LauncherWindow(data_root=tmp_path / "launcher-data", installer=installer)
    window.show()
    window.instance_name_input.setText("Survival")
    window.create_instance_button.click()

    window.install_button.click()
    wait_for_install(application, window)

    assert window.state["instances"][0]["ready"] is False
    assert "Installation failed: managed Java could not be verified" in window.instance_status_label.text()
    window.close()
    application.processEvents()


def test_retry_uses_persisted_version_without_resolving_again(tmp_path):
    application = QApplication.instance() or QApplication([])
    first_installer = FakeInstaller(version="1.21.4")
    root = tmp_path / "launcher-data"
    first = LauncherWindow(data_root=root, installer=first_installer)
    first.show()
    first.instance_name_input.setText("Survival")
    first.create_instance_button.click()
    first.install_button.click()
    wait_for_install(application, first)
    first.close()

    retry_installer = FakeInstaller(version="1.22")
    second = LauncherWindow(data_root=root, installer=retry_installer)
    second.show()
    second.install_button.click()
    wait_for_install(application, second)

    assert second.state["instances"][0]["version"] == "1.21.4"
    assert second.state["instances"][0]["ready"] is True
    second.close()
    application.processEvents()


class IsolatedWorldPlayer(FakePlayer):
    """A player seam that records the game data it would expose to Minecraft."""

    def launch(self, instance, minecraft_directory, username, player_uuid, on_started, on_finished, memory_gib=None):
        process = super().launch(
            instance,
            minecraft_directory,
            username,
            player_uuid,
            on_started,
            on_finished,
            memory_gib,
        )
        game_directory = minecraft_directory.parent
        world_name = instance["name"].lower()
        (game_directory / "saves" / world_name).mkdir(parents=True, exist_ok=True)
        (game_directory / "options.txt").write_text(f"{world_name}-settings", encoding="utf-8")
        (game_directory / "screenshots").mkdir(exist_ok=True)
        (game_directory / "screenshots" / f"{world_name}.png").write_bytes(b"screenshot")
        return process


def test_multiple_instances_route_install_and_play_to_selected_isolated_data(tmp_path):
    application = QApplication.instance() or QApplication([])
    installer = FakeInstaller(version="1.21.4")
    player = IsolatedWorldPlayer()
    root = tmp_path / "launcher-data"
    external = tmp_path / ".minecraft"
    external.mkdir()
    external_marker = external / "options.txt"
    external_marker.write_text("keep-me", encoding="utf-8")
    window = LauncherWindow(data_root=root, installer=installer, player=player)
    window.show()
    window.username_input.setText("Alex")
    window.save_username_button.click()
    for name in ("Creative", "Survival"):
        window.instance_name_input.setText(name)
        window.create_instance_button.click()
        window.install_button.click()
        wait_for_install(application, window)

    assert window.instance_list.count() == 2
    instances = {instance["name"]: instance for instance in window.state["instances"]}
    assert {instance["version"] for instance in instances.values()} == {"1.21.4"}

    window.instance_list.setCurrentRow(0)
    window.play_button.click()
    player.finish()
    window.instance_list.setCurrentRow(1)
    window.play_button.click()
    player.finish()

    creative_root = window.store.instance_root(instances["Creative"]["id"])
    survival_root = window.store.instance_root(instances["Survival"]["id"])
    assert creative_root != survival_root
    assert (creative_root / "saves" / "creative").is_dir()
    assert (survival_root / "saves" / "survival").is_dir()
    assert (creative_root / "options.txt").read_text(encoding="utf-8") == "creative-settings"
    assert (survival_root / "options.txt").read_text(encoding="utf-8") == "survival-settings"
    assert (creative_root / "screenshots" / "creative.png").is_file()
    assert (survival_root / "screenshots" / "survival.png").is_file()
    assert external_marker.read_text(encoding="utf-8") == "keep-me"
    window.close()
    application.processEvents()


def test_existing_instance_stays_pinned_when_new_release_is_available(tmp_path):
    application = QApplication.instance() or QApplication([])
    root = tmp_path / "launcher-data"
    first_installer = FakeInstaller(version="1.21.4")
    first = LauncherWindow(data_root=root, installer=first_installer)
    first.show()
    first.instance_name_input.setText("Pinned")
    first.create_instance_button.click()
    first.install_button.click()
    wait_for_install(application, first)
    first.close()

    newer_installer = FakeInstaller(version="1.22.0")
    second = LauncherWindow(data_root=root, installer=newer_installer, player=FakePlayer())
    second.show()
    assert second.state["instances"][0]["version"] == "1.21.4"
    assert newer_installer.resolve_calls == 0
    second.install_button.click()
    wait_for_install(application, second)
    assert second.state["instances"][0]["version"] == "1.21.4"
    assert newer_installer.resolve_calls == 0


def test_failed_install_survives_restart_and_explicit_retry_preserves_player_data(tmp_path):
    application = QApplication.instance() or QApplication([])
    root = tmp_path / "launcher-data"
    first_installer = FakeInstaller(error="download failed")
    first = LauncherWindow(data_root=root, installer=first_installer)
    first.show()
    first.instance_name_input.setText("Survival")
    first.create_instance_button.click()
    instance_id = first.state["instances"][0]["id"]
    worlds = first.store.instance_root(instance_id) / "worlds"
    marker = worlds / "keep.txt"
    marker.write_text("player progress", encoding="utf-8")

    first.install_button.click()
    wait_for_install(application, first)
    assert first.install_button.text() == "Retry installation"
    first.close()

    retry_installer = RecoveringInstaller(version="1.22")
    second = LauncherWindow(data_root=root, installer=retry_installer)
    second.show()
    assert retry_installer.calls == []
    assert second.state["instances"][0]["version"] == "1.21.4"
    assert second.state["instances"][0]["ready"] is False
    assert "download failed" in second.instance_status_label.text()
    assert second.install_button.text() == "Retry installation"
    second.install_button.click()
    wait_for_install(application, second)

    assert retry_installer.resolve_calls == 0
    assert retry_installer.observed_versions == ["1.21.4"]
    assert second.state["instances"][0]["ready"] is False
    assert marker.read_text(encoding="utf-8") == "player progress"
    second.install_button.click()
    wait_for_install(application, second)
    assert second.state["instances"][0]["ready"] is True
    assert marker.read_text(encoding="utf-8") == "player progress"
    second.close()
    application.processEvents()


def test_interrupted_install_is_unready_after_restart_until_retry(tmp_path):
    application = QApplication.instance() or QApplication([])
    root = tmp_path / "launcher-data"
    first_installer = FakeInstaller()
    first = LauncherWindow(data_root=root, installer=first_installer)
    first.show()
    first.instance_name_input.setText("Survival")
    first.create_instance_button.click()
    instance = first.state["instances"][0]
    instance["version"] = "1.21.4"
    instance["ready"] = False
    instance["install_state"] = "installing"
    first.store.save(first.state)
    first.close()

    restarted_installer = FakeInstaller()
    second = LauncherWindow(data_root=root, installer=restarted_installer)
    second.show()
    assert restarted_installer.calls == []
    assert second.state["instances"][0]["ready"] is False
    assert "interrupted" in second.instance_status_label.text().lower()
    assert second.install_button.text() == "Retry installation"
    second.close()
    application.processEvents()


def _ready_window(tmp_path, player):
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow(data_root=tmp_path / "launcher-data", player=player)
    window.show()
    window.username_input.setText("Alex")
    window.save_username_button.click()
    window.instance_name_input.setText("Survival")
    window.create_instance_button.click()
    instance = window.state["instances"][0]
    instance["version"] = "1.21.4"
    instance["ready"] = True
    window.store.save(window.state)
    window._select_instance(window.instance_list.currentItem(), None)
    return application, window


def test_player_launches_ready_instance_offline_with_saved_identity_and_status(tmp_path):
    player = FakePlayer()
    application, window = _ready_window(tmp_path, player)

    window.play_button.click()

    assert len(player.calls) == 1
    instance_id, game_directory, username, player_uuid = player.calls[0]
    assert instance_id == window.state["instances"][0]["id"]
    assert game_directory == window.store.instance_minecraft_root(instance_id)
    assert username == "Alex"
    assert player_uuid == local_identity("Alex")
    assert window.instance_status_label.text() == "Running: Survival"
    assert not window.play_button.isEnabled()
    window.close()
    application.processEvents()


def test_play_rejects_incomplete_instance_with_recovery_message(tmp_path):
    player = FakePlayer(error="Minecraft files are incomplete; install or retry before playing")
    application, window = _ready_window(tmp_path, player)

    window.play_button.click()

    assert window.instance_status_label.text() == (
        "Play failed: Minecraft files are incomplete; install or retry before playing"
    )
    assert window.play_button.isEnabled()
    window.close()
    application.processEvents()


def test_play_prevents_duplicate_launches_while_game_is_running(tmp_path):
    player = FakePlayer()
    application, window = _ready_window(tmp_path, player)

    window.play_button.click()
    window.play_button.click()

    assert len(player.calls) == 1
    assert window.instance_status_label.text() == "Running: Survival"
    window.close()
    application.processEvents()


def test_player_exit_is_reported_and_allows_another_launch(tmp_path):
    player = FakePlayer()
    application, window = _ready_window(tmp_path, player)

    window.play_button.click()
    player.finish()

    assert window.instance_status_label.text() == "Exited: Survival (exit 0)"
    assert window.play_button.isEnabled()
    window.close()
    application.processEvents()


def test_installation_failure_explains_retry_recovery(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow(
        data_root=tmp_path / "launcher-data",
        installer=FakeInstaller(error="managed Java could not be verified"),
    )
    window.show()
    window.instance_name_input.setText("Survival")
    window.create_instance_button.click()
    window.install_button.click()
    wait_for_install(application, window)

    assert "Installation failed" in window.instance_status_label.text()
    assert "Retry installation" in window.install_button.text()
    assert "Retry on Play" in window.diagnostic_hint_label.text()
    window.close()
    application.processEvents()


def test_launch_failure_is_saved_for_diagnostics_and_exported(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    window = _ready_window(tmp_path, FakePlayer(error="Minecraft files are incomplete"))[1]
    output = tmp_path / "launch-failure.log"
    monkeypatch.setattr(
        "mclauncher.app.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(output), "Diagnostic log (*.log)"),
    )

    window.play_button.click()
    window.save_log_button.click()

    assert "Play failed: Minecraft files are incomplete" in window.instance_status_label.text()
    assert "Saved diagnostic log" in window.diagnostic_hint_label.text()
    log = output.read_text(encoding="utf-8")
    assert "Instance: Survival" in log
    assert "Version: 1.21.4" in log
    assert "Minecraft files are incomplete" in log
    window.close()
    application.processEvents()


def test_crash_context_remains_available_after_game_exits(tmp_path, monkeypatch):
    player = FakePlayer()
    application, window = _ready_window(tmp_path, player)
    output = tmp_path / "crash.log"
    monkeypatch.setattr(
        "mclauncher.app.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(output), "Diagnostic log (*.log)"),
    )

    window.play_button.click()
    player.finish(exit_code=1, crashed=True)
    window.save_log_button.click()

    assert "Game crashed: Survival (exit 1)" == window.instance_status_label.text()
    assert "Saved diagnostic log" in window.diagnostic_hint_label.text()
    assert "Game crashed: Survival (exit 1)" in output.read_text(encoding="utf-8")
    window.close()
    application.processEvents()


def test_open_instance_folder_uses_selected_instance_root(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow(data_root=tmp_path / "launcher-data")
    window.show()
    window.instance_name_input.setText("Survival")
    window.create_instance_button.click()
    opened = []
    monkeypatch.setattr("mclauncher.app.QDesktopServices.openUrl", lambda url: opened.append(url) or True)

    window.open_folder_button.click()

    assert len(opened) == 1
    assert opened[0].toLocalFile() == str(window.store.instance_root(window.state["instances"][0]["id"]))
    assert "Opened instance folder" in window.diagnostic_hint_label.text()
    window.close()
    application.processEvents()


def test_diagnostic_export_failure_is_readable(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    window = _ready_window(tmp_path, FakePlayer())[1]
    target = tmp_path / "missing" / "diagnostic.log"
    monkeypatch.setattr(
        "mclauncher.app.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(target), "Diagnostic log (*.log)"),
    )

    window.save_log_button.click()

    assert "Could not save diagnostic log" in window.diagnostic_hint_label.text()
    window.close()
    application.processEvents()


def test_player_build_command_uses_pinned_identity_runtime_and_instance_directory(tmp_path, monkeypatch):
    import minecraft_launcher_lib

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

    command, game_directory = MinecraftPlayer().build_command(
        {"version": version}, minecraft_directory, "Alex", local_identity("Alex")
    )

    assert command == ["java"]
    assert game_directory == tmp_path
    assert captured["options"]["username"] == "Alex"
    assert captured["options"]["uuid"] == local_identity("Alex")
    assert captured["options"]["token"] == ""
    assert captured["options"]["executablePath"] == str(executable)
    assert captured["options"]["gameDirectory"] == str(tmp_path)
