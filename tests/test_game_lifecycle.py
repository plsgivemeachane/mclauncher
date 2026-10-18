import json
import os
import signal
import subprocess
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mclauncher.app import LauncherWindow
from mclauncher.installer import MinecraftPlayer
from mclauncher.lifecycle import GameProcessRegistry


def test_process_identity_rejects_stale_start_time_and_pid_reuse(tmp_path):
    process = subprocess.Popen(["sleep", "30"])
    try:
        identity = GameProcessRegistry.process_identity(process.pid)
        assert identity is not None
        assert GameProcessRegistry.is_alive(identity)
        stale = dict(identity, start_time=str(int(identity["start_time"]) + 1))
        assert not GameProcessRegistry.is_alive(stale)
        wrong_command = dict(identity, cmdline=["a-different-managed-game"])
        assert not GameProcessRegistry.is_alive(wrong_command)
    finally:
        process.terminate()
        process.wait()


def test_game_lock_allows_only_one_launcher_claim(tmp_path):
    first = GameProcessRegistry(tmp_path)
    second = GameProcessRegistry(tmp_path)
    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


def test_launcher_reopens_running_game_and_clears_record_after_exit(tmp_path):
    application = QApplication.instance() or QApplication([])
    data_root = tmp_path / "launcher-data"
    instance = {"id": "survival-12345678", "name": "Survival", "version": "1.21.4", "ready": True}
    data_root.mkdir()
    (data_root / "state.json").write_text(
        json.dumps({"username": "Alex", "memory_gib": 2, "instances": [instance]}), encoding="utf-8"
    )
    process = subprocess.Popen(["sleep", "30"])
    registry = GameProcessRegistry(data_root)
    try:
        record = registry.remember(process.pid, instance["id"])
        assert record is not None
        window = LauncherWindow(data_root=data_root)
        window.player.is_ready = lambda *_args: True
        assert window.instance_status_label.text() == "Running: Survival"
        assert not window.play_button.isEnabled()

        process.terminate()
        process.wait()
        window._poll_adopted_game()
        assert window.instance_status_label.text() == "Exited: Survival"
        assert window.play_button.isEnabled()
        assert registry.read() is None
        window.close()
        application.processEvents()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()


def test_closing_launcher_keeps_detached_game_alive_across_reopen(tmp_path):
    application = QApplication.instance() or QApplication([])
    player = MinecraftPlayer()
    player.build_command = lambda *_args, **_kwargs: (["sleep", "30"], tmp_path)
    player.is_ready = lambda *_args: True
    _, first = _ready_window(tmp_path, player)

    first.play_button.click()
    pid = first.game_process.processId()
    first.close()
    application.processEvents()
    os.kill(pid, 0)

    second = LauncherWindow(data_root=tmp_path / "launcher-data", player=player)
    assert second.instance_status_label.text() == "Running: Survival"
    assert not second.play_button.isEnabled()
    os.kill(pid, signal.SIGTERM)
    for _ in range(20):
        if not GameProcessRegistry.is_alive(second.game_record):
            break
        time.sleep(0.02)
    second._poll_adopted_game()
    assert second.play_button.isEnabled()
    assert second.instance_status_label.text() == "Exited: Survival"
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
