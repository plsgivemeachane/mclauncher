from __future__ import annotations

import hashlib
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, QUrl, Qt, Signal, QPoint
from PySide6.QtGui import QDesktopServices, QPainter, QPixmap, QColor
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
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
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .persistence import LauncherStore
from .installer import MinecraftInstaller, MinecraftPlayer, validate_version_id
from .memory import default_memory_gib, validate_memory_gib
from .lifecycle import GameProcessRegistry
from .modpack import (
    CurseForgePackError,
    CurseForgePackImporter,
    ModrinthPackError,
    ModrinthPackImporter,
    ModrinthPackUpdateError,
    ModrinthPackUpdater,
    UnsupportedModrinthPack,
)
from .modrinth_catalog import ModrinthCatalog, ModrinthCatalogError, ModrinthRelease
from .modrinth_mods import ModrinthModInstallError, ModrinthModInstaller
from .news import MinecraftNewsFeed
from .optifine import OptiFineError, OptiFineInstaller
from .localmods import copy_mod_to_instance, inspect_mod_jar

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
_ACTIVE_DISCOVERY_WORKERS: set[QThread] = set()
_ACTIVE_INSTALL_WORKERS: set[QThread] = set()
_ACTIVE_NEWS_WORKERS: set[QThread] = set()


def _release_discovery_worker(worker: QThread) -> None:
    _ACTIVE_DISCOVERY_WORKERS.discard(worker)
    worker.deleteLater()


def local_identity(username: str) -> str:
    """Return the stable offline-session identity for a saved username."""
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return str(uuid.UUID(digest[:32]))


class MinecraftHomePanel(QFrame):
    """Minecraft artwork panel with a bundled, offline-safe fallback."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("minecraftHomePanel")
        self.setMinimumHeight(120)
        self._background = QPixmap()
        self.set_background(None)

    @staticmethod
    def bundled_background() -> Path:
        return Path(__file__).with_name("assets") / "minecraft-home.png"

    def set_background(self, filename: str | Path | None) -> None:
        candidates = [Path(filename)] if filename else []
        candidates.append(self.bundled_background())
        self._background = QPixmap()
        for candidate in candidates:
            if candidate.is_file():
                pixmap = QPixmap(str(candidate))
                if not pixmap.isNull():
                    self._background = pixmap
                    break
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        width, height = self.width(), self.height()
        if self._background.isNull():
            painter.fillRect(self.rect(), "#263b30")
        else:
            scaled = self._background.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                             Qt.TransformationMode.SmoothTransformation)
            x = (scaled.width() - width) // 2
            y = (scaled.height() - height) // 2
            painter.drawPixmap(0, 0, scaled, x, y, width, height)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        painter.end()


# Kept as an import-compatible name for callers from the original launcher.
LandscapePanel = MinecraftHomePanel


class LauncherWindow(QMainWindow):
    def __init__(self, data_root: Path | str | None = None, installer=None, player=None, game_registry=None,
                 modpack_importer=None, news_provider=None, modrinth_catalog=None, optifine_installer=None,
                 curseforge_importer=None, mod_installer=None, modrinth_updater=None,
                 curseforge_updater=None) -> None:
        super().__init__()
        self.setWindowTitle("Minecraft Launcher")
        self.store = LauncherStore(data_root)
        self._installer_injected = installer is not None
        self.installer = installer or MinecraftInstaller()
        self.player = player or MinecraftPlayer()
        self.modpack_importer = modpack_importer or ModrinthPackImporter(provider=self.installer)
        self.modrinth_updater = modrinth_updater or ModrinthPackUpdater(self.modpack_importer)
        self.optifine_installer = optifine_installer or OptiFineInstaller()
        self.curseforge_importer = curseforge_importer or CurseForgePackImporter(
            loader_resolver=getattr(self.installer, "resolve_loader", None)
        )
        self.curseforge_updater = curseforge_updater or ModrinthPackUpdater(self.curseforge_importer)
        self.modrinth_catalog = modrinth_catalog or ModrinthCatalog()
        self.mod_installer = mod_installer or ModrinthModInstaller(self.modrinth_catalog)
        self._catalog_results = []
        self._catalog_releases = []
        self._catalog_installing = False
        self.install_worker = None
        self.installing_instance = None
        self.discovery_worker = None
        self.news_worker = None
        self._news_provider_injected = news_provider is not None
        self.news_provider = news_provider or MinecraftNewsFeed()
        self._launch_after_prepare = False
        self._operation_instance_id = None
        self._operation_selector_value = None
        self._operation_username = None
        self._operation_memory_gib = None
        self._session_controls_locked = False
        self.game_process = None
        self.game_instance = None
        self.game_record = None
        self.last_game_instance = None
        self.last_diagnostic_message = ""
        self.game_registry = game_registry or GameProcessRegistry(self.store.root)
        self.game_poll_timer = QTimer(self)
        self.game_poll_timer.setInterval(500)
        self.game_poll_timer.timeout.connect(self._poll_adopted_game)
        self._waiting_for_game_lock = False
        self.home_panel = None
        self.content_stack = None
        self._closing = False
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

        navigation = QFrame(root)
        navigation.setObjectName("navigationBar")
        navigation_layout = QHBoxLayout(navigation)
        navigation_layout.setContentsMargins(25, 4, 25, 4)
        self.home_nav_button = QPushButton("Home", navigation)
        self.home_nav_button.setObjectName("homeNavButton")
        self.instances_nav_button = QPushButton("Instances", navigation)
        self.instances_nav_button.setObjectName("instancesNavButton")
        self.home_nav_button.clicked.connect(lambda: self._show_page(0))
        self.instances_nav_button.clicked.connect(lambda: self._show_page(1))
        self.browse_nav_button = QPushButton("Browse", navigation)
        self.browse_nav_button.setObjectName("browseNavButton")
        self.browse_nav_button.clicked.connect(lambda: self._show_page(2))
        self.mods_nav_button = QPushButton("Mods", navigation)
        self.mods_nav_button.setObjectName("modsNavButton")
        self.mods_nav_button.clicked.connect(lambda: self._show_page(3))
        navigation_layout.addWidget(self.home_nav_button)
        navigation_layout.addWidget(self.instances_nav_button)
        navigation_layout.addWidget(self.browse_nav_button)
        navigation_layout.addWidget(self.mods_nav_button)
        navigation_layout.addStretch(1)
        layout.addWidget(navigation)

        self.content_stack = QStackedWidget(root)
        self.home_panel = QWidget(root)
        home_layout = QVBoxLayout(self.home_panel)
        home_layout.setContentsMargins(0, 0, 0, 0)
        scene = MinecraftHomePanel(self.home_panel)
        self.home_artwork = scene
        scene_layout = QVBoxLayout(scene)
        scene_layout.setContentsMargins(26, 22, 26, 22)
        scene_layout.addStretch(1)
        news_overlay = QFrame(scene)
        news_overlay.setObjectName("newsOverlay")
        news_layout = QVBoxLayout(news_overlay)
        news_layout.setContentsMargins(16, 12, 16, 12)
        news_layout.setSpacing(6)
        news_heading = QLabel("Minecraft news", news_overlay)
        news_heading.setObjectName("newsHeading")
        news_layout.addWidget(news_heading)
        self.news_cards = QHBoxLayout()
        self.news_cards.setSpacing(8)
        news_layout.addLayout(self.news_cards)
        changelog_heading = QLabel("Launcher changes", news_overlay)
        changelog_heading.setObjectName("changelogHeading")
        news_layout.addWidget(changelog_heading)
        self.launcher_changelog = QLabel(news_overlay)
        self.launcher_changelog.setObjectName("launcherChangelog")
        self.launcher_changelog.setWordWrap(True)
        news_layout.addWidget(self.launcher_changelog)
        scene_layout.addWidget(news_overlay)
        home_layout.addWidget(scene, 1)

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
        self.background_button = QPushButton("Choose background", launch_bar)
        self.background_button.setObjectName("backgroundButton")
        self.background_button.clicked.connect(self._choose_background)
        launch_layout.addWidget(self.background_button)
        home_layout.addWidget(launch_bar)
        self.content_stack.addWidget(self.home_panel)

        legacy_panel = QWidget(root)
        legacy_layout = QVBoxLayout(legacy_panel)
        legacy_layout.setContentsMargins(0, 0, 0, 0)
        self.instances_panel = legacy_panel

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
        mutation_row = QHBoxLayout()
        self.rename_instance_button = QPushButton("Rename selected")
        self.rename_instance_button.setObjectName("renameInstanceButton")
        self.rename_instance_button.clicked.connect(self._rename_selected_instance)
        self.duplicate_instance_button = QPushButton("Duplicate selected")
        self.duplicate_instance_button.setObjectName("duplicateInstanceButton")
        self.duplicate_instance_button.clicked.connect(self._duplicate_selected_instance)
        self.delete_instance_button = QPushButton("Delete selected")
        self.delete_instance_button.setObjectName("deleteInstanceButton")
        self.delete_instance_button.clicked.connect(self._delete_selected_instance)
        mutation_row.addWidget(self.rename_instance_button)
        mutation_row.addWidget(self.duplicate_instance_button)
        mutation_row.addWidget(self.delete_instance_button)
        legacy_layout.addLayout(mutation_row)
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
        self.import_modpack_button = QPushButton("Import Modrinth .mrpack")
        self.import_modpack_button.setObjectName("importModpackButton")
        self.import_modpack_button.clicked.connect(self._import_modrinth_pack)
        legacy_layout.addWidget(self.import_modpack_button)
        self.update_modpack_button = QPushButton("Update selected pack")
        self.update_modpack_button.setObjectName("updateModpackButton")
        self.update_modpack_button.clicked.connect(self._update_selected_modrinth_pack)
        legacy_layout.addWidget(self.update_modpack_button)
        self.recover_modpack_button = QPushButton("Recover last Modrinth update")
        self.recover_modpack_button.setObjectName("recoverModpackButton")
        self.recover_modpack_button.clicked.connect(self._recover_selected_modrinth_pack)
        legacy_layout.addWidget(self.recover_modpack_button)
        self.install_optifine_button = QPushButton("Install local OptiFine .jar")
        self.install_optifine_button.setObjectName("installOptifineButton")
        self.install_optifine_button.clicked.connect(self._install_local_optifine)
        legacy_layout.addWidget(self.install_optifine_button)
        self.import_curseforge_button = QPushButton("Import CurseForge ZIP")
        self.import_curseforge_button.setObjectName("importCurseForgeButton")
        self.import_curseforge_button.clicked.connect(self._import_curseforge_pack)
        legacy_layout.addWidget(self.import_curseforge_button)
        self.content_stack.addWidget(legacy_panel)
        browse_panel = QWidget(root)
        browse_layout = QVBoxLayout(browse_panel)
        browse_layout.setContentsMargins(26, 20, 26, 20)
        browse_layout.addWidget(QLabel("Modrinth modpacks"))
        browse_search_row = QHBoxLayout()
        self.modrinth_search_input = QLineEdit(browse_panel)
        self.modrinth_search_input.setObjectName("modrinthSearchInput")
        self.modrinth_search_input.setPlaceholderText("Search modpacks")
        self.modrinth_search_button = QPushButton("Search", browse_panel)
        self.modrinth_search_button.setObjectName("modrinthSearchButton")
        self.modrinth_search_button.clicked.connect(self._search_modrinth_catalog)
        browse_search_row.addWidget(self.modrinth_search_input, 1)
        browse_search_row.addWidget(self.modrinth_search_button)
        browse_layout.addLayout(browse_search_row)
        browse_body = QHBoxLayout()
        self.modrinth_pack_list = QListWidget(browse_panel)
        self.modrinth_pack_list.setObjectName("modrinthPackList")
        self.modrinth_pack_list.currentItemChanged.connect(self._select_modrinth_catalog_pack)
        browse_body.addWidget(self.modrinth_pack_list, 1)
        details = QVBoxLayout()
        self.modrinth_pack_details = QLabel("Search Modrinth to see pack details.", browse_panel)
        self.modrinth_pack_details.setObjectName("modrinthPackDetails")
        self.modrinth_pack_details.setWordWrap(True)
        details.addWidget(self.modrinth_pack_details)
        self.modrinth_release_selector = QComboBox(browse_panel)
        self.modrinth_release_selector.setObjectName("modrinthReleaseSelector")
        details.addWidget(self.modrinth_release_selector)
        self.modrinth_install_button = QPushButton("Install selected release", browse_panel)
        self.modrinth_install_button.setObjectName("modrinthInstallButton")
        self.modrinth_install_button.setEnabled(False)
        self.modrinth_install_button.clicked.connect(self._install_modrinth_catalog_release)
        details.addWidget(self.modrinth_install_button)
        self.modrinth_catalog_status = QLabel("", browse_panel)
        self.modrinth_catalog_status.setObjectName("modrinthCatalogStatus")
        self.modrinth_catalog_status.setWordWrap(True)
        details.addWidget(self.modrinth_catalog_status)
        details.addStretch(1)
        browse_body.addLayout(details, 1)
        browse_layout.addLayout(browse_body, 1)
        self.content_stack.addWidget(browse_panel)
        mods_panel = QWidget(root)
        mods_layout = QVBoxLayout(mods_panel)
        mods_layout.setContentsMargins(26, 24, 26, 24)
        mods_heading = QLabel("Mods", mods_panel)
        mods_heading.setObjectName("modsHeading")
        mods_layout.addWidget(mods_heading)
        self.mods_instance_label = QLabel("Select an instance to manage its mods.", mods_panel)
        self.mods_instance_label.setObjectName("modsInstanceLabel")
        mods_layout.addWidget(self.mods_instance_label)
        self.mods_warning_label = QLabel(mods_panel)
        self.mods_warning_label.setObjectName("modsWarningLabel")
        self.mods_warning_label.setWordWrap(True)
        mods_layout.addWidget(self.mods_warning_label)
        mod_search_row = QHBoxLayout()
        self.mod_search_input = QLineEdit(mods_panel)
        self.mod_search_input.setObjectName("modSearchInput")
        self.mod_search_input.setPlaceholderText("Search Modrinth mods for this instance")
        self.mod_search_button = QPushButton("Search Modrinth", mods_panel)
        self.mod_search_button.setObjectName("modSearchButton")
        self.mod_search_button.clicked.connect(self._search_modrinth_mods)
        mod_search_row.addWidget(self.mod_search_input, 1)
        mod_search_row.addWidget(self.mod_search_button)
        mods_layout.addLayout(mod_search_row)
        self.mod_search_results = QListWidget(mods_panel)
        self.mod_search_results.setObjectName("modSearchResults")
        self.mod_search_results.currentItemChanged.connect(self._select_modrinth_mod)
        mods_layout.addWidget(self.mod_search_results)
        self.mod_release_selector = QComboBox(mods_panel)
        self.mod_release_selector.setObjectName("modReleaseSelector")
        mods_layout.addWidget(self.mod_release_selector)
        self.mod_install_button = QPushButton("Install selected mod", mods_panel)
        self.mod_install_button.setObjectName("modInstallButton")
        self.mod_install_button.setEnabled(False)
        self.mod_install_button.clicked.connect(self._install_selected_modrinth_mod)
        mods_layout.addWidget(self.mod_install_button)
        self.mod_search_status = QLabel("", mods_panel)
        self.mod_search_status.setObjectName("modSearchStatus")
        self.mod_search_status.setWordWrap(True)
        mods_layout.addWidget(self.mod_search_status)
        self.mods_list = QListWidget(mods_panel)
        self.mods_list.setObjectName("modsList")
        self.mods_list.currentRowChanged.connect(lambda _row: self._refresh_mod_buttons())
        mods_layout.addWidget(self.mods_list, 1)
        mods_actions = QHBoxLayout()
        self.import_mod_button = QPushButton("Import local JAR", mods_panel)
        self.import_mod_button.setObjectName("importModButton")
        self.import_mod_button.clicked.connect(self._import_local_mod)
        self.toggle_mod_button = QPushButton("Disable selected", mods_panel)
        self.toggle_mod_button.setObjectName("toggleModButton")
        self.toggle_mod_button.clicked.connect(self._toggle_selected_mod)
        self.remove_mod_button = QPushButton("Remove selected", mods_panel)
        self.remove_mod_button.setObjectName("removeModButton")
        self.remove_mod_button.clicked.connect(self._remove_selected_mod)
        mods_actions.addWidget(self.import_mod_button)
        mods_actions.addWidget(self.toggle_mod_button)
        mods_actions.addWidget(self.remove_mod_button)
        mods_layout.addLayout(mods_actions)
        self.content_stack.addWidget(mods_panel)
        self.mods_panel = mods_panel
        layout.addWidget(self.content_stack, 1)
        self.setCentralWidget(root)
        self._apply_compact_theme()
        self._show_page(0)

    def _apply_compact_theme(self) -> None:
        self.resize(920, 560)
        self.setMinimumSize(680, 420)
        self.setStyleSheet("""
            QWidget { background: #161b19; color: #eef3e9; }
            QFrame#titleBar { background: #172019; }
            QFrame#navigationBar { background: #172019; }
            QPushButton#homeNavButton[active="true"], QPushButton#instancesNavButton[active="true"], QPushButton#browseNavButton[active="true"], QPushButton#modsNavButton[active="true"] { background: #2c3d30; color: #e6f4dc; }
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
            QFrame#newsOverlay { background: #101712d9; border: 1px solid #536052; border-radius: 10px; }
            QLabel#newsHeading, QLabel#changelogHeading { color: #e6f4dc; font-weight: 700; }
            QLabel#newsCard { background: #26352a; border: 1px solid #526452; border-radius: 6px; padding: 8px; color: #eef3e9; }
            QLabel#launcherChangelog { color: #c7d2c9; }
            QLabel#modsWarningLabel { color: #e7c17a; }
            QLabel#modsHeading { color: #e6f4dc; font-size: 18px; font-weight: 700; }
            QLabel#modsInstanceLabel { color: #c7d2c9; }
        """)
        self.save_username_button.hide()
        self.save_memory_button.hide()
        self.identity_label.hide()
        self.memory_input.hide()
        self.memory_setting_error.hide()
        self.username_warning.setStyleSheet("color: #e7c17a;")
        self.confirm_username_change_button.hide()
        self.home_nav_button.setProperty("active", True)
        self.browse_nav_button.setProperty("active", False)
        self.mods_nav_button.setProperty("active", False)

    def _show_page(self, index: int) -> None:
        if self.content_stack is None:
            return
        index = 0 if index not in (0, 1, 2, 3) else index
        self.content_stack.setCurrentIndex(index)
        self.home_nav_button.setProperty("active", index == 0)
        self.instances_nav_button.setProperty("active", index == 1)
        self.browse_nav_button.setProperty("active", index == 2)
        self.mods_nav_button.setProperty("active", index == 3)
        for button in (self.home_nav_button, self.instances_nav_button, self.browse_nav_button, self.mods_nav_button):
            button.style().unpolish(button)
            button.style().polish(button)
        if index == 3:
            self._refresh_mods_panel()

    def _choose_background(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Choose Minecraft background", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp *.svg)"
        )
        if not filename:
            return
        candidate = Path(filename)
        pixmap = QPixmap(str(candidate))
        if pixmap.isNull():
            self.diagnostic_hint_label.setText(
                "That image could not be loaded; the bundled background is still active."
            )
            return
        self.home_artwork.set_background(candidate)
        self.state["background_path"] = str(candidate)
        if not self.store.recovery_required:
            self.store.save(self.state)
        self.diagnostic_hint_label.setText("Custom background saved.")

    def _select_setup_from_selector(self, index: int) -> None:
        if index < 0 or index >= self.setup_selector.count():
            return
        value = self.setup_selector.itemData(index, Qt.ItemDataRole.UserRole)
        if value is None:
            return
        if self.install_worker is not None or self._session_controls_locked:
            original = self._operation_selector_value or self.state.get("selected_setup_id")
            original_index = self.setup_selector.findData(original, Qt.ItemDataRole.UserRole)
            if original_index >= 0 and original_index != index:
                self.setup_selector.blockSignals(True)
                self.setup_selector.setCurrentIndex(original_index)
                self.setup_selector.blockSignals(False)
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
            self._preserve_lifecycle_status()
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
        _ACTIVE_DISCOVERY_WORKERS.add(self.discovery_worker)
        self.discovery_worker.discovered.connect(self._versions_discovered)
        self.discovery_worker.failed.connect(self._version_discovery_failed)
        self.discovery_worker.finished.connect(self._discovery_finished)
        self.discovery_worker.finished.connect(lambda worker=self.discovery_worker: _release_discovery_worker(worker))
        self.discovery_worker.start()

    def _versions_discovered(self, versions: list) -> None:
        metadata = [
            {"id": entry, "type": "release"} if isinstance(entry, str)
            else {"id": str(entry.get("id", "")), "type": str(entry.get("type", "release"))}
            for entry in versions
        ]
        valid_metadata = []
        for entry in metadata:
            try:
                validate_version_id(entry["id"])
            except ValueError:
                continue
            valid_metadata.append(entry)
        metadata = valid_metadata
        self.state["available_version_metadata"] = metadata
        self.state["available_versions"] = [entry["id"] for entry in metadata]
        if not self.state.get("selected_setup_id") and not self.state.get("instances") and metadata:
            stable = next((entry["id"] for entry in metadata if entry.get("type") == "release"), metadata[0]["id"])
            self.state["selected_setup_id"] = f"version:{stable}"
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

    def _start_news_fetch(self) -> None:
        if not self._news_provider_injected and QApplication.platformName() == "offscreen":
            return
        self.news_worker = NewsWorker(self.news_provider)
        _ACTIVE_NEWS_WORKERS.add(self.news_worker)
        self.news_worker.fetched.connect(self._news_fetched)
        self.news_worker.failed.connect(self._news_failed)
        self.news_worker.finished.connect(self._news_finished)
        self.news_worker.finished.connect(lambda worker=self.news_worker: _ACTIVE_NEWS_WORKERS.discard(worker))
        self.news_worker.start()

    def _news_fetched(self, items: list[dict[str, str]]) -> None:
        self.state["news_items"] = items
        self.state["news_fetched_at"] = datetime.now(timezone.utc).isoformat()
        if not self.store.recovery_required:
            self.store.save(self.state)
        self._render_news(items)

    def _news_failed(self, message: str) -> None:
        del message
        if not self.state.get("news_items"):
            self._render_news([])

    def _news_finished(self) -> None:
        self.news_worker = None

    def _render_news(self, items: list[dict[str, str]]) -> None:
        while self.news_cards.count():
            item = self.news_cards.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        cards = items[:3]
        if not cards:
            empty = QLabel("Minecraft news is unavailable offline.")
            empty.setObjectName("newsCard")
            empty.setWordWrap(True)
            self.news_cards.addWidget(empty)
        else:
            for article in cards:
                title = str(article.get("title", "Minecraft news"))
                published = str(article.get("published", ""))
                card = QLabel(f"{title}\n{published}" if published else title)
                card.setObjectName("newsCard")
                card.setWordWrap(True)
                card.setMinimumWidth(170)
                card.setToolTip(str(article.get("url", "")))
                self.news_cards.addWidget(card, 1)
        self.launcher_changelog.setText(
            f"mclauncher {__version__}: responsive preparation, isolated instances, and cached Minecraft news."
        )

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
        lifecycle_target = self.game_instance is not None or self.last_game_instance is not None
        target_label = "running game" if self.game_instance is not None else "last game"
        open_folder_text = f"Open {target_label} folder" if lifecycle_target else "Open selected setup folder"
        log_text = f"Export {target_label} diagnostic log" if lifecycle_target else "Export diagnostic log"
        open_folder = QPushButton(open_folder_text, dialog)
        open_folder.clicked.connect(self._open_instance_folder)
        form.addRow("", open_folder)
        export_log = QPushButton(log_text, dialog)
        export_log.clicked.connect(self._save_diagnostic_log)
        form.addRow("", export_log)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        form.addRow(buttons)

        def save_memory() -> None:
            if self.store.recovery_required:
                return
            value, message = validate_memory_gib(memory.text())
            if message:
                error.setText(message)
                error.show()
                return
            self.state["memory_gib"] = value
            self.store.save(self.state)
            self.memory_input.setText(str(value))
            error.hide()

        def save_snapshots(enabled: bool) -> None:
            if self.store.recovery_required:
                return
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
            self.install_optifine_button.setEnabled(False)
            self.play_button.setEnabled(False)
            self.settings_button.setEnabled(False)
            self._restoring_state = False
            return
        self.state.setdefault("selected_setup_id", self.state.get("selected_instance_id", ""))
        self.state.setdefault("automatic_instances", {})
        self.state.setdefault("available_versions", [])
        self.state.setdefault("available_version_metadata", [])
        self.state.setdefault("show_snapshots", False)
        self.state.setdefault("background_path", "")
        self.state.setdefault("news_items", [])
        self.state.setdefault("news_fetched_at", "")
        if "memory_gib" not in self.state and not self.store.recovery_required:
            self.state["memory_gib"] = default_memory_gib()
            self.store.save(self.state)
        self.memory_input.setText(str(self.state["memory_gib"]))
        username = str(self.state.get("username", ""))
        self.username_input.setText(username)
        self._update_identity(username)
        self.home_artwork.set_background(self.state.get("background_path") or None)
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
        if self.state.get("selected_setup_id"):
            selected_index = self.setup_selector.findData(self.state["selected_setup_id"], Qt.ItemDataRole.UserRole)
            if selected_index >= 0:
                self.setup_selector.setCurrentIndex(selected_index)
                self.setup_selector.setToolTip(self.setup_selector.itemText(selected_index))
        self._restoring_state = False
        self._restore_running_game()
        self._render_news(self.state.get("news_items", []))
        self._start_news_fetch()

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
            pinned = (current == f"version:{version}" and self.state.get("automatic_instances", {}).get(version)) or any(
                instance.get("version") == version
                and self.state.get("automatic_instances", {}).get(version) == instance.get("id")
                for instance in instances
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
        self.settings_button.setEnabled(True)
        self.save_username_button.setEnabled(True)
        self.save_memory_button.setEnabled(True)
        self.create_instance_button.setEnabled(True)
        self.rename_instance_button.setEnabled(True)
        self.duplicate_instance_button.setEnabled(True)
        self.delete_instance_button.setEnabled(True)
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
        self._operation_selector_value = self.state.get("selected_setup_id") or self.setup_selector.currentData(
            Qt.ItemDataRole.UserRole
        )
        instance_id = record.get("instance_id")
        self.game_instance = next(
            (instance for instance in self.state["instances"] if instance.get("id") == instance_id), None
        )
        self.last_game_instance = self.game_instance
        if self.game_instance is not None:
            self.instance_status_label.setText(f"Running: {self.game_instance['name']}")
        else:
            self.instance_status_label.setText("A Minecraft game is already running")
        self._set_session_controls_locked(True)
        self.game_poll_timer.start()

    def _poll_adopted_game(self) -> None:
        if self._waiting_for_game_lock:
            if not self.game_registry.acquire():
                return
            self._waiting_for_game_lock = False
            record = self.game_registry.adopt()
            if record is not None and self.game_registry.is_alive(record):
                self.game_record = record
                self.game_process = record
                self._set_session_controls_locked(True)
                self.instance_status_label.setText("A Minecraft game is already running")
                return
            self.game_registry.release()
            self._refresh_play_button()
            return
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
        self._set_session_controls_locked(False)
        self._refresh_play_button()

    def _save_memory(self) -> None:
        if self.store.recovery_required or self._session_controls_locked:
            return
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
        if self._session_controls_locked:
            if self._operation_username is not None:
                self.username_input.setText(self._operation_username)
            return
        candidate = self.username_input.text().strip()
        if not candidate:
            self.username_input.setText(str(self.state.get("username", "")))
            self.username_warning.setText("Enter a username before playing.")
            self.username_warning.show()
            return
        if not USERNAME_RE.fullmatch(candidate):
            self.username_warning.setText("Use 3–16 letters, numbers, or underscores for the username.")
            self.username_warning.show()
            self.username_input.setText(str(self.state.get("username", "")))
            return
        if self.store.recovery_required:
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
        if self.store.recovery_required or self._session_controls_locked or not USERNAME_RE.fullmatch(username):
            return
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

    def _search_modrinth_catalog(self) -> None:
        query = self.modrinth_search_input.text().strip()
        if not query:
            self.modrinth_catalog_status.setText("Enter a search term to browse Modrinth modpacks.")
            return
        try:
            results = self.modrinth_catalog.search(query)
        except (ModrinthCatalogError, OSError, RuntimeError) as error:
            self._catalog_results = []
            self.modrinth_pack_list.clear()
            self.modrinth_catalog_status.setText(f"Modrinth search failed: {error}")
            return
        self._catalog_results = results
        self.modrinth_pack_list.clear()
        for result in results:
            title = str(result.get("title") or result.get("name") or result.get("slug") or result.get("project_id"))
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, result)
            item.setToolTip(str(result.get("description", "")))
            self.modrinth_pack_list.addItem(item)
        self.modrinth_catalog_status.setText(f"{len(results)} Modrinth pack(s) found." if results else "No Modrinth modpacks matched that search.")

    def _select_modrinth_catalog_pack(self, current, _previous=None) -> None:
        self.modrinth_release_selector.clear()
        self._catalog_releases = []
        self.modrinth_install_button.setEnabled(False)
        if current is None:
            return
        result = current.data(Qt.ItemDataRole.UserRole) or {}
        project_id = str(result.get("project_id") or result.get("id") or "")
        if not project_id:
            return
        try:
            details = self.modrinth_catalog.project(project_id)
            releases = self.modrinth_catalog.releases(project_id)
        except (ModrinthCatalogError, OSError, RuntimeError) as error:
            self.modrinth_pack_details.setText(f"Could not load pack details: {error}")
            self.modrinth_catalog_status.setText("Choose another pack or retry the search.")
            return
        description = str(details.get("description") or "No description available.")
        self.modrinth_pack_details.setText(f"{details.get('title', project_id)}\n\n{description}")
        self._catalog_releases = releases
        for release in releases:
            self.modrinth_release_selector.addItem(
                f"{release.version_number or release.name} · {', '.join(release.game_versions)}",
                release,
            )
        self.modrinth_install_button.setEnabled(bool(releases))
        self.modrinth_catalog_status.setText(f"{len(releases)} release(s) available.")

    def _install_modrinth_catalog_release(self) -> None:
        if self._catalog_installing or self._session_controls_locked or self.install_worker is not None:
            return
        release = self.modrinth_release_selector.currentData(Qt.ItemDataRole.UserRole)
        if not isinstance(release, ModrinthRelease):
            self.modrinth_catalog_status.setText("Select a release before installing.")
            return
        project = self.modrinth_pack_list.currentItem()
        project_data = project.data(Qt.ItemDataRole.UserRole) if project else {}
        title = str((project_data or {}).get("title") or (project_data or {}).get("slug") or release.project_id)
        self._catalog_installing = True
        self.modrinth_install_button.setEnabled(False)
        archive = self.store.root / f".modrinth-catalog-{release.id}.mrpack"
        try:
            archive.write_bytes(self.modrinth_catalog.download_release(release))
            self._install_modrinth_archive(
                archive, title, pack_release_id=release.id, pack_project_id=release.project_id,
            )
            self.modrinth_catalog_status.setText(f"Installed {title} {release.version_number or release.name}.")
        except (ModrinthCatalogError, ModrinthPackError, UnsupportedModrinthPack, OSError, RuntimeError) as error:
            self.modrinth_catalog_status.setText(f"Modrinth installation failed: {error}")
        finally:
            archive.unlink(missing_ok=True)
            self._catalog_installing = False
            self.modrinth_install_button.setEnabled(bool(self._catalog_releases))

    def _import_modrinth_pack(self) -> None:
        """Import and prepare a Modrinth pack through injected collaborators."""
        if self._session_controls_locked or self.install_worker is not None or self.store.recovery_required:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import Modrinth modpack", "", "Modrinth packs (*.mrpack);;All files (*)"
        )
        if not filename:
            return
        archive = Path(filename)
        name = archive.stem.strip() or "Imported Modrinth pack"
        self._install_modrinth_archive(archive, name)

    def _import_curseforge_pack(self) -> None:
        if self._session_controls_locked or self.install_worker is not None or self.store.recovery_required:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import CurseForge exported pack", "", "CurseForge packs (*.zip);;All files (*)"
        )
        if not filename:
            return
        archive = Path(filename)
        name = archive.stem.strip() or "Imported CurseForge pack"
        self._install_modrinth_archive(
            archive, name, importer=self.curseforge_importer, provider="curseforge", display_name="CurseForge"
        )

    def _install_modrinth_archive(self, archive: Path, name: str, *, pack_release_id: str = "",
                                  pack_project_id: str = "", importer=None, provider: str = "modrinth",
                                  display_name: str = "Modrinth") -> None:
        importer = importer or self.modpack_importer
        existing_names = {str(item.get("name")) for item in self.state.get("instances", [])}
        base_name = name
        suffix = 2
        while name in existing_names:
            name = f"{base_name} ({suffix})"
            suffix += 1
        instance = {
            "id": str(uuid.uuid4()), "name": name, "version": None, "ready": False,
            "automatic": False, "provider": provider, "pack_source": str(archive),
            "install_state": "importing", "install_error": "",
        }
        if pack_release_id:
            instance["pack_release_id"] = pack_release_id
        if pack_project_id:
            instance["pack_project_id"] = pack_project_id
        self.state["instances"].append(instance)
        self.store.create_instance_root(instance["id"])
        self.store.save(self.state)
        self._add_instance_item(instance)
        self.instance_list.setCurrentRow(self.instance_list.count() - 1)
        try:
            metadata = importer.import_archive(
                archive, self.store.instance_minecraft_root(instance["id"]),
                on_progress=self._show_import_progress,
            )
            instance.update(
                version=metadata["game_version"], minecraft_version=metadata["game_version"], loader=metadata["loader"],
                loader_version=metadata["loader_version"], installed_files=metadata["installed_files"],
                pack_format=metadata["format"], install_state="imported", ready=False, install_error="",
            )
            if not metadata.get("complete", True):
                missing = metadata.get("missing_files", [])
                instance["missing_files"] = missing
                instance["recovery_action"] = metadata.get(
                    "recovery_action", "Retry the import to recover missing files"
                )
                instance["install_state"] = "incomplete"
                instance["install_error"] = (
                    f"Missing {len(missing)} required {display_name} file(s). {instance['recovery_action']}"
                )
                self.store.save(self.state)
                self.instance_status_label.setText(f"Incomplete: {instance['name']} — recovery required")
                self.diagnostic_hint_label.setText(instance["install_error"])
                return
            installer_method = getattr(self.installer, "install_modpack", None)
            if not callable(installer_method):
                raise UnsupportedModrinthPack(
                    f"The configured installer cannot prepare {metadata.get('loader', 'this')} packs"
                )
            installed_version = installer_method(
                instance, self.store.instance_minecraft_root(instance["id"]), metadata, self._show_import_progress
            )
            if installed_version:
                instance["installed_version"] = installed_version
            ready = bool(self.player.is_ready(instance, self.store.instance_minecraft_root(instance["id"])))
            instance["ready"] = ready
            instance["install_state"] = "ready" if ready else "incomplete"
            if not ready:
                instance["install_error"] = "Required Minecraft, NeoForge, or runtime files are incomplete"
            self.store.save(self.state)
            self.instance_status_label.setText(
                f"Ready: {instance['name']} ({instance['version']})" if ready
                else f"Incomplete: {instance['name']} — retry preparation"
            )
            self.diagnostic_hint_label.setText("Imported Modrinth pack; Play is available." if ready else instance["install_error"])
        except (ModrinthPackError, UnsupportedModrinthPack, CurseForgePackError, OSError, RuntimeError) as error:
            instance["ready"] = False
            instance["install_state"] = "failed"
            instance["install_error"] = str(error) or f"{display_name} pack import failed"
            self.store.save(self.state)
            self.instance_status_label.setText(f"Import failed: {instance['install_error']}")
            self.diagnostic_hint_label.setText(
                (
                    "Choose a supported CurseForge exported ZIP and retry the import."
                    if provider == "curseforge"
                    else "Choose a supported Modrinth Fabric, Quilt, Forge, or NeoForge .mrpack and retry the import."
                )
            )
        finally:
            self._refresh_install_button()
            self._refresh_play_button()

    def _install_local_optifine(self) -> None:
        """Prepare a player-selected OptiFine jar for the selected instance."""
        instance = self._selected_instance()
        if self._mutation_blocked(instance) or self._session_controls_locked or self.install_worker is not None:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Install local OptiFine release", "", "OptiFine jars (*.jar);;All files (*)"
        )
        if not filename:
            return
        self._set_session_controls_locked(True)
        instance["install_state"] = "installing"
        instance["install_error"] = ""
        instance["ready"] = False
        self.store.save(self.state)
        self.instance_status_label.setText(f"Preparing OptiFine for {instance['name']}…")
        try:
            result = self.optifine_installer.prepare(
                instance, self.store.instance_minecraft_root(instance["id"]), Path(filename),
                on_progress=self._show_import_progress,
            )
            instance.update(result)
            instance["ready"] = bool(self.player.is_ready(instance, self.store.instance_minecraft_root(instance["id"])))
            instance["install_state"] = "ready" if instance["ready"] else "incomplete"
            if not instance["ready"]:
                instance["install_error"] = "OptiFine was copied but the managed runtime is incomplete"
            self.store.save(self.state)
            self.instance_status_label.setText(
                f"Ready: {instance['name']} ({instance.get('optifine_version', 'OptiFine')})"
                if instance["ready"] else f"Incomplete: {instance['name']} — retry preparation"
            )
            self.diagnostic_hint_label.setText(
                "Local OptiFine prepared; Play is available." if instance["ready"] else instance["install_error"]
            )
        except (OptiFineError, OSError, RuntimeError) as error:
            instance["ready"] = False
            instance["install_state"] = "failed"
            instance["install_error"] = str(error) or "OptiFine preparation failed"
            self.store.save(self.state)
            self.instance_status_label.setText(f"OptiFine preparation failed: {instance['install_error']}")
            self.diagnostic_hint_label.setText(
                "Choose an official local OptiFine jar for a verified vanilla or Forge combination."
            )
        finally:
            self._set_session_controls_locked(False)
            self._refresh_install_button()
            self._refresh_play_button()

    def _update_selected_pack(self) -> None:
        """Explicitly replace a Modrinth or CurseForge instance from an archive."""
        instance = self._selected_instance()
        provider = instance.get("provider") if instance else None
        if provider not in {"modrinth", "curseforge"}:
            self.diagnostic_hint_label.setText("Select an installed Modrinth or CurseForge pack before updating.")
            return
        if self._mutation_blocked(instance) or self._session_controls_locked or self.install_worker is not None:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Update imported pack", "",
            "Modrinth packs (*.mrpack);;CurseForge packs (*.zip);;All files (*)"
        )
        if not filename:
            return
        self._set_session_controls_locked(True)
        instance["install_state"] = "updating"
        instance["install_error"] = ""
        self.store.save(self.state)
        try:
            updater = self.modrinth_updater if provider == "modrinth" else self.curseforge_updater
            result = updater.update(
                instance, self.store.instance_minecraft_root(instance["id"]), Path(filename),
                release_id=str(instance.get("pending_pack_release_id", "")),
                on_progress=self._show_import_progress,
                confirm_local_changes=lambda paths: QMessageBox.question(
                    self, "Local changes detected",
                    "This update will replace pack files and may affect local changes:\n\n" + "\n".join(paths)
                    + "\n\nContinue?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                ) == QMessageBox.StandardButton.Yes,
            )
            instance["ready"] = bool(self.player.is_ready(instance, self.store.instance_minecraft_root(instance["id"])))
            if not instance["ready"]:
                raise ModrinthPackUpdateError("Updated files are incomplete; recover from the recorded backup")
            instance["install_state"] = "ready"
            self.store.save(self.state)
            self.instance_status_label.setText(f"Updated: {instance['name']}")
            self.diagnostic_hint_label.setText(f"Update complete; backup saved at {result['backup']}")
        except (ModrinthPackUpdateError, ModrinthPackError, OSError, RuntimeError) as error:
            instance["ready"] = False
            instance["install_state"] = "failed"
            instance["install_error"] = str(error) or "Modrinth pack update failed"
            self.store.save(self.state)
            self.instance_status_label.setText(f"Update failed: {instance['install_error']}")
            self.diagnostic_hint_label.setText("The previous instance is recoverable from its recorded backup; retry or recover.")
        finally:
            self._set_session_controls_locked(False)
            self._refresh_play_button()

    def _update_selected_modrinth_pack(self) -> None:
        self._update_selected_pack()

    def _update_selected_curseforge_pack(self) -> None:
        self._update_selected_pack()

    def _recover_selected_modrinth_pack(self) -> None:
        instance = self._selected_instance()
        provider = instance.get("provider") if instance else None
        if provider not in {"modrinth", "curseforge"}:
            return
        if self._mutation_blocked(instance) or self._session_controls_locked:
            return
        self._set_session_controls_locked(True)
        try:
            updater = self.modrinth_updater if provider == "modrinth" else self.curseforge_updater
            updater.recover(instance, self.store.instance_minecraft_root(instance["id"]))
            self.store.save(self.state)
            self.instance_status_label.setText(f"Recovered: {instance['name']}")
            self.diagnostic_hint_label.setText("The previous Modrinth release and worlds were restored.")
        except (ModrinthPackUpdateError, OSError, RuntimeError) as error:
            instance["install_error"] = str(error) or "Modrinth update recovery failed"
            self.store.save(self.state)
            self.diagnostic_hint_label.setText(instance["install_error"])
        finally:
            self._set_session_controls_locked(False)
            self._refresh_play_button()

    def _recover_selected_curseforge_pack(self) -> None:
        self._recover_selected_modrinth_pack()

    def _show_import_progress(self, status: str, current: int, maximum: int) -> None:
        if status:
            self.instance_status_label.setText(status)
        if maximum > 0:
            self.install_progress.setRange(0, maximum)
            self.install_progress.setValue(max(0, current))

    def _mutation_blocked(self, instance: dict | None, *, report: bool = True) -> bool:
        if instance is None:
            return True
        instance_id = instance.get("id")
        active_id = self.installing_instance.get("id") if self.installing_instance else None
        running_id = self.game_instance.get("id") if self.game_instance else None
        if instance_id in {active_id, running_id, self._operation_instance_id}:
            if report:
                self.diagnostic_hint_label.setText(
                    "This instance is active; wait until its preparation or game exits."
                )
            return True
        if instance.get("install_state") == "installing":
            if report:
                self.diagnostic_hint_label.setText(
                    "This instance is being prepared; wait until preparation finishes."
                )
            return True
        return False

    def _unique_instance_name(self, requested: str, *, exclude_id: str | None = None) -> str:
        existing = {
            str(instance.get("name", "")).casefold()
            for instance in self.state.get("instances", [])
            if instance.get("id") != exclude_id
        }
        candidate = requested.strip() or "Unnamed setup"
        if candidate.casefold() not in existing:
            return candidate
        suffix = 2
        while f"{candidate} ({suffix})".casefold() in existing:
            suffix += 1
        return f"{candidate} ({suffix})"

    def _rename_selected_instance(self) -> None:
        instance = self._selected_instance()
        if self._mutation_blocked(instance):
            return
        current_name = str(instance.get("name", "Unnamed setup"))
        name, accepted = QInputDialog.getText(self, "Rename instance", "Instance name", text=current_name)
        if not accepted:
            return
        name = name.strip()
        if not name or name.casefold() == current_name.casefold():
            return
        instance["name"] = self._unique_instance_name(name, exclude_id=instance["id"])
        row = self.instance_list.currentRow()
        if row >= 0:
            self.instance_list.item(row).setText(instance["name"])
        self.store.save(self.state)
        self._rebuild_setup_selector(selected=instance["id"])
        self.instance_status_label.setText(f"Selected instance: {instance['name']}")

    def _duplicate_selected_instance(self) -> None:
        instance = self._selected_instance()
        if self._mutation_blocked(instance):
            return
        source_id = str(instance["id"])
        destination_id = str(uuid.uuid4())
        source_root = self.store.instance_root(source_id)
        destination_root = self.store.instances_root / destination_id
        try:
            shutil.copytree(source_root, destination_root)
        except OSError as error:
            self.diagnostic_hint_label.setText(f"Could not duplicate instance: {error}")
            return
        duplicate = dict(instance)
        duplicate["id"] = destination_id
        duplicate["name"] = self._unique_instance_name(f"Copy of {instance.get('name', 'Unnamed setup')}")
        duplicate["install_state"] = instance.get("install_state", "ready")
        self.state["instances"].append(duplicate)
        self.store.save(self.state)
        self._add_instance_item(duplicate)
        self.instance_list.setCurrentRow(self.instance_list.count() - 1)

    def _delete_selected_instance(self) -> None:
        instance = self._selected_instance()
        if self._mutation_blocked(instance):
            return
        name = str(instance.get("name", "Unnamed setup"))
        answer = QMessageBox.question(
            self,
            "Delete instance",
            f"Delete {name} and remove its worlds and saved data?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        instance_id = str(instance["id"])
        try:
            root = self.store.instance_root(instance_id)
            shutil.rmtree(root)
        except OSError as error:
            self.diagnostic_hint_label.setText(f"Could not delete instance: {error}")
            return
        self.state["instances"] = [item for item in self.state["instances"] if item.get("id") != instance_id]
        self.state["automatic_instances"] = {
            version: value for version, value in self.state.get("automatic_instances", {}).items()
            if value != instance_id
        }
        if self.state.get("selected_instance_id") == instance_id:
            self.state["selected_instance_id"] = ""
        if self.state.get("selected_setup_id") == instance_id:
            self.state["selected_setup_id"] = ""
        self.store.save(self.state)
        row = self.instance_list.currentRow()
        self.instance_list.takeItem(row)
        self._rebuild_setup_selector(selected=self.state.get("selected_setup_id") or None)
        if self.instance_list.count():
            self.instance_list.setCurrentRow(min(row, self.instance_list.count() - 1))
        else:
            self._select_instance(None, None)

    def _add_instance_item(self, instance: dict) -> None:
        item = QListWidgetItem(str(instance["name"]))
        item.setData(Qt.ItemDataRole.UserRole, instance["id"])
        self.instance_list.addItem(item)
        self._rebuild_setup_selector(selected=instance["id"])

    def _select_instance(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            if self._preserve_lifecycle_status():
                return
            self.instance_status_label.setText("No instance selected")
            self.diagnostic_hint_label.clear()
            self.open_folder_button.setEnabled(False)
            self.save_log_button.setEnabled(False)
            self.install_button.setEnabled(False)
            self.play_button.setEnabled(False)
            self._refresh_instance_mutation_buttons()
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
        self._refresh_instance_mutation_buttons()
        self._refresh_mods_panel()
        self._preserve_lifecycle_status()

    def _search_modrinth_mods(self) -> None:
        instance = self._selected_instance()
        query = self.mod_search_input.text().strip()
        if instance is None:
            self.mod_search_status.setText("Select an instance before searching for mods.")
            return
        if not query:
            self.mod_search_status.setText("Enter a mod name or search term.")
            return
        game_version = instance.get("minecraft_version") or instance.get("version")
        loader = instance.get("loader")
        if not isinstance(game_version, str) or not isinstance(loader, str):
            self.mod_search_status.setText("This instance has no verified game and loader combination.")
            return
        try:
            results = self.modrinth_catalog.search_mods(query, game_version=game_version, loader=loader)
        except (ModrinthCatalogError, OSError, RuntimeError) as error:
            self.mod_search_results.clear()
            self.mod_search_status.setText(f"Mod search failed: {error}")
            return
        self.mod_search_results.clear()
        self.mod_release_selector.clear()
        self.mod_install_button.setEnabled(False)
        for result in results:
            item = QListWidgetItem(str(result.get("title") or result.get("slug") or result.get("project_id")))
            item.setData(Qt.ItemDataRole.UserRole, result)
            item.setToolTip(str(result.get("description", "")))
            self.mod_search_results.addItem(item)
        self.mod_search_status.setText(
            f"{len(results)} compatible Modrinth mod(s) found." if results else "No compatible Modrinth mods matched."
        )

    def _select_modrinth_mod(self, current, _previous=None) -> None:
        self.mod_release_selector.clear()
        self.mod_install_button.setEnabled(False)
        if current is None:
            return
        instance = self._selected_instance()
        result = current.data(Qt.ItemDataRole.UserRole) or {}
        project_id = str(result.get("project_id") or result.get("id") or "")
        game_version = instance.get("minecraft_version") or instance.get("version") if instance else ""
        loader = instance.get("loader") if instance else ""
        if not project_id or not game_version or not loader:
            return
        try:
            releases = self.modrinth_catalog.releases(project_id, game_version=game_version, loader=loader)
        except (ModrinthCatalogError, OSError, RuntimeError) as error:
            self.mod_search_status.setText(f"Could not load mod releases: {error}")
            return
        for release in releases:
            if game_version in release.game_versions and loader in release.loaders:
                self.mod_release_selector.addItem(
                    f"{release.version_number or release.name} · {release.file_name}", release
                )
        self.mod_install_button.setEnabled(self.mod_release_selector.count() > 0)
        self.mod_search_status.setText(f"{self.mod_release_selector.count()} compatible release(s) available.")

    def _install_selected_modrinth_mod(self) -> None:
        instance = self._selected_instance()
        release = self.mod_release_selector.currentData(Qt.ItemDataRole.UserRole)
        if self._mutation_blocked(instance) or instance is None or not isinstance(release, ModrinthRelease):
            return
        self.mod_install_button.setEnabled(False)
        try:
            entries = self.mod_installer.install(
                instance, self.store.instance_minecraft_root(instance["id"]), release,
                on_progress=lambda status, _current, _maximum: self.mod_search_status.setText(status),
            )
            instance.setdefault("mods", []).extend(entries)
            instance["modified"] = True
            self.store.save(self.state)
            self._refresh_mods_panel()
            if instance.get("provider"):
                self.mods_warning_label.setText(
                    "Added Modrinth mod. This curated pack is now marked modified; compatibility is not guaranteed."
                )
            self.mod_search_status.setText(f"Installed {len(entries)} mod and required dependency file(s).")
        except (ModrinthModInstallError, ModrinthCatalogError, OSError, RuntimeError) as error:
            self.mod_search_status.setText(f"Mod installation failed: {error}. Retry when the files are available.")
        finally:
            self.mod_install_button.setEnabled(self.mod_release_selector.count() > 0)

    _search_mods = _search_modrinth_mods
    _install_selected_mod = _install_selected_modrinth_mod

    def _refresh_mods_panel(self) -> None:
        instance = self._selected_instance()
        selected_mod_id = self.mods_list.currentItem().data(Qt.ItemDataRole.UserRole) if self.mods_list.currentItem() else None
        self.mods_list.clear()
        if instance is None:
            self.mods_instance_label.setText("Select an instance to manage its mods.")
            self.mods_warning_label.clear()
            self._refresh_mod_buttons()
            return
        modified = bool(instance.get("modified"))
        self.mods_instance_label.setText(
            f"{instance.get('name', 'Instance')} · {instance.get('version') or 'version not pinned'}"
            + (" · Modified curated pack" if modified else "")
        )
        if instance.get("provider") and modified:
            self.mods_warning_label.setText(
                "This curated pack has been modified. Added local mods may be incompatible with its release."
            )
        else:
            self.mods_warning_label.clear()
        for mod in instance.get("mods", []):
            enabled = bool(mod.get("enabled", True))
            verified = "verified" if mod.get("metadata_verified") and mod.get("compatible") is True else "unverified"
            item = QListWidgetItem(f"{'✓' if enabled else '○'} {mod.get('name', mod.get('filename', 'mod'))} · {verified}")
            item.setData(Qt.ItemDataRole.UserRole, mod.get("id"))
            item.setToolTip(str(mod.get("compatibility_reason", "")))
            self.mods_list.addItem(item)
            if selected_mod_id and mod.get("id") == selected_mod_id:
                self.mods_list.setCurrentItem(item)
        self._refresh_mod_buttons()

    def _refresh_mod_buttons(self) -> None:
        instance = self._selected_instance()
        blocked = self._mutation_blocked(instance, report=False) if instance else True
        has_mod = instance is not None and self.mods_list.currentRow() >= 0
        enabled = instance is not None and not blocked and not self._session_controls_locked
        self.mod_search_input.setEnabled(enabled)
        self.mod_search_button.setEnabled(enabled)
        self.mod_search_results.setEnabled(enabled)
        self.mod_release_selector.setEnabled(enabled)
        self.mod_install_button.setEnabled(enabled and self.mod_release_selector.count() > 0)
        self.import_mod_button.setEnabled(enabled)
        self.toggle_mod_button.setEnabled(enabled and has_mod)
        self.remove_mod_button.setEnabled(enabled and has_mod)
        if has_mod:
            mod = instance.get("mods", [])[self.mods_list.currentRow()]
            self.toggle_mod_button.setText("Disable selected" if mod.get("enabled", True) else "Enable selected")

    def _import_local_mod(self) -> None:
        instance = self._selected_instance()
        if self._mutation_blocked(instance) or self.store.recovery_required:
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Import local mod JAR", "", "Minecraft mods (*.jar);;All files (*)")
        if not filename:
            return
        source = Path(filename)
        metadata = inspect_mod_jar(source, game_version=instance.get("version"), loader=instance.get("loader"))
        if metadata.get("compatible") is False:
            self.mods_warning_label.setText(f"Cannot import {source.name}: {metadata['compatibility_reason']}")
            return
        try:
            target = copy_mod_to_instance(source, self.store.instance_minecraft_root(instance["id"]))
        except (OSError, ValueError) as error:
            self.mods_warning_label.setText(f"Could not import {source.name}: {error}")
            return
        mod = dict(metadata)
        mod.update({"id": f"local:{target.name}", "filename": target.name, "path": str(target.relative_to(self.store.instance_minecraft_root(instance["id"]))),
                    "enabled": True, "source": "local", "source_path": str(source)})
        instance.setdefault("mods", []).append(mod)
        instance["modified"] = True
        self.store.save(self.state)
        self._refresh_mods_panel()
        if metadata.get("compatible") is None:
            self.mods_warning_label.setText(
                f"Imported {source.name}, but metadata could not verify compatibility. Review it before playing."
            )
        elif instance.get("provider"):
            self.mods_warning_label.setText("Added local mod. This curated pack is now marked modified; compatibility is not guaranteed.")

    def _toggle_selected_mod(self) -> None:
        instance = self._selected_instance()
        row = self.mods_list.currentRow()
        if self._mutation_blocked(instance) or instance is None or row < 0:
            return
        mod = instance.get("mods", [])[row]
        root = self.store.instance_minecraft_root(instance["id"])
        current = root / str(mod.get("path", ""))
        enabled = not bool(mod.get("enabled", True))
        destination = root / ("mods" if enabled else "mods-disabled") / str(mod.get("filename", current.name))
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if current.exists():
                current.replace(destination)
            else:
                self.mods_warning_label.setText("The selected mod file is missing; restore it before enabling it.")
                return
        except OSError as error:
            self.mods_warning_label.setText(f"Could not change mod state: {error}")
            return
        mod["enabled"] = enabled
        mod["path"] = str(destination.relative_to(root))
        self.store.save(self.state)
        self._refresh_mods_panel()

    def _remove_selected_mod(self) -> None:
        instance = self._selected_instance()
        row = self.mods_list.currentRow()
        if self._mutation_blocked(instance) or instance is None or row < 0:
            return
        mod = instance.get("mods", [])[row]
        root = self.store.instance_minecraft_root(instance["id"])
        try:
            (root / str(mod.get("path", ""))).unlink(missing_ok=True)
        except OSError as error:
            self.mods_warning_label.setText(f"Could not remove mod: {error}")
            return
        instance["mods"] = [item for item in instance.get("mods", []) if item is not mod]
        instance["modified"] = True
        self.store.save(self.state)
        self._refresh_mods_panel()

    def _refresh_instance_mutation_buttons(self) -> None:
        instance = self._selected_instance()
        blocked = self._mutation_blocked(instance, report=False) if instance is not None else True
        enabled = instance is not None and not blocked and not self._session_controls_locked
        self.rename_instance_button.setEnabled(enabled)
        self.duplicate_instance_button.setEnabled(enabled)
        self.delete_instance_button.setEnabled(enabled)

    def _set_session_controls_locked(self, locked: bool) -> None:
        """Keep the active session target and launch inputs stable."""
        self._session_controls_locked = locked
        for control in (
            self.username_input,
            self.setup_selector,
            self.setup_search_input,
            self.settings_button,
            self.instance_list,
            self.instance_name_input,
            self.create_instance_button,
            self.install_button,
            self.install_optifine_button,
            self.update_modpack_button,
            self.recover_modpack_button,
            self.import_modpack_button,
            self.import_curseforge_button,
            self.rename_instance_button,
            self.duplicate_instance_button,
            self.delete_instance_button,
            self.import_mod_button,
            self.toggle_mod_button,
            self.remove_mod_button,
            self.mod_search_input,
            self.mod_search_button,
            self.mod_search_results,
            self.mod_release_selector,
            self.mod_install_button,
        ):
            control.setEnabled(not locked)
        self._refresh_play_button()
        self._refresh_instance_mutation_buttons()

    def _preserve_lifecycle_status(self) -> bool:
        if self.game_process is None:
            return False
        if self.game_instance is not None:
            self.instance_status_label.setText(f"Running: {self.game_instance['name']}")
        else:
            self.instance_status_label.setText("A Minecraft game is already running")
        self.diagnostic_hint_label.setText(
            "Another Minecraft game is already running; Play is unavailable until it exits."
        )
        self.play_button.setEnabled(False)
        return True

    def _record_diagnostic(self, instance: dict | None, message: str) -> None:
        self.last_diagnostic_message = message
        if instance is not None:
            instance["last_event"] = message
            instance["last_event_at"] = datetime.now(timezone.utc).isoformat()
            self.store.save(self.state)

    def _open_instance_folder(self) -> None:
        instance = self._diagnostic_instance()
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
            f"Launcher version: {__version__}",
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
        instance = self._diagnostic_instance()
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

    def _diagnostic_instance(self) -> dict | None:
        """Keep lifecycle diagnostics attached to the game that produced them."""
        if self.game_instance is not None:
            return self.game_instance
        if self.last_game_instance is not None:
            return self.last_game_instance
        return self._selected_instance()

    def _selected_version(self) -> str | None:
        value = self.setup_selector.currentData(Qt.ItemDataRole.UserRole)
        if isinstance(value, str) and value.startswith("version:"):
            return value.removeprefix("version:")
        return None

    def _ensure_automatic_instance(self, version: str) -> dict:
        validate_version_id(version)
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
        if self.install_worker is not None or self._closing:
            return
        instance = self._selected_instance()
        if instance is None:
            return
        self._operation_instance_id = instance["id"]
        self._operation_selector_value = self.setup_selector.currentData(Qt.ItemDataRole.UserRole)
        self.installing_instance = instance
        instance["install_state"] = "installing"
        instance["install_error"] = ""
        instance["ready"] = False
        self.store.save(self.state)
        self._set_session_controls_locked(True)
        self.diagnostic_hint_label.setText(
            "Preparing missing Minecraft files and runtime; an internet connection may be required."
        )
        self.install_progress.setValue(0)
        self.install_progress.setRange(0, 100)
        self.install_progress.show()
        self.instance_status_label.setText(f"Installing {instance['name']}…")
        self.install_worker = InstallWorker(
            self.installer,
            instance,
            self.store.instance_minecraft_root(instance["id"]),
        )
        _ACTIVE_INSTALL_WORKERS.add(self.install_worker)
        self.install_worker.version_resolved.connect(self._persist_version_for_install)
        self.install_worker.progress.connect(self._show_install_progress)
        self.install_worker.succeeded.connect(self._installation_succeeded)
        self.install_worker.failed.connect(self._installation_failed)
        self.install_worker.finished.connect(self._installation_finished)
        self.install_worker.finished.connect(
            lambda worker=self.install_worker: _release_install_worker(worker)
        )
        self.install_worker.start()

    def _persist_version(self, instance: dict, version: str) -> None:
        instance["version"] = version
        instance["ready"] = False
        instance["install_state"] = "installing"
        self.store.save(self.state)

    def _persist_version_for_install(self, version: str) -> None:
        if self._closing:
            return
        instance = self.installing_instance
        if instance is None or instance.get("id") != self._operation_instance_id:
            return
        self._persist_version(instance, version)
        if self.install_worker is not None:
            self.install_worker.acknowledge_version()

    def _show_install_progress(self, status: str, progress: int, maximum: int) -> None:
        if self._closing:
            return
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
        if self._closing:
            return
        instance = self.installing_instance
        if instance is None or instance.get("id") != self._operation_instance_id:
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
        self.diagnostic_hint_label.clear()
        if self._launch_after_prepare and instance.get("id") == self._operation_instance_id:
            self._launch_after_prepare = False
            username = self._operation_username or str(self.state.get("username", "")).strip()
            memory_gib = self._operation_memory_gib
            if memory_gib is not None:
                self._launch_ready_instance(instance, username, memory_gib)

    def _installation_failed(self, message: str) -> None:
        if self._closing:
            return
        instance = self.installing_instance
        if instance is None or instance.get("id") != self._operation_instance_id:
            return
        instance["ready"] = False
        instance["install_state"] = "failed"
        instance["install_error"] = message
        self._record_diagnostic(instance, f"Installation failed: {message}")
        self.instance_status_label.setText(f"Installation failed: {message}")
        self.diagnostic_hint_label.setText(
            "Press Retry on Play to prepare this setup again with the same pinned version."
        )
        if self._launch_after_prepare:
            self._launch_after_prepare = False
            self._operation_instance_id = None
            self._operation_username = None
            self._operation_memory_gib = None
            self.game_registry.release()

    def _installation_finished(self) -> None:
        if self._closing:
            return
        worker = self.install_worker
        self.install_worker = None
        if worker is not None:
            worker.deleteLater()
        self.installing_instance = None
        self.install_progress.hide()
        if not self._launch_after_prepare:
            self._operation_instance_id = None
        self.install_button.setEnabled(self.instance_list.currentItem() is not None)
        self.setup_selector.setEnabled(True)
        self.setup_search_input.setEnabled(True)
        self._operation_selector_value = None
        self._refresh_install_button()
        if self.game_process is None and not self._launch_after_prepare:
            self._set_session_controls_locked(False)
        else:
            self._refresh_play_button()
        self._refresh_instance_mutation_buttons()

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
            self.play_button.setEnabled(
                not self._session_controls_locked and self.install_worker is None and self.game_process is None
            )
            self.play_button.setText("▶  Play")
            return
        available = bool(
            instance and instance.get("install_state") != "incomplete"
            and not self._session_controls_locked and self.install_worker is None and self.game_process is None
        )
        self.play_button.setEnabled(available)
        if instance and (instance.get("install_error") or instance.get("install_state") == "interrupted"):
            self.play_button.setText("↻  Retry")
        else:
            self.play_button.setText("▶  Play")

    def _play_selected_instance(self) -> None:
        if self.install_worker is not None or self._session_controls_locked:
            return
        instance = self._selected_instance()
        selected_version = self._selected_version()
        if instance is None and not selected_version:
            return
        if self.game_process is not None:
            self.instance_status_label.setText("A Minecraft game is already running")
            return
        if not self.game_registry.acquire():
            self.instance_status_label.setText("A Minecraft game is already running")
            self._waiting_for_game_lock = True
            self.game_poll_timer.start()
            self.play_button.setEnabled(False)
            return
        candidate_username = self.username_input.text().strip()
        if candidate_username != str(self.state.get("username", "")):
            self._save_username()
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
        self._operation_instance_id = instance["id"]
        self._operation_selector_value = self.setup_selector.currentData(Qt.ItemDataRole.UserRole)
        self._operation_username = username
        self._operation_memory_gib = memory_gib
        self._set_session_controls_locked(True)
        ready = bool(instance.get("ready"))
        if ready and hasattr(self.player, "is_ready"):
            try:
                ready = bool(self.player.is_ready(instance, self.store.instance_minecraft_root(instance["id"])))
            except Exception as error:
                self.game_registry.release()
                self._operation_instance_id = None
                self._operation_username = None
                self._operation_memory_gib = None
                self._set_session_controls_locked(False)
                self.instance_status_label.setText(f"Play failed: {error}")
                self.diagnostic_hint_label.setText("Check the instance diagnostic log before retrying.")
                self._refresh_play_button()
                return
        if not ready:
            self._launch_after_prepare = True
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
            self._operation_instance_id = None
            self._operation_username = None
            self._operation_memory_gib = None
            self._set_session_controls_locked(False)
            self.instance_status_label.setText(f"Play failed: {error}")
            self._record_diagnostic(instance, f"Play failed: {error}")
            self.diagnostic_hint_label.setText("Install or retry this instance, then try Play again.")
            self._refresh_play_button()
            return
        self.game_process = process
        self.game_instance = instance
        self.last_game_instance = instance
        process_id = process.processId() if hasattr(process, "processId") else None
        if process_id:
            self.game_record = self.game_registry.remember(process_id, instance["id"])
            if self.game_record is None:
                self.game_registry.release()
                self.instance_status_label.setText("Play failed: could not verify the Minecraft process")
                self.game_process = None
                self.game_instance = None
                self._operation_instance_id = None
                self._operation_username = None
                self._operation_memory_gib = None
                self._set_session_controls_locked(False)
                self._refresh_play_button()
                return
        if self.instance_status_label.text().startswith("Starting"):
            self._game_started(instance)

    def _game_started(self, instance: dict) -> None:
        self.instance_status_label.setText(f"Running: {instance['name']}")
        self._set_session_controls_locked(True)
        self._refresh_instance_mutation_buttons()

    def _game_finished(self, instance: dict, exit_code: int, crashed: bool) -> None:
        if self.game_instance is not None and self.game_instance.get("id") != instance.get("id"):
            return
        self.game_process = None
        self.game_instance = None
        self.last_game_instance = instance
        self.game_record = None
        self.game_registry.clear()
        self.game_registry.release()
        self._operation_instance_id = None
        self._operation_username = None
        self._operation_memory_gib = None
        self._set_session_controls_locked(False)
        if crashed:
            self.instance_status_label.setText(f"Game crashed: {instance['name']} (exit {exit_code})")
            self.diagnostic_hint_label.setText("Save a diagnostic log or open the instance folder before relaunching.")
        else:
            self.instance_status_label.setText(f"Exited: {instance['name']} (exit {exit_code})")
            self.diagnostic_hint_label.setText("Save a diagnostic log if you need help with this game exit.")
        self._record_diagnostic(instance, self.instance_status_label.text())
        self._refresh_play_button()
        self._refresh_instance_mutation_buttons()

    def closeEvent(self, event) -> None:
        if self.install_worker is not None and self.installing_instance is not None:
            instance = self.installing_instance
            resolved_version = getattr(self.install_worker, "resolved_version", None)
            if not instance.get("version") and resolved_version:
                instance["version"] = resolved_version
            instance["ready"] = False
            instance["install_state"] = "interrupted"
            instance["install_error"] = "Installation interrupted; retry to continue"
            if not self.store.recovery_required:
                self.store.save(self.state)
            self._closing = True
            self._launch_after_prepare = False
            self._operation_instance_id = None
            self.install_worker.cancel()
            self.game_registry.release()
            event.accept()
            self.game_poll_timer.stop()
            if self.game_process is None:
                self.game_registry.clear()
            super().closeEvent(event)
            return
        if self.discovery_worker is not None and self.discovery_worker.isRunning():
            self.discovery_worker.requestInterruption()
            self.instance_status_label.setText("Release discovery is stopping…")
            event.accept()
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
    version_resolved = Signal(str)

    def __init__(self, installer, instance: dict, minecraft_directory: Path) -> None:
        super().__init__()
        self.installer = installer
        self.instance = instance
        self.minecraft_directory = minecraft_directory
        self._version_ack = threading.Event()
        self._cancelled = threading.Event()
        self.resolved_version: str | None = None

    def cancel(self) -> None:
        self._cancelled.set()
        self.requestInterruption()

    def acknowledge_version(self) -> None:
        self._version_ack.set()

    def run(self) -> None:
        try:
            self._raise_if_cancelled()
            if not self.instance.get("version"):
                version = self.installer.resolve_version()
                self._raise_if_cancelled()
                self.resolved_version = version
                self.version_resolved.emit(version)
                self._version_ack.wait(15)
                self._raise_if_cancelled()
                if not self.instance.get("version"):
                    raise RuntimeError("Minecraft version resolution was not acknowledged")
            self.installer.install(
                self.instance,
                self.minecraft_directory,
                self._emit_progress,
            )
            self._raise_if_cancelled()
        except Exception as error:
            if not isinstance(error, InstallationCancelled):
                self.failed.emit(str(error) or "unknown installation error")
        else:
            self.succeeded.emit()

    def _raise_if_cancelled(self) -> None:
        if self._cancelled.is_set() or self.isInterruptionRequested():
            raise InstallationCancelled()

    def _emit_progress(self, status: str, progress: int, maximum: int) -> None:
        self._raise_if_cancelled()
        self.progress.emit(status, progress, maximum)


class InstallationCancelled(Exception):
    """Internal worker signal used to suppress results after launcher close."""


class NewsWorker(QThread):
    fetched = Signal(list)
    failed = Signal(str)

    def __init__(self, provider) -> None:
        super().__init__()
        self.provider = provider

    def run(self) -> None:
        try:
            items = self.provider.fetch()
            if self.isInterruptionRequested():
                return
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise ValueError("news provider returned an invalid response")
            self.fetched.emit(items[:6])
        except Exception as error:
            if not self.isInterruptionRequested():
                self.failed.emit(str(error) or "unknown news error")


def _release_install_worker(worker: QThread) -> None:
    _ACTIVE_INSTALL_WORKERS.discard(worker)


class VersionDiscoveryWorker(QThread):
    discovered = Signal(list)
    failed = Signal(str)

    def __init__(self, installer, *, select_latest: bool = False) -> None:
        super().__init__()
        self.installer = installer
        self.select_latest = select_latest

    def run(self) -> None:
        try:
            if self.isInterruptionRequested():
                return
            if hasattr(self.installer, "discover_versions"):
                versions = self.installer.discover_versions()
            else:
                versions = []
            if self.isInterruptionRequested():
                return
            if self.select_latest and versions and hasattr(self.installer, "resolve_version"):
                latest = self.installer.resolve_version()
                if self.isInterruptionRequested():
                    return
                versions = sorted(
                    versions,
                    key=lambda entry: (entry if isinstance(entry, str) else entry.get("id")) != latest,
                )
            if not self.isInterruptionRequested():
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
