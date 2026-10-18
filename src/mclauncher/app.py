from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .persistence import LauncherStore
from .installer import MinecraftInstaller, MinecraftPlayer
from .memory import default_memory_gib, validate_memory_gib
from .lifecycle import GameProcessRegistry


def local_identity(username: str) -> str:
    """Return the stable offline-session identity for a saved username."""
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return str(uuid.UUID(digest[:32]))


class LauncherWindow(QMainWindow):
    def __init__(self, data_root: Path | str | None = None, installer=None, player=None, game_registry=None) -> None:
        super().__init__()
        self.setWindowTitle("Minecraft Launcher")
        self.store = LauncherStore(data_root)
        self.installer = installer or MinecraftInstaller()
        self.player = player or MinecraftPlayer()
        self.install_worker = None
        self.installing_instance = None
        self.game_process = None
        self.game_instance = None
        self.game_record = None
        self.last_diagnostic_message = ""
        self.game_registry = game_registry or GameProcessRegistry(self.store.root)
        self.game_poll_timer = QTimer(self)
        self.game_poll_timer.setInterval(500)
        self.game_poll_timer.timeout.connect(self._poll_adopted_game)
        self.state = self.store.load()
        self._build_ui()
        self._restore_state()

    def _build_ui(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        identity_form = QFormLayout()
        self.username_input = QLineEdit()
        self.username_input.setObjectName("usernameInput")
        self.username_input.setPlaceholderText("Enter a local username")
        self.save_username_button = QPushButton("Save username")
        self.save_username_button.setObjectName("saveUsernameButton")
        self.save_username_button.clicked.connect(self._save_username)
        username_row = QHBoxLayout()
        username_row.addWidget(self.username_input)
        username_row.addWidget(self.save_username_button)
        identity_form.addRow("Local username", username_row)
        self.identity_label = QLabel("Local player identity: not saved")
        self.identity_label.setObjectName("identityLabel")
        self.identity_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        identity_form.addRow("", self.identity_label)
        layout.addLayout(identity_form)

        memory_form = QFormLayout()
        self.memory_input = QLineEdit()
        self.memory_input.setObjectName("memoryInput")
        self.memory_input.setPlaceholderText("Memory in GiB")
        self.save_memory_button = QPushButton("Save memory")
        self.save_memory_button.setObjectName("saveMemoryButton")
        self.save_memory_button.clicked.connect(self._save_memory)
        memory_row = QHBoxLayout()
        memory_row.addWidget(self.memory_input)
        memory_row.addWidget(self.save_memory_button)
        memory_form.addRow("Game memory (GiB)", memory_row)
        self.memory_setting_error = QLabel()
        self.memory_setting_error.setObjectName("memorySettingError")
        self.memory_setting_error.setStyleSheet("color: #b91c1c;")
        self.memory_setting_error.setWordWrap(True)
        self.memory_setting_error.hide()
        memory_form.addRow("", self.memory_setting_error)
        layout.addLayout(memory_form)

        self.username_warning = QLabel("Changing your username may cause worlds or servers to recognize a different player.")
        self.username_warning.setObjectName("usernameWarning")
        self.username_warning.setWordWrap(True)
        self.username_warning.setStyleSheet("color: #9a3412;")
        self.username_warning.hide()
        self.confirm_username_change_button = QPushButton("Confirm username change")
        self.confirm_username_change_button.setObjectName("confirmUsernameChangeButton")
        self.confirm_username_change_button.clicked.connect(self._confirm_username_change)
        self.confirm_username_change_button.hide()
        layout.addWidget(self.username_warning)
        layout.addWidget(self.confirm_username_change_button)

        layout.addWidget(QLabel("Instances"))
        self.instance_list = QListWidget()
        self.instance_list.setObjectName("instanceList")
        self.instance_list.currentItemChanged.connect(self._select_instance)
        layout.addWidget(self.instance_list)
        instance_row = QHBoxLayout()
        self.instance_name_input = QLineEdit()
        self.instance_name_input.setObjectName("instanceNameInput")
        self.instance_name_input.setPlaceholderText("Name a new instance")
        self.create_instance_button = QPushButton("Create instance")
        self.create_instance_button.setObjectName("createInstanceButton")
        self.create_instance_button.clicked.connect(self._create_instance)
        instance_row.addWidget(self.instance_name_input)
        instance_row.addWidget(self.create_instance_button)
        layout.addLayout(instance_row)
        self.instance_status_label = QLabel("No instance selected")
        self.instance_status_label.setObjectName("instanceStatusLabel")
        self.instance_status_label.setWordWrap(True)
        layout.addWidget(self.instance_status_label)
        self.diagnostic_hint_label = QLabel()
        self.diagnostic_hint_label.setObjectName("diagnosticHintLabel")
        self.diagnostic_hint_label.setWordWrap(True)
        self.diagnostic_hint_label.setStyleSheet("color: #475569;")
        layout.addWidget(self.diagnostic_hint_label)
        diagnostics_row = QHBoxLayout()
        self.open_folder_button = QPushButton("Open instance folder")
        self.open_folder_button.setObjectName("openFolderButton")
        self.open_folder_button.clicked.connect(self._open_instance_folder)
        self.open_folder_button.setEnabled(False)
        diagnostics_row.addWidget(self.open_folder_button)
        self.save_log_button = QPushButton("Save diagnostic log")
        self.save_log_button.setObjectName("saveDiagnosticLogButton")
        self.save_log_button.clicked.connect(self._save_diagnostic_log)
        self.save_log_button.setEnabled(False)
        diagnostics_row.addWidget(self.save_log_button)
        layout.addLayout(diagnostics_row)
        self.install_button = QPushButton("Install Minecraft")
        self.install_button.setObjectName("installButton")
        self.install_button.clicked.connect(self._install_selected_instance)
        layout.addWidget(self.install_button)
        self.install_progress = QProgressBar()
        self.install_progress.setObjectName("installProgress")
        self.install_progress.setRange(0, 100)
        layout.addWidget(self.install_progress)
        self.play_button = QPushButton("Play")
        self.play_button.setObjectName("playButton")
        self.play_button.clicked.connect(self._play_selected_instance)
        self.play_button.setEnabled(False)
        layout.addWidget(self.play_button)
        self.setCentralWidget(root)

    def _restore_state(self) -> None:
        if "memory_gib" not in self.state:
            self.state["memory_gib"] = default_memory_gib()
            self.store.save(self.state)
        self.memory_input.setText(str(self.state["memory_gib"]))
        username = str(self.state.get("username", ""))
        self.username_input.setText(username)
        self._update_identity(username)
        state_changed = False
        for instance in self.state.get("instances", []):
            if isinstance(instance, dict) and instance.get("name") and instance.get("id"):
                if instance.get("install_state") == "installing":
                    instance["install_state"] = "interrupted"
                    instance["ready"] = False
                    instance["install_error"] = "Installation interrupted; retry to continue"
                    state_changed = True
                self._add_instance_item(instance)
        if state_changed:
            self.store.save(self.state)
        if self.instance_list.count():
            self.instance_list.setCurrentRow(0)
        self._restore_running_game()

    def _restore_running_game(self) -> None:
        acquired = self.game_registry.acquire()
        record = self.game_registry.adopt() if acquired else self.game_registry.read()
        if record is None or not self.game_registry.is_alive(record):
            if acquired:
                self.game_registry.clear()
                self.game_registry.release()
            return
        self.game_record = record
        self.game_process = record
        instance_id = record.get("instance_id")
        self.game_instance = next(
            (instance for instance in self.state["instances"] if instance.get("id") == instance_id), None
        )
        if self.game_instance is not None:
            self.instance_status_label.setText(f"Running: {self.game_instance['name']}")
        else:
            self.instance_status_label.setText("A Minecraft game is already running")
        self.play_button.setEnabled(False)
        self.game_poll_timer.start()

    def _poll_adopted_game(self) -> None:
        if self.game_record is None or self.game_registry.is_alive(self.game_record):
            return
        self.game_poll_timer.stop()
        self.game_registry.clear()
        self.game_registry.release()
        instance = self.game_instance
        self.game_process = None
        self.game_record = None
        self.game_instance = None
        if instance is not None:
            self.instance_status_label.setText(f"Exited: {instance['name']}")
        self._refresh_play_button()

    def _save_memory(self) -> None:
        memory_gib, error = validate_memory_gib(self.memory_input.text())
        if error:
            self.memory_setting_error.setText(error)
            self.memory_setting_error.show()
            return
        self.state["memory_gib"] = memory_gib
        self.store.save(self.state)
        self.memory_input.setText(str(memory_gib))
        self.memory_setting_error.clear()
        self.memory_setting_error.hide()

    def _update_identity(self, username: str) -> None:
        if username:
            self.identity_label.setText(f"Local player identity: {local_identity(username)}")
        else:
            self.identity_label.setText("Local player identity: not saved")

    def _save_username(self) -> None:
        candidate = self.username_input.text().strip()
        if not candidate or candidate == self.state.get("username", ""):
            if candidate == self.state.get("username", ""):
                self.username_input.setText(candidate)
            return
        if self.state.get("username", ""):
            self.username_warning.show()
            self.confirm_username_change_button.show()
            return
        self._persist_username(candidate)

    def _confirm_username_change(self) -> None:
        candidate = self.username_input.text().strip()
        if candidate:
            self._persist_username(candidate)
        self.username_warning.hide()
        self.confirm_username_change_button.hide()

    def _persist_username(self, username: str) -> None:
        self.state["username"] = username
        self.store.save(self.state)
        self.username_input.setText(username)
        self._update_identity(username)

    def _create_instance(self) -> None:
        name = self.instance_name_input.text().strip()
        if not name or any(instance.get("name") == name for instance in self.state["instances"]):
            return
        instance_id = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "instance"
        instance_id = f"{instance_id}-{uuid.uuid4().hex[:8]}"
        instance = {"id": instance_id, "name": name, "version": None, "ready": False}
        self.state["instances"].append(instance)
        self.store.create_instance_root(instance_id)
        self.store.save(self.state)
        self._add_instance_item(instance)
        self.instance_list.setCurrentRow(self.instance_list.count() - 1)
        self.instance_name_input.clear()

    def _add_instance_item(self, instance: dict) -> None:
        item = QListWidgetItem(str(instance["name"]))
        item.setData(Qt.ItemDataRole.UserRole, instance["id"])
        self.instance_list.addItem(item)

    def _select_instance(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            self.instance_status_label.setText("No instance selected")
            self.diagnostic_hint_label.clear()
            self.open_folder_button.setEnabled(False)
            self.save_log_button.setEnabled(False)
            self.install_button.setEnabled(False)
            self.play_button.setEnabled(False)
            return
        instance = self._selected_instance()
        self.open_folder_button.setEnabled(instance is not None)
        self.save_log_button.setEnabled(instance is not None)
        if instance and instance.get("ready"):
            self.instance_status_label.setText(f"Ready: {current.text()} ({instance.get('version')})")
        elif instance and instance.get("install_error"):
            self.instance_status_label.setText(f"Installation failed: {instance['install_error']}")
            self.diagnostic_hint_label.setText("Install Minecraft again to retry this instance.")
        else:
            self.instance_status_label.setText(f"Selected instance: {current.text()}")
            self.diagnostic_hint_label.setText(str(instance.get("last_event", "")))
        self.install_button.setEnabled(self.install_worker is None)
        self._refresh_install_button()
        self._refresh_play_button()

    def _record_diagnostic(self, instance: dict | None, message: str) -> None:
        self.last_diagnostic_message = message
        if instance is not None:
            instance["last_event"] = message
            instance["last_event_at"] = datetime.now(timezone.utc).isoformat()
            self.store.save(self.state)

    def _open_instance_folder(self) -> None:
        instance = self._selected_instance()
        if instance is None:
            return
        folder = self.store.instance_root(instance["id"])
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self.diagnostic_hint_label.setText(f"Opened instance folder: {folder}")
        else:
            self.diagnostic_hint_label.setText(f"Could not open instance folder: {folder}")

    def _diagnostic_log(self, instance: dict) -> str:
        lines = [
            "Minecraft Launcher diagnostic log",
            "Launcher version: 0.1.0",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            f"Launcher data root: {self.store.root}",
            "",
            f"Instance: {instance.get('name', 'unknown')}",
            f"Instance ID: {instance.get('id', 'unknown')}",
            f"Version: {instance.get('version') or 'not pinned'}",
            f"Instance folder: {self.store.instance_root(instance['id'])}",
            f"Ready: {instance.get('ready', False)}",
            f"Install state: {instance.get('install_state', 'unknown')}",
            f"Installation error: {instance.get('install_error') or 'none'}",
            f"Last event: {instance.get('last_event') or 'none'}",
            f"Last event time: {instance.get('last_event_at') or 'unknown'}",
            "",
            f"Local username: {self.state.get('username') or 'not saved'}",
            f"Local player identity: {local_identity(self.state['username']) if self.state.get('username') else 'not available'}",
            f"Memory (GiB): {self.state.get('memory_gib', 'unknown')}",
        ]
        return "\n".join(lines) + "\n"

    def _save_diagnostic_log(self) -> None:
        instance = self._selected_instance()
        if instance is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save diagnostic log",
            f"mclauncher-{instance.get('id', 'instance')}.log",
            "Diagnostic log (*.log);;Text files (*.txt);;All files (*)",
        )
        if not filename:
            return
        try:
            Path(filename).write_text(self._diagnostic_log(instance), encoding="utf-8")
        except OSError as error:
            self.diagnostic_hint_label.setText(f"Could not save diagnostic log: {error}")
            return
        self.diagnostic_hint_label.setText(f"Saved diagnostic log: {filename}")

    def _selected_instance(self) -> dict | None:
        current = self.instance_list.currentItem()
        if current is None:
            return None
        instance_id = current.data(Qt.ItemDataRole.UserRole)
        return next((instance for instance in self.state["instances"] if instance.get("id") == instance_id), None)

    def _install_selected_instance(self) -> None:
        instance = self._selected_instance()
        if instance is None:
            return
        self.installing_instance = instance
        instance["install_state"] = "installing"
        instance["install_error"] = ""
        instance["ready"] = False
        self.store.save(self.state)
        self.play_button.setEnabled(False)
        self.install_button.setEnabled(False)
        self.install_progress.setValue(0)
        self.instance_status_label.setText(f"Installing {instance['name']}…")
        self.install_worker = InstallWorker(
            self.installer,
            instance,
            self.store.instance_minecraft_root(instance["id"]),
            self._persist_version,
        )
        self.install_worker.progress.connect(self._show_install_progress)
        self.install_worker.succeeded.connect(self._installation_succeeded)
        self.install_worker.failed.connect(self._installation_failed)
        self.install_worker.finished.connect(self._installation_finished)
        self.install_worker.start()

    def _persist_version(self, instance: dict, version: str) -> None:
        instance["version"] = version
        instance["ready"] = False
        instance["install_state"] = "installing"
        self.store.save(self.state)

    def _show_install_progress(self, status: str, progress: int, maximum: int) -> None:
        if status:
            self.instance_status_label.setText(status)
        if maximum >= 0:
            self.install_progress.setMaximum(maximum)
        if progress >= 0:
            self.install_progress.setValue(progress)

    def _installation_succeeded(self) -> None:
        instance = self.installing_instance
        if instance is None:
            return
        instance["ready"] = True
        instance["install_state"] = "ready"
        instance["install_error"] = ""
        self.store.save(self.state)
        self.instance_status_label.setText(f"Ready: {instance['name']} ({instance['version']})")

    def _installation_failed(self, message: str) -> None:
        instance = self.installing_instance
        if instance is not None:
            instance["ready"] = False
            instance["install_state"] = "failed"
            instance["install_error"] = message
            self._record_diagnostic(instance, f"Installation failed: {message}")
        self.instance_status_label.setText(f"Installation failed: {message}")
        self.diagnostic_hint_label.setText("Install Minecraft again to retry this instance.")

    def _installation_finished(self) -> None:
        worker = self.install_worker
        self.install_worker = None
        if worker is not None:
            worker.deleteLater()
        self.installing_instance = None
        self.install_button.setEnabled(self.instance_list.currentItem() is not None)
        self._refresh_install_button()
        self._refresh_play_button()

    def _refresh_install_button(self) -> None:
        instance = self._selected_instance()
        if instance is None:
            self.install_button.setText("Install Minecraft")
        elif instance.get("install_error") or instance.get("install_state") == "interrupted":
            self.install_button.setText("Retry installation")
        else:
            self.install_button.setText("Install Minecraft")

    def _refresh_play_button(self) -> None:
        instance = self._selected_instance()
        self.play_button.setEnabled(bool(instance and instance.get("ready") and self.game_process is None))

    def _play_selected_instance(self) -> None:
        instance = self._selected_instance()
        if instance is None:
            return
        if self.game_process is not None:
            self.instance_status_label.setText("A Minecraft game is already running")
            return
        if not self.game_registry.acquire():
            self.instance_status_label.setText("A Minecraft game is already running")
            self.game_process = self.game_registry.read() or object()
            self.play_button.setEnabled(False)
            return
        username = str(self.state.get("username", "")).strip()
        if not username:
            self.game_registry.release()
            self.instance_status_label.setText("Play failed: save a local username first")
            return
        if not instance.get("ready"):
            self.game_registry.release()
            self.instance_status_label.setText("Play failed: install Minecraft before playing")
            return
        memory_gib, memory_error = validate_memory_gib(self.memory_input.text())
        if memory_error:
            self.game_registry.release()
            self.instance_status_label.setText(f"Play failed: {memory_error}")
            self.memory_setting_error.setText(memory_error)
            self.memory_setting_error.show()
            return
        if memory_gib != self.state.get("memory_gib"):
            self.state["memory_gib"] = memory_gib
            self.store.save(self.state)
        self.play_button.setEnabled(False)
        self.instance_status_label.setText(f"Starting {instance['name']}…")
        try:
            launch_args = (
                instance,
                self.store.instance_minecraft_root(instance["id"]),
                username,
                local_identity(username),
                lambda: self._game_started(instance),
                lambda exit_code, crashed: self._game_finished(instance, exit_code, crashed),
            )
            try:
                process = self.player.launch(*launch_args, memory_gib=memory_gib)
            except TypeError as error:
                if "memory_gib" not in str(error):
                    raise
                process = self.player.launch(*launch_args)
        except Exception as error:
            self.game_registry.release()
            self.instance_status_label.setText(f"Play failed: {error}")
            self._record_diagnostic(instance, f"Play failed: {error}")
            self.diagnostic_hint_label.setText("Install or retry this instance, then try Play again.")
            self._refresh_play_button()
            return
        self.game_process = process
        self.game_instance = instance
        process_id = process.processId() if hasattr(process, "processId") else None
        if process_id:
            self.game_record = self.game_registry.remember(process_id, instance["id"])
            if self.game_record is None:
                self.game_registry.release()
                self.instance_status_label.setText("Play failed: could not verify the Minecraft process")
                self.game_process = None
                self.game_instance = None
                self._refresh_play_button()
                return
        if self.instance_status_label.text().startswith("Starting"):
            self._game_started(instance)

    def _game_started(self, instance: dict) -> None:
        self.instance_status_label.setText(f"Running: {instance['name']}")
        self.play_button.setEnabled(False)

    def _game_finished(self, instance: dict, exit_code: int, crashed: bool) -> None:
        if self.game_instance is not None and self.game_instance.get("id") != instance.get("id"):
            return
        self.game_process = None
        self.game_instance = None
        self.game_record = None
        self.game_registry.clear()
        self.game_registry.release()
        if crashed:
            self.instance_status_label.setText(f"Game crashed: {instance['name']} (exit {exit_code})")
            self.diagnostic_hint_label.setText("Save a diagnostic log or open the instance folder before relaunching.")
        else:
            self.instance_status_label.setText(f"Exited: {instance['name']} (exit {exit_code})")
            self.diagnostic_hint_label.setText("Save a diagnostic log if you need help with this game exit.")
        self._record_diagnostic(instance, self.instance_status_label.text())
        self._refresh_play_button()

    def closeEvent(self, event) -> None:
        if self.install_worker is not None and self.installing_instance is not None:
            self.installing_instance["ready"] = False
            self.installing_instance["install_state"] = "installing"
            self.installing_instance["install_error"] = "Installation interrupted; retry to continue"
        self.store.save(self.state)
        self.game_poll_timer.stop()
        if self.game_process is None:
            self.game_registry.clear()
        self.game_registry.release()
        super().closeEvent(event)


class InstallWorker(QThread):
    progress = Signal(str, int, int)
    succeeded = Signal()
    failed = Signal(str)

    def __init__(self, installer, instance: dict, minecraft_directory: Path, persist_version) -> None:
        super().__init__()
        self.installer = installer
        self.instance = instance
        self.minecraft_directory = minecraft_directory
        self.persist_version = persist_version

    def run(self) -> None:
        try:
            if not self.instance.get("version"):
                self.persist_version(self.instance, self.installer.resolve_version())
            self.installer.install(
                self.instance,
                self.minecraft_directory,
                self.progress.emit,
            )
        except Exception as error:
            self.failed.emit(str(error) or "unknown installation error")
        else:
            self.succeeded.emit()


def main() -> int:
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
