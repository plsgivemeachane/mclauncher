from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, QUrl, Qt, Signal, QPoint
from PySide6.QtGui import QDesktopServices, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
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


class LandscapePanel(QFrame):
    """Small block landscape that keeps the launch surface visually quiet."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("landscapePanel")
        self.setMinimumHeight(120)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        width, height = self.width(), self.height()
        painter.fillRect(self.rect(), "#9bbbaa")
        painter.fillRect(0, int(height * 0.52), width, int(height * 0.48), "#537d68")
        painter.fillRect(0, int(height * 0.69), width, int(height * 0.31), "#416750")
        painter.setPen("#9bbba0")
        painter.setBrush("#7f9d8c")
        painter.drawPolygon([QPoint(0, int(height * .55)), QPoint(int(width * .12), int(height * .34)),
                             QPoint(int(width * .25), int(height * .50)), QPoint(int(width * .39), int(height * .28)),
                             QPoint(int(width * .56), int(height * .52)), QPoint(int(width * .72), int(height * .32)),
                             QPoint(width, int(height * .52)), QPoint(width, int(height * .7)), QPoint(0, int(height * .7))])
        painter.setPen("#5b5840")
        for x, scale in ((50, 1.0), (150, .7), (width - 120, .8), (width - 45, 1.1)):
            trunk = max(5, int(10 * scale))
            painter.drawRect(x - trunk // 2, int(height * .52), trunk, int(height * .25))
            painter.setBrush("#284d3d")
            painter.drawRect(x - int(28 * scale), int(height * .34), int(56 * scale), int(30 * scale))
            painter.drawRect(x - int(20 * scale), int(height * .25), int(40 * scale), int(25 * scale))
        painter.end()


class LauncherWindow(QMainWindow):
    def __init__(self, data_root: Path | str | None = None, installer=None, player=None, game_registry=None) -> None:
        super().__init__()
        self.setWindowTitle("Minecraft Launcher")
        self.store = LauncherStore(data_root)
        self._installer_injected = installer is not None
        self.installer = installer or MinecraftInstaller()
        self.player = player or MinecraftPlayer()
        self.install_worker = None
        self.installing_instance = None
        self.discovery_worker = None
        self._launch_after_prepare = False
        self._operation_instance_id = None
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
        self._start_version_discovery()

    def _build_ui(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame(root)
        header.setObjectName("titleBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(25, 10, 25, 10)
        brand = QLabel("▦  mclauncher", header)
        brand.setObjectName("brandLabel")
        header_layout.addWidget(brand)
        header_layout.addStretch(1)
        self.settings_button = QPushButton("⚙  Settings", header)
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.clicked.connect(self._open_settings)
        header_layout.addWidget(self.settings_button)
        layout.addWidget(header)

        scene = LandscapePanel(root)
        layout.addWidget(scene, 1)

        launch_bar = QFrame(root)
        launch_bar.setObjectName("launchBar")
        launch_layout = QVBoxLayout(launch_bar)
        launch_layout.setContentsMargins(26, 16, 26, 20)
        launch_layout.setSpacing(7)

        self.instance_status_label = QLabel("No saved setup selected", launch_bar)
        self.instance_status_label.setObjectName("instanceStatusLabel")
        self.instance_status_label.setWordWrap(True)
        launch_layout.addWidget(self.instance_status_label)
        self.diagnostic_hint_label = QLabel(launch_bar)
        self.diagnostic_hint_label.setObjectName("diagnosticHintLabel")
        self.diagnostic_hint_label.setWordWrap(True)
        launch_layout.addWidget(self.diagnostic_hint_label)
        self.install_progress = QProgressBar(launch_bar)
        self.install_progress.setObjectName("installProgress")
        self.install_progress.setRange(0, 100)
        self.install_progress.setTextVisible(False)
        self.install_progress.hide()
        launch_layout.addWidget(self.install_progress)

        controls = QGridLayout()
        controls.setHorizontalSpacing(15)
        controls.setVerticalSpacing(5)
        username_label = QLabel("Username", launch_bar)
        username_label.setObjectName("usernameFieldLabel")
        setup_label = QLabel("Saved setup", launch_bar)
        setup_label.setObjectName("setupFieldLabel")
        controls.addWidget(username_label, 0, 0)
        controls.addWidget(setup_label, 0, 1)
        self.username_input = QLineEdit()
        self.username_input.setObjectName("usernameInput")
        self.username_input.setPlaceholderText("Enter a local username")
        self.username_input.setMinimumHeight(47)
        self.username_input.editingFinished.connect(self._save_username)
        controls.addWidget(self.username_input, 1, 0)
        self.setup_selector = QComboBox(launch_bar)
        self.setup_selector.setObjectName("setupSelector")
        self.setup_selector.setMinimumHeight(47)
        self.setup_selector.currentIndexChanged.connect(self._select_setup_from_selector)
        controls.addWidget(self.setup_selector, 1, 1)
        self.play_button = QPushButton("▶  Play", launch_bar)
        self.play_button.setObjectName("playButton")
        self.play_button.setMinimumHeight(47)
        self.play_button.clicked.connect(self._play_selected_instance)
        self.play_button.setEnabled(False)
        controls.addWidget(self.play_button, 1, 2)
        controls.setColumnStretch(0, 1)
        controls.setColumnStretch(1, 1)
        controls.setColumnStretch(2, 0)
        launch_layout.addLayout(controls)
        self.setup_search_input = QLineEdit(launch_bar)
        self.setup_search_input.setObjectName("setupSearchInput")
        self.setup_search_input.setPlaceholderText("Search versions and saved setups")
        self.setup_search_input.setClearButtonEnabled(True)
        self.setup_search_input.setMaximumHeight(32)
        self.setup_search_input.textChanged.connect(self._filter_setup_selector)
        launch_layout.addWidget(self.setup_search_input)
        self.selector_empty_label = QLabel(launch_bar)
        self.selector_empty_label.setObjectName("selectorEmptyLabel")
        self.selector_empty_label.setText("No matching versions or saved setups")
        self.selector_empty_label.hide()
        launch_layout.addWidget(self.selector_empty_label)
        layout.addWidget(launch_bar)

        legacy_panel = QWidget(root)
        legacy_layout = QVBoxLayout(legacy_panel)
        legacy_layout.setContentsMargins(0, 0, 0, 0)
        legacy_panel.hide()

        identity_form = QFormLayout()
        self.save_username_button = QPushButton("Save username")
        self.save_username_button.setObjectName("saveUsernameButton")
        self.save_username_button.clicked.connect(self._save_username)
        username_row = QHBoxLayout()
        username_row.addWidget(self.save_username_button)
        identity_form.addRow("Local username", username_row)
        self.identity_label = QLabel("Local player identity: not saved")
        self.identity_label.setObjectName("identityLabel")
        self.identity_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        identity_form.addRow("", self.identity_label)
        legacy_layout.addLayout(identity_form)

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
        legacy_layout.addLayout(memory_form)

        self.state_recovery_label = QLabel()
        self.state_recovery_label.setObjectName("stateRecoveryLabel")
        self.state_recovery_label.setWordWrap(True)
        self.state_recovery_label.setStyleSheet("color: #b91c1c;")
        self.state_recovery_label.hide()
        self.recover_state_button = QPushButton("Recover defaults after backup")
        self.recover_state_button.setObjectName("recoverStateButton")
        self.recover_state_button.clicked.connect(self._recover_state)
        self.recover_state_button.hide()
        launch_layout.insertWidget(0, self.state_recovery_label)
        launch_layout.insertWidget(1, self.recover_state_button)

        self.username_warning = QLabel("Changing your username may cause worlds or servers to recognize a different player.")
        self.username_warning.setObjectName("usernameWarning")
        self.username_warning.setWordWrap(True)
        self.username_warning.setStyleSheet("color: #9a3412;")
        self.username_warning.hide()
        self.confirm_username_change_button = QPushButton("Confirm username change")
        self.confirm_username_change_button.setObjectName("confirmUsernameChangeButton")
        self.confirm_username_change_button.clicked.connect(self._confirm_username_change)
        self.confirm_username_change_button.hide()
        launch_layout.insertWidget(1, self.username_warning)
        legacy_layout.addWidget(self.confirm_username_change_button)

        self.instance_list = QListWidget()
        self.instance_list.setObjectName("instanceList")
        self.instance_list.currentItemChanged.connect(self._select_instance)
        legacy_layout.addWidget(self.instance_list)
        instance_row = QHBoxLayout()
        self.instance_name_input = QLineEdit()
        self.instance_name_input.setObjectName("instanceNameInput")
        self.instance_name_input.setPlaceholderText("Name a new instance")
        self.create_instance_button = QPushButton("Create instance")
        self.create_instance_button.setObjectName("createInstanceButton")
        self.create_instance_button.clicked.connect(self._create_instance)
        instance_row.addWidget(self.instance_name_input)
        instance_row.addWidget(self.create_instance_button)
        legacy_layout.addLayout(instance_row)
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
        legacy_layout.addLayout(diagnostics_row)
        self.install_button = QPushButton("Install Minecraft")
        self.install_button.setObjectName("installButton")
        self.install_button.clicked.connect(self._install_selected_instance)
        legacy_layout.addWidget(self.install_button)
        layout.addWidget(legacy_panel)
        self.setCentralWidget(root)
        self._apply_compact_theme()

    def _apply_compact_theme(self) -> None:
        self.resize(920, 560)
        self.setMinimumSize(680, 420)
        self.setStyleSheet("""
            QWidget { background: #161b19; color: #eef3e9; }
            QFrame#titleBar { background: #172019; }
            QLabel#brandLabel { color: #c5cfc7; font-size: 15px; font-weight: 650; }
            QFrame#launchBar { background: #1b231e; }
            QLabel#usernameFieldLabel, QLabel#setupFieldLabel { color: #a7b3a9; font-size: 11px; }
            QLabel#instanceStatusLabel { color: #c2d0c4; font-size: 12px; }
            QLabel#diagnosticHintLabel, QLabel#usernameWarning { color: #e7c17a; font-size: 11px; }
            QLineEdit, QComboBox { background: #252e28; color: #eef3e9; border: 1px solid #3b453d; border-radius: 7px; padding: 8px 13px; min-height: 28px; }
            QLabel#selectorEmptyLabel { color: #a7b3a9; font-size: 11px; }
            QLineEdit#setupSearchInput { min-height: 18px; padding: 4px 9px; }
            QPushButton { background: transparent; color: #c7d2c9; border: 1px solid transparent; border-radius: 7px; padding: 8px 12px; }
            QPushButton:hover { background: #ffffff10; border-color: #516052; }
            QPushButton#playButton { background: #a6e175; color: #1c2c16; border-color: #b7eb89; font-weight: 750; min-width: 120px; }
            QPushButton#playButton:disabled { background: #35452f; color: #a9c597; border-color: #53664a; }
            QLineEdit:focus, QComboBox:focus, QPushButton:focus { border: 2px solid #a6e175; }
            QProgressBar { background: #3a473c; border: 0; border-radius: 2px; height: 4px; }
            QProgressBar::chunk { background: #a6e175; }
        """)
        self.instance_list.hide()
        self.save_username_button.hide()
        self.save_memory_button.hide()
        self.identity_label.hide()
        self.memory_input.hide()
        self.memory_setting_error.hide()
        self.username_warning.setStyleSheet("color: #e7c17a;")
        self.confirm_username_change_button.hide()
        self.instance_name_input.hide()
        self.create_instance_button.hide()
        self.install_button.hide()

    def _select_setup_from_selector(self, index: int) -> None:
        if index < 0 or index >= self.setup_selector.count():
            return
        value = self.setup_selector.itemData(index, Qt.ItemDataRole.UserRole)
        if value is None:
            return
        self.setup_selector.setToolTip(self.setup_selector.itemText(index))
        if isinstance(value, str) and value.startswith("version:"):
            version = value.removeprefix("version:")
            self.state["selected_setup_id"] = value
            if not getattr(self, "_restoring_state", False) and not self.store.recovery_required:
                self.store.save(self.state)
            self.instance_list.setCurrentRow(-1)
            self.instance_status_label.setText(f"Minecraft {version} selected")
            self.diagnostic_hint_label.clear()
            self._refresh_play_button()
            return
        selector_row = self.setup_selector.findData(value, Qt.ItemDataRole.UserRole)
        instance_row = next(
            (row for row in range(self.instance_list.count())
             if self.instance_list.item(row).data(Qt.ItemDataRole.UserRole) == value),
            -1,
        )
        if selector_row >= 0 and instance_row >= 0:
            self.instance_list.setCurrentRow(instance_row)
            instance = self.state["instances"][instance_row]
            if not getattr(self, "_restoring_state", False) and not self.store.recovery_required:
                self.state["selected_instance_id"] = instance["id"]
                self.state["selected_setup_id"] = instance["id"]
                self.store.save(self.state)

    def _start_version_discovery(self) -> None:
        if not self._installer_injected and QApplication.platformName() == "offscreen":
            return
        first_use = not self.state.get("instances") and not self.state.get("selected_setup_id")
        self.discovery_worker = VersionDiscoveryWorker(self.installer, select_latest=first_use)
        self.discovery_worker.discovered.connect(self._versions_discovered)
        self.discovery_worker.failed.connect(self._version_discovery_failed)
        self.discovery_worker.finished.connect(self._discovery_finished)
        self.discovery_worker.start()

    def _versions_discovered(self, versions: list) -> None:
        metadata = [
            {"id": entry, "type": "release"} if isinstance(entry, str)
            else {"id": str(entry.get("id", "")), "type": str(entry.get("type", "release"))}
            for entry in versions
        ]
        metadata = [entry for entry in metadata if entry["id"]]
        self.state["available_version_metadata"] = metadata
        self.state["available_versions"] = [entry["id"] for entry in metadata]
        if not self.store.recovery_required:
            self.store.save(self.state)
        selected = self.state.get("selected_setup_id") or self.state.get("selected_instance_id")
        self._rebuild_setup_selector(selected=selected)
        self._refresh_play_button()

    def _version_discovery_failed(self, message: str) -> None:
        self.diagnostic_hint_label.setText(f"Could not discover Minecraft releases: {message}")
        self._refresh_play_button()

    def _discovery_finished(self) -> None:
        worker = self.discovery_worker
        self.discovery_worker = None
        if worker is not None:
            worker.deleteLater()

    def _open_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setModal(True)
        form = QFormLayout(dialog)
        memory = QLineEdit(str(self.state.get("memory_gib", default_memory_gib())), dialog)
        memory.setObjectName("settingsMemoryInput")
        error = QLabel(dialog)
        error.setStyleSheet("color: #ffb4a8;")
        error.setWordWrap(True)
        error.hide()
        form.addRow("Game memory (GiB)", memory)
        form.addRow("", error)
        snapshots = QCheckBox("Show snapshots", dialog)
        snapshots.setChecked(bool(self.state.get("show_snapshots", False)))
        form.addRow("Experimental versions", snapshots)
        open_folder = QPushButton("Open selected setup folder", dialog)
        open_folder.clicked.connect(self._open_instance_folder)
        form.addRow("", open_folder)
        export_log = QPushButton("Export diagnostic log", dialog)
        export_log.clicked.connect(self._save_diagnostic_log)
        form.addRow("", export_log)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        form.addRow(buttons)

        def save_memory() -> None:
            value, message = validate_memory_gib(memory.text())
            if message:
                error.setText(message)
                error.show()
                return
            self.state["memory_gib"] = value
            self.store.save(self.state)
            error.hide()

        def save_snapshots(enabled: bool) -> None:
            self.state["show_snapshots"] = bool(enabled)
            self.store.save(self.state)
            selected = self.state.get("selected_setup_id") or self.state.get("selected_instance_id")
            self._rebuild_setup_selector(selected=selected)

        snapshots.toggled.connect(save_snapshots)

        memory.editingFinished.connect(save_memory)
        dialog.exec()

    def _restore_state(self) -> None:
        self._restoring_state = True
        if self.store.recovery_required:
            self.state_recovery_label.setText(self.store.load_error)
            self.state_recovery_label.show()
            self.recover_state_button.show()
            self.save_username_button.setEnabled(False)
            self.save_memory_button.setEnabled(False)
            self.create_instance_button.setEnabled(False)
            self.install_button.setEnabled(False)
            self.play_button.setEnabled(False)
            self._restoring_state = False
            return
        self.state.setdefault("selected_setup_id", self.state.get("selected_instance_id", ""))
        self.state.setdefault("automatic_instances", {})
        self.state.setdefault("available_versions", [])
        self.state.setdefault("available_version_metadata", [])
        self.state.setdefault("show_snapshots", False)
        if "memory_gib" not in self.state and not self.store.recovery_required:
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
        self._append_cached_versions()
        if not self.state.get("selected_setup_id") and self.state.get("selected_instance_id"):
            self.state["selected_setup_id"] = self.state["selected_instance_id"]
        if not self.state.get("selected_setup_id") and self.state.get("instances"):
            self.state["selected_setup_id"] = self.state["instances"][0].get("id", "")
        if state_changed and not self.store.recovery_required:
            self.store.save(self.state)
        if self.instance_list.count():
            selected_id = self.state.get("selected_instance_id")
            selected_row = next(
                (row for row in range(self.instance_list.count())
                 if self.instance_list.item(row).data(Qt.ItemDataRole.UserRole) == selected_id),
                0,
            )
            self.instance_list.setCurrentRow(selected_row)
            self.setup_selector.setCurrentIndex(selected_row)
        if self.state.get("selected_setup_id"):
            selected_index = self.setup_selector.findData(self.state["selected_setup_id"], Qt.ItemDataRole.UserRole)
            if selected_index >= 0:
                self.setup_selector.setCurrentIndex(selected_index)
        self._restoring_state = False
        self._restore_running_game()

    def _append_cached_versions(self) -> None:
        selected = self.state.get("selected_setup_id") or self.state.get("selected_instance_id")
        self._rebuild_setup_selector(selected=selected)

    def _version_metadata(self) -> list[dict]:
        metadata = self.state.get("available_version_metadata", [])
        if metadata:
            return metadata
        return [{"id": value, "type": "release"} for value in self.state.get("available_versions", [])]

    def _rebuild_setup_selector(self, *, selected: str | None = None) -> None:
        current = selected or self.setup_selector.currentData(Qt.ItemDataRole.UserRole)
        metadata = self._version_metadata()
        instances = self.state.get("instances", [])
        if not metadata and not instances:
            self.setup_selector.blockSignals(True)
            self.setup_selector.clear()
            self.setup_selector.blockSignals(False)
            self.selector_empty_label.hide()
            return
        self.setup_selector.blockSignals(True)
        self.setup_selector.clear()
        self.setup_selector.addItem("Versions", None)
        header = self.setup_selector.model().item(0)
        if header is not None:
            header.setEnabled(False)
        for entry in metadata:
            version = str(entry.get("id", ""))
            if not version:
                continue
            pinned = current == f"version:{version}" or any(
                instance.get("version") == version for instance in instances
            )
            if entry.get("type") != "release" and not self.state.get("show_snapshots", False) and not pinned:
                continue
            marker = "✓ " if self._version_is_downloaded(version) else ""
            label = f"{marker}Minecraft {version}"
            self.setup_selector.addItem(label, f"version:{version}")
            row = self.setup_selector.count() - 1
            self.setup_selector.setItemData(row, entry.get("type", "release"), Qt.ItemDataRole.UserRole + 1)
            self.setup_selector.setItemData(row, label, Qt.ItemDataRole.ToolTipRole)
            self.setup_selector.setItemData(row, label, Qt.ItemDataRole.AccessibleTextRole)
        self.setup_selector.addItem("Saved setups", None)
        header = self.setup_selector.model().item(self.setup_selector.count() - 1)
        if header is not None:
            header.setEnabled(False)
        for instance in instances:
            name = str(instance.get("name", "Unnamed setup"))
            suffix = f" · {instance.get('id', '')}"
            label = f"{name}{suffix}"
            self.setup_selector.addItem(label, instance.get("id"))
            row = self.setup_selector.count() - 1
            self.setup_selector.setItemData(row, label, Qt.ItemDataRole.ToolTipRole)
            self.setup_selector.setItemData(row, label, Qt.ItemDataRole.AccessibleTextRole)
        index = self.setup_selector.findData(current, Qt.ItemDataRole.UserRole) if current else -1
        if index < 0:
            for row in range(self.setup_selector.count()):
                if self.setup_selector.itemData(row, Qt.ItemDataRole.UserRole) is not None:
                    index = row
                    break
        if index >= 0:
            self.setup_selector.setCurrentIndex(index)
        self.setup_selector.blockSignals(False)
        self._filter_setup_selector(self.setup_search_input.text())

    def _version_is_downloaded(self, version: str) -> bool:
        instance_id = self.state.get("automatic_instances", {}).get(version)
        instance = next((item for item in self.state.get("instances", []) if item.get("id") == instance_id), None)
        if instance is None or instance.get("version") != version:
            return False
        try:
            return bool(self.player.is_ready(instance, self.store.instance_minecraft_root(instance["id"])))
        except Exception:
            return False

    def _filter_setup_selector(self, text: str) -> None:
        needle = text.strip().casefold()
        selected = self.setup_selector.currentData(Qt.ItemDataRole.UserRole)
        visible = 0
        for row in range(self.setup_selector.count()):
            value = self.setup_selector.itemData(row, Qt.ItemDataRole.UserRole)
            label = self.setup_selector.itemText(row)
            is_header = value is None
            matches = not needle or (not is_header and needle in label.casefold())
            self.setup_selector.view().setRowHidden(row, not matches)
            if matches and not is_header:
                visible += 1
        self.selector_empty_label.setVisible(bool(needle) and visible == 0)
        if selected:
            index = self.setup_selector.findData(selected, Qt.ItemDataRole.UserRole)
            if index >= 0 and not self.setup_selector.view().isRowHidden(index):
                self.setup_selector.setCurrentIndex(index)

    def _recover_state(self) -> None:
        self.store.recover_defaults()
        self.state = self.store.load()
        self.state["memory_gib"] = default_memory_gib()
        self.store.save(self.state)
        self.state_recovery_label.hide()
        self.recover_state_button.hide()
        self.save_username_button.setEnabled(True)
        self.save_memory_button.setEnabled(True)
        self.create_instance_button.setEnabled(True)
        self.memory_input.setText(str(self.state.get("memory_gib", default_memory_gib())))
        self.instance_list.clear()
        self.setup_selector.clear()
        self._refresh_play_button()

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
        if not candidate:
            self.username_input.setText(str(self.state.get("username", "")))
            self.username_warning.setText("Enter a username before playing.")
            self.username_warning.show()
            return
        if candidate == self.state.get("username", ""):
            self.username_warning.hide()
            return
        if self.state.get("username", ""):
            self.username_warning.setText("Username changed. Offline worlds may recognize a different player.")
            self.username_warning.show()
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
        instance_id = str(uuid.uuid4())
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
        self._rebuild_setup_selector(selected=instance["id"])

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
        if instance is not None:
            if not getattr(self, "_restoring_state", False):
                self.state["selected_instance_id"] = instance["id"]
                self.state["selected_setup_id"] = instance["id"]
            if not self.store.recovery_required and not getattr(self, "_restoring_state", False):
                self.store.save(self.state)
            selector_row = self.setup_selector.findData(instance["id"], Qt.ItemDataRole.UserRole)
            if self.setup_selector.currentIndex() != selector_row:
                self.setup_selector.blockSignals(True)
                self.setup_selector.setCurrentIndex(selector_row)
                self.setup_selector.blockSignals(False)
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
        log_path = self.store.instance_root(instance["id"]) / "logs" / "minecraft.log"
        try:
            log_tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]) or "(empty)"
        except OSError as error:
            log_tail = f"(unavailable: {error})"
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
            f"Minecraft log: {log_path}",
            "Minecraft log tail (last 40 lines):",
            log_tail,
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

    def _selected_version(self) -> str | None:
        value = self.setup_selector.currentData(Qt.ItemDataRole.UserRole)
        if isinstance(value, str) and value.startswith("version:"):
            return value.removeprefix("version:")
        return None

    def _ensure_automatic_instance(self, version: str) -> dict:
        instance_id = self.state.setdefault("automatic_instances", {}).get(version)
        instance = next(
            (candidate for candidate in self.state["instances"] if candidate.get("id") == instance_id), None
        )
        if instance is None:
            instance_id = str(uuid.uuid4())
            instance = {
                "id": instance_id,
                "name": f"Minecraft {version}",
                "version": version,
                "ready": False,
                "automatic": True,
            }
            self.state["instances"].append(instance)
            self.state["automatic_instances"][version] = instance_id
            self.store.create_instance_root(instance_id)
            self.store.save(self.state)
            self._add_instance_item(instance)
            self.instance_list.setCurrentRow(self.instance_list.count() - 1)
        return instance

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
        self.install_progress.setRange(0, 100)
        self.install_progress.show()
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
        if maximum < 0 or progress < 0:
            self.install_progress.setRange(0, 0)
        elif maximum >= 0:
            self.install_progress.setRange(0, maximum)
            self.install_progress.setMaximum(maximum)
        if progress >= 0:
            self.install_progress.setValue(progress)

    def _installation_succeeded(self) -> None:
        instance = self.installing_instance
        if instance is None:
            return
        ready = True
        if self._launch_after_prepare and hasattr(self.player, "is_ready"):
            try:
                ready = bool(self.player.is_ready(instance, self.store.instance_minecraft_root(instance["id"])))
            except Exception as error:
                ready = False
                instance["install_error"] = str(error) or "Minecraft files are incomplete"
        if not ready:
            instance["ready"] = False
            instance["install_state"] = "failed"
            instance["install_error"] = instance.get("install_error") or "Minecraft files are incomplete"
            self.store.save(self.state)
            self.instance_status_label.setText(f"Installation failed: {instance['install_error']}")
            self.diagnostic_hint_label.setText("Minecraft is not ready; retry preparation before playing.")
            if self._launch_after_prepare:
                self._launch_after_prepare = False
                self._operation_instance_id = None
                self.game_registry.release()
            return
        instance["ready"] = True
        instance["install_state"] = "ready"
        instance["install_error"] = ""
        self.store.save(self.state)
        self.instance_status_label.setText(f"Ready: {instance['name']} ({instance['version']})")
        if self._launch_after_prepare and instance.get("id") == self._operation_instance_id:
            self._launch_after_prepare = False
            self._operation_instance_id = None
            username = str(self.state.get("username", "")).strip()
            memory_gib, error = validate_memory_gib(self.memory_input.text())
            if not error:
                self._launch_ready_instance(instance, username, memory_gib)

    def _installation_failed(self, message: str) -> None:
        instance = self.installing_instance
        if instance is not None:
            instance["ready"] = False
            instance["install_state"] = "failed"
            instance["install_error"] = message
            self._record_diagnostic(instance, f"Installation failed: {message}")
        self.instance_status_label.setText(f"Installation failed: {message}")
        self.diagnostic_hint_label.setText("Install Minecraft again to retry this instance.")
        if self._launch_after_prepare:
            self._launch_after_prepare = False
            self._operation_instance_id = None
            self.game_registry.release()

    def _installation_finished(self) -> None:
        worker = self.install_worker
        self.install_worker = None
        if worker is not None:
            worker.deleteLater()
        self.installing_instance = None
        self.install_progress.hide()
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
        if instance is None and self._selected_version():
            self.play_button.setEnabled(self.install_worker is None and self.game_process is None)
            return
        ready = bool(instance and instance.get("ready") and self.game_process is None)
        if ready and hasattr(self.player, "is_ready"):
            try:
                ready = bool(self.player.is_ready(instance, self.store.instance_minecraft_root(instance["id"])))
            except Exception:
                ready = False
        self.play_button.setEnabled(ready)

    def _play_selected_instance(self) -> None:
        instance = self._selected_instance()
        selected_version = self._selected_version()
        if instance is None and not selected_version:
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
        if instance is None and selected_version:
            instance = self._ensure_automatic_instance(selected_version)
        if not instance.get("ready"):
            self._launch_after_prepare = True
            self._operation_instance_id = instance["id"]
            self._install_selected_instance()
            return
        self._launch_ready_instance(instance, username, memory_gib)

    def _launch_ready_instance(self, instance: dict, username: str, memory_gib: int) -> None:
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
            process = self.player.launch(*launch_args, memory_gib=memory_gib)
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
            self.instance_status_label.setText("Installation is still running; wait for it to finish before closing.")
            event.ignore()
            return
        if self.discovery_worker is not None and self.discovery_worker.isRunning():
            self.discovery_worker.requestInterruption()
            if not self.discovery_worker.wait(1000):
                self.instance_status_label.setText("Release discovery is still running; wait for it to finish before closing.")
                event.ignore()
                return
        if not self.store.recovery_required:
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


class VersionDiscoveryWorker(QThread):
    discovered = Signal(list)
    failed = Signal(str)

    def __init__(self, installer, *, select_latest: bool = False) -> None:
        super().__init__()
        self.installer = installer
        self.select_latest = select_latest

    def run(self) -> None:
        try:
            if hasattr(self.installer, "discover_versions"):
                versions = self.installer.discover_versions()
            else:
                versions = []
            if self.select_latest and versions and hasattr(self.installer, "resolve_version"):
                latest = self.installer.resolve_version()
                versions = sorted(
                    versions,
                    key=lambda entry: (entry if isinstance(entry, str) else entry.get("id")) != latest,
                )
            self.discovered.emit(list(versions))
        except Exception as error:
            self.failed.emit(str(error) or "unknown release discovery error")


def main() -> int:
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
