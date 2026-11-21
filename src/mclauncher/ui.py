"""Visual building blocks for the launcher window.

The palette borrows from the game's own materials: deepslate for surfaces,
prismarine for the one action that matters (Play), gold and redstone for
warnings and destructive actions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QEvent, QModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

# ── Tokens ──────────────────────────────────────────────────────────────────
DEEPSLATE = "#1f232a"   # window base
SLATE = "#272c34"       # panels
COBBLE = "#313742"      # raised controls
SEAM = "#414957"        # borders
SEAM_SOFT = "#363d49"
SNOW = "#eceff3"        # primary text
FOG = "#9aa3b1"         # secondary text
ASH = "#6f7887"         # disabled text
PRISMARINE = "#5fd0b5"  # the play accent
PRISMARINE_DEEP = "#123a32"
GOLD = "#e9c25b"
REDSTONE = "#e5574c"

BODY_FONT = '"Noto Sans", "Ubuntu", "Cantarell", "DejaVu Sans"'
DISPLAY_FONT = '"Liberation Sans Narrow", "Nimbus Sans Narrow", "Ubuntu Condensed", "DejaVu Sans Condensed"'


def display_font(pixel_size: int, weight: QFont.Weight = QFont.Weight.Bold) -> QFont:
    font = QFont()
    font.setFamilies(["Liberation Sans Narrow", "Nimbus Sans Narrow", "Ubuntu Condensed", "DejaVu Sans Condensed"])
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


def body_font(pixel_size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(["Noto Sans", "Ubuntu", "Cantarell", "DejaVu Sans"])
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


STYLESHEET = f"""
QWidget {{ background: {DEEPSLATE}; color: {SNOW}; font-family: {BODY_FONT}; font-size: 13px; }}
QLabel {{ background: transparent; }}
QToolTip {{ background: {COBBLE}; color: {SNOW}; border: 1px solid {SEAM}; padding: 4px 6px; }}

/* Top bar: brand, page tabs, settings */
QFrame#titleBar {{ background: {DEEPSLATE}; border-bottom: 1px solid {SEAM_SOFT}; }}
QLabel#brandLabel {{ font-family: {DISPLAY_FONT}; font-size: 19px; font-weight: 700; color: {SNOW};
    padding-right: 18px; }}
QPushButton#homeNavButton, QPushButton#instancesNavButton, QPushButton#browseNavButton,
QPushButton#modsNavButton {{ background: transparent; border: 0; border-bottom: 2px solid transparent;
    border-radius: 0; color: {FOG}; padding: 14px 4px 12px 4px; margin: 0 10px; font-weight: 600; }}
QPushButton#homeNavButton:hover, QPushButton#instancesNavButton:hover, QPushButton#browseNavButton:hover,
QPushButton#modsNavButton:hover {{ color: {SNOW}; background: transparent; }}
QPushButton#homeNavButton[active="true"], QPushButton#instancesNavButton[active="true"],
QPushButton#browseNavButton[active="true"], QPushButton#modsNavButton[active="true"] {{
    color: {SNOW}; border-bottom: 2px solid {PRISMARINE}; }}
QPushButton#settingsButton {{ background: transparent; border: 1px solid transparent; color: {FOG}; }}
QPushButton#settingsButton:hover {{ color: {SNOW}; background: {COBBLE}; }}

/* Home hero over the artwork */
QLabel#heroTitle {{ font-family: {DISPLAY_FONT}; font-size: 40px; font-weight: 700; color: #ffffff; }}
QLabel#heroDetail {{ font-size: 14px; color: #dfe6ea; }}

/* Launch dock */
QFrame#launchBar {{ background: {SLATE}; border-top: 1px solid {SEAM_SOFT}; }}
QLabel#usernameFieldLabel, QLabel#setupFieldLabel {{ color: {FOG}; font-size: 12px; }}
QLabel#instanceStatusLabel {{ color: {SNOW}; font-size: 13px; }}
QLabel#diagnosticHintLabel, QLabel#usernameWarning, QLabel#modsWarningLabel {{ color: {GOLD}; font-size: 12px; }}
QLabel#stateRecoveryLabel, QLabel#memorySettingError, QLabel#settingsError {{ color: #ff9d94; }}

/* Inputs */
QLineEdit, QComboBox {{ background: {COBBLE}; color: {SNOW}; border: 1px solid {SEAM}; border-radius: 6px;
    padding: 7px 11px; min-height: 22px; selection-background-color: {PRISMARINE}; selection-color: {PRISMARINE_DEEP}; }}
QLineEdit:hover, QComboBox:hover {{ border-color: #566072; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {PRISMARINE}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {ASH}; background: {SLATE}; border-color: {SEAM_SOFT}; }}
QComboBox::drop-down {{ border: 0; width: 26px; }}
QComboBox QAbstractItemView {{ background: {SLATE}; border: 1px solid {SEAM}; selection-background-color: {COBBLE};
    outline: 0; padding: 4px; }}
QComboBox#setupSelector {{ padding: 0; }}

/* Buttons */
QPushButton {{ background: {COBBLE}; color: {SNOW}; border: 1px solid {SEAM}; border-radius: 6px;
    padding: 7px 14px; font-weight: 600; }}
QPushButton:hover {{ background: #3a4150; border-color: #566072; }}
QPushButton:pressed {{ background: {SLATE}; }}
QPushButton:focus {{ border: 1px solid {PRISMARINE}; }}
QPushButton:disabled {{ color: {ASH}; background: {SLATE}; border-color: {SEAM_SOFT}; }}
QPushButton[role="primary"] {{ background: {PRISMARINE}; color: {PRISMARINE_DEEP}; border: 1px solid {PRISMARINE}; }}
QPushButton[role="primary"]:hover {{ background: #7fe0c8; }}
QPushButton[role="primary"]:disabled {{ background: #2c4a44; color: #8fb3aa; border-color: #2c4a44; }}
QPushButton[role="danger"] {{ background: transparent; color: #ff9d94; border: 1px solid #6b3833; }}
QPushButton[role="danger"]:hover {{ background: #3b2423; }}
QPushButton[role="danger"]:disabled {{ color: {ASH}; border-color: {SEAM_SOFT}; }}
QPushButton[role="quiet"] {{ background: transparent; border: 1px solid transparent; color: {FOG}; }}
QPushButton[role="quiet"]:hover {{ background: {COBBLE}; color: {SNOW}; }}
QPushButton#playButton {{ background: {PRISMARINE}; color: {PRISMARINE_DEEP}; border: 0; border-radius: 6px;
    font-family: {DISPLAY_FONT}; font-size: 20px; font-weight: 700; padding: 0 26px; }}
QPushButton#playButton:hover {{ background: #7fe0c8; }}
QPushButton#playButton:focus {{ border: 2px solid #ffffff; }}
QPushButton#playButton:disabled {{ background: #2c4a44; color: #8fb3aa; }}

/* Lists */
QListWidget {{ background: {SLATE}; border: 1px solid {SEAM_SOFT}; border-radius: 8px; padding: 4px; outline: 0; }}
QListWidget::item {{ padding: 9px 10px; border-radius: 5px; color: {SNOW}; }}
QListWidget::item:selected {{ background: {COBBLE}; color: {SNOW}; }}
QListWidget::item:hover {{ background: #2d333d; }}
QListWidget:disabled {{ color: {ASH}; }}

/* Page typography */
QLabel[role="pageTitle"] {{ font-family: {DISPLAY_FONT}; font-size: 26px; font-weight: 700; color: {SNOW}; }}
QLabel[role="sectionTitle"] {{ font-size: 13px; font-weight: 700; color: {SNOW}; padding-top: 6px; }}
QLabel[role="muted"] {{ color: {FOG}; }}
QLabel#selectedInstanceHeading {{ font-family: {DISPLAY_FONT}; font-size: 24px; font-weight: 700; }}
QLabel#selectedInstanceDescription, QLabel#modsInstanceLabel, QLabel#modrinthCatalogStatus,
QLabel#modSearchStatus {{ color: {FOG}; }}
QLabel#modrinthPackDetails {{ color: {SNOW}; line-height: 140%; }}
QFrame[role="card"] {{ background: {SLATE}; border: 1px solid {SEAM_SOFT}; border-radius: 10px; }}
QFrame[role="card"] QLabel, QFrame[role="card"] QWidget#cardBody {{ background: transparent; }}
QFrame[role="rule"] {{ background: {SEAM_SOFT}; max-height: 1px; min-height: 1px; border: 0; }}

/* Scrolling, progress */
QScrollArea {{ background: transparent; border: 0; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SEAM}; border-radius: 3px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: #5a6475; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}
QProgressBar {{ background: {COBBLE}; border: 0; border-radius: 2px; max-height: 4px; min-height: 4px; }}
QProgressBar::chunk {{ background: {PRISMARINE}; border-radius: 2px; }}

/* Version picker popup */
QFrame#versionPopup {{ background: {SLATE}; border: 1px solid {SEAM}; border-radius: 10px; }}
QFrame#versionPopup QListWidget {{ background: transparent; border: 0; padding: 0; }}
QLineEdit#setupSearchInput {{ background: {DEEPSLATE}; }}
QLabel#selectorEmptyLabel {{ color: {FOG}; padding: 18px 6px; }}
QPushButton[role="chip"] {{ background: transparent; color: {FOG}; border: 1px solid {SEAM}; border-radius: 13px;
    padding: 3px 12px; font-weight: 600; font-size: 12px; }}
QPushButton[role="chip"]:hover {{ color: {SNOW}; }}
QPushButton[role="chip"]:checked {{ background: {COBBLE}; color: {SNOW}; border-color: {PRISMARINE}; }}

QDialog {{ background: {SLATE}; }}
QCheckBox {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {SEAM}; border-radius: 4px; background: {COBBLE}; }}
QCheckBox::indicator:checked {{ background: {PRISMARINE}; border-color: {PRISMARINE}; }}
"""


def set_role(widget: QWidget, role: str) -> QWidget:
    widget.setProperty("role", role)
    return widget


def rule(parent: QWidget | None = None) -> QFrame:
    line = QFrame(parent)
    line.setProperty("role", "rule")
    line.setFrameShape(QFrame.Shape.NoFrame)
    return line


# ── Row descriptions ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RowInfo:
    """What a version/setup row says about itself."""

    title: str
    detail: str = ""
    badge: str = ""
    tone: str = "muted"   # muted | good | warn | bad
    header: bool = False


Describe = Callable[[object, str], RowInfo]

_TONE_COLORS = {
    "good": (QColor(PRISMARINE), QColor(PRISMARINE_DEEP)),
    "warn": (QColor(GOLD), QColor("#3a2e0c")),
    "bad": (QColor(REDSTONE), QColor("#ffffff")),
    "muted": (QColor(SEAM), QColor(SNOW)),
}

ROW_INFO_ROLE = Qt.ItemDataRole.UserRole + 20


class RowDelegate(QStyledItemDelegate):
    """Two-line rows with a status pill, shared by the picker and the instance list."""

    def __init__(self, describe: Describe, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._describe = describe
        self._title_font = body_font(13, QFont.Weight.DemiBold)
        self._detail_font = body_font(12)
        self._badge_font = body_font(11, QFont.Weight.Bold)
        self._header_font = body_font(12, QFont.Weight.Bold)

    def _info(self, index: QModelIndex) -> RowInfo:
        cached = index.data(ROW_INFO_ROLE)
        if isinstance(cached, RowInfo):
            return cached
        return self._describe(index.data(Qt.ItemDataRole.UserRole), str(index.data(Qt.ItemDataRole.DisplayRole) or ""))

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        info = self._info(index)
        if info.header:
            return QSize(option.rect.width(), 30)
        return QSize(option.rect.width(), 50 if info.detail else 38)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        info = self._info(index)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(2, 1, -2, -1)
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        if info.header:
            painter.setFont(self._header_font)
            painter.setPen(QColor(FOG))
            text_rect = rect.adjusted(10, 8, -10, 0)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, info.title)
            painter.restore()
            return
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            path = QPainterPath()
            path.addRoundedRect(rect, 6, 6)
            painter.fillPath(path, QColor(COBBLE if selected else "#2d333d"))
        if selected:
            painter.fillRect(QRect(rect.left(), rect.top() + 8, 3, rect.height() - 16), QColor(PRISMARINE))

        badge_width = 0
        if info.badge:
            metrics = QFontMetrics(self._badge_font)
            badge_width = metrics.horizontalAdvance(info.badge) + 16
            badge = QRect(rect.right() - badge_width - 10, rect.center().y() - 10, badge_width, 20)
            fill, ink = _TONE_COLORS.get(info.tone, _TONE_COLORS["muted"])
            pill = QPainterPath()
            pill.addRoundedRect(badge, 10, 10)
            if info.tone == "muted":
                painter.setPen(QPen(fill, 1))
                painter.drawPath(pill)
                ink = QColor(FOG)
            else:
                painter.fillPath(pill, fill)
            painter.setFont(self._badge_font)
            painter.setPen(ink)
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, info.badge)
            badge_width += 14

        text_left = rect.left() + 14
        text_width = rect.width() - 24 - badge_width
        title_color = QColor(SNOW if enabled else ASH)
        painter.setFont(self._title_font)
        painter.setPen(title_color)
        title = QFontMetrics(self._title_font).elidedText(info.title, Qt.TextElideMode.ElideRight, text_width)
        if info.detail:
            painter.drawText(QRect(text_left, rect.top() + 7, text_width, 20),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
            painter.setFont(self._detail_font)
            painter.setPen(QColor(FOG))
            detail = QFontMetrics(self._detail_font).elidedText(info.detail, Qt.TextElideMode.ElideRight, text_width)
            painter.drawText(QRect(text_left, rect.top() + 26, text_width, 18),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, detail)
        else:
            painter.drawText(QRect(text_left, rect.top(), text_width, rect.height()),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        painter.restore()


# ── Version picker ──────────────────────────────────────────────────────────
_RELEASE_FAMILY = re.compile(r"^(\d+\.\d+)")


def version_family(version: str, kind: str) -> str:
    if kind == "snapshot":
        return "Snapshots"
    if kind in {"old_beta", "old_alpha"}:
        return "Beta and alpha"
    match = _RELEASE_FAMILY.match(version)
    return f"Minecraft {match.group(1)}" if match else "Other versions"


class VersionPopup(QFrame):
    """Searchable, grouped list that replaces the combo box's flat drop-down."""

    FILTERS = (("all", "Everything"), ("installed", "Installed"), ("setups", "My setups"))

    def __init__(self, picker: "VersionPicker") -> None:
        super().__init__(picker, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("versionPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._picker = picker
        self._filter = "all"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        self.search_slot = QVBoxLayout()
        self.search_slot.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.search_slot)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self._chips: dict[str, QPushButton] = {}
        for key, label in self.FILTERS:
            chip = QPushButton(label, self)
            chip.setProperty("role", "chip")
            chip.setCheckable(True)
            chip.setChecked(key == self._filter)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            chip.clicked.connect(lambda _checked=False, value=key: self.set_filter(value))
            chips.addWidget(chip)
            self._chips[key] = chip
        chips.addStretch(1)
        layout.addLayout(chips)
        self.list = QListWidget(self)
        self.list.setObjectName("versionPopupList")
        self.list.setItemDelegate(RowDelegate(picker.describe, self.list))
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.itemClicked.connect(self._choose)
        self.list.itemActivated.connect(self._choose)
        layout.addWidget(self.list, 1)
        self.empty_slot = QVBoxLayout()
        layout.addLayout(self.empty_slot)

    # The window owns the search field and empty label; they live here.
    def adopt(self, search: QLineEdit, empty_label: QLabel) -> None:
        search.setParent(self)
        self.search_slot.addWidget(search)
        search.installEventFilter(self)
        search.returnPressed.connect(self._choose_current)
        empty_label.setParent(self)
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_slot.addWidget(empty_label)
        self._search = search

    def set_filter(self, key: str) -> None:
        self._filter = key
        for name, chip in self._chips.items():
            chip.setChecked(name == key)
        self.refresh()

    def refresh(self) -> None:
        combo = self._picker
        self.list.clear()
        current_row = combo.currentIndex()
        selected_item = None
        group = None
        in_setups = False
        for row in range(combo.count()):
            value = combo.itemData(row, Qt.ItemDataRole.UserRole)
            text = combo.itemText(row)
            if value is None:
                in_setups = text == "Saved setups"
                group = None
                continue
            if combo.view().isRowHidden(row):
                continue
            info = combo.describe(value, text)
            if self._filter == "setups" and not in_setups:
                continue
            if self._filter == "installed" and info.tone != "good":
                continue
            if in_setups:
                heading = "My setups"
            else:
                kind = str(combo.itemData(row, Qt.ItemDataRole.UserRole + 1) or "release")
                heading = version_family(str(value).removeprefix("version:"), kind)
            if heading != group:
                group = heading
                header = QListWidgetItem()
                header.setData(ROW_INFO_ROLE, RowInfo(title=heading, header=True))
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                self.list.addItem(header)
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setData(Qt.ItemDataRole.UserRole + 1, row)
            item.setData(ROW_INFO_ROLE, info)
            item.setToolTip(text)
            self.list.addItem(item)
            if row == current_row:
                selected_item = item
        if selected_item is not None:
            self.list.setCurrentItem(selected_item)
            self.list.scrollToItem(selected_item, QListWidget.ScrollHint.PositionAtCenter)
        has_rows = any(self.list.item(i).flags() & Qt.ItemFlag.ItemIsSelectable for i in range(self.list.count()))
        self.list.setVisible(has_rows)
        if not has_rows and hasattr(self, "_search"):
            message = ("No versions or setups match that search" if self._search.text().strip()
                       else "Nothing installed yet. Pick a version and press Play to download it."
                       if self._filter == "installed" else "No saved setups yet. Create one on the Instances page.")
            self._picker.empty_label.setText(message)
            self._picker.empty_label.show()
        elif hasattr(self, "_search") and not self._search.text().strip():
            self._picker.empty_label.hide()

    def _choose(self, item: QListWidgetItem | None) -> None:
        if item is None or not item.flags() & Qt.ItemFlag.ItemIsSelectable:
            return
        row = item.data(Qt.ItemDataRole.UserRole + 1)
        if isinstance(row, int):
            self._picker.setCurrentIndex(row)
        self.hide()

    def _choose_current(self) -> None:
        item = self.list.currentItem()
        if item is None or not item.flags() & Qt.ItemFlag.ItemIsSelectable:
            item = next((self.list.item(i) for i in range(self.list.count())
                         if self.list.item(i).flags() & Qt.ItemFlag.ItemIsSelectable), None)
        self._choose(item)

    def _step(self, delta: int) -> None:
        count = self.list.count()
        row = self.list.currentRow()
        for _ in range(count):
            row = max(0, min(count - 1, row + delta))
            item = self.list.item(row)
            if item.flags() & Qt.ItemFlag.ItemIsSelectable:
                self.list.setCurrentItem(item)
                return
            if row in (0, count - 1):
                return

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.KeyPress and watched is getattr(self, "_search", None):
            key = event.key()
            if key == Qt.Key.Key_Down:
                self._step(1)
                return True
            if key == Qt.Key.Key_Up:
                self._step(-1)
                return True
            if key == Qt.Key.Key_Escape:
                self.hide()
                return True
        return super().eventFilter(watched, event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if hasattr(self, "_search"):
            self._search.setFocus()
            self._search.selectAll()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._picker.update()


class VersionPicker(QComboBox):
    """Combo box kept as the selection model, drawn as a two-line card.

    Its drop-down is a ``VersionPopup`` with search, filters and grouping.
    """

    def __init__(self, describe: Describe, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.describe = describe
        self.popup = VersionPopup(self)
        self.empty_label: QLabel | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title_font = body_font(14, QFont.Weight.DemiBold)
        self._detail_font = body_font(12)

    def adopt(self, search: QLineEdit, empty_label: QLabel) -> None:
        self.empty_label = empty_label
        self.popup.adopt(search, empty_label)

    def showPopup(self) -> None:  # noqa: N802
        if not self.isEnabled():
            return
        self.popup.refresh()
        width = max(self.width(), 440)
        height = 400
        below = self.mapToGlobal(QPoint(0, self.height() + 6))
        above = self.mapToGlobal(QPoint(0, -height - 6))
        screen = self.screen().availableGeometry() if self.screen() else None
        origin = above if screen is not None and above.y() >= screen.top() else below
        if screen is not None and origin is below and below.y() + height > screen.bottom():
            height = max(220, screen.bottom() - below.y())
        self.popup.setGeometry(origin.x(), origin.y(), width, height)
        self.popup.show()

    def hidePopup(self) -> None:  # noqa: N802
        self.popup.hide()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(260, 52)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(160, 52)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)
        enabled = self.isEnabled()
        open_ = self.popup.isVisible()
        border = QColor(PRISMARINE) if (self.hasFocus() or open_) and enabled else QColor(SEAM)
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)
        painter.fillPath(path, QColor(COBBLE if enabled else SLATE))
        painter.setPen(QPen(border, 1))
        painter.drawPath(path)

        index = self.currentIndex()
        value = self.itemData(index, Qt.ItemDataRole.UserRole) if index >= 0 else None
        if value is None:
            info = RowInfo(title="Choose a version", detail="Loading the version list…" if not self.count() else "")
        else:
            info = self.describe(value, self.itemText(index))

        # Chevron
        painter.setPen(QPen(QColor(FOG if enabled else ASH), 1.6))
        cx, cy = rect.right() - 18, rect.center().y()
        if open_:
            painter.drawPolyline([QPoint(cx - 5, cy + 2), QPoint(cx, cy - 3), QPoint(cx + 5, cy + 2)])
        else:
            painter.drawPolyline([QPoint(cx - 5, cy - 2), QPoint(cx, cy + 3), QPoint(cx + 5, cy - 2)])

        right = rect.right() - 36
        if info.badge:
            metrics = QFontMetrics(body_font(11, QFont.Weight.Bold))
            badge_width = metrics.horizontalAdvance(info.badge) + 16
            badge = QRect(right - badge_width, rect.center().y() - 10, badge_width, 20)
            fill, ink = _TONE_COLORS.get(info.tone, _TONE_COLORS["muted"])
            pill = QPainterPath()
            pill.addRoundedRect(badge, 10, 10)
            if info.tone == "muted":
                painter.setPen(QPen(fill, 1))
                painter.drawPath(pill)
                ink = QColor(FOG)
            else:
                painter.fillPath(pill, fill)
            painter.setFont(body_font(11, QFont.Weight.Bold))
            painter.setPen(ink)
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, info.badge)
            right = badge.left() - 10
        text_width = max(10, right - 14)
        painter.setFont(self._title_font)
        painter.setPen(QColor(SNOW if enabled else ASH))
        title = QFontMetrics(self._title_font).elidedText(info.title, Qt.TextElideMode.ElideRight, text_width)
        if info.detail:
            painter.drawText(QRect(14, rect.center().y() - 19, text_width, 20),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
            painter.setFont(self._detail_font)
            painter.setPen(QColor(FOG if enabled else ASH))
            detail = QFontMetrics(self._detail_font).elidedText(info.detail, Qt.TextElideMode.ElideRight, text_width)
            painter.drawText(QRect(14, rect.center().y() + 1, text_width, 18),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, detail)
        else:
            painter.drawText(QRect(14, rect.top(), text_width, rect.height()),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        painter.end()


def install_application_font(app: QApplication) -> None:
    app.setFont(body_font(13))
