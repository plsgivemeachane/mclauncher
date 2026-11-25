from __future__ import annotations

import json
import re
import shutil
import sys
import threading
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, QUrl, Qt, Signal, QPoint
from PySide6.QtGui import QDesktopServices, QPainter, QPixmap, QColor, QLinearGradient
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
    QButtonGroup,
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QMainWindow,
    QMenu,
    QProgressBar,
    QPushButton,
    QMessageBox,
    QStackedWidget,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .persistence import LauncherStore, game_directory_for
from .audit import compact_instance, file_facts, inventory
from .installer import MinecraftInstaller, MinecraftPlayer, validate_version_id
from .memory import default_memory_gib, validate_memory_gib, whole_physical_memory_gib
from .lifecycle import GameProcessRegistry
from .modpack import (
    CurseForgePackError,
    CurseForgePackImporter,
    CurseForgeProvider,
    ModrinthPackError,
    ModrinthPackImporter,
    ModrinthPackUpdateError,
    ModrinthPackUpdater,
    UnsupportedModrinthPack,
)
from .modrinth_catalog import ModrinthCatalog, ModrinthCatalogError, ModrinthRelease
from .modrinth_mods import ModrinthModInstallError, ModrinthModInstaller
from .optifine import OptiFineError, OptiFineInstaller
from .localmods import copy_mod_to_instance, inspect_mod_jar
from .identity import USERNAME_RE, local_identity
from . import ui
from .ui import ROW_INFO_ROLE, RowDelegate, RowInfo, VersionPicker, rule, set_role

_ACTIVE_DISCOVERY_WORKERS: set[QThread] = set()
_ACTIVE_INSTALL_WORKERS: set[QThread] = set()


PACK_DETAILS_PROMPT = "Pick a pack from the results to see what it includes."


def _release_discovery_worker(worker: QThread) -> None:
    _ACTIVE_DISCOVERY_WORKERS.discard(worker)
    worker.deleteLater()


def _small_mod(mod: dict) -> dict:
    return {key: mod.get(key) for key in ("id", "filename", "path", "enabled", "source", "source_path", "version")
            if key in mod}


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
        executable = Path(sys.executable)
        executable_candidates = [
            executable.resolve().parent / "assets" / "minecraft-home.png",
            executable.parent / "assets" / "minecraft-home.png",
        ]
        for candidate in executable_candidates:
            if candidate.is_file():
                return candidate
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
        # Darken toward the bottom so the hero text and launch dock read cleanly.
        shade = QLinearGradient(0, 0, 0, height)
        shade.setColorAt(0.0, QColor(16, 19, 24, 40))
        shade.setColorAt(0.55, QColor(16, 19, 24, 70))
        shade.setColorAt(1.0, QColor(31, 35, 42, 235))
        painter.fillRect(self.rect(), shade)
        painter.end()


# Kept as an import-compatible name for callers from the original launcher.
LandscapePanel = MinecraftHomePanel


class LauncherWindow(QMainWindow):
    def __init__(self, data_root: Path | str | None = None, installer=None, player=None, game_registry=None,
                 modpack_importer=None, modrinth_catalog=None, optifine_installer=None,
                 curseforge_importer=None, mod_installer=None, modrinth_updater=None,
                 curseforge_updater=None) -> None:
        super().__init__()
        self.setWindowTitle("Minecraft Launcher")
        self.store = LauncherStore(data_root)
        self.audit = self.store.audit
        self.audit.record("app_start", version=__version__, data_root=str(self.store.root))
        self._installer_injected = installer is not None
        self.installer = installer or MinecraftInstaller()
        self.player = player or MinecraftPlayer()
        self.modpack_importer = modpack_importer or ModrinthPackImporter(provider=self.installer)
        self._modpack_importer_injected = modpack_importer is not None
        self.modrinth_updater = modrinth_updater or ModrinthPackUpdater(self.modpack_importer)
        self._modrinth_updater_injected = modrinth_updater is not None
        self.optifine_installer = optifine_installer or OptiFineInstaller()
        self._optifine_injected = optifine_installer is not None
        self.curseforge_importer = curseforge_importer or CurseForgePackImporter(
            provider=CurseForgeProvider(
                allow_public=lambda: bool(getattr(self, "state", {}).get("curseforge_public_downloads"))
            ),
            loader_resolver=getattr(self.installer, "resolve_loader", None),
        )
        self._curseforge_importer_injected = curseforge_importer is not None
        self.curseforge_updater = curseforge_updater or ModrinthPackUpdater(self.curseforge_importer)
        self._curseforge_updater_injected = curseforge_updater is not None
        for updater in (self.modrinth_updater, self.curseforge_updater):
            if hasattr(updater, "audit") and getattr(updater, "audit") is None:
                updater.audit = self.audit
        self.modrinth_catalog = modrinth_catalog or ModrinthCatalog()
        self._catalog_injected = modrinth_catalog is not None
        self._catalog_worker = None
        self._catalog_browse_worker = None
        self._catalog_browse_request = 0
        self._mod_query_request = 0
        self.mod_installer = mod_installer or ModrinthModInstaller(self.modrinth_catalog)
        self._mod_installer_injected = mod_installer is not None
        self._catalog_results = []
        self._catalog_releases = []
        self._catalog_installing = False
        self.install_worker = None
        self.installing_instance = None
        self.discovery_worker = None
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
        # Focus rings follow the keyboard, not mouse clicks or focus hand-offs.
        ui.install_focus_visibility()
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Top bar ────────────────────────────────────────────────────────
        header = QFrame(root)
        header.setObjectName("titleBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 14, 0)
        header_layout.setSpacing(0)
        brand = QLabel("mclauncher", header)
        brand.setObjectName("brandLabel")
        header_layout.addWidget(brand)
        navigation = header
        navigation_layout = header_layout
        self.settings_button = QPushButton("Settings", header)
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.clicked.connect(self._open_settings)
        self.home_nav_button = QPushButton("Home", navigation)
        self.home_nav_button.setObjectName("homeNavButton")
        self.instances_nav_button = QPushButton("Instances", navigation)
        self.instances_nav_button.setObjectName("instancesNavButton")
        self.home_nav_button.clicked.connect(lambda: self._show_page(0))
        self.instances_nav_button.clicked.connect(lambda: self._show_page(1))
        # The tab is named for what the page is about, matching its heading.
        self.browse_nav_button = QPushButton("Modpacks", navigation)
        self.browse_nav_button.setObjectName("browseNavButton")
        self.browse_nav_button.clicked.connect(lambda: self._show_page(2))
        self.mods_nav_button = QPushButton("Mods", navigation)
        self.mods_nav_button.setObjectName("modsNavButton")
        self.mods_nav_button.clicked.connect(lambda: self._show_page(3))
        self.mods_nav_button.hide()
        navigation_layout.addWidget(self.home_nav_button)
        navigation_layout.addWidget(self.instances_nav_button)
        navigation_layout.addWidget(self.browse_nav_button)
        navigation_layout.addWidget(self.mods_nav_button)
        navigation_layout.addStretch(1)
        navigation_layout.addWidget(self.settings_button)
        for button in (self.home_nav_button, self.instances_nav_button, self.browse_nav_button,
                       self.mods_nav_button, self.settings_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.home_nav_button.setAccessibleName("Home: play")
        self.instances_nav_button.setAccessibleName("Instances: manage setups")
        self.browse_nav_button.setAccessibleName("Modpacks: browse and import")
        layout.addWidget(header)

        # ── Home: artwork hero that explains the current launch target ─────
        self.content_stack = QStackedWidget(root)
        self.content_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.home_panel = QWidget(root)
        home_layout = QVBoxLayout(self.home_panel)
        home_layout.setContentsMargins(0, 0, 0, 0)
        scene = MinecraftHomePanel(self.home_panel)
        self.home_artwork = scene
        scene_layout = QVBoxLayout(scene)
        scene_layout.setContentsMargins(28, 22, 28, 18)
        scene_layout.setSpacing(4)
        scene_layout.addStretch(1)
        self.hero_eyebrow = QLabel("", scene)
        self.hero_eyebrow.setObjectName("heroEyebrow")
        self.hero_title = QLabel("", scene)
        self.hero_title.setObjectName("heroTitle")
        self.hero_title.setWordWrap(True)
        self.hero_detail = QLabel("", scene)
        self.hero_detail.setObjectName("heroDetail")
        self.hero_detail.setWordWrap(True)
        scene_layout.addWidget(self.hero_eyebrow, 0, Qt.AlignmentFlag.AlignLeft)
        scene_layout.addWidget(self.hero_title)
        scene_layout.addWidget(self.hero_detail)
        home_layout.addWidget(scene, 1)

        # ── Launch dock: shared by every page ──────────────────────────────
        launch_bar = QFrame(root)
        launch_bar.setObjectName("launchBar")
        launch_layout = QVBoxLayout(launch_bar)
        launch_layout.setContentsMargins(20, 10, 20, 12)
        launch_layout.setSpacing(6)
        self._launch_layout = launch_layout

        self.instance_status_label = ui.StatusLabel("Choose a version or setup to play", launch_bar)
        self.instance_status_label.setObjectName("instanceStatusLabel")
        self.instance_status_label.setWordWrap(True)
        self.instance_status_label.changed.connect(self._refresh_status_visibility)
        launch_layout.addWidget(self.instance_status_label)
        hint_row = QHBoxLayout()
        hint_row.setSpacing(10)
        self.diagnostic_hint_label = ui.HintLabel(launch_bar)
        self.diagnostic_hint_label.setObjectName("diagnosticHintLabel")
        hint_row.addWidget(self.diagnostic_hint_label, 1)
        self.retry_discovery_button = QPushButton("Retry", launch_bar)
        self.retry_discovery_button.setObjectName("retryDiscoveryButton")
        self.retry_discovery_button.setToolTip("Download the Minecraft version list again")
        self.retry_discovery_button.clicked.connect(self._retry_version_discovery)
        self.retry_discovery_button.hide()
        hint_row.addWidget(self.retry_discovery_button, 0, Qt.AlignmentFlag.AlignVCenter)
        launch_layout.addLayout(hint_row)
        self.install_progress = QProgressBar(launch_bar)
        self.install_progress.setObjectName("installProgress")
        self.install_progress.setRange(0, 100)
        self.install_progress.setTextVisible(False)
        self.install_progress.hide()
        launch_layout.addWidget(self.install_progress)

        controls = QGridLayout()
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(4)
        self._launch_controls = controls
        username_label = QLabel("Player name", launch_bar)
        username_label.setObjectName("usernameFieldLabel")
        self.username_field_label = username_label
        setup_label = QLabel("Version or setup", launch_bar)
        setup_label.setObjectName("setupFieldLabel")
        self.setup_field_label = setup_label
        controls.addWidget(username_label, 0, 0)
        controls.addWidget(setup_label, 0, 1)
        self.username_input = QLineEdit()
        self.username_input.setObjectName("usernameInput")
        self.username_input.setPlaceholderText("Steve")
        self.username_input.setAccessibleName("Player name")
        self.username_input.setAccessibleDescription("Your offline name in game, 3 to 16 letters, digits or underscores")
        self.username_input.setToolTip("Your offline name in game: 3–16 letters, digits or underscores")
        self.username_input.setMinimumHeight(52)
        self.username_input.setMinimumWidth(130)
        self.username_input.setMaximumWidth(240)
        self.username_input.editingFinished.connect(self._save_username)
        username_label.setBuddy(self.username_input)
        controls.addWidget(self.username_input, 1, 0)
        self.setup_selector = VersionPicker(self._describe_row, launch_bar)
        self.setup_selector.setObjectName("setupSelector")
        self.setup_selector.setAccessibleName("Version or setup")
        self.setup_selector.setAccessibleDescription(
            "What Play starts. Press Space or Alt+Down to search versions and setups.")
        self.setup_selector.setMinimumHeight(52)
        self.setup_selector.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setup_selector.currentIndexChanged.connect(self._select_setup_from_selector)
        setup_label.setBuddy(self.setup_selector)
        controls.addWidget(self.setup_selector, 1, 1)
        self.play_button = QPushButton("▶  Play", launch_bar)
        self.play_button.setObjectName("playButton")
        self.play_button.setMinimumHeight(52)
        self.play_button.clicked.connect(self._play_selected_instance)
        self.play_button.setEnabled(False)
        self.play_button.setMinimumWidth(170)
        self.play_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_folder_button = QPushButton("Open folder", launch_bar)
        self.open_folder_button.setObjectName("openFolderButton")
        self.open_folder_button.setMinimumSize(120, 52)
        self.open_folder_button.setToolTip("Open the selected instance’s Minecraft folder: screenshots, saves, mods and more")
        self.open_folder_button.clicked.connect(self._open_selected_instance_folder)
        self.open_folder_button.setEnabled(False)
        controls.addWidget(self.open_folder_button, 1, 2)
        controls.addWidget(self.play_button, 1, 3)
        controls.setColumnStretch(0, 2)
        controls.setColumnStretch(1, 5)
        controls.setColumnStretch(2, 0)
        launch_layout.addLayout(controls)
        # Search and its empty state live inside the version picker's popup.
        self.setup_search_input = QLineEdit(launch_bar)
        self.setup_search_input.setObjectName("setupSearchInput")
        self.setup_search_input.setPlaceholderText("Search, e.g. 1.20.1 or a setup name")
        self.setup_search_input.setClearButtonEnabled(True)
        self.setup_search_input.textChanged.connect(self._filter_setup_selector)
        self.selector_empty_label = QLabel(launch_bar)
        self.selector_empty_label.setObjectName("selectorEmptyLabel")
        self.selector_empty_label.setText("No versions or setups match that search")
        self.selector_empty_label.setWordWrap(True)
        self.selector_empty_label.hide()
        self.setup_selector.adopt(self.setup_search_input, self.selector_empty_label)
        self.setup_search_input.textChanged.connect(lambda _text: self.setup_selector.popup.refresh())
        self.setup_selector.currentIndexChanged.connect(lambda _index: self._refresh_hero())
        self.content_stack.addWidget(self.home_panel)

        # ── Instances: library (create and import) beside the selected setup ──
        legacy_panel = QWidget(root)
        legacy_layout = QVBoxLayout(legacy_panel)
        legacy_layout.setContentsMargins(24, 16, 24, 12)
        legacy_layout.setSpacing(10)
        self.instances_panel = legacy_panel
        heading = QLabel("Instances", legacy_panel)
        heading.setObjectName("instancesHeading")
        set_role(heading, "pageTitle")
        legacy_layout.addWidget(heading)
        instance_body = QHBoxLayout()
        instance_body.setSpacing(16)
        library_scroll = QScrollArea(legacy_panel)
        library_scroll.setObjectName("instanceLibraryScroll")
        library_scroll.setWidgetResizable(True)
        library_scroll.setFrameShape(QFrame.Shape.NoFrame)
        library_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        library_scroll.setMinimumWidth(276)
        library_panel = QWidget()
        library = QVBoxLayout(library_panel)
        library.setContentsMargins(0, 0, 8, 0)
        library.setSpacing(8)
        library_scroll.setWidget(library_panel)
        self._library_scroll = library_scroll
        instance_body.addWidget(library_scroll, 2)
        tools_scroll = QScrollArea(legacy_panel)
        tools_scroll.setObjectName("instanceToolsScroll")
        tools_scroll.setWidgetResizable(True)
        tools_scroll.setFrameShape(QFrame.Shape.NoFrame)
        tools_scroll.setMinimumWidth(300)
        tools_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tools_panel = QFrame()
        tools_panel.setObjectName("instanceToolsCard")
        set_role(tools_panel, "card")
        tools = QVBoxLayout(tools_panel)
        tools.setContentsMargins(18, 14, 18, 16)
        tools.setSpacing(8)
        tools_scroll.setWidget(tools_panel)
        self._tools_scroll = tools_scroll
        instance_body.addWidget(tools_scroll, 3)
        legacy_layout.addLayout(instance_body, 1)

        # Hidden compatibility controls used by existing handlers and tests.
        hidden_settings = QWidget(legacy_panel)
        hidden_settings.hide()
        hidden_settings_layout = QVBoxLayout(hidden_settings)
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
        hidden_settings_layout.addLayout(identity_form)
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
        self.memory_setting_error.setWordWrap(True)
        self.memory_setting_error.hide()
        memory_form.addRow("", self.memory_setting_error)
        hidden_settings_layout.addLayout(memory_form)

        self.state_recovery_label = QLabel()
        self.state_recovery_label.setObjectName("stateRecoveryLabel")
        self.state_recovery_label.setWordWrap(True)
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
        self.username_warning.hide()
        self.confirm_username_change_button = QPushButton("Confirm username change")
        self.confirm_username_change_button.setObjectName("confirmUsernameChangeButton")
        self.confirm_username_change_button.clicked.connect(self._confirm_username_change)
        self.confirm_username_change_button.hide()
        launch_layout.insertWidget(1, self.username_warning)
        launch_layout.insertWidget(2, self.confirm_username_change_button)

        # Library column: every way to get a new setup lives here.
        self.instance_list = ui.PlaceholderList()
        self.instance_list.setObjectName("instanceList")
        self.instance_list.setAccessibleName("Your setups")
        self.instance_list.set_placeholder("No setups yet", "Name one below, or import a modpack file.")
        self.instance_list.currentItemChanged.connect(self._select_instance)
        self.instance_list.setMinimumHeight(96)
        self.instance_list.setItemDelegate(RowDelegate(self._describe_instance_row, self.instance_list))
        self.instance_list.setMouseTracking(True)
        library.addWidget(self.instance_list, 1)
        self._new_setup_title = set_role(QLabel("New setup"), "sectionTitle")
        library.addWidget(self._new_setup_title)
        instance_row = QHBoxLayout()
        instance_row.setSpacing(8)
        self.instance_name_input = QLineEdit()
        self.instance_name_input.setObjectName("instanceNameInput")
        self.instance_name_input.setPlaceholderText("New setup name")
        self.instance_name_input.setAccessibleName("New setup name")
        self.instance_name_input.setToolTip("Name a new setup, then press Create")
        self.instance_name_input.returnPressed.connect(lambda: self._create_instance())
        self.create_instance_button = QPushButton("Create")
        set_role(self.create_instance_button, "primary")
        self.create_instance_button.setObjectName("createInstanceButton")
        self.create_instance_button.setAccessibleName("Create setup")
        self.create_instance_button.clicked.connect(self._create_instance)
        instance_row.addWidget(self.instance_name_input, 1)
        instance_row.addWidget(self.create_instance_button)
        # Compact windows fold both pack imports into one menu on this row,
        # so the list above keeps room for whole rows.
        self.import_pack_menu_button = QPushButton("Import")
        self.import_pack_menu_button.setObjectName("importPackMenuButton")
        self.import_pack_menu_button.setAccessibleName("Import a modpack file")
        self.import_pack_menu_button.setToolTip("Create a setup from a modpack file on this computer")
        import_menu = QMenu(self.import_pack_menu_button)
        import_menu.setStyleSheet(ui.STYLESHEET)
        import_menu.addAction("Modrinth pack (.mrpack)…", self._import_modrinth_pack)
        import_menu.addAction("CurseForge pack (.zip)…", self._import_curseforge_pack)
        self.import_pack_menu_button.setMenu(import_menu)
        self.import_pack_menu_button.hide()
        instance_row.addWidget(self.import_pack_menu_button)
        library.addLayout(instance_row)
        import_row = QHBoxLayout()
        import_row.setSpacing(8)
        self.import_modpack_button = QPushButton("Import .mrpack")
        self.import_modpack_button.setObjectName("importModpackButton")
        self.import_modpack_button.setToolTip("Create a setup from a Modrinth modpack file on this computer")
        self.import_modpack_button.clicked.connect(self._import_modrinth_pack)
        self.import_curseforge_button = QPushButton("CurseForge .zip")
        self.import_curseforge_button.setObjectName("importCurseForgeButton")
        self.import_curseforge_button.setToolTip("Create a setup from a CurseForge modpack .zip on this computer")
        self.import_curseforge_button.clicked.connect(self._import_curseforge_pack)
        import_row.addWidget(self.import_modpack_button)
        import_row.addWidget(self.import_curseforge_button)
        library.addLayout(import_row)

        # Tools card: what you can do with the selected setup, by intent.
        self.selected_instance_heading = QLabel("Select an instance")
        self.selected_instance_heading.setObjectName("selectedInstanceHeading")
        self.selected_instance_heading.setWordWrap(True)
        tools.addWidget(self.selected_instance_heading)
        self.selected_instance_description = QLabel("Pick a setup from the list, or create a new one.")
        self.selected_instance_description.setObjectName("selectedInstanceDescription")
        self.selected_instance_description.setWordWrap(True)
        summary_row = QHBoxLayout()
        summary_row.setSpacing(10)
        summary_row.addWidget(self.selected_instance_description, 1)
        # One plain state line, so the recommended action below is obvious.
        self.selected_instance_state = QLabel("")
        self.selected_instance_state.setObjectName("selectedInstanceState")
        self.selected_instance_state.hide()
        summary_row.addWidget(self.selected_instance_state, 0, Qt.AlignmentFlag.AlignTop)
        tools.addLayout(summary_row)
        primary_row = QHBoxLayout()
        primary_row.setSpacing(8)
        self.install_button = QPushButton("Install Minecraft")
        self.install_button.setObjectName("installButton")
        self.install_button.clicked.connect(self._install_selected_instance)
        self.manage_mods_button = QPushButton("Manage mods")
        self.manage_mods_button.setObjectName("manageModsButton")
        self.manage_mods_button.clicked.connect(lambda: self._show_page(3))
        primary_row.addWidget(self.install_button)
        primary_row.addWidget(self.manage_mods_button)
        tools.addLayout(primary_row)

        tools.addWidget(rule())
        tools.addWidget(set_role(QLabel("Setup"), "sectionTitle"))
        mutation_row = QHBoxLayout()
        mutation_row.setSpacing(8)
        self.rename_instance_button = QPushButton("Rename")
        self.rename_instance_button.setObjectName("renameInstanceButton")
        self.rename_instance_button.clicked.connect(self._rename_selected_instance)
        self.duplicate_instance_button = QPushButton("Duplicate")
        self.duplicate_instance_button.setObjectName("duplicateInstanceButton")
        self.duplicate_instance_button.clicked.connect(self._duplicate_selected_instance)
        self.delete_instance_button = QPushButton("Delete")
        self.delete_instance_button.setObjectName("deleteInstanceButton")
        self.delete_instance_button.clicked.connect(self._delete_selected_instance)
        set_role(self.delete_instance_button, "danger")
        mutation_row.addWidget(self.rename_instance_button)
        mutation_row.addWidget(self.duplicate_instance_button)
        mutation_row.addWidget(self.delete_instance_button)
        tools.addLayout(mutation_row)

        tools.addWidget(rule())
        tools.addWidget(set_role(QLabel("Modpack and extras"), "sectionTitle"))
        install_tools = QGridLayout()
        install_tools.setSpacing(8)
        install_tools.setColumnStretch(0, 1)
        install_tools.setColumnStretch(1, 1)
        tools.addLayout(install_tools)
        self.update_modpack_button = QPushButton("Update pack")
        self.update_modpack_button.setObjectName("updateModpackButton")
        self.update_modpack_button.clicked.connect(self._update_selected_modrinth_pack)
        install_tools.addWidget(self.update_modpack_button, 0, 0)
        self.recover_modpack_button = QPushButton("Recover update")
        self.recover_modpack_button.setObjectName("recoverModpackButton")
        self.recover_modpack_button.clicked.connect(self._recover_selected_modrinth_pack)
        install_tools.addWidget(self.recover_modpack_button, 0, 1)
        self.install_optifine_button = QPushButton("Add OptiFine jar")
        self.install_optifine_button.setObjectName("installOptifineButton")
        self.install_optifine_button.clicked.connect(self._install_local_optifine)
        install_tools.addWidget(self.install_optifine_button, 1, 0, 1, 2)

        tools.addWidget(rule())
        tools.addWidget(set_role(QLabel("Files and troubleshooting"), "sectionTitle"))
        self.open_screenshots_button = QPushButton("Open screenshots")
        self.open_screenshots_button.setObjectName("openScreenshotsButton")
        self.open_screenshots_button.clicked.connect(self._open_instance_screenshots)
        self.open_screenshots_button.setEnabled(False)
        self.save_log_button = QPushButton("Save log")
        self.save_log_button.setObjectName("saveDiagnosticLogButton")
        self.save_log_button.setToolTip("Save a diagnostic log to share when asking for help")
        self.save_log_button.clicked.connect(self._save_diagnostic_log)
        self.save_log_button.setEnabled(False)
        self._instance_quick_row = QHBoxLayout()
        self._instance_quick_row.setSpacing(8)
        self._instance_quick_row.addWidget(self.open_screenshots_button)
        self._instance_quick_row.addWidget(self.save_log_button)
        tools.addLayout(self._instance_quick_row)
        tools.addStretch(1)
        legacy_panel.setMaximumWidth(1160)
        instances_page = QWidget(root)
        instances_page_layout = QHBoxLayout(instances_page)
        instances_page_layout.setContentsMargins(0, 0, 0, 0)
        instances_page_layout.addWidget(legacy_panel)
        self.content_stack.addWidget(instances_page)

        # ── Modpacks: search online, or import a file you already have ─────
        browse_panel = QWidget(root)
        browse_layout = QVBoxLayout(browse_panel)
        browse_layout.setContentsMargins(24, 16, 24, 12)
        browse_layout.setSpacing(10)
        browse_heading = set_role(QLabel("Modpacks", browse_panel), "pageTitle")
        browse_heading.setObjectName("browseHeading")
        browse_layout.addWidget(browse_heading)
        browse_layout.addWidget(set_role(QLabel(
            "Search Modrinth and install a pack as a new setup, or import a pack file you already have.",
            browse_panel), "muted"))
        browse_search_row = QHBoxLayout()
        browse_search_row.setSpacing(8)
        self.modrinth_search_input = QLineEdit(browse_panel)
        self.modrinth_search_input.setObjectName("modrinthSearchInput")
        self.modrinth_search_input.setPlaceholderText("Search modpacks, e.g. Fabulously Optimized")
        self.modrinth_search_input.setAccessibleName("Search Modrinth modpacks")
        self.modrinth_search_input.setClearButtonEnabled(True)
        self.modrinth_search_input.returnPressed.connect(self._search_modrinth_catalog)
        self.modrinth_search_button = QPushButton("Search", browse_panel)
        self.modrinth_search_button.setObjectName("modrinthSearchButton")
        self.modrinth_search_button.clicked.connect(self._search_modrinth_catalog)
        set_role(self.modrinth_search_button, "primary")
        browse_search_row.addWidget(self.modrinth_search_input, 1)
        browse_search_row.addWidget(self.modrinth_search_button)
        browse_layout.addLayout(browse_search_row)
        browse_body = QHBoxLayout()
        browse_body.setSpacing(16)
        self.modrinth_pack_list = ui.PlaceholderList(browse_panel)
        self.modrinth_pack_list.setObjectName("modrinthPackList")
        self.modrinth_pack_list.setAccessibleName("Modpack search results")
        self.modrinth_pack_list.setMinimumHeight(150)
        self.modrinth_pack_list.set_placeholder(
            "Find a modpack", "Type a name above and press Search. Results from Modrinth appear here.")
        self.modrinth_pack_list.currentItemChanged.connect(self._select_modrinth_catalog_pack)
        self.modrinth_pack_list.setItemDelegate(RowDelegate(lambda _value, text: RowInfo(text), self.modrinth_pack_list))
        self.modrinth_pack_list.setMouseTracking(True)
        browse_body.addWidget(self.modrinth_pack_list, 1)
        details_card = QFrame(browse_panel)
        set_role(details_card, "card")
        details = QVBoxLayout(details_card)
        details.setContentsMargins(18, 16, 18, 16)
        details.setSpacing(8)
        self.modrinth_pack_details = QLabel(PACK_DETAILS_PROMPT, browse_panel)
        self.modrinth_pack_details.setObjectName("modrinthPackDetails")
        self.modrinth_pack_details.setWordWrap(True)
        details.addWidget(self.modrinth_pack_details)
        self._catalog_release_section = QWidget(details_card)
        self._catalog_release_section.setObjectName("cardBody")
        release_layout = QVBoxLayout(self._catalog_release_section)
        release_layout.setContentsMargins(0, 4, 0, 0)
        release_layout.setSpacing(6)
        release_label = set_role(QLabel("Release", browse_panel), "sectionTitle")
        release_layout.addWidget(release_label)
        self.modrinth_release_selector = QComboBox(browse_panel)
        self.modrinth_release_selector.setObjectName("modrinthReleaseSelector")
        self.modrinth_release_selector.setAccessibleName("Modpack release")
        release_label.setBuddy(self.modrinth_release_selector)
        release_layout.addWidget(self.modrinth_release_selector)
        self.modrinth_install_button = QPushButton("Install as new setup", browse_panel)
        set_role(self.modrinth_install_button, "primary")
        self.modrinth_install_button.setObjectName("modrinthInstallButton")
        self.modrinth_install_button.setEnabled(False)
        self.modrinth_install_button.clicked.connect(self._install_modrinth_catalog_release)
        release_layout.addWidget(self.modrinth_install_button)
        self._catalog_release_section.hide()
        details.addWidget(self._catalog_release_section)
        self.modrinth_catalog_status = QLabel("", browse_panel)
        self.modrinth_catalog_status.setObjectName("modrinthCatalogStatus")
        self.modrinth_catalog_status.setWordWrap(True)
        details.addWidget(self.modrinth_catalog_status)
        details.addStretch(1)
        browse_body.addWidget(details_card, 1)
        browse_layout.addLayout(browse_body, 1)
        pack_file_row = QHBoxLayout()
        pack_file_row.setSpacing(8)
        pack_file_row.addWidget(set_role(QLabel("Have a pack file?", browse_panel), "muted"))
        self.browse_import_modrinth_button = QPushButton("Import .mrpack", browse_panel)
        self.browse_import_modrinth_button.setObjectName("browseImportModrinthButton")
        self.browse_import_modrinth_button.clicked.connect(self._import_modrinth_pack)
        self.browse_import_curseforge_button = QPushButton("Import CurseForge .zip", browse_panel)
        self.browse_import_curseforge_button.setObjectName("browseImportCurseForgeButton")
        self.browse_import_curseforge_button.clicked.connect(self._import_curseforge_pack)
        pack_file_row.addWidget(self.browse_import_modrinth_button)
        pack_file_row.addWidget(self.browse_import_curseforge_button)
        pack_file_row.addStretch(1)
        browse_layout.addLayout(pack_file_row)
        browse_scroll = QScrollArea(root)
        browse_scroll.setWidgetResizable(True)
        browse_scroll.setFrameShape(QFrame.Shape.NoFrame)
        browse_scroll.setWidget(browse_panel)
        self.content_stack.addWidget(browse_scroll)

        # ── Mods: a sub-page of the selected instance ──────────────────────
        # Two mutually exclusive tasks — review what is installed, or find
        # something new — so each one gets the whole first viewport.
        mods_panel = QWidget(root)
        mods_layout = QVBoxLayout(mods_panel)
        mods_layout.setContentsMargins(24, 6, 24, 10)
        mods_layout.setSpacing(6)
        self.mods_back_button = QPushButton("‹  Back to Instances", mods_panel)
        self.mods_back_button.setObjectName("modsBackButton")
        set_role(self.mods_back_button, "back")
        self.mods_back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mods_back_button.clicked.connect(lambda: self._show_page(1))
        mods_layout.addWidget(self.mods_back_button, 0, Qt.AlignmentFlag.AlignLeft)
        mods_header = QHBoxLayout()
        mods_header.setSpacing(12)
        mods_heading = QLabel("Mods", mods_panel)
        mods_heading.setObjectName("modsHeading")
        set_role(mods_heading, "pageTitle")
        mods_header.addWidget(mods_heading)
        mods_header.addStretch(1)
        self.mods_installed_mode_button = QPushButton("Installed", mods_panel)
        self.mods_installed_mode_button.setObjectName("modsInstalledModeButton")
        self.mods_find_mode_button = QPushButton("Find mods", mods_panel)
        self.mods_find_mode_button.setObjectName("modsFindModeButton")
        self.mods_find_mode_button.setAccessibleName("Find mods")
        self._mods_mode_group = QButtonGroup(mods_panel)
        self._mods_mode_group.setExclusive(True)
        for position, (mode, button) in enumerate((("installed", self.mods_installed_mode_button),
                                                    ("find", self.mods_find_mode_button))):
            set_role(button, "segment")
            button.setProperty("segment", "first" if position == 0 else "last")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, mode=mode: self._set_mods_mode(mode))
            self._mods_mode_group.addButton(button)
        mode_row = QHBoxLayout()
        mode_row.setSpacing(0)
        mode_row.addWidget(self.mods_installed_mode_button)
        mode_row.addWidget(self.mods_find_mode_button)
        mods_header.addLayout(mode_row)
        mods_layout.addLayout(mods_header)
        self.mods_instance_label = QLabel("Select an instance to manage its mods.", mods_panel)
        self.mods_instance_label.setObjectName("modsInstanceLabel")
        mods_layout.addWidget(self.mods_instance_label)
        self.mods_warning_label = ui.HintLabel(mods_panel)
        self.mods_warning_label.setObjectName("modsWarningLabel")
        mods_layout.addWidget(self.mods_warning_label)
        self.mods_mode_stack = QStackedWidget(mods_panel)
        self.mods_mode_stack.setObjectName("modsModeStack")
        mods_layout.addWidget(self.mods_mode_stack, 1)

        # Installed mode: the list and what you can do with a listed mod.
        installed_page = QWidget(self.mods_mode_stack)
        installed_layout = QVBoxLayout(installed_page)
        installed_layout.setContentsMargins(0, 4, 0, 0)
        installed_layout.setSpacing(8)
        self.mods_list = ui.PlaceholderList(installed_page)
        self.mods_list.setObjectName("modsList")
        self.mods_list.setAccessibleName("Installed mods")
        self.mods_list.setMinimumHeight(72)
        self.mods_list.set_preferred_height(140)
        self.mods_list.currentRowChanged.connect(lambda _row: self._refresh_mod_buttons())
        installed_layout.addWidget(self.mods_list, 1)
        mods_actions = QHBoxLayout()
        self.import_mod_button = QPushButton("Add jar from disk", installed_page)
        self.import_mod_button.setObjectName("importModButton")
        self.import_mod_button.clicked.connect(self._import_local_mod)
        self.toggle_mod_button = QPushButton("Disable selected", installed_page)
        self.toggle_mod_button.setObjectName("toggleModButton")
        self.toggle_mod_button.clicked.connect(self._toggle_selected_mod)
        self.remove_mod_button = QPushButton("Remove selected", installed_page)
        self.remove_mod_button.setObjectName("removeModButton")
        self.remove_mod_button.clicked.connect(self._remove_selected_mod)
        set_role(self.remove_mod_button, "danger")
        mods_actions.addWidget(self.import_mod_button)
        mods_actions.addWidget(self.toggle_mod_button)
        mods_actions.addStretch(1)
        mods_actions.addWidget(self.remove_mod_button)
        installed_layout.addLayout(mods_actions)
        self.mods_mode_stack.addWidget(installed_page)

        # Find mode: vanilla setups get one truthful state with ways forward
        # instead of a disabled search that still says "Search for mods".
        find_page = QWidget(self.mods_mode_stack)
        find_layout = QVBoxLayout(find_page)
        find_layout.setContentsMargins(0, 4, 0, 0)
        find_layout.setSpacing(8)
        self.mods_vanilla_notice = QFrame(find_page)
        self.mods_vanilla_notice.setObjectName("modsVanillaNotice")
        notice_layout = QVBoxLayout(self.mods_vanilla_notice)
        notice_layout.setContentsMargins(18, 12, 18, 12)
        notice_layout.setSpacing(6)
        self.mods_vanilla_title = QLabel("Online mods need a mod loader", self.mods_vanilla_notice)
        self.mods_vanilla_title.setObjectName("modsVanillaTitle")
        self.mods_vanilla_detail = QLabel("", self.mods_vanilla_notice)
        self.mods_vanilla_detail.setObjectName("modsVanillaDetail")
        self.mods_vanilla_detail.setWordWrap(True)
        notice_layout.addWidget(self.mods_vanilla_title)
        notice_layout.addWidget(self.mods_vanilla_detail)
        notice_actions = QHBoxLayout()
        notice_actions.setSpacing(8)
        self.mods_switch_setup_button = QPushButton("", self.mods_vanilla_notice)
        self.mods_switch_setup_button.setObjectName("modsSwitchSetupButton")
        set_role(self.mods_switch_setup_button, "primary")
        self.mods_switch_setup_button.clicked.connect(self._switch_to_modded_setup)
        self.mods_browse_packs_button = QPushButton("Find a modded pack", self.mods_vanilla_notice)
        self.mods_browse_packs_button.setObjectName("modsBrowsePacksButton")
        self.mods_browse_packs_button.clicked.connect(lambda: self._show_page(2))
        notice_actions.addWidget(self.mods_switch_setup_button)
        notice_actions.addWidget(self.mods_browse_packs_button)
        notice_actions.addStretch(1)
        notice_layout.addLayout(notice_actions)
        self.mods_vanilla_notice.hide()
        find_layout.addWidget(self.mods_vanilla_notice)
        self._mods_online_section = QWidget(find_page)
        online_layout = QVBoxLayout(self._mods_online_section)
        online_layout.setContentsMargins(0, 0, 0, 0)
        online_layout.setSpacing(8)
        mod_search_row = QHBoxLayout()
        mod_search_row.setSpacing(8)
        self.mod_search_input = QLineEdit(find_page)
        self.mod_search_input.setObjectName("modSearchInput")
        self.mod_search_input.setPlaceholderText("Search Modrinth for this setup, e.g. Sodium")
        self.mod_search_input.setAccessibleName("Search Modrinth mods")
        self.mod_search_input.setClearButtonEnabled(True)
        self.mod_search_input.returnPressed.connect(self._search_modrinth_mods)
        self.mod_search_button = QPushButton("Search", find_page)
        self.mod_search_button.setObjectName("modSearchButton")
        self.mod_search_button.clicked.connect(self._search_modrinth_mods)
        mod_search_row.addWidget(self.mod_search_input, 1)
        mod_search_row.addWidget(self.mod_search_button)
        online_layout.addLayout(mod_search_row)
        self.mod_search_results = ui.PlaceholderList(find_page)
        self.mod_search_results.setObjectName("modSearchResults")
        self.mod_search_results.setAccessibleName("Mod search results")
        self.mod_search_results.setMinimumHeight(60)
        self.mod_search_results.set_preferred_height(72)
        self.mod_search_results.currentItemChanged.connect(self._select_modrinth_mod)
        self.mod_search_results.setItemDelegate(RowDelegate(lambda _value, text: RowInfo(text), self.mod_search_results))
        self.mod_search_results.setMouseTracking(True)
        online_layout.addWidget(self.mod_search_results, 1)
        self._mod_release_section = QWidget(find_page)
        mod_release_layout = QHBoxLayout(self._mod_release_section)
        mod_release_layout.setContentsMargins(0, 0, 0, 0)
        mod_release_layout.setSpacing(8)
        self.mod_release_selector = QComboBox(find_page)
        self.mod_release_selector.setObjectName("modReleaseSelector")
        self.mod_release_selector.setAccessibleName("Mod release")
        self.mod_install_button = QPushButton("Add mod", find_page)
        set_role(self.mod_install_button, "primary")
        self.mod_install_button.setObjectName("modInstallButton")
        self.mod_install_button.setEnabled(False)
        self.mod_install_button.clicked.connect(self._install_selected_modrinth_mod)
        mod_release_layout.addWidget(self.mod_release_selector, 1)
        mod_release_layout.addWidget(self.mod_install_button)
        self._mod_release_section.hide()
        online_layout.addWidget(self._mod_release_section)
        find_layout.addWidget(self._mods_online_section, 1)
        # Search and install feedback belongs to the find task.
        self.mod_search_status = ui.HintLabel(find_page)
        self.mod_search_status.setObjectName("modSearchStatus")
        find_layout.addWidget(self.mod_search_status)
        # Keeps the vanilla notice at the top when the search is hidden.
        find_layout.addStretch(0)
        self.mods_mode_stack.addWidget(find_page)
        mods_scroll = QScrollArea(root)
        mods_scroll.setObjectName("modsScroll")
        mods_scroll.setWidgetResizable(True)
        mods_scroll.setFrameShape(QFrame.Shape.NoFrame)
        mods_scroll.setWidget(mods_panel)
        self.content_stack.addWidget(mods_scroll)
        self.mods_panel = mods_panel
        self._set_mods_mode("find")
        # Release choices appear once there is something to choose.
        self.modrinth_release_selector.model().rowsInserted.connect(lambda *_: self._refresh_release_sections())
        self.modrinth_release_selector.model().modelReset.connect(self._refresh_release_sections)
        self.modrinth_release_selector.model().rowsRemoved.connect(lambda *_: self._refresh_release_sections())
        self.mod_release_selector.model().rowsInserted.connect(lambda *_: self._refresh_release_sections())
        self.mod_release_selector.model().modelReset.connect(self._refresh_release_sections)
        self.mod_release_selector.model().rowsRemoved.connect(lambda *_: self._refresh_release_sections())
        layout.addWidget(self.content_stack, 1)
        layout.addWidget(launch_bar)
        self.setCentralWidget(root)
        self._apply_compact_theme()
        self._density = None
        self._apply_density()
        self._show_page(0)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._apply_density()

    def _apply_density(self) -> None:
        """Fit the first fold of the supported 680×420 window.

        Narrow: the launch strip gives the version picker room for an ordinary
        name and version line. Compact: the library folds its two pack imports
        into one menu so the list keeps room for whole rows.
        """
        if self.content_stack is None or not hasattr(self, "import_pack_menu_button"):
            return
        narrow = self.width() < 780
        compact = narrow or self.height() < 500
        if getattr(self, "_density", None) == (narrow, compact):
            return
        self._density = (narrow, compact)
        self.open_folder_button.setText("Folder" if narrow else "Open folder")
        self.open_folder_button.setAccessibleName("Open folder")
        self.open_folder_button.setMinimumWidth(88 if narrow else 120)
        self.play_button.setMinimumWidth(150 if narrow else 170)
        self.username_input.setMinimumWidth(112 if narrow else 130)
        self._new_setup_title.setVisible(not compact)
        self.import_modpack_button.setVisible(not compact)
        self.import_curseforge_button.setVisible(not compact)
        self.import_pack_menu_button.setVisible(compact)
        # Without its "New setup" heading the input's placeholder is its label,
        # so it must stay whole.
        name_input = self.instance_name_input
        name_input.setPlaceholderText("New setup" if compact else "New setup name")
        name_input.setMinimumWidth(name_input.fontMetrics().horizontalAdvance(name_input.placeholderText()) + 34)
        self._fit_library_column()

    def _fit_library_column(self) -> None:
        """The library and tools columns never scroll sideways, so each must be
        at least as wide as its content plus the vertical scroll bar; otherwise
        rows and buttons are clipped when the platform font is wider."""
        for scroll, floor in ((self._library_scroll, 260), (self._tools_scroll, 300)):
            panel = scroll.widget()
            # Showing/hiding controls only invalidates the top layout;
            # activate() re-measures the nested rows before we read the minimum.
            panel.layout().activate()
            scroll.setMinimumWidth(max(
                floor, panel.minimumSizeHint().width() + scroll.verticalScrollBar().sizeHint().width()))
        # Apply now rather than on the next pass, so the columns never overlap.
        self.instances_panel.layout().activate()

    def _refresh_release_sections(self) -> None:
        self._catalog_release_section.setVisible(self.modrinth_release_selector.count() > 0)
        self._mod_release_section.setVisible(self.mod_release_selector.count() > 0)

    def _apply_compact_theme(self) -> None:
        self.resize(920, 560)
        self.setMinimumSize(680, 420)
        self.setStyleSheet(ui.STYLESHEET)
        ui.apply_palette(self)
        # Top-level popups and dialogs do not inherit the window stylesheet.
        self.setup_selector.popup.setStyleSheet(ui.STYLESHEET)
        ui.apply_palette(self.setup_selector.popup)
        self.save_username_button.hide()
        self.save_memory_button.hide()
        self.identity_label.hide()
        self.memory_input.hide()
        self.memory_setting_error.hide()
        self.confirm_username_change_button.hide()
        self.home_nav_button.setProperty("active", True)
        self.browse_nav_button.setProperty("active", False)
        self.mods_nav_button.setProperty("active", False)

    def _show_page(self, index: int) -> None:
        if self.content_stack is None:
            return
        index = 0 if index not in (0, 1, 2, 3) else index
        self.content_stack.setCurrentIndex(index)
        home = index == 0
        # Home owns the launch form; other pages keep a one-line launch strip
        # whose status explains what the (quieter) Play button would start.
        for control in (self.username_field_label, self.setup_field_label,
                        self.username_input, self.setup_selector):
            control.setVisible(home)
        if not home:
            self.setup_selector.hidePopup()
        self._place_status_label(home)
        strip_height = 52 if home else 48
        self.play_button.setMinimumHeight(strip_height)
        self.open_folder_button.setMinimumHeight(strip_height)
        self._launch_layout.setContentsMargins(20, 10 if home else 8, 20, 12 if home else 8)
        self.play_button.setProperty("subdued", not home)
        self.play_button.style().unpolish(self.play_button)
        self.play_button.style().polish(self.play_button)
        self.home_nav_button.setProperty("active", home)
        # Mods belongs to the selected instance, so Instances stays highlighted.
        self.instances_nav_button.setProperty("active", index in (1, 3))
        self.browse_nav_button.setProperty("active", index == 2)
        self.mods_nav_button.setProperty("active", index == 3)
        for button in (self.home_nav_button, self.instances_nav_button, self.browse_nav_button, self.mods_nav_button):
            button.style().unpolish(button)
            button.style().polish(button)
        if index == 3:
            self._refresh_mods_panel()

    def _place_status_label(self, home: bool) -> None:
        label = self.instance_status_label
        self._launch_layout.removeWidget(label)
        self._launch_controls.removeWidget(label)
        if home:
            # Directly above the hint row, which sits just before the progress bar.
            row = max(0, self._launch_layout.indexOf(self.install_progress) - 1)
            self._launch_layout.insertWidget(row, label)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            self._launch_controls.addWidget(label, 1, 0, 1, 2)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._refresh_status_visibility()

    def _refresh_status_visibility(self) -> None:
        label = self.instance_status_label
        on_home = self.content_stack is not None and self.content_stack.currentIndex() == 0
        # On Home the hero already says what is selected; only news shows here.
        label.setVisible(bool(label.text()) and not (on_home and label.is_summary))

    def _describe_instance(self, instance: dict) -> RowInfo:
        version = instance.get("minecraft_version") or instance.get("version")
        parts = [f"Minecraft {version}" if version else "Version not picked"]
        loader = str(instance.get("loader") or "").strip()
        if loader and loader.lower() != "vanilla":
            parts.append(loader.capitalize())
        provider = str(instance.get("provider") or "").strip()
        if provider in {"modrinth", "curseforge"}:
            parts.append("Modrinth pack" if provider == "modrinth" else "CurseForge pack")
        if instance.get("install_error"):
            badge, tone = "Needs attention", "warn"
        elif instance.get("ready"):
            badge, tone = "Ready", "good"
        else:
            badge, tone = "Not installed", "muted"
        return RowInfo(str(instance.get("name") or "Unnamed setup"), " · ".join(parts), badge, tone)

    def _describe_row(self, value, text: str) -> RowInfo:
        """Describe a picker row for display; ids stay internal."""
        if isinstance(value, str) and value.startswith("version:"):
            version = value.split(":", 1)[1]
            row = self.setup_selector.findData(value, Qt.ItemDataRole.UserRole)
            kind = str(self.setup_selector.itemData(row, Qt.ItemDataRole.UserRole + 1) or "release") if row >= 0 else "release"
            detail = {"release": "Release", "snapshot": "Snapshot", "old_beta": "Beta", "old_alpha": "Alpha"}.get(kind, kind.replace("_", " ").capitalize())
            installed = text.startswith("✓ ")
            return RowInfo(f"Minecraft {version}", f"Vanilla · {detail}", "Installed" if installed else "", "good" if installed else "muted")
        instance = next((item for item in self.state.get("instances", []) if item.get("id") == value), None)
        if instance is None:
            return RowInfo(text or "Nothing selected", "Pick a version or setup")
        info = self._describe_instance(instance)
        return RowInfo(text or info.title, info.detail, info.badge, info.tone)

    def _describe_instance_row(self, value, text: str) -> RowInfo:
        instance = next((item for item in self.state.get("instances", []) if item.get("id") == value), None)
        return self._describe_instance(instance) if instance is not None else RowInfo(text)

    def _set_hero(self, eyebrow: str, title: str, detail: str, tone: str = "") -> None:
        self.hero_eyebrow.setText(eyebrow)
        self.hero_eyebrow.setVisible(bool(eyebrow))
        if self.hero_eyebrow.property("tone") != tone:
            self.hero_eyebrow.setProperty("tone", tone)
            self.hero_eyebrow.style().unpolish(self.hero_eyebrow)
            self.hero_eyebrow.style().polish(self.hero_eyebrow)
        self.hero_title.setText(title)
        self.hero_detail.setText(detail)

    def _refresh_hero(self) -> None:
        """Explain, in plain words, what Play will do right now."""
        if not hasattr(self, "hero_title"):
            return
        index = self.setup_selector.currentIndex()
        value = self.setup_selector.itemData(index, Qt.ItemDataRole.UserRole) if index >= 0 else None
        name = str(self.state.get("username") or "").strip()
        first_run = not self.state.get("instances")
        if value is None:
            if getattr(self, "_discovery_error", ""):
                self._set_hero(
                    "Version list unavailable", "Couldn’t reach Minecraft’s version list",
                    "Check your connection and press Retry below. Setups you already created still work.", "bad")
            elif first_run and self.setup_selector.count() == 0:
                # Say what is happening now, then the one next step.
                self._set_hero(
                    "Welcome", "Getting the version list…",
                    "Fetching Minecraft versions from Mojang. Then pick a version below, or press "
                    "Install & Play to download and start the newest release.", "muted")
            elif first_run:
                self._set_hero("Welcome", "Pick a version to start",
                               "Choose a Minecraft version below, then press Install & Play.", "muted")
            else:
                self._set_hero("Choose what to play", "Nothing selected",
                               "Pick a Minecraft version or one of your setups below.", "muted")
            self.setup_selector.setToolTip("Choose a version or setup")
            self.setup_selector.update()
            return
        info = self._describe_row(value, self.setup_selector.itemText(index))
        # The compact picker may show the state as a dot; the tooltip says it.
        self.setup_selector.setToolTip(" · ".join(part for part in (info.title, info.detail, info.badge) if part))
        greeting = f"Welcome back, {name}" if name and not first_run else ("Welcome" if first_run else "")
        if isinstance(value, str) and value.startswith("version:"):
            if info.badge == "Installed":
                self._set_hero(greeting or "Ready to play", info.title,
                               f"{info.detail} · Downloaded and ready. Press Play to start.", "")
            else:
                self._set_hero(greeting or "Ready to install", info.title,
                               f"{info.detail} · Not downloaded yet. Install & Play downloads it "
                               "(a few hundred MB, one time) and then starts the game.", "")
        else:
            instance = next((item for item in self.state.get("instances", []) if item.get("id") == value), None) or {}
            if info.tone == "warn":
                self._set_hero("Needs attention", info.title,
                               f"{info.detail} · {instance.get('install_error') or 'The last install did not finish'}. "
                               "Press Retry to try again.", "warn")
            elif info.badge == "Ready":
                self._set_hero(greeting or "Ready to play", info.title, f"{info.detail} · Ready. Press Play to start.", "")
            else:
                self._set_hero(greeting or "Ready to install", info.title,
                               f"{info.detail} · Not installed yet. Install & Play downloads it and then starts the game.", "")
        self.setup_selector.update()

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
            self.instance_status_label.set_summary(f"Minecraft {version} selected")
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

    def _retry_version_discovery(self) -> None:
        if self.discovery_worker is not None:
            return
        self.retry_discovery_button.hide()
        if self._start_version_discovery():
            self.diagnostic_hint_label.setText("Checking for Minecraft versions again…")

    def _start_version_discovery(self) -> bool:
        if not self._installer_injected and QApplication.platformName() == "offscreen":
            return False
        first_use = not self.state.get("instances") and not self.state.get("selected_setup_id")
        self.discovery_worker = VersionDiscoveryWorker(self.installer, select_latest=first_use)
        _ACTIVE_DISCOVERY_WORKERS.add(self.discovery_worker)
        self.discovery_worker.discovered.connect(self._versions_discovered)
        self.discovery_worker.failed.connect(self._version_discovery_failed)
        self.discovery_worker.finished.connect(self._discovery_finished)
        self.discovery_worker.finished.connect(lambda worker=self.discovery_worker: _release_discovery_worker(worker))
        self.discovery_worker.start()
        return True

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
        if getattr(self, "_discovery_error", ""):
            self._discovery_error = ""
            self.retry_discovery_button.hide()
            self.diagnostic_hint_label.clear()
        elif self.diagnostic_hint_label.text().startswith("Checking for Minecraft versions"):
            self.diagnostic_hint_label.clear()
        # The selector was rebuilt quietly, so restate what is now selected.
        version = self._selected_version()
        if version and self._selected_instance() is None and (
            self.instance_status_label.is_summary and self.game_process is None
        ):
            self.instance_status_label.set_summary(f"Minecraft {version} selected")
        self._refresh_play_button()
        self._refresh_hero()

    def _version_discovery_failed(self, message: str) -> None:
        self._discovery_error = message
        cached = bool(self.state.get("available_versions")) or bool(self.state.get("instances"))
        self.diagnostic_hint_label.setText(
            f"Could not discover Minecraft releases: {message}. "
            + ("Your saved setups and cached versions still work." if cached else "Check your connection, then retry.")
        )
        self.retry_discovery_button.show()
        self._refresh_play_button()
        self._refresh_hero()

    def _discovery_finished(self) -> None:
        worker = self.discovery_worker
        self.discovery_worker = None

    def _open_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setModal(True)
        dialog.setMinimumWidth(440)
        dialog.setStyleSheet(ui.STYLESHEET)
        ui.apply_palette(dialog)
        # Sections scroll inside a dialog that never outgrows the smallest
        # supported window (420 px); Close stays pinned below them.
        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(0, 0, 0, 14)
        outer.setSpacing(8)
        body = QWidget(dialog)
        body.setObjectName("settingsBody")
        page = QVBoxLayout(body)
        page.setContentsMargins(22, 14, 22, 4)
        page.setSpacing(6)
        scroll = QScrollArea(dialog)
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        intro = set_role(QLabel("Changes are saved automatically.", dialog), "muted")
        intro.setObjectName("settingsSavedNote")
        page.addWidget(intro)

        def section(title: str) -> QFormLayout:
            page.addWidget(set_role(QLabel(title, dialog), "sectionTitle"))
            form = QFormLayout()
            form.setHorizontalSpacing(14)
            form.setVerticalSpacing(6)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            page.addLayout(form)
            return form

        # Game
        game = section("Game")
        maximum = whole_physical_memory_gib()
        memory = QLineEdit(str(self.state.get("memory_gib", default_memory_gib())), dialog)
        memory.setObjectName("settingsMemoryInput")
        memory.setAccessibleName("Game memory in GiB")
        memory.setMaximumWidth(90)
        memory_row = QHBoxLayout()
        memory_row.setSpacing(8)
        memory_row.addWidget(memory)
        memory_row.addWidget(QLabel("GiB", dialog))
        memory_row.addStretch(1)
        memory_label = QLabel("Memory", dialog)
        memory_label.setBuddy(memory)
        game.addRow(memory_label, memory_row)
        memory_hint = set_role(QLabel(
            f"Whole number from 1 to {maximum} GiB (this computer’s RAM). "
            f"{default_memory_gib()} GiB suits most setups.", dialog), "muted")
        memory_hint.setObjectName("settingsMemoryHint")
        memory_hint.setWordWrap(True)
        game.addRow("", memory_hint)
        error = QLabel(dialog)
        error.setObjectName("settingsError")
        error.setWordWrap(True)
        error.hide()
        game.addRow("", error)

        # Versions
        versions = section("Versions")
        snapshots = QCheckBox("Show snapshots", dialog)
        snapshots.setChecked(bool(self.state.get("show_snapshots", False)))
        snapshots.setToolTip("List experimental Minecraft builds in the version picker")
        versions.addRow("Experimental", snapshots)

        # Appearance
        appearance = section("Appearance")
        background_button = QPushButton("Choose background", dialog)
        background_button.setObjectName("settingsBackgroundButton")
        background_button.clicked.connect(self._choose_background)
        appearance.addRow("Home artwork", background_button)

        # Troubleshooting
        trouble = section("Troubleshooting")
        lifecycle_target = self.game_instance is not None or self.last_game_instance is not None
        target_label = "running game" if self.game_instance is not None else "last game"
        open_folder_text = f"Open {target_label} folder" if lifecycle_target else "Open selected setup folder"
        log_text = f"Export {target_label} diagnostic log" if lifecycle_target else "Export diagnostic log"
        open_folder = QPushButton(open_folder_text, dialog)
        open_folder.clicked.connect(self._open_instance_folder)
        export_log = QPushButton(log_text, dialog)
        export_log.setToolTip("Save a log file to share when asking for help")
        export_log.clicked.connect(self._save_diagnostic_log)
        trouble_row = QHBoxLayout()
        trouble_row.setSpacing(8)
        trouble_row.addWidget(open_folder)
        trouble_row.addWidget(export_log)
        trouble.addRow(trouble_row)

        page.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.setContentsMargins(22, 0, 22, 0)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        outer.addWidget(buttons)
        dialog.setMaximumHeight(400)
        dialog.resize(440, min(400, body.sizeHint().height() + buttons.sizeHint().height() + 22))

        def mark_invalid(invalid: bool) -> None:
            memory.setProperty("invalid", invalid)
            memory_hint.setVisible(not invalid)
            memory.style().unpolish(memory)
            memory.style().polish(memory)

        def save_memory() -> None:
            if self.store.recovery_required:
                return
            value, message = validate_memory_gib(memory.text())
            if message:
                error.setText(f"{message} (1–{maximum}). Not saved; the game keeps "
                              f"{self.state.get('memory_gib', default_memory_gib())} GiB.")
                error.show()
                mark_invalid(True)
                memory.setAccessibleDescription(error.text())
                scroll.ensureWidgetVisible(error)
                return
            self.state["memory_gib"] = value
            self.store.save(self.state)
            self.memory_input.setText(str(value))
            memory.setText(str(value))
            error.hide()
            mark_invalid(False)
            memory.setAccessibleDescription(memory_hint.text())

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
                journal = self.store.instance_root(instance["id"]) / "update-journal.json"
                if journal.is_file():
                    try:
                        journal_data = json.loads(journal.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        journal_data = {}
                    instance["update_recovery_required"] = True
                    if isinstance(journal_data, dict) and isinstance(journal_data.get("backup"), str):
                        instance["recovery_backup"] = journal_data["backup"]
                    instance["ready"] = False
                    instance["install_state"] = "failed"
                    instance["install_error"] = "An interrupted pack update needs recovery from its backup"
                    state_changed = True
                elif instance.get("update_recovery_required"):
                    # The cleanup entry may have been removed before its
                    # directory fsync failed; there is no journal to recover.
                    instance["update_recovery_required"] = False
                    state_changed = True
                interrupted_state = instance.get("install_state")
                if interrupted_state in {"installing", "importing", "updating"}:
                    instance["install_state"] = "interrupted"
                    instance["ready"] = False
                    if instance.get("update_recovery_required") or interrupted_state == "updating":
                        instance["update_recovery_required"] = True
                        instance["install_error"] = "Pack update interrupted; recover the previous release before playing"
                    else:
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
        self._refresh_hero()
        self._explain_play_state()
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
        seen_names: dict[str, int] = {}
        for instance in instances:
            name = str(instance.get("name", "Unnamed setup"))
            # Internal ids never reach the user; duplicate names get a short ordinal instead.
            seen_names[name] = seen_names.get(name, 0) + 1
            label = name if seen_names[name] == 1 else f"{name} ({seen_names[name]})"
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
        self._refresh_hero()
        if hasattr(self, "instance_list"):
            self.instance_list.viewport().update()

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
        self._bind_running_game(record)
        self._operation_selector_value = self.state.get("selected_setup_id") or self.setup_selector.currentData(
            Qt.ItemDataRole.UserRole
        )
        self.game_poll_timer.start()

    def _poll_adopted_game(self) -> None:
        if self._waiting_for_game_lock:
            if not self.game_registry.acquire():
                return
            self._waiting_for_game_lock = False
            record = self.game_registry.adopt()
            if record is not None and self.game_registry.is_alive(record):
                self._bind_running_game(record)
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

    def _bind_running_game(self, record: dict) -> None:
        self.game_record = record
        self.game_process = record
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
            self.modrinth_search_input.setFocus()
            return
        self._catalog_last_query = query
        self.modrinth_pack_list.clear()
        self.modrinth_pack_list.set_placeholder("Searching Modrinth…", f"Looking for “{query}”.")
        self._reset_catalog_details(PACK_DETAILS_PROMPT, f"Searching Modrinth for “{query}”…")
        if not self._catalog_injected:
            self._catalog_browse_request += 1
            if self._catalog_browse_worker is not None and self._catalog_browse_worker.isRunning():
                self._catalog_browse_worker.cancel()
            worker = CatalogBrowseWorker(self.modrinth_catalog, "search", query)
            self._catalog_browse_worker = worker
            request = self._catalog_browse_request
            worker.completed.connect(lambda results, request=request: self._catalog_search_completed(request, results))
            worker.failed.connect(lambda message, request=request: self._catalog_search_failed(request, message))
            worker.finished.connect(lambda worker=worker: self._clear_catalog_browse_worker(worker))
            worker.start()
            return
        try:
            results = self.modrinth_catalog.search(query)
        except (ModrinthCatalogError, OSError, RuntimeError) as error:
            self._show_catalog_search_failure(error)
            return
        self._show_catalog_results(results)

    def _reset_catalog_details(self, details: str, status: str = "") -> None:
        """Drop the previous pack's description, releases and Install button.

        A new search, an empty result or a failure must never leave an old
        pack offered beside results it does not belong to.
        """
        self.modrinth_release_selector.clear()
        self._catalog_releases = []
        self.modrinth_install_button.setEnabled(False)
        self.modrinth_pack_details.setText(details)
        self.modrinth_catalog_status.setText(status)

    def _show_catalog_results(self, results) -> None:
        self._catalog_results = results
        self.modrinth_pack_list.clear()
        for result in results:
            self.modrinth_pack_list.addItem(self._result_item(result))
        if results:
            self._reset_catalog_details(PACK_DETAILS_PROMPT, f"{len(results)} Modrinth pack(s) found.")
        else:
            self._reset_catalog_details(
                "Nothing to install from this search. Try different words, or import a pack file below.",
                "No Modrinth modpacks matched that search.")
        self._catalog_placeholder_empty()

    def _show_catalog_search_failure(self, message) -> None:
        self._catalog_results = []
        self.modrinth_pack_list.clear()
        self._reset_catalog_details(
            "Pack details appear here once Modrinth can be reached. You can still import a pack file below.",
            f"Modrinth search failed: {message}")
        self._catalog_placeholder_failed()

    def _catalog_search_completed(self, request: int, results) -> None:
        if self._closing or request != self._catalog_browse_request:
            return
        self._show_catalog_results(results)

    def _catalog_search_failed(self, request: int, message: str) -> None:
        if self._closing or request != self._catalog_browse_request:
            return
        self._show_catalog_search_failure(message)

    def _catalog_placeholder_empty(self) -> None:
        query = getattr(self, "_catalog_last_query", "")
        self.modrinth_pack_list.set_placeholder(
            f"No modpacks match “{query}”", "Try a shorter name or different words.")

    def _catalog_placeholder_failed(self) -> None:
        self.modrinth_pack_list.set_placeholder(
            "Couldn’t reach Modrinth", "Check your connection and press Search again. "
            "You can still import a pack file below.")

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
        if not self._catalog_injected:
            self._catalog_browse_request += 1
            request = self._catalog_browse_request
            if self._catalog_browse_worker is not None and self._catalog_browse_worker.isRunning():
                self._catalog_browse_worker.cancel()
            worker = CatalogBrowseWorker(self.modrinth_catalog, "details", project_id)
            self._catalog_browse_worker = worker
            worker.completed.connect(lambda value, request=request: self._catalog_details_completed(request, value))
            worker.failed.connect(lambda message, request=request: self._catalog_details_failed(request, message))
            worker.finished.connect(lambda worker=worker: self._clear_catalog_browse_worker(worker))
            worker.start()
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

    def _catalog_details_completed(self, request: int, value) -> None:
        if self._closing or request != self._catalog_browse_request:
            return
        details, releases = value
        self.modrinth_pack_details.setText(f"{details.get('title', '')}\n\n{details.get('description') or 'No description available.'}")
        self._catalog_releases = releases
        for release in releases:
            self.modrinth_release_selector.addItem(
                f"{release.version_number or release.name} · {', '.join(release.game_versions)}", release,
            )
        self.modrinth_install_button.setEnabled(bool(releases))
        self.modrinth_catalog_status.setText(f"{len(releases)} release(s) available.")

    def _catalog_details_failed(self, request: int, message: str) -> None:
        if self._closing or request != self._catalog_browse_request:
            return
        self.modrinth_pack_details.setText(f"Could not load pack details: {message}")
        self.modrinth_catalog_status.setText("Choose another pack or retry the search.")

    def _clear_catalog_browse_worker(self, worker) -> None:
        if self._catalog_browse_worker is worker:
            self._catalog_browse_worker = None

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
        if not self._catalog_injected:
            self._catalog_installing = True
            existing = self._selected_instance()
            updating = bool(existing and existing.get("provider") == "modrinth" and existing.get("pack_project_id") == release.project_id)
            if updating and self._update_journal_exists(existing):
                self.modrinth_catalog_status.setText("Recover the interrupted pack update before starting another update.")
                self._catalog_installing = False
                self.modrinth_install_button.setEnabled(bool(self._catalog_releases))
                return
            if updating:
                answer = QMessageBox.question(
                    self, "Update pack", "Replace this instance with the selected release? Local mods and config changes will be backed up.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    self._catalog_installing = False
                    self.modrinth_install_button.setEnabled(bool(self._catalog_releases))
                    return
            instance = existing if updating else self._create_pack_instance(title, archive, provider="modrinth", pack_release_id=release.id, pack_project_id=release.project_id)
            self._catalog_release_context = (release, title, archive, instance)
            instance["install_state"] = "updating" if updating else "importing"
            instance["ready"] = False
            instance["install_error"] = ""
            if updating:
                instance.pop("recovery_backup", None)
                instance["update_recovery_required"] = False
            self.store.save(self.state)
            self._set_session_controls_locked(True)
            self.modrinth_install_button.setEnabled(False)
            self._catalog_worker = CatalogOperationWorker(
                self.modrinth_catalog, release, self.modpack_importer, self.installer,
                archive, self.store.instance_minecraft_root(instance["id"]), instance,
                self.modrinth_updater if updating else None, release.id if updating else "",
                game_directory=self.store.instance_game_root(instance["id"]),
            )
            self._catalog_worker.progress.connect(self._show_import_progress)
            self._catalog_worker.completed.connect(self._catalog_download_completed)
            self._catalog_worker.failed.connect(self._catalog_download_failed)
            self._catalog_worker.finished.connect(lambda: setattr(self, "_catalog_worker", None))
            self._catalog_worker.start()
            return
        try:
            archive.write_bytes(self.modrinth_catalog.download_release(release))
            selected = self._selected_instance()
            if selected and selected.get("provider") == "modrinth" and selected.get("pack_project_id") == release.project_id:
                self._perform_pack_update(selected, archive, release_id=release.id)
                self.modrinth_catalog_status.setText(f"Updated {title} {release.version_number or release.name}.")
            else:
                self._install_pack_archive(
                    archive, title, pack_release_id=release.id, pack_project_id=release.project_id,
                )
                self.modrinth_catalog_status.setText(f"Installed {title} {release.version_number or release.name}.")
        except (ModrinthCatalogError, ModrinthPackError, UnsupportedModrinthPack, OSError, RuntimeError) as error:
            self.modrinth_catalog_status.setText(f"Modrinth installation failed: {error}")
        finally:
            archive.unlink(missing_ok=True)
            self._catalog_installing = False
            self._set_session_controls_locked(False)
            self.modrinth_install_button.setEnabled(bool(self._catalog_releases))

    def _catalog_download_completed(self) -> None:
        if self._closing:
            return
        release, title, archive, instance = self._catalog_release_context
        try:
            if self._catalog_worker.updating:
                instance.update(self._catalog_worker.instance_result)
                self.store.save(self.state)
                try:
                    ModrinthPackUpdater._durable_unlink(self.store.instance_root(instance["id"]) / "update-journal.json")
                except (OSError, RuntimeError):
                    self._mark_update_recovery_required(instance, "Pack update journal cleanup was not durable", force_recovery=True)
                    raise
                self.modrinth_catalog_status.setText(f"Updated {title} {release.version_number or release.name}.")
            else:
                self._finish_pack_install(instance, self._catalog_worker.metadata, self._catalog_worker.instance_result, title)
                self.modrinth_catalog_status.setText(f"Installed {title} {release.version_number or release.name}.")
        except (ModrinthCatalogError, ModrinthPackError, UnsupportedModrinthPack, OSError, RuntimeError) as error:
            if instance.get("provider") in {"modrinth", "curseforge"} and self._update_journal_exists(instance):
                self._mark_update_recovery_required(instance, str(error))
            self.modrinth_catalog_status.setText(f"Modrinth installation failed: {error}")
        finally:
            archive.unlink(missing_ok=True)
            self._catalog_installing = False
            self._set_session_controls_locked(False)
            self.modrinth_install_button.setEnabled(bool(self._catalog_releases))

    def _catalog_download_failed(self, message: str) -> None:
        if self._closing:
            self._catalog_installing = False
            return
        context = getattr(self, "_catalog_release_context", None)
        if context:
            instance = context[3]
            instance["install_state"] = "failed"
            instance["install_error"] = message or "Modrinth catalog preparation failed"
            instance["ready"] = False
            if self._update_journal_exists(instance):
                self._mark_update_recovery_required(instance, message)
            if not self.store.recovery_required:
                self.store.save(self.state)
        if not self._closing:
            self.modrinth_catalog_status.setText(f"Modrinth installation failed: {message}")
        self._catalog_installing = False
        self._set_session_controls_locked(False)
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
        self._install_pack_archive(archive, name)

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
        self._install_pack_archive(
            archive, name, importer=self.curseforge_importer, provider="curseforge", display_name="CurseForge"
        )

    def _install_pack_archive(self, archive: Path, name: str, *, pack_release_id: str = "",
                                  pack_project_id: str = "", importer=None, provider: str = "modrinth",
                                  display_name: str = "Modrinth") -> None:
        importer = importer or self.modpack_importer
        instance = self._create_pack_instance(name, archive, provider=provider, pack_release_id=pack_release_id, pack_project_id=pack_project_id)
        if (provider == "modrinth" and not self._modpack_importer_injected) or (provider == "curseforge" and not self._curseforge_importer_injected):
            self._start_pack_preparation_worker(instance, archive, importer, display_name)
            return
        self._install_pack_archive_sync(instance, archive, importer, display_name)

    def _start_pack_preparation_worker(self, instance: dict, archive: Path, importer, display_name: str) -> None:
        self._set_session_controls_locked(True)
        worker = PackPreparationWorker(
            importer, self.installer, archive, self.store.instance_minecraft_root(instance["id"]), instance,
            game_directory=self.store.instance_game_root(instance["id"]),
        )
        self._pack_worker = worker
        self._pack_worker_instance = instance
        self._pack_worker_display_name = display_name
        worker.progress.connect(self._show_import_progress)
        worker.completed.connect(self._pack_preparation_completed)
        worker.failed.connect(self._pack_preparation_failed)
        worker.finished.connect(lambda: setattr(self, "_pack_worker", None))
        worker.start()

    def _pack_preparation_completed(self) -> None:
        if self._closing:
            return
        worker = self._pack_worker
        instance = self._pack_worker_instance
        self._finish_pack_install(instance, worker.metadata, worker.instance_result, self._pack_worker_display_name)
        self._set_session_controls_locked(False)
        self._refresh_install_button()
        self._refresh_play_button()

    def _pack_preparation_failed(self, message: str) -> None:
        if self._closing:
            return
        instance = self._pack_worker_instance
        instance["ready"] = False
        instance["install_state"] = "failed"
        instance["install_error"] = message or f"{self._pack_worker_display_name} pack import failed"
        if not self.store.recovery_required:
            self.store.save(self.state)
        if not self._closing:
            self.instance_status_label.setText(f"Import failed: {instance['install_error']}")
            self.diagnostic_hint_label.setText("Retry the import after correcting the source or provider access.")
            self._set_session_controls_locked(False)
            self._refresh_install_button()
            self._refresh_play_button()

    def _create_pack_instance(self, name: str, archive: Path, *, provider: str, pack_release_id: str = "", pack_project_id: str = "") -> dict:
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
        return instance

    def _finish_pack_install(self, instance: dict, metadata: dict, result: dict, display_name: str) -> None:
        instance.update(result)
        instance.update(
            version=metadata["game_version"], minecraft_version=metadata["game_version"], loader=metadata["loader"],
            loader_version=metadata["loader_version"], installed_files=metadata["installed_files"],
            pack_format=metadata["format"], install_state="ready", ready=True, install_error="",
        )
        instance["installed_file_hashes"] = ModrinthPackUpdater._file_hashes(
            self.store.instance_game_root(instance["id"]), metadata.get("installed_files", [])
        )
        self.store.save(self.state)
        self.instance_status_label.setText(f"Ready: {instance['name']} ({instance['version']})")
        self.diagnostic_hint_label.setText(f"{display_name} pack installed; Play is available.")

    def _install_pack_archive_sync(self, instance: dict, archive: Path, importer, display_name: str) -> None:
        provider = instance.get("provider")
        try:
            metadata = importer.import_archive(
                archive, self.store.instance_game_root(instance["id"]),
                on_progress=self._show_import_progress,
            )
            instance.update(
                version=metadata["game_version"], minecraft_version=metadata["game_version"], loader=metadata["loader"],
                loader_version=metadata["loader_version"], installed_files=metadata["installed_files"],
                pack_format=metadata["format"], install_state="imported", ready=False, install_error="",
            )
            instance["installed_file_hashes"] = ModrinthPackUpdater._file_hashes(
                self.store.instance_game_root(instance["id"]), metadata.get("installed_files", [])
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
        if not self._optifine_injected:
            self._optifine_worker = OptiFineWorker(self.optifine_installer, instance, self.store.instance_minecraft_root(instance["id"]), Path(filename))
            self._optifine_worker.completed.connect(self._optifine_completed)
            self._optifine_worker.failed.connect(self._optifine_failed)
            self._optifine_worker.start()
            return
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

    def _optifine_completed(self, result) -> None:
        if self._closing:
            return
        worker = self._optifine_worker
        instance_id = worker.instance_id if worker is not None else None
        instance = next((item for item in self.state.get("instances", []) if item.get("id") == instance_id), None)
        if instance is None:
            return
        instance.update(result)
        instance["ready"] = bool(self.player.is_ready(instance, self.store.instance_minecraft_root(instance["id"])))
        instance["install_state"] = "ready" if instance["ready"] else "incomplete"
        self.store.save(self.state)
        self._set_session_controls_locked(False)
        self._refresh_play_button()

    def _optifine_failed(self, message: str) -> None:
        if self._closing:
            return
        instance = self._selected_instance()
        if instance is None:
            return
        instance["ready"] = False
        instance["install_state"] = "failed"
        instance["install_error"] = message
        self.store.save(self.state)
        if not self._closing:
            self.diagnostic_hint_label.setText(message)
            self._set_session_controls_locked(False)
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
        self._perform_pack_update(instance, Path(filename))

    def _perform_pack_update(self, instance: dict, archive: Path, *, release_id: str = "") -> None:
        provider = instance.get("provider")
        if self._update_journal_exists(instance):
            self.diagnostic_hint_label.setText("Recover the interrupted pack update before starting another update.")
            return
        replacement_directory = None
        updater_injected = self._modrinth_updater_injected if provider == "modrinth" else self._curseforge_updater_injected
        if provider == "curseforge" and not updater_injected:
            replacement_directory = self._replacement_directory_for_update()
        if not updater_injected:
            answer = QMessageBox.question(
                self, "Update pack", "Prepare and replace this pack in the background? Local changes will be backed up.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._set_session_controls_locked(True)
            instance["install_state"] = "updating"
            instance["install_error"] = ""
            instance["ready"] = False
            instance.pop("recovery_backup", None)
            instance["update_recovery_required"] = False
            self.store.save(self.state)
            worker = PackUpdateWorker(
                self._updater_for_provider(provider), archive, self.store.instance_game_root(instance["id"]), instance,
                release_id, replacement_directory,
            )
            self._update_worker = worker
            self._update_worker_instance = instance
            worker.progress.connect(self._show_import_progress)
            worker.completed.connect(self._pack_update_completed)
            worker.failed.connect(self._pack_update_failed)
            worker.finished.connect(lambda: setattr(self, "_update_worker", None))
            worker.start()
            return
        self._set_session_controls_locked(True)
        instance["install_state"] = "updating"
        instance["install_error"] = ""
        self.store.save(self.state)
        try:
            updater = self._updater_for_provider(provider)
            result = updater.update(
                instance, self.store.instance_game_root(instance["id"]), archive,
                release_id=release_id or str(instance.get("pending_pack_release_id", "")),
                on_progress=self._show_import_progress,
                confirm_local_changes=lambda paths: QMessageBox.question(
                    self, "Local changes detected",
                    "This update will replace pack files and may affect local changes:\n\n" + "\n".join(paths)
                    + "\n\nContinue?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                ) == QMessageBox.StandardButton.Yes,
                replacements=(self.curseforge_importer.prepare_replacements(archive, replacement_directory)
                              if provider == "curseforge" and replacement_directory else None),
            )
            instance["ready"] = bool(self.player.is_ready(instance, self.store.instance_minecraft_root(instance["id"])))
            if not instance["ready"]:
                raise ModrinthPackUpdateError("Updated files are incomplete; recover from the recorded backup")
            instance["install_state"] = "ready"
            self.store.save(self.state)
            try:
                ModrinthPackUpdater._durable_unlink(self.store.instance_root(instance["id"]) / "update-journal.json")
            except (OSError, RuntimeError):
                self._mark_update_recovery_required(instance, "Pack update journal cleanup was not durable", force_recovery=True)
                raise
            self.instance_status_label.setText(f"Updated: {instance['name']}")
            self.diagnostic_hint_label.setText(f"Update complete; backup saved at {result['backup']}")
        except (ModrinthPackUpdateError, ModrinthPackError, OSError, RuntimeError) as error:
            self._mark_update_recovery_required(instance, str(error))
            self.instance_status_label.setText(f"Update failed: {instance['install_error']}")
            self.diagnostic_hint_label.setText("The previous instance is recoverable from its recorded backup; retry or recover.")
        finally:
            self._set_session_controls_locked(False)
            self._refresh_play_button()

    def _replacement_directory_for_update(self) -> Path | None:
        selected = QFileDialog.getExistingDirectory(self, "Select verified CurseForge replacement files", "")
        return Path(selected) if selected else None

    def _pack_update_completed(self) -> None:
        if self._closing:
            return
        instance = self._update_worker_instance
        try:
            instance.update(self._update_worker.instance_result)
            self.store.save(self.state)
            try:
                ModrinthPackUpdater._durable_unlink(self.store.instance_root(instance["id"]) / "update-journal.json")
            except (OSError, RuntimeError):
                self._mark_update_recovery_required(instance, "Pack update journal cleanup was not durable", force_recovery=True)
                raise
        except (OSError, RuntimeError) as error:
            self._mark_update_recovery_required(instance, str(error))
            self._set_session_controls_locked(False)
            self._refresh_play_button()
            return
        self.instance_status_label.setText(f"Updated: {instance['name']}")
        self.diagnostic_hint_label.setText("Update complete; the previous release is backed up.")
        self._set_session_controls_locked(False)
        self._refresh_play_button()

    def _pack_update_failed(self, message: str) -> None:
        if self._closing:
            return
        instance = self._update_worker_instance
        instance["ready"] = False
        instance["install_state"] = "failed"
        instance["install_error"] = message or "Pack update failed"
        if self._update_journal_exists(instance):
            self._mark_update_recovery_required(instance, instance["install_error"])
        elif not self.store.recovery_required:
            self.store.save(self.state)
        if not self._closing:
            self.instance_status_label.setText(f"Update failed: {instance['install_error']}")
            self.diagnostic_hint_label.setText("Recover the previous release or retry the update.")
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
        if self._mutation_blocked(instance, allow_recovery=True) or self._session_controls_locked:
            return
        self._set_session_controls_locked(True)
        try:
            updater = self._updater_for_provider(provider)
            game_root = self.store.instance_game_root(instance["id"])
            updater.recover(instance, game_root)
            self.store.save(self.state)
            try:
                ModrinthPackUpdater._durable_unlink(game_root / "update-journal.json")
            except (OSError, RuntimeError):
                self._mark_update_recovery_required(instance, "Pack recovery journal cleanup was not durable", force_recovery=True)
                raise
            self.instance_status_label.setText(f"Recovered: {instance['name']}")
            self.diagnostic_hint_label.setText("The previous Modrinth release and worlds were restored.")
        except (ModrinthPackUpdateError, OSError, RuntimeError) as error:
            self._mark_update_recovery_required(instance, str(error) or "Modrinth update recovery failed")
            self.diagnostic_hint_label.setText(instance["install_error"])
        finally:
            self._set_session_controls_locked(False)
            self._refresh_play_button()

    def _recover_selected_curseforge_pack(self) -> None:
        self._recover_selected_modrinth_pack()

    def _updater_for_provider(self, provider: str):
        if provider == "modrinth":
            return self.modrinth_updater
        if provider == "curseforge":
            return self.curseforge_updater
        raise ModrinthPackUpdateError(f"No updater is configured for provider {provider!r}")

    def _show_import_progress(self, status: str, current: int, maximum: int) -> None:
        if status:
            self.instance_status_label.setText(status)
        if maximum > 0:
            self.install_progress.setRange(0, maximum)
            self.install_progress.setValue(max(0, current))

    def _update_journal_path(self, instance: dict) -> Path:
        return self.store.instance_root(str(instance["id"])) / "update-journal.json"

    def _update_journal_exists(self, instance: dict | None) -> bool:
        return bool(instance and instance.get("id") and self._update_journal_path(instance).is_file())

    def _mark_update_recovery_required(self, instance: dict, message: str, *, force_recovery: bool = False) -> None:
        journal = self._update_journal_path(instance)
        journal_exists = journal.is_file()
        try:
            data = json.loads(journal.read_text(encoding="utf-8")) if journal_exists else {}
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict) and isinstance(data.get("backup"), str):
            instance["recovery_backup"] = data["backup"]
        instance["ready"] = False
        instance["install_state"] = "failed"
        instance["update_recovery_required"] = force_recovery or journal_exists or bool(instance.get("update_recovery_required"))
        instance["install_error"] = message or "Pack update recovery is required"
        if not self.store.recovery_required:
            try:
                self.store.save(self.state)
            except (OSError, RuntimeError):
                pass

    def _mutation_blocked(self, instance: dict | None, *, report: bool = True,
                          allow_recovery: bool = False) -> bool:
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
        if instance.get("update_recovery_required") and not allow_recovery:
            if report:
                self.diagnostic_hint_label.setText("Recover the interrupted pack update before playing or updating it.")
            return True
        if self._update_journal_exists(instance) and not allow_recovery:
            if report:
                self.diagnostic_hint_label.setText("Recover the interrupted pack update before playing or updating it.")
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
            self.selected_instance_heading.setText(str(instance["name"]))
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
            self.audit.record("duplicate_instance", outcome="failed", source_id=source_id, error=str(error))
            self.diagnostic_hint_label.setText(f"Could not duplicate instance: {error}")
            return
        self.audit.record("duplicate_instance", outcome="copied", source_id=source_id,
                          destination_id=destination_id, folder=inventory(destination_root))
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
            self.audit.record("delete_instance", phase="started", instance_id=instance_id, name=name,
                              instance=compact_instance(instance), folder=inventory(root))
            shutil.rmtree(root)
        except OSError as error:
            self.audit.record("delete_instance", phase="failed", instance_id=instance_id, error=str(error))
            self.diagnostic_hint_label.setText(f"Could not delete instance: {error}")
            return
        self.audit.record("delete_instance", phase="folder_removed", instance_id=instance_id)
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
            self.open_folder_button.setEnabled(False)
            self.open_screenshots_button.setEnabled(False)
            self.selected_instance_heading.setText("No setup selected")
            self.selected_instance_description.setText("Pick a setup from the list, or create a new one below it.")
            self._refresh_install_button()
            if self._preserve_lifecycle_status():
                return
            self.instance_status_label.set_summary("No instance selected")
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
        self.open_screenshots_button.setEnabled(instance is not None)
        if instance:
            self.selected_instance_heading.setText(str(instance["name"]))
            self.selected_instance_description.setText(self._describe_instance(instance).detail)
        self.save_log_button.setEnabled(instance is not None)
        if instance and instance.get("ready"):
            self.instance_status_label.set_summary(f"Ready: {current.text()} ({instance.get('version')})")
        elif instance and instance.get("install_error"):
            self.instance_status_label.setText(f"Installation failed: {instance['install_error']}")
            self.diagnostic_hint_label.setText("Install Minecraft again to retry this instance.")
        else:
            self.instance_status_label.set_summary(f"Selected instance: {current.text()}")
            self.diagnostic_hint_label.setText(str(instance.get("last_event", "")))
        self.install_button.setEnabled(self.install_worker is None)
        self._refresh_install_button()
        self._refresh_play_button()
        self._refresh_instance_mutation_buttons()
        self._refresh_mods_panel()
        self._refresh_hero()
        self._preserve_lifecycle_status()

    def _search_modrinth_mods(self) -> None:
        self._set_mods_mode("find")
        instance = self._selected_instance()
        query = self.mod_search_input.text().strip()
        if instance is None:
            self.mod_search_status.setText("Select an instance before searching for mods.")
            return
        if not query:
            self.mod_search_status.setText("Enter a mod name or search term.")
            self.mod_search_input.setFocus()
            return
        game_version = instance.get("minecraft_version") or instance.get("version")
        loader = instance.get("loader")
        if not isinstance(game_version, str) or not isinstance(loader, str):
            self.mod_search_status.setText("This instance has no verified game and loader combination.")
            return
        if not self._catalog_injected:
            if self._mod_query_worker is not None and self._mod_query_worker.isRunning():
                self._mod_query_worker.cancel()
            self._mod_query_request += 1
            request = self._mod_query_request
            instance_id = instance.get("id")
            self._mod_query_worker = ModQueryWorker(self.modrinth_catalog, "search", query, game_version, loader)
            self._mod_query_worker.completed.connect(
                lambda results, request=request, instance_id=instance_id, game_version=game_version, loader=loader:
                self._mod_search_completed(request, instance_id, game_version, loader, results)
            )
            self._mod_query_worker.failed.connect(lambda message, request=request: self._mod_search_failed(request, message))
            self._mod_last_query = query
            self.mod_search_results.clear()
            self.mod_search_results.set_placeholder("Searching Modrinth…", f"Looking for “{query}”.")
            self._mod_query_worker.start()
            return
        try:
            results = self.modrinth_catalog.search_mods(query, game_version=game_version, loader=loader)
        except (ModrinthCatalogError, OSError, RuntimeError) as error:
            self.mod_search_results.clear()
            self.mod_search_status.setText(f"Mod search failed: {error}")
            self._mod_placeholder_failed()
            return
        self._mod_last_query = query
        self.mod_search_results.clear()
        self.mod_release_selector.clear()
        self.mod_install_button.setEnabled(False)
        for result in results:
            self.mod_search_results.addItem(self._result_item(result))
        self.mod_search_status.setText(
            f"{len(results)} compatible Modrinth mod(s) found." if results else "No compatible Modrinth mods matched."
        )
        self._mod_placeholder_empty()

    def _mod_search_completed(self, request, instance_id, game_version, loader, results) -> None:
        if self._closing or request != self._mod_query_request:
            return
        instance = self._selected_instance()
        if not instance or instance.get("id") != instance_id:
            return
        current_game_version = instance.get("minecraft_version") or instance.get("version")
        if current_game_version != game_version or instance.get("loader") != loader:
            return
        self.mod_search_results.clear()
        self.mod_release_selector.clear()
        self.mod_install_button.setEnabled(False)
        for result in results:
            self.mod_search_results.addItem(self._result_item(result))
        self.mod_search_status.setText(f"{len(results)} compatible Modrinth mod(s) found." if results else "No compatible Modrinth mods matched.")
        self._mod_placeholder_empty()

    def _mod_search_failed(self, request, message: str) -> None:
        if self._closing or request != self._mod_query_request:
            return
        self.mod_search_status.setText(f"Mod search failed: {message}")
        self._mod_placeholder_failed()

    def _mod_placeholder_empty(self) -> None:
        self.mod_search_results.set_placeholder(
            f"No compatible mods match “{getattr(self, '_mod_last_query', '')}”",
            "Only mods for this setup’s game version and loader are shown.")

    def _mod_placeholder_failed(self) -> None:
        self.mod_search_results.set_placeholder(
            "Couldn’t reach Modrinth", "Check your connection and search again, or add a jar from disk.")

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
        if not self._catalog_injected:
            if self._mod_query_worker is not None and self._mod_query_worker.isRunning():
                self._mod_query_worker.cancel()
            self._mod_query_request += 1
            request = self._mod_query_request
            self._mod_query_worker = ModQueryWorker(self.modrinth_catalog, "releases", project_id, game_version, loader)
            instance_id = instance.get("id")
            self._mod_query_worker.completed.connect(
                lambda releases, request=request, instance_id=instance_id, game_version=game_version, loader=loader:
                self._mod_releases_completed(request, instance_id, game_version, loader, releases)
            )
            self._mod_query_worker.failed.connect(lambda message, request=request: self._mod_releases_failed(request, message))
            self._mod_query_worker.start()
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

    def _mod_releases_completed(self, request, instance_id, game_version, loader, releases) -> None:
        if self._closing or request != self._mod_query_request:
            return
        instance = self._selected_instance()
        if not instance or instance.get("id") != instance_id:
            return
        current_game_version = instance.get("minecraft_version") or instance.get("version")
        current_loader = instance.get("loader")
        if current_game_version != game_version or current_loader != loader:
            return
        self.mod_release_selector.clear()
        for release in releases:
            if game_version in release.game_versions and loader in release.loaders:
                self.mod_release_selector.addItem(f"{release.version_number or release.name} · {release.file_name}", release)
        self.mod_install_button.setEnabled(self.mod_release_selector.count() > 0)
        self.mod_search_status.setText(f"{self.mod_release_selector.count()} compatible release(s) available.")

    def _mod_releases_failed(self, request, message: str) -> None:
        if self._closing or request != self._mod_query_request:
            return
        self.mod_search_status.setText(f"Could not load mod releases: {message}")

    def _install_selected_modrinth_mod(self) -> None:
        instance = self._selected_instance()
        release = self.mod_release_selector.currentData(Qt.ItemDataRole.UserRole)
        if self._mutation_blocked(instance) or instance is None or not isinstance(release, ModrinthRelease):
            return
        self.mod_install_button.setEnabled(False)
        if not self._mod_installer_injected:
            self._mod_worker = ModInstallWorker(self.mod_installer, instance, self.store.instance_game_root(instance["id"]), release)
            self._mod_worker.completed.connect(self._mod_install_completed)
            self._mod_worker.failed.connect(lambda message: self.mod_search_status.setText(f"Mod installation failed: {message}. Retry when the files are available."))
            self._mod_worker.finished.connect(lambda: self.mod_install_button.setEnabled(self.mod_release_selector.count() > 0))
            self._mod_worker.start()
            return
        try:
            entries = self.mod_installer.install(
                instance, self.store.instance_game_root(instance["id"]), release,
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

    def _mod_install_completed(self, entries) -> None:
        if self._closing:
            return
        worker = self._mod_worker
        instance_id = worker.instance_id if worker is not None else None
        instance = next((item for item in self.state.get("instances", []) if item.get("id") == instance_id), None)
        if instance is None:
            return
        instance.setdefault("mods", []).extend(entries)
        instance["modified"] = True
        self.store.save(self.state)
        self._refresh_mods_panel()
        self.mod_search_status.setText(f"Installed {len(entries)} mod and required dependency file(s).")

    _search_mods = _search_modrinth_mods
    _install_selected_mod = _install_selected_modrinth_mod

    def _set_mods_mode(self, mode: str) -> None:
        """Show one Mods task: "installed" (manage the list) or "find" (search Modrinth)."""
        find = mode == "find"
        self.mods_mode_stack.setCurrentIndex(1 if find else 0)
        self.mods_find_mode_button.setChecked(find)
        self.mods_installed_mode_button.setChecked(not find)

    def _refresh_mods_panel(self) -> None:
        instance = self._selected_instance()
        selected_mod_id = self.mods_list.currentItem().data(Qt.ItemDataRole.UserRole) if self.mods_list.currentItem() else None
        self.mods_list.clear()
        if instance is None:
            self.mods_instance_label.setText("Select an instance to manage its mods.")
            self.mods_warning_label.clear()
            self.mods_list.set_placeholder("No setup selected", "Go back to Instances and pick a setup.")
            self.mod_search_results.set_placeholder("No setup selected")
            self.mods_vanilla_notice.hide()
            self._mods_online_section.show()
            self.mods_installed_mode_button.setText("Installed")
            self._refresh_mod_buttons()
            return
        if getattr(self, "_mods_panel_instance_id", None) != instance.get("id"):
            # Results and releases were filtered to the previous setup's
            # version and loader; never offer them for this one.
            self._mods_panel_instance_id = instance.get("id")
            self.mod_search_results.clear()
            self.mod_release_selector.clear()
            self.mod_search_status.clear()
            # Nothing installed yet: the next step is finding something.
            self._set_mods_mode("installed" if instance.get("mods") else "find")
        loader = str(instance.get("loader") or "").strip().lower()
        modded = bool(loader) and loader != "vanilla"
        self.mods_list.set_placeholder(
            "No mods installed yet",
            "Open Find mods to search Modrinth, or add a .jar you downloaded." if modded
            else "This setup runs vanilla Minecraft, which doesn’t load mods.")
        # One truthful state: vanilla swaps the online search for a way forward.
        self._mods_online_section.setVisible(modded)
        self.mods_vanilla_notice.setVisible(not modded)
        if not modded:
            self._refresh_vanilla_notice(instance)
        if not self.mod_search_results.count():
            self.mod_search_results.set_placeholder(
                "Search for mods", "Results are filtered to this setup’s version and loader.")
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
        installed = len(instance.get("mods", []))
        self.mods_installed_mode_button.setText(f"Installed ({installed})")
        self.mods_installed_mode_button.setAccessibleName(f"Installed mods, {installed}")
        self._refresh_mod_buttons()

    def _compatible_mod_setup(self, exclude_id: str | None = None) -> dict | None:
        """First saved setup with a mod loader, for routing away from vanilla."""
        return next((item for item in self.state.get("instances", [])
                     if item.get("id") != exclude_id
                     and str(item.get("loader") or "").strip().lower() not in {"", "vanilla"}), None)

    def _refresh_vanilla_notice(self, instance: dict) -> None:
        target = self._compatible_mod_setup(instance.get("id"))
        name = str(instance.get("name") or "This setup")
        if target is not None:
            self.mods_vanilla_detail.setText(
                f"{name} is vanilla Minecraft, which can’t load mods. "
                f"Switch to {target.get('name')}, which uses {str(target.get('loader')).capitalize()}, "
                "or install a modded pack.")
            self.mods_switch_setup_button.setText(f"Switch to {target.get('name')}")
            self.mods_switch_setup_button.setProperty("targetId", target.get("id"))
            self.mods_switch_setup_button.show()
            set_role(self.mods_browse_packs_button, "")
        else:
            self.mods_vanilla_detail.setText(
                f"{name} is vanilla Minecraft, which can’t load mods. Install a modded pack "
                "(Fabric, Forge, Quilt or NeoForge) from Modpacks to add mods to it.")
            self.mods_switch_setup_button.setProperty("targetId", None)
            self.mods_switch_setup_button.hide()
            set_role(self.mods_browse_packs_button, "primary")
        ui.repolish(self.mods_browse_packs_button)

    def _switch_to_modded_setup(self) -> None:
        target_id = self.mods_switch_setup_button.property("targetId")
        for row in range(self.instance_list.count()):
            if self.instance_list.item(row).data(Qt.ItemDataRole.UserRole) == target_id:
                self.instance_list.setCurrentRow(row)
                self._set_mods_mode("find")
                self.mod_search_input.setFocus(Qt.FocusReason.OtherFocusReason)
                return

    def _result_item(self, result: dict) -> QListWidgetItem:
        """A two-line search result: name, then who made it or what it is."""
        title = str(result.get("title") or result.get("name") or result.get("slug") or result.get("project_id"))
        description = " ".join(str(result.get("description") or "").split())
        meta = []
        if result.get("author"):
            meta.append(f"by {result['author']}")
        downloads = result.get("downloads")
        if isinstance(downloads, int) and downloads > 0:
            meta.append(f"{downloads / 1_000_000:.1f}M downloads" if downloads >= 1_000_000
                        else f"{downloads / 1000:.0f}k downloads" if downloads >= 1000 else f"{downloads} downloads")
        item = QListWidgetItem(title)
        item.setData(Qt.ItemDataRole.UserRole, result)
        item.setData(ROW_INFO_ROLE, RowInfo(title, " · ".join(meta) or description))
        item.setToolTip(description)
        return item

    def _refresh_mod_buttons(self) -> None:
        instance = self._selected_instance()
        blocked = self._mutation_blocked(instance, report=False) if instance else True
        has_mod = instance is not None and self.mods_list.currentRow() >= 0
        enabled = instance is not None and not blocked and not self._session_controls_locked
        loader = str((instance or {}).get("loader") or "").strip().lower()
        searchable = enabled and bool(loader) and loader != "vanilla"
        self.mod_search_input.setEnabled(searchable)
        self.mod_search_button.setEnabled(searchable)
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
            target = copy_mod_to_instance(source, self.store.instance_game_root(instance["id"]))
        except (OSError, ValueError) as error:
            self.audit.record("import_local_mod", outcome="failed", instance_id=instance["id"],
                              source_path=str(source), error=str(error))
            self.mods_warning_label.setText(f"Could not import {source.name}: {error}")
            return
        mod = dict(metadata)
        mod.update({"id": f"local:{target.name}", "filename": target.name, "path": str(target.relative_to(self.store.instance_game_root(instance["id"]))),
                    "enabled": True, "source": "local", "source_path": str(source)})
        instance.setdefault("mods", []).append(mod)
        instance["modified"] = True
        self.audit.record("import_local_mod", outcome="copied", instance_id=instance["id"],
                          source_path=str(source), target=file_facts(target),
                          compatible=metadata.get("compatible"))
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
        root = self.store.instance_game_root(instance["id"])
        current = root / str(mod.get("path", ""))
        enabled = not bool(mod.get("enabled", True))
        destination = root / ("mods" if enabled else "mods-disabled") / str(mod.get("filename", current.name))
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if current.exists():
                self.audit.record("toggle_mod", instance_id=instance["id"], mod=mod.get("filename"),
                                  enabled=enabled, source=str(current), destination=str(destination))
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
        root = self.store.instance_game_root(instance["id"])
        target = root / str(mod.get("path", ""))
        self.audit.record("remove_mod", phase="started", instance_id=instance["id"], mod=_small_mod(mod),
                          file=file_facts(target))
        try:
            target.unlink(missing_ok=True)
        except OSError as error:
            self.audit.record("remove_mod", phase="failed", instance_id=instance["id"], error=str(error))
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
            self.import_pack_menu_button,
            self.browse_import_modrinth_button,
            self.browse_import_curseforge_button,
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
        self._refresh_mod_buttons()

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

    def _open_selected_instance_folder(self) -> None:
        self._open_selected_game_directory(screenshots=False)

    def _open_instance_screenshots(self) -> None:
        self._open_selected_game_directory(screenshots=True)

    def _open_selected_game_directory(self, *, screenshots: bool) -> None:
        instance = self._selected_instance()
        if instance is None:
            return
        label = "screenshots folder" if screenshots else "instance folder"
        try:
            folder = self.store.instance_game_root(instance["id"])
            if screenshots:
                folder = folder / "screenshots"
                folder.mkdir(parents=True, exist_ok=True)
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        except OSError as error:
            self.diagnostic_hint_label.setText(f"Could not open {label}: {error}")
            return
        result = "Opened" if opened else "Could not open"
        self.diagnostic_hint_label.setText(f"{result} {label}: {folder}")

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
        """Name the selected setup's state and make its next step the primary one."""
        instance = self._selected_instance()
        role, tooltip = "primary", "Download this setup’s Minecraft files"
        state, tone = "", "muted"
        if instance is None:
            self.install_button.setText("Install Minecraft")
            role = ""
        elif instance.get("install_error") or instance.get("install_state") == "interrupted":
            self.install_button.setText("Retry installation")
            tooltip = "Try the install again"
            state, tone = "● Needs attention", "warn"
        elif instance.get("install_state") in {"installing", "importing", "updating"}:
            self.install_button.setText("Install Minecraft")
            role, state = "", "● Installing…"
        elif instance.get("ready"):
            # Ready: Play is the recommended action, so this is maintenance.
            self.install_button.setText("Repair files")
            role, tooltip = "", "Check this setup’s Minecraft files and download anything missing"
            state, tone = "● Ready to play", "good"
        else:
            self.install_button.setText("Install Minecraft")
            state = "● Not installed"
        self.install_button.setToolTip(tooltip)
        if self.install_button.property("role") != role:
            set_role(self.install_button, role)
            ui.repolish(self.install_button)
        self.selected_instance_state.setText(state)
        self.selected_instance_state.setVisible(bool(state))
        ui.set_tone(self.selected_instance_state, tone)

    def _refresh_play_button(self) -> None:
        instance = self._selected_instance()
        version = self._selected_version()
        if instance is None and version:
            self.play_button.setEnabled(
                not self._session_controls_locked and self.install_worker is None and self.game_process is None
            )
            automatic = next((item for item in self.state.get("instances", [])
                              if item.get("id") == self.state.get("automatic_instances", {}).get(version)), None)
            ready = self._version_is_downloaded(version) or bool(automatic and automatic.get("ready"))
            self.play_button.setText("▶  Play" if ready else "⬇  Install && Play")
            self._explain_play_state()
            return
        available = bool(
            instance and instance.get("install_state") != "incomplete"
            and not self._session_controls_locked and self.install_worker is None and self.game_process is None
        )
        if instance and instance.get("provider") in {"modrinth", "curseforge"} and instance.get("install_state") in {
            "failed", "importing", "updating", "interrupted"
        }:
            available = False
        self.play_button.setEnabled(available)
        if instance and (instance.get("install_error") or instance.get("install_state") == "interrupted"):
            self.play_button.setText("↻  Retry")
        elif instance and not instance.get("ready") and not instance.get("provider"):
            self.play_button.setText("⬇  Install && Play")
        else:
            self.play_button.setText("▶  Play")
        self._explain_play_state()

    def _play_block_reason(self) -> str:
        if self.play_button.isEnabled():
            return ""
        if self.store.recovery_required:
            return "Recover your settings first"
        if self.game_process is not None:
            return "A game is already running"
        if self.install_worker is not None:
            return "Wait for the current install to finish"
        if self._session_controls_locked:
            return "Busy with another task"
        instance = self._selected_instance()
        if instance is None and not self._selected_version():
            if self.setup_selector.count() == 0:
                return ("The version list hasn’t loaded yet" if not getattr(self, "_discovery_error", "")
                        else "No versions available. Retry the version list")
            return "Pick a version or setup first"
        if instance is not None and instance.get("provider"):
            return "This modpack needs to be repaired from Instances first"
        return "This setup isn’t ready to start"

    def _explain_play_state(self) -> None:
        reason = self._play_block_reason()
        tooltip = reason or {
            "▶  Play": "Start Minecraft",
            "⬇  Install && Play": "Download this version, then start Minecraft",
            "↻  Retry": "Try the install again, then start Minecraft",
        }.get(self.play_button.text(), "")
        self.play_button.setToolTip(tooltip)
        self.play_button.setAccessibleDescription(tooltip)

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
            self.audit.record("game_launch", outcome="failed", instance_id=instance.get("id"),
                              name=instance.get("name"), error=str(error))
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
        self.audit.record("game_launch", outcome="started", instance_id=instance["id"],
                          name=instance.get("name"), pid=process_id, username=username, memory_gib=memory_gib,
                          version=instance.get("version"), loader=instance.get("loader"))
        if self.instance_status_label.text().startswith("Starting"):
            self._game_started(instance)

    def _game_started(self, instance: dict) -> None:
        self.instance_status_label.setText(f"Running: {instance['name']}")
        self._set_session_controls_locked(True)
        self._refresh_instance_mutation_buttons()

    def _game_finished(self, instance: dict, exit_code: int, crashed: bool) -> None:
        if self.game_instance is not None and self.game_instance.get("id") != instance.get("id"):
            return
        self.audit.record("game_exit", instance_id=instance.get("id"), name=instance.get("name"),
                          pid=(self.game_record or {}).get("pid"), exit_code=exit_code, crashed=crashed)
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

    def _persist_interrupted_operation(self, instance: dict | None, *, updating: bool = False) -> None:
        if not instance or self.store.recovery_required:
            return
        instance["ready"] = False
        instance["install_state"] = "interrupted"
        if updating:
            instance["update_recovery_required"] = True
            instance["install_error"] = "Pack update interrupted; recover the previous release before playing"
        else:
            instance["install_error"] = "Pack preparation interrupted; retry to continue"
        self.store.save(self.state)

    def closeEvent(self, event) -> None:
        self.audit.record(
            "app_close",
            installing_instance_id=(self.installing_instance or {}).get("id") if self.install_worker else None,
            game_running=self.game_process is not None,
            game_instance_id=(self.game_instance or {}).get("id"),
        )
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
        if self._catalog_browse_worker is not None and self._catalog_browse_worker.isRunning():
            self._closing = True
            self._catalog_browse_worker.cancel()
            event.accept()
            return
        if self._catalog_worker is not None and self._catalog_worker.isRunning():
            self._closing = True
            context = getattr(self, "_catalog_release_context", None)
            self._persist_interrupted_operation(context[3] if context else None, updating=self._catalog_worker.updating)
            self._catalog_worker.cancel()
            self._set_session_controls_locked(False)
            event.accept()
            return
        if getattr(self, "_pack_worker", None) is not None and self._pack_worker.isRunning():
            self._closing = True
            self._persist_interrupted_operation(getattr(self, "_pack_worker_instance", None))
            self._pack_worker.cancel()
            self._set_session_controls_locked(False)
            event.accept()
            return
        if getattr(self, "_update_worker", None) is not None and self._update_worker.isRunning():
            self._closing = True
            self._persist_interrupted_operation(getattr(self, "_update_worker_instance", None), updating=True)
            self._update_worker.cancel()
            self._set_session_controls_locked(False)
            event.accept()
            return
        if getattr(self, "_mod_query_worker", None) is not None and self._mod_query_worker.isRunning():
            self._closing = True
            self._mod_query_worker.cancel()
            event.accept()
            return
        if getattr(self, "_mod_worker", None) is not None and self._mod_worker.isRunning():
            self._closing = True
            self._mod_worker.cancel()
            event.accept()
            return
        if getattr(self, "_optifine_worker", None) is not None and self._optifine_worker.isRunning():
            self._closing = True
            self._optifine_worker.cancel()
            event.accept()
            return
        if not self.store.recovery_required:
            self.store.save(self.state)
        self.game_poll_timer.stop()
        if self.game_process is None:
            self.game_registry.clear()
        self.game_registry.release()
        super().closeEvent(event)


class OptiFineWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, installer, instance, directory, jar) -> None:
        super().__init__()
        self.installer = installer
        self.instance = instance.copy()
        self.instance_id = instance.get("id")
        self.directory = directory
        self.jar = jar
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.requestInterruption()

    def run(self) -> None:
        try:
            result = self.installer.prepare(
                self.instance, self.directory, self.jar, cancel_event=self.cancel_event,
            )
            if not self.isInterruptionRequested():
                self.completed.emit(result)
        except Exception as error:
            if not self.isInterruptionRequested():
                self.failed.emit(str(error))


class ModQueryWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, catalog, mode, value, game_version, loader) -> None:
        super().__init__()
        self.catalog = catalog
        self.mode = mode
        self.value = value
        self.game_version = game_version
        self.loader = loader
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.requestInterruption()

    def run(self) -> None:
        try:
            if self.mode == "search":
                result = self.catalog.search_mods(self.value, game_version=self.game_version, loader=self.loader)
            else:
                result = self.catalog.releases(self.value, game_version=self.game_version, loader=self.loader)
            if not self.isInterruptionRequested():
                self.completed.emit(result)
        except Exception as error:
            if not self.isInterruptionRequested():
                self.failed.emit(str(error))


class CatalogBrowseWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, catalog, mode, value) -> None:
        super().__init__()
        self.catalog = catalog
        self.mode = mode
        self.value = value
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.requestInterruption()

    def run(self) -> None:
        try:
            if self.mode == "search":
                result = self.catalog.search(self.value)
            else:
                result = (self.catalog.project(self.value), self.catalog.releases(self.value))
            if not self.isInterruptionRequested() and not self.cancel_event.is_set():
                self.completed.emit(result)
        except Exception as error:
            if not self.isInterruptionRequested() and not self.cancel_event.is_set():
                self.failed.emit(str(error))


class ModInstallWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, installer, instance, directory, release) -> None:
        super().__init__()
        self.installer = installer
        self.instance = instance.copy()
        self.instance_id = instance.get("id")
        self.directory = directory
        self.release = release
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.requestInterruption()

    def run(self) -> None:
        try:
            entries = self.installer.install(
                self.instance, self.directory, self.release, cancel_event=self.cancel_event,
            )
            if not self.isInterruptionRequested():
                self.completed.emit(entries)
        except Exception as error:
            if not self.isInterruptionRequested():
                self.failed.emit(str(error))


class PackUpdateWorker(QThread):
    completed = Signal()
    failed = Signal(str)
    progress = Signal(str, int, int)

    def __init__(self, updater, archive, directory, instance, release_id, replacement_directory=None) -> None:
        super().__init__()
        self.updater = updater
        self.archive = archive
        self.directory = directory
        self.instance = instance.copy()
        self.release_id = release_id
        self.replacement_directory = replacement_directory
        self.instance_result = None
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.requestInterruption()

    def run(self) -> None:
        try:
            self.updater.update(
                self.instance, self.directory, self.archive, release_id=self.release_id,
                on_progress=lambda *args: self.progress.emit(*args),
                confirm_local_changes=lambda _paths: True,
                cancel_event=self.cancel_event,
                replacements=(self.updater.importer.prepare_replacements(self.archive, self.replacement_directory)
                              if self.replacement_directory and hasattr(self.updater.importer, "prepare_replacements") else None),
            )
            self.instance_result = self.instance
            if not self.isInterruptionRequested():
                self.completed.emit()
        except Exception as error:
            if not self.isInterruptionRequested():
                self.failed.emit(str(error))


class PackPreparationWorker(QThread):
    completed = Signal()
    failed = Signal(str)
    progress = Signal(str, int, int)

    def __init__(self, importer, installer, archive, directory, instance, *, game_directory=None) -> None:
        super().__init__()
        self.importer = importer
        self.installer = installer
        self.archive = archive
        self.directory = directory
        self.game_directory = game_directory or game_directory_for(directory)
        self.instance = instance.copy()
        self.metadata = None
        self.instance_result = None
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.requestInterruption()

    def run(self) -> None:
        try:
            self.metadata = self.importer.import_archive(
                self.archive, self.game_directory,
                on_progress=lambda *args: self.progress.emit(*args),
                cancel_event=self.cancel_event,
            )
            if not self.metadata.get("complete", True):
                raise RuntimeError("The selected pack has unavailable required files")
            installer_method = getattr(self.installer, "install_modpack", None)
            if not callable(installer_method):
                raise RuntimeError("The configured installer cannot prepare this modpack")
            installed = installer_method(
                self.instance, self.directory, self.metadata,
                lambda *args: self.progress.emit(*args),
                cancel_event=self.cancel_event,
            )
            if installed:
                self.instance["installed_version"] = installed
            self.instance_result = self.instance
            if not self.isInterruptionRequested():
                self.completed.emit()
        except Exception as error:
            if not self.isInterruptionRequested():
                self.failed.emit(str(error))


class CatalogOperationWorker(QThread):
    completed = Signal()
    failed = Signal(str)
    progress = Signal(str, int, int)

    def __init__(self, catalog, release, importer, installer, archive, directory, instance, updater=None, release_id="",
                 *, game_directory=None) -> None:
        super().__init__()
        self.catalog = catalog
        self.release = release
        self.importer = importer
        self.installer = installer
        self.archive = archive
        self.directory = directory
        self.game_directory = game_directory or game_directory_for(directory)
        self.instance = instance.copy()
        self.updater = updater
        self.release_id = release_id
        self.updating = updater is not None
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.requestInterruption()
        self.metadata = None
        self.instance_result = None

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            downloaded = self.catalog.download_release(self.release)
            if self.cancel_event.is_set() or self.isInterruptionRequested():
                return
            self.archive.write_bytes(downloaded)
            if self.updating:
                result = self.updater.update(
                    self.instance, self.game_directory, self.archive, release_id=self.release_id,
                    on_progress=lambda *args: self.progress.emit(*args),
                    confirm_local_changes=lambda _paths: True,
                    cancel_event=self.cancel_event,
                )
                self.metadata = result["metadata"]
            else:
                self.metadata = self.importer.import_archive(
                    self.archive, self.game_directory,
                    on_progress=lambda *args: self.progress.emit(*args), cancel_event=self.cancel_event,
                )
                if not self.metadata.get("complete", True):
                    raise RuntimeError("The selected catalog pack has unavailable required files")
                if self.isInterruptionRequested():
                    return
                installer_method = getattr(self.installer, "install_modpack", None)
                if not callable(installer_method):
                    raise RuntimeError("The configured installer cannot prepare this modpack")
                installed = installer_method(
                    self.instance, self.directory, self.metadata,
                    lambda *args: self.progress.emit(*args),
                    cancel_event=self.cancel_event,
                )
                if installed:
                    self.instance["installed_version"] = installed
            self.instance_result = self.instance
            if not self.isInterruptionRequested():
                self.completed.emit()
        except Exception as error:
            if not self.isInterruptionRequested():
                self.failed.emit(str(error))


class CatalogDownloadWorker(QThread):
    completed = Signal(bytes)
    failed = Signal(str)

    def __init__(self, catalog, release) -> None:
        super().__init__()
        self.catalog = catalog
        self.release = release

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            content = self.catalog.download_release(self.release)
            if not self.isInterruptionRequested():
                self.completed.emit(content)
        except Exception as error:
            if not self.isInterruptionRequested():
                self.failed.emit(str(error))


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
