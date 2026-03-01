# -*- coding: utf-8 -*-
import io
import os
import pickle
import sys
from functools import partial

import rawpy
import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageQt
from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import (QBrush, QColor, QFont, QIcon, QImage, QKeySequence,
                         QPainter, QPixmap, QShortcut)
from PyQt6.QtWidgets import (QApplication, QColorDialog, QDialog, QFileDialog, QFrame,
                             QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QMainWindow, QMenu, QMessageBox, QPushButton,
                             QScrollArea, QSlider, QStyle, QToolButton,
                             QVBoxLayout, QWidget)
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas

from .config import (RAW_EXT, SESSION_FILE, THEME_DARK, THEME_LIGHT,
                     THUMB_HEIGHT, THUMB_WIDTH, TRANS)
from .widgets import ImageViewer
from .workers import PdfExportWorker

# --- Main Application ---
class TurretEyeApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TurretEye")
        self.resize(1200, 800)
        self.setMinimumSize(800, 600)

        # Load Icon
        if hasattr(sys, "_MEIPASS"):
            icon_path = os.path.join(sys._MEIPASS, "TurretEye.ico")
        else:
            icon_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "TurretEye.ico",
            )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # State
        self.image_list = []
        self.current_image_index = 0
        self.loaded_folder = None
        self.original_image = None # PIL
        self.displayed_image = None # PIL (processed)

        self.brightness = 1.0
        self.saturation = 1.0
        self.sharpness = 1.0
        self.rotation = 0

        self.history = []
        self.future = []

        self.is_dark_theme = True
        self.language = "pl"
        self.turret_active = False
        self.hover_outline_color = None

        self.slideshow_active = False
        self.slideshow_timer = QTimer()
        self.slideshow_timer.timeout.connect(self.slideshow_next)
        self.slideshow_timer.setInterval(5000)
        self._window_geometry_before_fullscreen = None
        self._window_was_maximized_before_fullscreen = False

        # Thumb Cache (Stores (pixmap, info_text))
        self.thumb_cache = {}
        self._icon_cache = {}
        self._svg_icon_cache = {}
        self._icon_roots = []
        if hasattr(sys, "_MEIPASS"):
            self._icon_roots.extend(
                [
                    os.path.join(sys._MEIPASS, "turreteye", "assets", "icons"),
                    os.path.join(sys._MEIPASS, "assets", "icons"),
                ]
            )
        self._icon_roots.extend(
            [
                os.path.join(os.path.dirname(__file__), "assets", "icons"),
                os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    "turreteye",
                    "assets",
                    "icons",
                ),
            ]
        )

        # UI Setup
        self.central_widget = QWidget()
        self.central_widget.setObjectName("Root")
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(6)

        # View
        self.viewer = ImageViewer()
        self.viewer.fileDropped.connect(self.load_image_path)
        self.viewer.doubleClicked.connect(self.toggle_zoom_fit)
        self.main_layout.addWidget(self.viewer, 1)

        # Overlay Counter (Floating label)
        self.counter_label = QLabel("", self.viewer)
        self.counter_label.setObjectName("CounterLabel")
        self.counter_label.setStyleSheet("background: transparent; color: white; font-weight: bold; font-family: 'Segoe UI'; font-size: 14px; padding: 5px;")

        # Controls (bottom bar, compact)
        self.control_bar = QWidget()
        self.control_bar.setObjectName("ControlBar")
        self.control_bar.setFixedHeight(50)
        self.control_layout = QHBoxLayout(self.control_bar)
        self.control_layout.setContentsMargins(8, 4, 8, 4)
        self.control_layout.setSpacing(4)
        self.control_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.control_bar)

        # Status Bar
        self.status_bar = QLabel("")
        self.status_bar.setObjectName("StatusBar")
        self.status_bar.setContentsMargins(5, 2, 5, 2)
        self.main_layout.addWidget(self.status_bar)

        self.buttons = []
        self._create_buttons()

        # Apply Theme
        self.apply_theme()

        # Shortcuts
        self._bind_shortcuts()

        # Context Menu
        self.viewer.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.viewer.customContextMenuRequested.connect(self.show_context_menu)

        # Edit debounce timer
        self._edit_timer = QTimer()
        self._edit_timer.setSingleShot(True)
        self._edit_timer.setInterval(150) # 150ms debounce
        self._edit_timer.timeout.connect(self._apply_debounced_adjustments)

        # Load session
        self.load_last_session()

    def resizeEvent(self, event):
        # Update counter position
        if self.counter_label.isVisible():
            self.counter_label.move(self.viewer.width() - self.counter_label.width() - 20, 20)
        super().resizeEvent(event)

    def tr(self, key):
        return TRANS.get(self.language, TRANS["pl"]).get(key, key)

    def toggle_language(self):
        self.language = "en" if self.language == "pl" else "pl"
        self.refresh_ui_text()

    def refresh_ui_text(self):
        # Update buttons
        for btn in self.buttons:
            tip_key = getattr(btn, "_tip_key", None)
            if tip_key:
                txt = self.tr(tip_key)
                btn.setToolTip(txt)
                btn.setStatusTip(txt)
                btn.setAccessibleName(txt)
            fallback = self._button_icon_key(btn)
            if fallback is not None:
                btn.setIcon(self._mono_icon(fallback, False, 18))

        # Update turret
        self.viewer.set_turret_text(self.tr("turret_msg"))

        # Update status bar if it has URL
        txt = self.status_bar.text()
        if txt.startswith("URL:"):
            # We can't easily parse back the URL from the translated string without more state.
            # But the user asked for URL: to be centered in dialog, here we are talking about status bar.
            # The status bar updates on load. If language changes, we might want to refresh status text.
            # But we don't store the raw filename/url easily accessible other than last_loaded_path
            # We can re-call update_status_bar()
            self.update_status_bar()

    def _current_theme(self):
        return THEME_DARK if self.is_dark_theme else THEME_LIGHT

    def _hover_outline_default(self):
        return self._current_theme()["accent"]

    def _hover_outline_css(self):
        return self.hover_outline_color or self._hover_outline_default()

    def _normalize_hover_outline_color(self, raw_color):
        text = (raw_color or "").strip()
        if not text:
            return None
        color = QColor(text)
        if not color.isValid():
            return None
        if color.alpha() == 255:
            return color.name(QColor.NameFormat.HexRgb).upper()
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"

    def _set_hover_outline_color(self, raw_color):
        normalized = self._normalize_hover_outline_color(raw_color)
        if normalized is None:
            return False
        self.hover_outline_color = normalized
        self.apply_theme()
        self.save_last_session()
        return True

    def _resolve_svg_path(self, name):
        for root in self._icon_roots:
            path = os.path.join(root, f"{name}.svg")
            if os.path.exists(path):
                return path
        return None

    def _svg_icon(self, name):
        if name in self._svg_icon_cache:
            return self._svg_icon_cache[name]
        path = self._resolve_svg_path(name)
        if not path:
            self._svg_icon_cache[name] = None
            return None
        icon = QIcon(path)
        self._svg_icon_cache[name] = icon if not icon.isNull() else None
        return self._svg_icon_cache[name]

    def _button_icon_key(self, btn):
        key = getattr(btn, "_icon_fallback", None)
        if getattr(btn, "_tip_key", None) == "btn_theme":
            return "sun" if self.is_dark_theme else "moon"
        return key

    def _mono_icon(self, fallback, active=False, size=20):
        t = self._current_theme()
        tint = self._hover_outline_css() if active else t["fg"]
        cache_key = (str(fallback), tint, size)
        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]

        base_icon = None
        if isinstance(fallback, str):
            src = self._svg_icon(fallback)
            if src is None:
                base_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
                glyph = base_icon.pixmap(size, size)
            else:
                base_icon = src
                glyph = src.pixmap(size, size)
        else:
            base_icon = self.style().standardIcon(fallback)
            glyph = base_icon.pixmap(size, size)

        if glyph.isNull() or glyph.width() <= 0 or glyph.height() <= 0:
            self._icon_cache[cache_key] = base_icon
            return base_icon

        tinted = QPixmap(glyph.size())
        tinted.fill(Qt.GlobalColor.transparent)
        painter = QPainter(tinted)
        if not painter.isActive():
            self._icon_cache[cache_key] = base_icon
            return base_icon

        painter.drawPixmap(0, 0, glyph)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), QColor(tint))
        painter.end()

        icon = QIcon(tinted)
        self._icon_cache[cache_key] = icon
        return icon

    def _style_dialog(self, dialog):
        t = self._current_theme()
        hover_outline = self._hover_outline_css()
        dialog.setWindowIcon(self.windowIcon())
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dialog.setStyleSheet(
            f"""
            QDialog, QMessageBox {{
                background-color: {t['card_bg_2']};
                color: {t['fg']};
                border: 1px solid {t['border']};
            }}
            QLabel {{
                color: {t['fg']};
                font-family: 'Segoe UI';
                font-size: 13px;
            }}
            QLabel#Key {{
                font-weight: 700;
                border: 1px solid {t['border']};
                border-radius: 8px;
                padding: 6px 10px;
                background-color: {t['btn_bg']};
            }}
            QLabel#Desc {{
                color: {t['muted_fg']};
            }}
            QWidget#DialogBanner {{
                background-color: {t['card_bg']};
                border: 1px solid {t['border']};
                border-radius: 12px;
            }}
            QLineEdit {{
                border: 1px solid {t['border']};
                border-radius: 10px;
                padding: 7px 10px;
                background-color: {t['card_bg']};
                color: {t['fg']};
                selection-background-color: {hover_outline};
            }}
            QLineEdit:focus {{
                border: 1px solid {hover_outline};
                background-color: {t['btn_bg']};
            }}
            QPushButton, QToolButton {{
                background-color: {t['btn_bg']};
                color: {t['fg']};
                border: 1px solid {t['border']};
                border-radius: 10px;
                padding: 6px 10px;
                font-weight: 600;
            }}
            QPushButton:hover, QToolButton:hover {{
                background-color: {t['hover_bg']};
            }}
            QPushButton:pressed, QToolButton:pressed {{
                background-color: {t['hover_bg']};
            }}
            QToolButton[thumbCard="true"] {{
                background-color: {t['card_bg']};
                border-radius: 12px;
                padding: 8px;
                text-align: center;
            }}
            QToolButton[thumbCard="true"]:hover {{
                border: 1px solid {hover_outline};
                background-color: {t['hover_bg']};
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QSlider::groove:horizontal {{
                height: 6px;
                background: {t['border']};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                width: 16px;
                margin: -6px 0;
                background: {hover_outline};
                border-radius: 8px;
                border: 1px solid {t['border']};
            }}
            QToolTip {{
                background-color: {t['card_bg_2']};
                color: {t['fg']};
                border: 1px solid {t['border']};
                padding: 6px;
            }}
            """
        )

    def _show_info(self, title, text):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.NoIcon)
        box.setIconPixmap(self._mono_icon("info", True, 24).pixmap(30, 30))
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        self._style_dialog(box)
        box.exec()

    def _show_error(self, title, text):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.NoIcon)
        box.setIconPixmap(self._mono_icon("alert-triangle", True, 24).pixmap(30, 30))
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        self._style_dialog(box)
        box.exec()

    def _create_buttons(self):
        actions = [
            ("btn_prev", "arrow-left", self.show_prev_image),
            ("btn_next", "arrow-right", self.show_next_image),
            ("btn_zoom_in", "plus", self.zoom_in),
            ("btn_zoom_out", "minus", self.zoom_out),
            ("btn_rot_l", "rotate-ccw", self.rotate_left),
            ("btn_rot_r", "rotate-cw", self.rotate_right),
            ("btn_full", "maximize", self.toggle_fullscreen_mode),
            ("btn_nav", "grid", self.open_nav_window),
            ("btn_help", "help-circle", self.open_help_panel),
            ("btn_theme", "sun", self.toggle_theme),
            ("btn_file", "file", self.select_file),
            ("btn_folder", "folder", self.select_folder),
            ("btn_save", "save", self.save_image_as),
            ("btn_edit", "sliders", self.open_edit_panel),
        ]

        while self.control_layout.count():
            item = self.control_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self.buttons = []

        def add_control_button(key, fallback, func):
            btn = QToolButton()
            btn.setProperty("controlAction", True)
            btn._tip_key = key
            btn._icon_fallback = fallback
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            btn.setFixedSize(36, 36)
            btn.setIcon(self._mono_icon(fallback, False, 18))
            btn.setIconSize(QSize(18, 18))
            btn.setToolTip(self.tr(key))
            btn.clicked.connect(func)
            self.control_layout.addWidget(btn)
            self.buttons.append(btn)

        for key, fallback, func in actions:
            add_control_button(key, fallback, func)

        # Initial turret text
        self.viewer.set_turret_text(self.tr("turret_msg"))

    def _bind_shortcuts(self):
        # Define shortcuts
        sc = [
            (Qt.Key.Key_Left, self.show_prev_image),
            (Qt.Key.Key_Right, self.show_next_image),
            (Qt.Key.Key_Plus, self.zoom_in),
            (Qt.Key.Key_Equal, self.zoom_in), # Often + is =
            (Qt.Key.Key_Minus, self.zoom_out),
            (Qt.Key.Key_F11, self.toggle_fullscreen_mode),
            (Qt.Key.Key_F, self.toggle_fullscreen_mode),
            (Qt.Key.Key_R, self.rotate_right),
            (Qt.Key.Key_L, self.rotate_left),
            ("Ctrl+U", self.load_image_from_url),
            ("Ctrl+B", self.open_palette_window),
            ("Ctrl+L", self.mirror_image),
            ("Alt+P", self.export_to_pdf),
            ("Alt+I", self.export_folder_to_pdf),
            (Qt.Key.Key_F10, self.toggle_slideshow),
            ("Ctrl+T", self.open_nav_window),
            ("Ctrl+Z", self.undo_edit),
            ("Ctrl+Y", self.redo_edit),
            ("Ctrl+P", self.toggle_turret_mode),
            (Qt.Key.Key_F1, self.open_help_panel),
            ("Ctrl+1", lambda: self.apply_style("sketch")),
            ("Ctrl+2", lambda: self.apply_style("sepia")),
            ("Ctrl+3", lambda: self.apply_style("oil")),
            ("Ctrl+4", lambda: self.apply_style("contrast")),
            ("Ctrl+5", lambda: self.apply_style("bw")),
            ("Alt+T", self.toggle_language),
            (Qt.Key.Key_Escape, self.exit_fullscreen_or_slideshow)
        ]
        for key, func in sc:
            if isinstance(key, str):
                QShortcut(QKeySequence(key), self).activated.connect(func)
            else:
                QShortcut(QKeySequence(key), self).activated.connect(func)

    def apply_theme(self):
        t = self._current_theme()
        hover_outline = self._hover_outline_css()

        # Stylesheet string
        qss = f"""
            QWidget {{
                background-color: transparent;
                color: {t['fg']};
                font-family: 'Segoe UI';
            }}
            QWidget#Root {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {t['bg']},
                    stop:1 {t['bg_alt']}
                );
            }}
            QLabel {{ color: {t['fg']}; }}
            QWidget#ControlBar {{
                background-color: transparent;
                border: none;
                border-radius: 0px;
            }}
            QLabel#StatusBar {{
                background-color: {t['card_bg']};
                border: 1px solid {t['border']};
                border-radius: 10px;
                padding: 6px 10px;
                color: {t['muted_fg']};
            }}
            QPushButton {{
                background-color: {t['btn_bg']};
                color: {t['fg']};
                border: 1px solid {t['border']};
                border-radius: 10px;
                padding: 6px 10px;
            }}
            QPushButton:hover {{ background-color: {t['hover_bg']}; }}
            QPushButton:pressed {{ background-color: {t['hover_bg']}; color: {t['fg']}; }}

            QToolButton {{
                background-color: {t['btn_bg']};
                color: {t['fg']};
                border: 1px solid {t['border']};
                border-radius: 10px;
                padding: 6px 10px;
                font-weight: 600;
            }}
            QToolButton:hover {{ background-color: {t['hover_bg']}; }}
            QToolButton:pressed {{ background-color: {t['hover_bg']}; color: {t['fg']}; }}
            QToolButton[controlAction="true"] {{
                background: {t['btn_bg']};
                border: 1px solid {t['border']};
                border-radius: 18px;
                padding: 4px;
                min-width: 36px;
                min-height: 36px;
                max-width: 36px;
                max-height: 36px;
            }}
            QToolButton[controlAction="true"]:hover {{
                background: {t['hover_bg']};
                border: 1px solid {hover_outline};
            }}
            QToolButton[controlAction="true"]:pressed {{
                background: {t['btn_bg']};
                border: 1px solid {hover_outline};
            }}

            QDialog {{ background-color: {t['bg']}; }}

            QMenu {{
                background-color: {t['card_bg_2']};
                color: {t['fg']};
                border: 1px solid {t['border']};
                border-radius: 10px;
                padding: 6px;
            }}
            QMenu::item {{ padding: 6px 20px; }}
            QMenu::item:selected {{ background-color: {t['hover_bg']}; }}

            QScrollBar:vertical {{
                border: none;
                background: {t['scroll_bg']};
                width: 16px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {t['scroll_handle']};
                min-height: 20px;
                border-radius: 8px;
                margin: 2px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                subcontrol-position: bottom;
                subcontrol-origin: margin;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: {t['scroll_bg']};
            }}
            QScrollBar:horizontal {{
                border: none;
                background: {t['scroll_bg']};
                height: 16px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: {t['scroll_handle']};
                min-width: 20px;
                border-radius: 8px;
                margin: 2px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
                subcontrol-position: right;
                subcontrol-origin: margin;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: {t['scroll_bg']};
            }}
            QToolTip {{
                background-color: {t['card_bg_2']};
                color: {t['fg']};
                border: 1px solid {t['border']};
                padding: 6px;
            }}
        """

        # Apply to QApplication to ensure dialogs get it
        app = QApplication.instance()
        if app: app.setStyleSheet(qss)

        # Update Canvas/Turret theme
        self.viewer.setBackgroundBrush(QBrush(QColor(t['bg'])))
        self.viewer.update_turret_theme(t)
        for btn in self.buttons:
            fallback = self._button_icon_key(btn)
            if fallback is not None:
                btn.setIcon(self._mono_icon(fallback, False, 18))

        # Update Counter style override
        self.counter_label.setStyleSheet(
            f"background: {t['card_bg_2']}; color: {t['fg']}; "
            f"border: 1px solid {t['border']}; padding: 4px 8px; border-radius: 8px;"
        )

    def toggle_theme(self):
        self.is_dark_theme = not self.is_dark_theme
        self.apply_theme()
        self.save_last_session()

    def closeEvent(self, event):
        self.save_last_session()
        super().closeEvent(event)

    def toggle_turret_mode(self):
        self.turret_active = not self.turret_active
        t = THEME_DARK if self.is_dark_theme else THEME_LIGHT
        self.viewer.toggle_turret(self.turret_active, t)

    def show_context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction(
            self._mono_icon("rotate-ccw", False, 16),
            self.tr("ctx_rot_l"),
            self.rotate_left,
        )
        menu.addAction(
            self._mono_icon("rotate-cw", False, 16),
            self.tr("ctx_rot_r"),
            self.rotate_right,
        )
        menu.addSeparator()
        menu.addAction(
            self._mono_icon("maximize", False, 16),
            self.tr("ctx_full"),
            self.toggle_fullscreen_mode,
        )
        menu.addAction(
            self._mono_icon("arrow-left", False, 16),
            self.tr("ctx_undo"),
            self.undo_edit,
        )

        style_menu = menu.addMenu(
            self._mono_icon("aperture", False, 16),
            self.tr("ctx_style"),
        )
        style_menu.addAction(
            self._mono_icon("edit-3", False, 16),
            self.tr("style_sketch"),
            lambda: self.apply_style("sketch"),
        )
        style_menu.addAction(
            self._mono_icon("image", False, 16),
            self.tr("style_oil"),
            lambda: self.apply_style("oil"),
        )
        style_menu.addAction(
            self._mono_icon("sun", False, 16),
            self.tr("style_sepia"),
            lambda: self.apply_style("sepia"),
        )
        style_menu.addAction(
            self._mono_icon("sliders", False, 16),
            self.tr("style_contrast"),
            lambda: self.apply_style("contrast"),
        )
        style_menu.addAction(
            self._mono_icon("moon", False, 16),
            self.tr("style_bw"),
            lambda: self.apply_style("bw"),
        )

        menu.exec(self.viewer.mapToGlobal(pos))

    # --- Image Logic ---

    def _open_image(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext in RAW_EXT:
            with rawpy.imread(path) as raw:
                rgb = raw.postprocess()
                return Image.fromarray(rgb).convert("RGBA")
        elif ext == ".ico":
            # Best frame logic
            im = Image.open(path)
            max_size = (0, 0)
            best = im.copy()
            try:
                n = getattr(im, "n_frames", 1)
                for i in range(n):
                    im.seek(i)
                    if im.size[0]*im.size[1] > max_size[0]*max_size[1]:
                        max_size = im.size
                        best = im.copy()
            except: pass
            return best.convert("RGBA")
        elif ext == ".svg":
            try:
                import cairosvg
                with open(path, 'rb') as f:
                    svg_bytes = f.read()
                png_bytes = cairosvg.svg2png(bytestring=svg_bytes)
                return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
            except:
                raise Exception("SVG requires cairosvg")
        else:
            return Image.open(path).convert("RGBA")

    def load_image_path(self, path):
        try:
            self.loaded_folder = None
            self.image_list = [path]
            self.current_image_index = 0
            self._load_current_image()
        except Exception as e:
            self._show_error("Error", str(e))

    def _load_current_image(self):
        if not self.image_list: return
        path = self.image_list[self.current_image_index]
        try:
            self.last_loaded_path = path
            self.original_image = self._open_image(path)
            self.displayed_image = self.original_image.copy()
            self.rotation = 0
            self.brightness = 1.0
            self.saturation = 1.0
            self.sharpness = 1.0
            self.history.clear()
            self.push_history(self.displayed_image)

            self._update_display()
            self.update_status_bar()
            self.update_counter()
            self.save_last_session()

            # Reset view zoom/pos (center)
            self.viewer.resetTransform()
            QTimer.singleShot(0, self._center_image) # Delay fit to allow layout update

        except Exception as e:
            print(f"Error loading {path}: {e}")

    def _update_display(self):
        if not self.displayed_image: return

        # Apply rotation
        img = self.displayed_image
        if self.rotation != 0:
            img = img.rotate(self.rotation, expand=True)

        # Convert to QPixmap
        try:
            # PIL -> QImage -> QPixmap
            # Optimization: Ensure RGBA
            if img.mode != "RGBA": img = img.convert("RGBA")
            data = img.tobytes("raw", "RGBA")
            qim = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
            pix = QPixmap.fromImage(qim)
            self.viewer.set_image(pix)
        except Exception as e:
            print("Display error:", e)

    def update_status_bar(self):
        if not self.last_loaded_path or not self.original_image:
            self.status_bar.setText("")
            return
        fname = os.path.basename(self.last_loaded_path)
        w, h = self.original_image.size
        size_bytes = os.path.getsize(self.last_loaded_path) if os.path.exists(self.last_loaded_path) else 0
        size_str = f"{size_bytes/1024/1024:.2f} MB" if size_bytes > 1024*1024 else f"{size_bytes/1024:.1f} KB"
        self.status_bar.setText(f"{fname} ({w}×{h}, {size_str})")

    def update_counter(self):
        if self.image_list:
            self.counter_label.setText(f"{self.current_image_index+1}/{len(self.image_list)}")
            self.counter_label.adjustSize()
            self.counter_label.move(self.viewer.width() - self.counter_label.width() - 20, 20)
        else:
            self.counter_label.setText("")

    def _center_image(self):
        # Simple logic to fit or center
        if not self.viewer.pixmap_item.pixmap().isNull():
            self.viewer.fitInView(self.viewer.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    # --- Actions ---

    def show_prev_image(self):
        if self.image_list and self.current_image_index > 0:
            self.current_image_index -= 1
            self._load_current_image()

    def show_next_image(self):
        if self.image_list and self.current_image_index < len(self.image_list) - 1:
            self.current_image_index += 1
            self._load_current_image()
        elif self.slideshow_active:
            self.current_image_index = 0
            self._load_current_image()

    def zoom_in(self):
        self.viewer.scale(1.2, 1.2)

    def zoom_out(self):
        self.viewer.scale(1/1.2, 1/1.2)

    def rotate_left(self):
        self.rotation = (self.rotation - 90) % 360
        self._update_display()

    def rotate_right(self):
        self.rotation = (self.rotation + 90) % 360
        self._update_display()

    def toggle_fullscreen_mode(self):
        if self.isFullScreen():
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self):
        if self.isFullScreen():
            return
        self._window_was_maximized_before_fullscreen = self.isMaximized()
        if self._window_was_maximized_before_fullscreen:
            self._window_geometry_before_fullscreen = self.normalGeometry()
        else:
            self._window_geometry_before_fullscreen = self.geometry()
        self.showFullScreen()

    def _exit_fullscreen(self):
        if not self.isFullScreen():
            return
        self.showNormal()
        if self._window_was_maximized_before_fullscreen:
            self.showMaximized()
        elif (
            self._window_geometry_before_fullscreen is not None
            and self._window_geometry_before_fullscreen.isValid()
        ):
            self.setGeometry(self._window_geometry_before_fullscreen)

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("file_dialog_img"), "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff *.jfif *.svg *.cr2 *.nef *.arw *.dng *.ico)")
        if path:
            self.load_image_path(path)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("file_dialog_folder"))
        if folder:
            self.loaded_folder = folder
            exts = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".jfif", ".svg", ".cr2", ".nef", ".arw", ".dng", ".ico")
            files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(exts)]
            files.sort()
            self.image_list = files
            self.current_image_index = 0
            self._load_current_image()

    def save_image_as(self):
        if not self.displayed_image: return
        path, _ = QFileDialog.getSaveFileName(self, self.tr("save_title"), "", "PNG (*.png);;JPEG (*.jpg);;BMP (*.bmp)")
        if path:
            # We save the rotated version
            to_save = self.displayed_image
            if self.rotation:
                to_save = to_save.rotate(self.rotation, expand=True)
            to_save.convert("RGB").save(path)
            self._show_info(self.tr("save_info"), self.tr("save_msg").format(path))

    def load_image_from_url(self):
        # Dialog
        d = QDialog(self)
        d.setWindowTitle(self.tr("open_with_url"))
        d.setWindowIcon(self._mono_icon("link", True, 18))
        d.resize(400, 150)
        self._style_dialog(d)
        layout = QVBoxLayout(d)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Reverted to cleaner look, just centered as requested
        lbl = QLabel(self.tr("url_lbl"))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)

        inp = QLineEdit()
        inp.setPlaceholderText("https://...")
        inp.setClearButtonEnabled(True)
        layout.addWidget(inp)

        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_cancel = QPushButton(self.tr("url_cancel"))
        btn_cancel.setFixedSize(100, 30)
        btn_cancel.setIcon(self._mono_icon("x", False, 16))
        btn_cancel.clicked.connect(d.reject)

        btn_load = QPushButton(self.tr("url_load"))
        btn_load.setFixedSize(100, 30)
        btn_load.setIcon(self._mono_icon("check", False, 16))

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_load)
        layout.addLayout(btn_layout)

        def do_load():
            url = inp.text().strip()
            if not url: return
            try:
                btn_load.setText(self.tr("url_downloading"))
                btn_load.setEnabled(False)
                QApplication.processEvents()

                headers = {'User-Agent': 'Mozilla/5.0'}
                r = requests.get(url, headers=headers, timeout=10)
                r.raise_for_status()
                img = Image.open(io.BytesIO(r.content)).convert("RGBA")
                self.loaded_folder = None
                self.image_list = []
                self.current_image_index = 0
                self.original_image = img
                self.displayed_image = img.copy()
                self.rotation = 0
                self.history.clear()
                self.push_history(img)
                self._update_display()
                self.status_bar.setText(self.tr("status_url").format(url))
                d.accept()
            except Exception as e:
                btn_load.setText(self.tr("url_load"))
                btn_load.setEnabled(True)
                self._show_error(self.tr("url_err_title"), self.tr("url_err_msg").format(str(e)))

        btn_load.clicked.connect(do_load)
        d.exec()

    # --- Editing ---
    def push_history(self, img):
        self.history.append(img.copy())
        if len(self.history) > 20: self.history.pop(0)
        self.future.clear()

    def undo_edit(self):
        if len(self.history) > 1:
            curr = self.history.pop()
            self.future.append(curr)
            self.displayed_image = self.history[-1].copy()
            self.original_image = self.displayed_image.copy() # Sync original so further edits apply to this state
            self._update_display()

    def redo_edit(self):
        if self.future:
            nxt = self.future.pop()
            self.history.append(nxt)
            self.displayed_image = nxt.copy()
            self.original_image = nxt.copy()
            self._update_display()

    def mirror_image(self):
        if not self.original_image: return
        self.displayed_image = ImageOps.mirror(self.displayed_image)
        self.original_image = self.displayed_image.copy()
        self.push_history(self.displayed_image)
        self._update_display()

    def apply_style(self, style):
        if not self.original_image: return
        img = self.original_image.convert("RGB")
        if style == "sketch":
            gray = img.convert("L")
            edges = gray.filter(ImageFilter.FIND_EDGES)
            img = ImageOps.invert(edges)
        elif style == "oil":
            img = img.filter(ImageFilter.SMOOTH_MORE).filter(ImageFilter.DETAIL)
            img = ImageEnhance.Color(img).enhance(1.5)
        elif style == "sepia":
            # Simple sepia using matrix
            # R*0.393 + G*0.769 + B*0.189 etc.
            # Using fast PIL matrix
            matrix = ( 0.393, 0.769, 0.189, 0,
                       0.349, 0.686, 0.168, 0,
                       0.272, 0.534, 0.131, 0)
            img = img.convert("RGB", matrix)
        elif style == "contrast":
            img = ImageEnhance.Contrast(img).enhance(2.0)
        elif style == "bw":
            img = img.convert("L").convert("RGB")

        self.displayed_image = img.convert("RGBA")
        self.original_image = self.displayed_image.copy() # Commit change
        self.push_history(self.displayed_image)
        self._update_display()

    def open_edit_panel(self):
        d = QDialog(self)
        d.setWindowTitle(self.tr("edit_title"))
        d.setWindowIcon(self._mono_icon("sliders", True, 18))
        d.resize(560, 320)
        self._style_dialog(d)
        layout = QVBoxLayout(d)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        def create_slider(name, initial, cb):
            row = QHBoxLayout()
            title = QLabel(name)
            value = QLabel(f"{initial:.2f}x")
            value.setFixedWidth(52)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(title)
            row.addStretch(1)
            row.addWidget(value)
            layout.addLayout(row)

            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(20, 300) # 0.2 to 3.0
            s.setValue(int(initial * 100))
            def on_change(raw):
                factor = raw / 100.0
                value.setText(f"{factor:.2f}x")
                cb(factor)
            s.valueChanged.connect(on_change)
            layout.addWidget(s)

        create_slider(self.tr("edit_bright"), self.brightness, lambda v: self._queue_adjustment("b", v))
        create_slider(self.tr("edit_sat"), self.saturation, lambda v: self._queue_adjustment("s", v))
        create_slider(self.tr("edit_sharp"), self.sharpness, lambda v: self._queue_adjustment("sh", v))

        layout.addSpacing(8)
        layout.addWidget(QLabel(self.tr("edit_hover_border")))

        color_row = QHBoxLayout()
        color_row.setSpacing(8)

        color_input = QLineEdit(self._hover_outline_css())
        color_input.setPlaceholderText(self.tr("edit_hover_border_placeholder"))
        color_input.setMinimumWidth(220)
        color_row.addWidget(color_input, 1)

        preview = QLabel()
        preview.setFixedSize(28, 28)
        color_row.addWidget(preview)

        def refresh_preview(color_css):
            t = self._current_theme()
            preview.setStyleSheet(
                f"background-color: {color_css}; "
                f"border: 1px solid {t['border']}; "
                "border-radius: 6px;"
            )

        def apply_manual_color():
            if not self._set_hover_outline_color(color_input.text()):
                self._show_error(
                    self.tr("edit_hover_border_invalid_title"),
                    self.tr("edit_hover_border_invalid_msg"),
                )
                return
            color_input.setText(self._hover_outline_css())
            refresh_preview(self._hover_outline_css())

        def pick_color():
            picked = QColorDialog.getColor(
                QColor(self._hover_outline_css()),
                d,
                self.tr("edit_pick_color"),
                QColorDialog.ColorDialogOption.ShowAlphaChannel,
            )
            if not picked.isValid():
                return
            if self._set_hover_outline_color(picked.name(QColor.NameFormat.HexArgb)):
                color_input.setText(self._hover_outline_css())
                refresh_preview(self._hover_outline_css())

        btn_pick = QPushButton(self.tr("edit_pick_color"))
        btn_pick.setIcon(self._mono_icon("aperture", False, 16))
        btn_pick.clicked.connect(pick_color)
        color_row.addWidget(btn_pick)

        color_input.returnPressed.connect(apply_manual_color)
        refresh_preview(self._hover_outline_css())
        layout.addLayout(color_row)

        d.show() # Non-modal

    def _queue_adjustment(self, type_, val):
        if type_ == "b": self.brightness = val
        if type_ == "s": self.saturation = val
        if type_ == "sh": self.sharpness = val
        self._edit_timer.start() # Restart debounce

    def _apply_debounced_adjustments(self):
        # Apply to base history state to avoid compounding
        if not self.history: return
        base = self.history[-1].convert("RGB")

        if abs(self.brightness - 1.0) > 0.01:
            base = ImageEnhance.Brightness(base).enhance(self.brightness)
        if abs(self.saturation - 1.0) > 0.01:
            base = ImageEnhance.Color(base).enhance(self.saturation)
        if abs(self.sharpness - 1.0) > 0.01:
            base = ImageEnhance.Sharpness(base).enhance(self.sharpness)

        self.displayed_image = base.convert("RGBA")
        self.original_image = self.displayed_image.copy()
        self._update_display()

    # --- Extra Windows ---

    def open_help_panel(self):
        d = QDialog(self)
        d.setWindowTitle(self.tr("help_title"))
        d.setWindowIcon(self._mono_icon("help-circle", True, 18))
        d.resize(560, 640)
        self._style_dialog(d)

        l = QVBoxLayout(d)
        l.setContentsMargins(12, 12, 12, 12)
        l.setSpacing(10)

        banner = QWidget()
        banner.setObjectName("DialogBanner")
        bl = QHBoxLayout(banner)
        bl.setContentsMargins(12, 10, 12, 10)
        bl.setSpacing(10)

        badge = QLabel()
        badge.setPixmap(self._mono_icon("help-circle", True, 24).pixmap(28, 28))
        bl.addWidget(badge)

        title_wrap = QVBoxLayout()
        title = QLabel(self.tr("help_title"))
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        subtitle_text = "Mapa skrótów i szybkie akcje" if self.language == "pl" else "Keyboard map and quick actions"
        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("Desc")
        title_wrap.addWidget(title)
        title_wrap.addWidget(subtitle)
        bl.addLayout(title_wrap)
        bl.addStretch(1)
        l.addWidget(banner)

        sa = QScrollArea()
        sa.setWidgetResizable(True) # Fix resizing/gaps
        sa.setFrameShape(QFrame.Shape.NoFrame)

        w = QWidget()
        w.setObjectName("Content")
        gl = QGridLayout(w)
        gl.setSpacing(12)
        gl.setContentsMargins(2, 2, 2, 2)
        gl.setColumnStretch(1, 1)

        shortcuts = [
            ("← / →", self.tr("h_prev")), ("+ / -", self.tr("h_zoom")), ("F11", self.tr("h_full")),
            ("R / L", self.tr("h_rot")), ("Ctrl+U", self.tr("h_url")), ("Ctrl+B", self.tr("h_pal")), ("Ctrl+L", self.tr("h_mir")),
            ("Alt+T", self.tr("h_lang")), # Added Language shortcut
            ("Alt+P/I", self.tr("h_pdf")), ("F10", self.tr("h_slide")), ("Ctrl+Z/Y", self.tr("h_undo")),
            ("Ctrl+P", self.tr("h_turret")), (self.tr("h_scroll"), self.tr("h_zoom")), ("LPM+Drag", self.tr("h_pan"))
        ]

        for i, (k, desc) in enumerate(shortcuts):
            lbl_k = QLabel(k)
            lbl_k.setObjectName("Key")
            lbl_k.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_k.setFixedWidth(128) # Fixed width for alignment

            lbl_d = QLabel(desc)
            lbl_d.setObjectName("Desc")
            lbl_d.setWordWrap(True)

            gl.addWidget(lbl_k, i, 0)
            gl.addWidget(lbl_d, i, 1)

        # Push to top
        gl.setRowStretch(len(shortcuts), 1)

        sa.setWidget(w)
        l.addWidget(sa)

        btn_ok = QPushButton("OK")
        btn_ok.setFixedSize(100, 35)
        btn_ok.setIcon(self._mono_icon("check", False, 16))
        btn_ok.clicked.connect(d.accept)
        l.addWidget(btn_ok, 0, Qt.AlignmentFlag.AlignCenter)

        d.exec()

    def open_palette_window(self):
        if not self.displayed_image: return
        # Extract colors
        img = self.displayed_image.convert("RGB")
        img.thumbnail((200, 200))
        q = img.quantize(colors=5, method=Image.MEDIANCUT)
        palette = q.getpalette()[:15] # 5 colors * 3 channels

        d = QDialog(self)
        d.setWindowTitle(self.tr("pal_title"))
        d.setWindowIcon(self._mono_icon("aperture", True, 18))
        self._style_dialog(d)
        l = QVBoxLayout(d)

        t = self._current_theme()
        for i in range(0, len(palette), 3):
            r, g, b = palette[i:i+3]
            hex_c = f"#{r:02x}{g:02x}{b:02x}"
            row = QHBoxLayout()
            lbl_col = QLabel()
            lbl_col.setFixedSize(40, 40)
            lbl_col.setStyleSheet(
                f"background-color: {hex_c}; "
                f"border: 1px solid {t['border']}; "
                "border-radius: 8px;"
            )
            row.addWidget(lbl_col)
            row.addWidget(QLabel(hex_c.upper()))
            l.addLayout(row)

        btn_save = QPushButton(self.tr("pal_save"))
        btn_save.setIcon(self._mono_icon("save", False, 16))
        def save_pal():
            # Create palette image
            im_pal = Image.new("RGB", (500, 100), "#1c1c1c")
            draw = ImageDraw.Draw(im_pal)
            for j in range(5):
                r,g,b = palette[j*3:j*3+3]
                draw.rectangle([j*100, 0, (j+1)*100, 80], fill=(r,g,b))
                # Text drawing omitted for brevity, logic remains similar
            path, _ = QFileDialog.getSaveFileName(d, self.tr("pal_dlg_save"), "palette.png")
            if path: im_pal.save(path)

        btn_save.clicked.connect(save_pal)
        l.addWidget(btn_save)
        d.exec()

    def open_nav_window(self):
        if not self.image_list: return
        d = QDialog(self)
        d.setWindowTitle(self.tr("nav_title"))
        d.resize(980, 420)
        d.setWindowIcon(self._mono_icon("grid", True, 18))
        self._style_dialog(d)

        layout = QVBoxLayout(d)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        banner = QWidget()
        banner.setObjectName("DialogBanner")
        bl = QHBoxLayout(banner)
        bl.setContentsMargins(12, 10, 12, 10)
        bl.setSpacing(10)

        badge = QLabel()
        badge.setPixmap(self._mono_icon("grid", True, 24).pixmap(28, 28))
        bl.addWidget(badge)

        title_wrap = QVBoxLayout()
        title = QLabel(self.tr("nav_title"))
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        subtitle = QLabel(
            f"{len(self.image_list)} plików"
            if self.language == "pl"
            else f"{len(self.image_list)} files"
        )
        subtitle.setObjectName("Desc")
        title_wrap.addWidget(title)
        title_wrap.addWidget(subtitle)
        bl.addLayout(title_wrap)
        bl.addStretch(1)
        layout.addWidget(banner)

        sa = QScrollArea()
        sa.setWidgetResizable(True) # Fixes gaps (the "two bars" issue)
        sa.setFrameShape(QFrame.Shape.NoFrame) # Removes border "bar"
        # Horizontal scrollbar restored as requested

        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        # Use QToolButton for cleaner layout (icon top, text bottom)
        col = 0
        for i, path in enumerate(self.image_list):

            # Simple button with name
            name = os.path.basename(path)
            # Truncate name
            short_name = (name[:12] + '...') if len(name) > 12 else name

            # --- Added Metadata Loading Logic ---
            res_str = ""
            size_str = ""

            # Try to load thumb and info
            if path not in self.thumb_cache:
                try:
                    im = Image.open(path)

                    # Store info for reuse (optional, but good if we cache texts too)
                    w, h = im.size
                    res_str = f"{w}x{h}"

                    # File Size
                    try:
                        sz = os.path.getsize(path)
                        size_str = f"{sz/1024:.1f} KB" if sz < 1024*1024 else f"{sz/1024/1024:.1f} MB"
                    except: pass

                    # Use cover mode to avoid ugly stretching, or contain
                    im.thumbnail((THUMB_WIDTH, THUMB_HEIGHT))
                    # Center on a transparent background to preserve layout
                    bg = Image.new('RGBA', (THUMB_WIDTH, THUMB_HEIGHT), (0,0,0,0))
                    offset = ((THUMB_WIDTH - im.width) // 2, (THUMB_HEIGHT - im.height) // 2)
                    bg.paste(im, offset)

                    # Store tuple (pixmap, info_string)
                    info_text = f"{short_name}\n{res_str}\n{size_str}"
                    self.thumb_cache[path] = (ImageQt.toqpixmap(bg), info_text)
                except: pass

            # Create Button with Info
            btn = QToolButton()
            btn.setProperty("textAction", True)
            btn.setProperty("thumbCard", True)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            # Increase height to fit 3 lines of text
            btn.setFixedSize(THUMB_WIDTH + 20, THUMB_HEIGHT + 60)

            if path in self.thumb_cache:
                pix, txt = self.thumb_cache[path]
                btn.setIcon(QIcon(pix))
                btn.setText(txt)
                btn.setIconSize(QSize(THUMB_WIDTH, THUMB_HEIGHT))
            else:
                btn.setText(short_name)

            btn.clicked.connect(partial(self.nav_jump, i, d))
            grid.addWidget(btn, 0, col)
            col += 1

        sa.setWidget(content)
        layout.addWidget(sa)

        btn_close = QPushButton("OK")
        btn_close.setFixedSize(100, 35)
        btn_close.setIcon(self._mono_icon("check", False, 16))
        btn_close.clicked.connect(d.accept)
        layout.addWidget(btn_close, 0, Qt.AlignmentFlag.AlignCenter)
        d.exec()

    def nav_jump(self, idx, dialog):
        self.current_image_index = idx
        self._load_current_image()
        # dialog.accept() # Optional: close on click

    # --- PDF & Utils ---
    
    def export_to_pdf(self):
        if not self.displayed_image: return
        path, _ = QFileDialog.getSaveFileName(self, self.tr("pdf_title"), "", "PDF (*.pdf)")
        if path:
            try:
                c = pdfcanvas.Canvas(path, pagesize=A4)
                img = self.displayed_image
                pw, ph = A4
                iw, ih = img.size
                scale = min(pw/iw, ph/ih)
                nw, nh = iw*scale, ih*scale

                with io.BytesIO() as bio:
                    img.save(bio, format="PNG")
                    bio.seek(0)
                    c.drawImage(ImageReader(bio), (pw-nw)/2, (ph-nh)/2, nw, nh)
                    c.showPage()
                    c.save()
                self._show_info(self.tr("pdf_success"), self.tr("pdf_success"))
            except Exception as e:
                self._show_error(self.tr("pdf_err_title"), str(e))

    def export_folder_to_pdf(self):
        if not self.image_list: return
        path, _ = QFileDialog.getSaveFileName(self, self.tr("pdf_folder_title"), "", "PDF (*.pdf)")
        if not path: return

        # Use QThread Worker to keep UI responsive AND give feedback
        self.worker = PdfExportWorker(self.image_list, path, self._open_image)
        self.worker.finished.connect(self._on_pdf_finished)
        self.worker.start()

        self._show_info(self.tr("pdf_bg_title"), self.tr("pdf_bg_info"))

    def _on_pdf_finished(self, msg):
        if msg == "SUCCESS":
            text = self.tr("pdf_worker_success")
        elif msg.startswith("ERROR||"):
            text = self.tr("pdf_worker_err").format(msg.split("||", 1)[1])
        else:
            text = msg
        self._show_info(self.tr("pdf_box_title"), text)

    def toggle_slideshow(self):
        self.slideshow_active = not self.slideshow_active
        if self.slideshow_active:
            self._enter_fullscreen()
            self.slideshow_timer.start()
        else:
            self.slideshow_timer.stop()
            self._exit_fullscreen()

    def slideshow_next(self):
        self.show_next_image()

    def exit_fullscreen_or_slideshow(self):
        if self.slideshow_active:
            self.toggle_slideshow()
        elif self.isFullScreen():
            self._exit_fullscreen()

    def load_last_session(self):
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, "rb") as f:
                    data = pickle.load(f)
                    saved_hover_outline = data.get("hover_outline_color")
                    if saved_hover_outline is None:
                        self.hover_outline_color = None
                    else:
                        normalized_hover_outline = self._normalize_hover_outline_color(saved_hover_outline)
                        if normalized_hover_outline is not None:
                            self.hover_outline_color = normalized_hover_outline

                    if isinstance(data.get("is_dark_theme"), bool):
                        self.is_dark_theme = data["is_dark_theme"]

                    self.apply_theme()

                    if data.get("folder") and os.path.isdir(data["folder"]):
                        self.loaded_folder = data["folder"]
                        # Re-scan
                        exts = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".jfif", ".svg", ".cr2", ".nef", ".arw", ".dng", ".ico")
                        files = [os.path.join(self.loaded_folder, fn) for fn in os.listdir(self.loaded_folder) if fn.lower().endswith(exts)]
                        files.sort()
                        self.image_list = files
                        self.current_image_index = data.get("index", 0)
                        self._load_current_image()
            except: pass

    def save_last_session(self):
        data = {
            "folder": self.loaded_folder,
            "index": self.current_image_index,
            # Zoom/rotation are typically transient in this viewer logic or reset on load,
            # but we save them if needed. For now, matching old behavior of saving basic state.
            "zoom": self.viewer.transform().m11(),
            "rotation": self.rotation,
            "is_dark_theme": self.is_dark_theme,
            "hover_outline_color": self.hover_outline_color,
        }
        try:
            with open(SESSION_FILE, "wb") as f:
                pickle.dump(data, f)
        except: pass

    def toggle_zoom_fit(self):
        # Toggle: If zoomed in (> 1.0 or significantly larger than window), zoom to fit.
        # If at fit or smaller, zoom to 1.0 (100%).

        current_scale = self.viewer.transform().m11()

        # Calculate scale needed to fit
        if self.viewer.pixmap_item.pixmap().isNull(): return

        view_rect = self.viewer.viewport().rect()
        pix_rect = self.viewer.pixmap_item.boundingRect()

        fit_scale_w = view_rect.width() / pix_rect.width()
        fit_scale_h = view_rect.height() / pix_rect.height()
        fit_scale = min(fit_scale_w, fit_scale_h)

        # Threshold to decide "are we fit?"
        if current_scale > fit_scale * 1.1:
            # We are zoomed in -> Zoom out to fit
            self.viewer.fitInView(self.viewer.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        else:
            # We are fit or small -> Zoom to 100%
            self.viewer.resetTransform()
            self.viewer.scale(1.0, 1.0)

