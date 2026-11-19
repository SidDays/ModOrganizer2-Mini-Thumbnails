import os
from pathlib import Path
from typing import Dict, Optional

import mobase
from PyQt6 import QtCore, QtGui, QtWidgets


class DynamicThumbnailDelegate(QtWidgets.QStyledItemDelegate):
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    THUMB_SIZE = 20
    PADDING = 4
    MAX_SEARCH_DEPTH = 3

    # Set to True to keep Overwrite completely plain (no image, no placeholder)
    # Set to False if you want Overwrite to display images located inside the overwrite folder
    IGNORE_OVERWRITE = True

    def __init__(
        self,
        parent_delegate: Optional[QtWidgets.QAbstractItemDelegate],
        organizer: mobase.IOrganizer,
        tree_view: QtWidgets.QTreeView,
    ):
        super().__init__(tree_view)
        self._parent_delegate = parent_delegate
        self._organizer = organizer
        self._tree_view = tree_view

        self._pixmap_cache: Dict[str, Optional[QtGui.QPixmap]] = {}
        self._placeholder_pixmap: Optional[QtGui.QPixmap] = None

    def clear_cache(self):
        self._pixmap_cache.clear()
        if self._tree_view and self._tree_view.viewport():
            self._tree_view.viewport().update()

    def _get_placeholder(self) -> QtGui.QPixmap:
        if self._placeholder_pixmap is not None:
            return self._placeholder_pixmap

        pm = QtGui.QPixmap(self.THUMB_SIZE, self.THUMB_SIZE)
        pm.fill(QtCore.Qt.GlobalColor.transparent)

        painter = QtGui.QPainter(pm)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor(90, 90, 90, 160), 1))
        painter.setBrush(QtGui.QBrush(QtGui.QColor(40, 40, 40, 120)))
        painter.drawRoundedRect(1, 1, self.THUMB_SIZE - 2, self.THUMB_SIZE - 2, 3, 3)

        painter.setPen(QtGui.QPen(QtGui.QColor(110, 110, 110, 180), 1))
        path = QtGui.QPainterPath()
        path.moveTo(4, 14)
        path.lineTo(8, 9)
        path.lineTo(12, 13)
        path.lineTo(15, 10)
        path.lineTo(16, 14)
        painter.drawPath(path)
        painter.end()

        self._placeholder_pixmap = pm
        return pm

    def _resolve_directory(
        self, mod_name: str, mod: Optional[mobase.IModInterface]
    ) -> Optional[Path]:
        if mod_name.lower() == "overwrite":
            return Path(self._organizer.overwritePath())
        if mod:
            return Path(mod.absolutePath())
        return None

    def _find_first_image(
        self, mod_name: str, mod: Optional[mobase.IModInterface]
    ) -> Optional[QtGui.QPixmap]:
        if mod_name in self._pixmap_cache:
            return self._pixmap_cache[mod_name]

        mod_dir = self._resolve_directory(mod_name, mod)
        if not mod_dir or not mod_dir.is_dir():
            self._pixmap_cache[mod_name] = None
            return None

        found_path: Optional[Path] = None

        # 1. Root check
        try:
            for entry in mod_dir.iterdir():
                if entry.is_file() and entry.suffix.lower() in self.IMAGE_EXTENSIONS:
                    found_path = entry
                    break
        except OSError:
            pass

        # 2. Deep search
        if not found_path:
            root_parts_len = len(mod_dir.parts)
            try:
                for root, dirs, files in os.walk(mod_dir):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    current_depth = len(Path(root).parts) - root_parts_len
                    if current_depth > self.MAX_SEARCH_DEPTH:
                        dirs.clear()
                        continue

                    for file_name in files:
                        if Path(file_name).suffix.lower() in self.IMAGE_EXTENSIONS:
                            found_path = Path(root) / file_name
                            break
                    if found_path:
                        break
            except OSError:
                pass

        if found_path:
            raw_pixmap = QtGui.QPixmap(str(found_path))
            if not raw_pixmap.isNull():
                scaled = raw_pixmap.scaled(
                    self.THUMB_SIZE,
                    self.THUMB_SIZE,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
                self._pixmap_cache[mod_name] = scaled
                return scaled

        self._pixmap_cache[mod_name] = None
        return None

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ):
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        mod_name = str(index.data(QtCore.Qt.ItemDataRole.DisplayRole) or "")
        is_overwrite = mod_name.lower() == "overwrite"

        # Bypass Overwrite when IGNORE_OVERWRITE is active
        if is_overwrite and self.IGNORE_OVERWRITE:
            if self._parent_delegate:
                self._parent_delegate.paint(painter, option, index)
            else:
                super().paint(painter, option, index)
            return

        mod = self._organizer.modList().getMod(mod_name)

        # Bypass separators and invalid/empty items
        if not is_overwrite and (not mod or mod.isSeparator()):
            if self._parent_delegate:
                self._parent_delegate.paint(painter, option, index)
            else:
                super().paint(painter, option, index)
            return

        pixmap = self._find_first_image(mod_name, mod)
        if not pixmap:
            pixmap = self._get_placeholder()

        painter.save()
        y_offset = opt.rect.top() + (opt.rect.height() - pixmap.height()) // 2
        x_offset = opt.rect.left() + self.PADDING
        painter.drawPixmap(x_offset, y_offset, pixmap)
        painter.restore()

        indent = self.THUMB_SIZE + (self.PADDING * 2)
        opt.rect.setLeft(opt.rect.left() + indent)

        if self._parent_delegate:
            self._parent_delegate.paint(painter, opt, index)
        else:
            super().paint(painter, opt, index)

    def sizeHint(
        self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex
    ) -> QtCore.QSize:
        base_size = (
            self._parent_delegate.sizeHint(option, index)
            if self._parent_delegate
            else super().sizeHint(option, index)
        )
        min_height = self.THUMB_SIZE + (self.PADDING * 2)
        return QtCore.QSize(
            base_size.width() + self.THUMB_SIZE + (self.PADDING * 2),
            max(base_size.height(), min_height),
        )


class ModThumbnailPlugin(mobase.IPlugin):
    def __init__(self):
        super().__init__()
        self._organizer: Optional[mobase.IOrganizer] = None
        self._delegate: Optional[DynamicThumbnailDelegate] = None

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._organizer = organizer
        self._organizer.onUserInterfaceInitialized(self._setup_ui)
        return True

    def name(self) -> str:
        return "Mod Thumbnail Preview"

    def author(self) -> str:
        return "Local Dev"

    def description(self) -> str:
        return "Displays mod thumbnails with overwrite handling."

    def version(self) -> mobase.VersionInfo:
        return mobase.VersionInfo(1, 1, 1, mobase.ReleaseType.FINAL)

    def settings(self) -> list[mobase.PluginSetting]:
        return []

    def _setup_ui(self, main_window: QtWidgets.QMainWindow):
        tree = main_window.findChild(QtWidgets.QTreeView, "modList")
        if not tree:
            return

        self._delegate = DynamicThumbnailDelegate(
            tree.itemDelegateForColumn(0), self._organizer, tree
        )
        tree.setItemDelegateForColumn(0, self._delegate)

        refresh_action = main_window.findChild(QtGui.QAction, "actionRefresh")
        if refresh_action:
            refresh_action.triggered.connect(self._delegate.clear_cache)

        refresh_shortcut = QtGui.QShortcut(
            QtGui.QKeySequence("Ctrl+Shift+R"), main_window
        )
        refresh_shortcut.activated.connect(self._delegate.clear_cache)

        self._organizer.modList().onModInstalled(
            lambda mod: self._delegate.clear_cache()
        )
        self._organizer.modList().onModRemoved(lambda mod: self._delegate.clear_cache())


def createPlugin() -> mobase.IPlugin:
    return ModThumbnailPlugin()
