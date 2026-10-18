from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .persistence import LauncherStore


def local_identity(username: str) -> str:
    """Return the stable offline-session identity for a saved username."""
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return str(uuid.UUID(digest[:32]))


class LauncherWindow(QMainWindow):
    def __init__(self, data_root: Path | str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Minecraft Launcher")
        self.store = LauncherStore(data_root)
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
        layout.addWidget(self.instance_status_label)
        self.setCentralWidget(root)

    def _restore_state(self) -> None:
        username = str(self.state.get("username", ""))
        self.username_input.setText(username)
        self._update_identity(username)
        for instance in self.state.get("instances", []):
            if isinstance(instance, dict) and instance.get("name") and instance.get("id"):
                self._add_instance_item(instance)
        if self.instance_list.count():
            self.instance_list.setCurrentRow(0)

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
            return
        self.instance_status_label.setText(f"Selected instance: {current.text()}")

    def closeEvent(self, event) -> None:
        self.store.save(self.state)
        super().closeEvent(event)


def main() -> int:
    application = QApplication.instance() or QApplication([])
    window = LauncherWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
