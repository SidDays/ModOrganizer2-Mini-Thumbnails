import os
from pathlib import Path
from typing import Callable, Dict, Optional

import mobase
from PyQt6 import QtCore, QtGui, QtWidgets


class DynamicThumbnailDelegate(QtWidgets.QStyledItemDelegate):
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    DEFAULT_THUMB_SIZE = 20
    DEFAULT_PADDING = 1
    DEFAULT_HOVER_PREVIEW_SIZE = 256
    MAX_SEARCH_DEPTH = 3

    # Set to True to keep Overwrite completely plain (no image, no placeholder)
    # Set to False if you want Overwrite to display images located inside the overwrite folder
    IGNORE_OVERWRITE = True

    def __init__(
        self,
        parent_delegate: Optional[QtWidgets.QAbstractItemDelegate],
        organizer: mobase.IOrganizer,
        tree_view: QtWidgets.QTreeView,
        is_enabled: Callable[[], bool],
        is_placeholder_enabled: Callable[[], bool] = lambda: False,
        get_thumb_size: Callable[[], int] = lambda: DynamicThumbnailDelegate.DEFAULT_THUMB_SIZE,
        get_padding: Callable[[], int] = lambda: DynamicThumbnailDelegate.DEFAULT_PADDING,
        is_hover_preview_enabled: Callable[[], bool] = lambda: True,
        get_hover_preview_size: Callable[[], int] = lambda: DynamicThumbnailDelegate.DEFAULT_HOVER_PREVIEW_SIZE,
    ):
        super().__init__(tree_view)
        self._parent_delegate = parent_delegate
        self._organizer = organizer
        self._tree_view = tree_view
        self._is_enabled = is_enabled
        self._is_placeholder_enabled = is_placeholder_enabled
        self._get_thumb_size = get_thumb_size
        self._get_padding = get_padding
        self._is_hover_preview_enabled = is_hover_preview_enabled
        self._get_hover_preview_size = get_hover_preview_size

        self._cached_thumb_size: Optional[int] = None
        self._image_path_cache: Dict[str, Optional[Path]] = {}
        self._pixmap_cache: Dict[str, Optional[QtGui.QPixmap]] = {}
        self._placeholder_pixmap: Optional[QtGui.QPixmap] = None
        self._preview_popup: Optional[QtWidgets.QLabel] = None
        self._hovered_preview_key: Optional[tuple[str, int]] = None

        if self._tree_view and self._tree_view.viewport():
            self._tree_view.viewport().setMouseTracking(True)
            self._tree_view.viewport().installEventFilter(self)

    def _sync_thumb_size(self) -> int:
        thumb_size = self._get_thumb_size()
        if thumb_size != self._cached_thumb_size:
            self._pixmap_cache.clear()
            self._placeholder_pixmap = None
            self._cached_thumb_size = thumb_size
        return thumb_size

    def clear_cache(self):
        self._image_path_cache.clear()
        self._pixmap_cache.clear()
        self._hide_hover_preview()
        if self._tree_view and self._tree_view.viewport():
            self._tree_view.viewport().update()

    def _get_placeholder(self) -> QtGui.QPixmap:
        thumb_size = self._sync_thumb_size()
        if self._placeholder_pixmap is not None:
            return self._placeholder_pixmap

        pm = QtGui.QPixmap(thumb_size, thumb_size)
        pm.fill(QtCore.Qt.GlobalColor.transparent)

        painter = QtGui.QPainter(pm)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor(90, 90, 90, 160), 1))
        painter.setBrush(QtGui.QBrush(QtGui.QColor(40, 40, 40, 120)))
        painter.drawRoundedRect(1, 1, thumb_size - 2, thumb_size - 2, 3, 3)

        painter.setPen(QtGui.QPen(QtGui.QColor(110, 110, 110, 180), 1))
        path = QtGui.QPainterPath()
        path.moveTo(thumb_size * 0.2, thumb_size * 0.7)
        path.lineTo(thumb_size * 0.4, thumb_size * 0.45)
        path.lineTo(thumb_size * 0.6, thumb_size * 0.65)
        path.lineTo(thumb_size * 0.75, thumb_size * 0.5)
        path.lineTo(thumb_size * 0.8, thumb_size * 0.7)
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

    def _find_image_path(
        self, mod_name: str, mod: Optional[mobase.IModInterface]
    ) -> Optional[Path]:
        if mod_name in self._image_path_cache:
            return self._image_path_cache[mod_name]

        mod_dir = self._resolve_directory(mod_name, mod)
        if not mod_dir or not mod_dir.is_dir():
            self._image_path_cache[mod_name] = None
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

        self._image_path_cache[mod_name] = found_path
        return found_path

    def _find_first_image(
        self, mod_name: str, mod: Optional[mobase.IModInterface]
    ) -> Optional[QtGui.QPixmap]:
        thumb_size = self._sync_thumb_size()
        if mod_name in self._pixmap_cache:
            return self._pixmap_cache[mod_name]

        found_path = self._find_image_path(mod_name, mod)
        if found_path:
            raw_pixmap = QtGui.QPixmap(str(found_path))
            if not raw_pixmap.isNull():
                scaled = raw_pixmap.scaled(
                    thumb_size,
                    thumb_size,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
                self._pixmap_cache[mod_name] = scaled
                return scaled

        self._pixmap_cache[mod_name] = None
        return None

    def _get_thumbnail_target(
        self, index: QtCore.QModelIndex
    ) -> Optional[tuple[str, Optional[mobase.IModInterface]]]:
        mod_name = str(index.data(QtCore.Qt.ItemDataRole.DisplayRole) or "")
        is_overwrite = mod_name.lower() == "overwrite"

        # Bypass Overwrite when IGNORE_OVERWRITE is active
        if is_overwrite and self.IGNORE_OVERWRITE:
            return None

        mod = self._organizer.modList().getMod(mod_name)

        # Bypass separators and invalid/empty items
        if not is_overwrite and (not mod or mod.isSeparator()):
            return None

        return mod_name, mod

    def _paint_base(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ):
        if self._parent_delegate:
            self._parent_delegate.paint(painter, option, index)
        else:
            super().paint(painter, option, index)

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ):
        if not self._is_enabled():
            self._paint_base(painter, option, index)
            return

        target = self._get_thumbnail_target(index)
        thumb_size = self._sync_thumb_size()
        padding = self._get_padding()
        indent = thumb_size + (padding * 2)

        if target is None or option.rect.width() < indent:
            self._paint_base(painter, option, index)
            return

        mod_name, mod = target
        pixmap = self._find_first_image(mod_name, mod)
        if pixmap is None and self._is_placeholder_enabled():
            pixmap = self._get_placeholder()

        if pixmap is None:
            self._paint_base(painter, option, index)
            return

        opt = QtWidgets.QStyleOptionViewItem(option)
        opt.rect.setRight(opt.rect.right() - indent)
        self._paint_base(painter, opt, index)

        painter.save()
        x_offset = option.rect.right() - thumb_size - padding + 1
        y_offset = option.rect.top() + (option.rect.height() - pixmap.height()) // 2
        painter.drawPixmap(x_offset, y_offset, pixmap)
        painter.restore()

    def editorEvent(
        self,
        event: QtCore.QEvent,
        model: QtCore.QAbstractItemModel,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> bool:
        if self._parent_delegate:
            return self._parent_delegate.editorEvent(event, model, option, index)
        return super().editorEvent(event, model, option, index)

    def createEditor(
        self,
        parent: QtWidgets.QWidget,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> Optional[QtWidgets.QWidget]:
        if self._parent_delegate:
            return self._parent_delegate.createEditor(parent, option, index)
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor: QtWidgets.QWidget, index: QtCore.QModelIndex):
        if self._parent_delegate:
            self._parent_delegate.setEditorData(editor, index)
        else:
            super().setEditorData(editor, index)

    def setModelData(
        self,
        editor: QtWidgets.QWidget,
        model: QtCore.QAbstractItemModel,
        index: QtCore.QModelIndex,
    ):
        if self._parent_delegate:
            self._parent_delegate.setModelData(editor, model, index)
        else:
            super().setModelData(editor, model, index)

    def updateEditorGeometry(
        self,
        editor: QtWidgets.QWidget,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ):
        if self._parent_delegate:
            self._parent_delegate.updateEditorGeometry(editor, option, index)
        else:
            super().updateEditorGeometry(editor, option, index)

    def _thumbnail_rect(self, row_rect: QtCore.QRect) -> QtCore.QRect:
        thumb_size = self._sync_thumb_size()
        padding = self._get_padding()
        x = row_rect.right() - thumb_size - padding + 1
        y = row_rect.top() + (row_rect.height() - thumb_size) // 2
        return QtCore.QRect(x, y, thumb_size, thumb_size)

    def _ensure_preview_popup(self) -> QtWidgets.QLabel:
        if self._preview_popup is None:
            popup = QtWidgets.QLabel(
                None,
                QtCore.Qt.WindowType.ToolTip | QtCore.Qt.WindowType.FramelessWindowHint,
            )
            popup.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
            popup.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            popup.setStyleSheet(
                "background-color: #1e1e1e; border: 1px solid #555; padding: 2px;"
            )
            self._preview_popup = popup
        return self._preview_popup

    def _hide_hover_preview(self):
        self._hovered_preview_key = None
        if self._preview_popup and self._preview_popup.isVisible():
            self._preview_popup.hide()

    def _position_preview_popup(self, popup: QtWidgets.QLabel, global_pos: QtCore.QPoint):
        pos = global_pos + QtCore.QPoint(16, 16)
        screen = QtGui.QGuiApplication.screenAt(global_pos) or QtGui.QGuiApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            size = popup.sizeHint()
            if pos.x() + size.width() > avail.right():
                pos.setX(max(avail.left(), global_pos.x() - size.width() - 12))
            if pos.y() + size.height() > avail.bottom():
                pos.setY(max(avail.top(), global_pos.y() - size.height() - 12))
        popup.move(pos)

    def _show_hover_preview(
        self, mod_name: str, image_path: Path, global_pos: QtCore.QPoint
    ):
        preview_size = self._get_hover_preview_size()
        key = (mod_name, preview_size)
        popup = self._ensure_preview_popup()

        if self._hovered_preview_key != key:
            raw = QtGui.QPixmap(str(image_path))
            if raw.isNull():
                self._hide_hover_preview()
                return
            scaled = raw.scaled(
                preview_size,
                preview_size,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            popup.setPixmap(scaled)
            popup.adjustSize()
            self._hovered_preview_key = key

        self._position_preview_popup(popup, global_pos)
        if not popup.isVisible():
            popup.show()

    def _get_hovered_image(
        self, viewport_pos: QtCore.QPoint
    ) -> Optional[tuple[str, Path]]:
        if not self._is_enabled() or not self._is_hover_preview_enabled():
            return None
        index = self._tree_view.indexAt(viewport_pos)
        if not index.isValid() or index.column() != 0:
            return None
        row_rect = self._tree_view.visualRect(index)
        if not self._thumbnail_rect(row_rect).contains(viewport_pos):
            return None
        target = self._get_thumbnail_target(index)
        if not target:
            return None
        mod_name, mod = target
        image_path = self._find_image_path(mod_name, mod)
        if not image_path:
            return None
        return mod_name, image_path

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if self._tree_view and obj is self._tree_view.viewport():
            etype = event.type()
            if etype == QtCore.QEvent.Type.MouseMove:
                mouse_event = event
                if isinstance(mouse_event, QtGui.QMouseEvent):
                    pos = mouse_event.position().toPoint()
                    hovered = self._get_hovered_image(pos)
                    if hovered:
                        mod_name, image_path = hovered
                        self._show_hover_preview(
                            mod_name, image_path, mouse_event.globalPosition().toPoint()
                        )
                    else:
                        self._hide_hover_preview()
            elif etype in (
                QtCore.QEvent.Type.Leave,
                QtCore.QEvent.Type.Wheel,
                QtCore.QEvent.Type.MouseButtonPress,
            ):
                self._hide_hover_preview()
        return super().eventFilter(obj, event)

    def helpEvent(
        self,
        event: QtGui.QHelpEvent,
        view: QtWidgets.QAbstractItemView,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> bool:
        if (
            event.type() == QtCore.QEvent.Type.ToolTip
            and self._get_hovered_image(event.pos()) is not None
        ):
            return True
        if self._parent_delegate:
            return self._parent_delegate.helpEvent(event, view, option, index)
        return super().helpEvent(event, view, option, index)

    def sizeHint(
        self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex
    ) -> QtCore.QSize:
        base_size = (
            self._parent_delegate.sizeHint(option, index)
            if self._parent_delegate
            else super().sizeHint(option, index)
        )
        if not self._is_enabled():
            return base_size

        thumb_size = self._get_thumb_size()
        padding = self._get_padding()
        min_height = thumb_size + (padding * 2)
        return QtCore.QSize(
            base_size.width() + thumb_size + (padding * 2),
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
        return "Mini Thumbnails"

    def author(self) -> str:
        return "Sid Days"

    def description(self) -> str:
        return "Displays tiny preview thumbnails for mods."

    def version(self) -> mobase.VersionInfo:
        return mobase.VersionInfo(1, 1, 1, mobase.ReleaseType.FINAL)

    SETTING_ENABLE_PLACEHOLDER = "enable_placeholder_images"
    SETTING_THUMB_SIZE = "thumbnail_size"
    SETTING_PADDING = "thumbnail_padding"
    SETTING_ENABLE_HOVER_PREVIEW = "enable_hover_preview"
    SETTING_HOVER_PREVIEW_SIZE = "hover_preview_size"

    def settings(self) -> list[mobase.PluginSetting]:
        return [
            mobase.PluginSetting(
                self.SETTING_ENABLE_PLACEHOLDER,
                "Enable placeholder images for mods without an image.",
                False,
            ),
            mobase.PluginSetting(
                self.SETTING_THUMB_SIZE,
                "Thumbnail size in pixels.",
                DynamicThumbnailDelegate.DEFAULT_THUMB_SIZE,
            ),
            mobase.PluginSetting(
                self.SETTING_PADDING,
                "Padding around each thumbnail in pixels.",
                DynamicThumbnailDelegate.DEFAULT_PADDING,
            ),
            mobase.PluginSetting(
                self.SETTING_ENABLE_HOVER_PREVIEW,
                "Show a larger preview popup when hovering over a thumbnail.",
                True,
            ),
            mobase.PluginSetting(
                self.SETTING_HOVER_PREVIEW_SIZE,
                "Maximum width/height in pixels of the hover preview popup.",
                DynamicThumbnailDelegate.DEFAULT_HOVER_PREVIEW_SIZE,
            ),
        ]

    def is_enabled(self) -> bool:
        return bool(self._organizer and self._organizer.isPluginEnabled(self.name()))

    def is_placeholder_enabled(self) -> bool:
        return bool(
            self._organizer
            and self._organizer.pluginSetting(
                self.name(), self.SETTING_ENABLE_PLACEHOLDER
            )
        )

    def thumb_size(self) -> int:
        if not self._organizer:
            return DynamicThumbnailDelegate.DEFAULT_THUMB_SIZE
        val = self._organizer.pluginSetting(self.name(), self.SETTING_THUMB_SIZE)
        return max(1, int(val))

    def padding(self) -> int:
        if not self._organizer:
            return DynamicThumbnailDelegate.DEFAULT_PADDING
        val = self._organizer.pluginSetting(self.name(), self.SETTING_PADDING)
        return max(0, int(val))

    def is_hover_preview_enabled(self) -> bool:
        return bool(
            self._organizer
            and self._organizer.pluginSetting(
                self.name(), self.SETTING_ENABLE_HOVER_PREVIEW
            )
        )

    def hover_preview_size(self) -> int:
        if not self._organizer:
            return DynamicThumbnailDelegate.DEFAULT_HOVER_PREVIEW_SIZE
        val = self._organizer.pluginSetting(
            self.name(), self.SETTING_HOVER_PREVIEW_SIZE
        )
        return max(32, int(val))

    def _on_refresh(self):
        if not self.is_enabled() or not self._delegate:
            return
        self._delegate.clear_cache()

    def _setup_ui(self, main_window: QtWidgets.QMainWindow):
        tree = main_window.findChild(QtWidgets.QTreeView, "modList")
        if not tree:
            return

        self._delegate = DynamicThumbnailDelegate(
            tree.itemDelegateForColumn(0) or tree.itemDelegate(),
            self._organizer,
            tree,
            self.is_enabled,
            self.is_placeholder_enabled,
            self.thumb_size,
            self.padding,
            self.is_hover_preview_enabled,
            self.hover_preview_size,
        )
        tree.setItemDelegateForColumn(0, self._delegate)

        refresh_action = main_window.findChild(QtGui.QAction, "actionRefresh")
        if refresh_action:
            refresh_action.triggered.connect(self._on_refresh)

        refresh_shortcut = QtGui.QShortcut(
            QtGui.QKeySequence("Ctrl+Shift+R"), main_window
        )
        refresh_shortcut.activated.connect(self._on_refresh)

        self._organizer.modList().onModInstalled(lambda mod: self._on_refresh())
        self._organizer.modList().onModRemoved(lambda mod: self._on_refresh())


def createPlugin() -> mobase.IPlugin:
    return ModThumbnailPlugin()
