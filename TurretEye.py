# TurretEye.py (Ported to PyQt6)
# -*- coding: utf-8 -*-
import sys
import os
import io
import pickle
import math
import time
import threading
import ctypes
from functools import partial
import requests
import rawpy
from tqdm import tqdm
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageQt, ImageDraw
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QFileDialog, QMessageBox, QGraphicsView,
                             QGraphicsScene, QGraphicsPixmapItem, QGraphicsItem, QDialog,
                             QScrollArea, QFrame, QGridLayout, QSlider, QCheckBox, QMenu,
                             QSizePolicy, QLineEdit, QProgressBar, QToolButton)
from PyQt6.QtCore import (Qt, QTimer, QSize, QPoint, QPointF, QEvent, QObject, pyqtSignal, QRectF, QThread)
from PyQt6.QtGui import (QPixmap, QImage, QPainter, QColor, QIcon, QAction, QShortcut, QKeySequence,
                         QPainterPath, QPen, QBrush, QFont, QPolygonF)

# --- Constants & Config ---
SESSION_FILE = "last_session.pkl"
RAW_EXT = (".cr2", ".nef", ".arw", ".dng")
THUMB_WIDTH = 120
THUMB_HEIGHT = 100

# Colors extracted from original
THEME_DARK = {
    "bg": "#1c1c1c", "fg": "#ffffff",
    "btn_bg": "#2a2a2a", "hover_bg": "#3c3c3c",
    "card_bg": "#1f1f1f", "border": "#2b2b2b",
    "accent": "#3a82f7",
    "turret_base_fill": "#3a3a3a", "turret_base_outline": "#777",
    "turret_barrel": "#eaeaea", "turret_bubble_fill": "#222",
    "turret_bubble_text": "#fff", "pedestal": "#2f2f2f",
    "scroll_handle": "#555", "scroll_bg": "#2b2b2b"
}
THEME_LIGHT = {
    "bg": "#ffffff", "fg": "#000000",
    "btn_bg": "#f0f0f0", "hover_bg": "#d0d0d0",
    "card_bg": "#f5f5f5", "border": "#d9d9d9",
    "accent": "#1e5fbf",
    "turret_base_fill": "#e6e6e6", "turret_base_outline": "#888",
    "turret_barrel": "#444", "turret_bubble_fill": "#f5f5f5",
    "turret_bubble_text": "#000", "pedestal": "#e0e0e0",
    "scroll_handle": "#ccc", "scroll_bg": "#f0f0f0"
}

# --- Workers ---
class PdfExportWorker(QThread):
    finished = pyqtSignal(str) # Emits message on finish

    def __init__(self, image_list, save_path, opener_func):
        super().__init__()
        self.image_list = image_list
        self.save_path = save_path
        self.opener_func = opener_func

    def run(self):
        try:
            c = pdfcanvas.Canvas(self.save_path, pagesize=A4)
            pw, ph = A4
            for fpath in tqdm(self.image_list):
                try:
                    img = self.opener_func(fpath).convert("RGB")
                    iw, ih = img.size
                    scale = min(pw/iw, ph/ih)
                    nw, nh = iw*scale, ih*scale
                    with io.BytesIO() as bio:
                        img.save(bio, format="PNG")
                        bio.seek(0)
                        c.drawImage(ImageReader(bio), (pw-nw)/2, (ph-nh)/2, nw, nh)
                        c.showPage()
                except: pass
            c.save()
            self.finished.emit("Eksport PDF zakończony sukcesem!")
        except Exception as e:
            self.finished.emit(f"Błąd eksportu: {str(e)}")

# --- Turret Graphics Item ---
class TurretItem(QGraphicsItem):
    def __init__(self, theme_colors):
        super().__init__()
        self.theme = theme_colors
        self.radius = 18
        self.angle = 0
        self.target_pos = QPointF(0, 0)
        self.show_bubble = False
        # Create children
        self.base_rect = QRectF(-self.radius, -self.radius, self.radius*2, self.radius*2)

        # Pedestal
        r = self.radius
        self.pedestal_rect = QRectF(-r*1.4, r+2, r*2.8, 8)

        # Bubble geometry
        self.bw, self.bh = 172, 34

    def boundingRect(self):
        # Rough bounding rect covering everything
        return QRectF(-200, -200, 400, 400)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw Pedestal
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.theme["pedestal"]))
        painter.drawRect(self.pedestal_rect)

        # Draw Base
        painter.setPen(QPen(QColor(self.theme["turret_base_outline"]), 2))
        painter.setBrush(QColor(self.theme["turret_base_fill"]))
        painter.drawEllipse(self.base_rect)

        # Draw Barrel (Rotated)
        painter.save()
        painter.rotate(math.degrees(self.angle))
        painter.setPen(QPen(QColor("#ff2b2b"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        barrel_len = int(self.radius * 1.6)
        painter.drawLine(0, 0, barrel_len, 0)
        painter.restore()

        # Draw Bubble if active
        if self.show_bubble:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.theme["turret_bubble_fill"]))

            # Bubble position relative to turret center
            bx1 = -self.bw - 14
            by1 = -self.radius - 14 - self.bh
            rect = QRectF(bx1, by1, self.bw, self.bh)
            painter.drawRoundedRect(rect, 10, 10)

            # Tail
            tail = QPolygonF([
                QPointF(bx1 + self.bw - 20, by1 + self.bh),
                QPointF(-self.radius - 2, -self.radius - 2), # Tip
                QPointF(bx1 + self.bw - 10, by1 + self.bh - 10)
            ])
            painter.drawPolygon(tail)

            # Text
            painter.setPen(QColor(self.theme["turret_bubble_text"]))
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Are you still there?")

    def update_aim(self, target_scene_pos):
        pos = self.scenePos()
        dx = target_scene_pos.x() - pos.x()
        dy = target_scene_pos.y() - pos.y()
        self.angle = math.atan2(dy, dx)
        dist = math.hypot(dx, dy)
        self.show_bubble = (dist <= 100)
        self.update()

    def set_theme(self, theme):
        self.theme = theme
        self.update()

# --- Custom Canvas (Graphics View) ---
class ImageViewer(QGraphicsView):
    fileDropped = pyqtSignal(str)
    doubleClicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter) # Center small images

        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        self.turret_item = None
        self.turret_mode = False
        self.current_theme = None

    def set_image(self, qpixmap):
        self.pixmap_item.setPixmap(qpixmap)
        # Ensure drag freedom
        rect = self.pixmap_item.boundingRect()
        w, h = rect.width(), rect.height()
        # Make scene rect at least 3x the image size for panning freedom
        margin_x = max(w, 2000)
        margin_y = max(h, 2000)
        self.scene.setSceneRect(-margin_x, -margin_y, w + 2*margin_x, h + 2*margin_y)
        self.pixmap_item.setPos(0, 0)

    def wheelEvent(self, event):
        zoom_in = event.angleDelta().y() > 0
        factor = 1.1 if zoom_in else 1 / 1.1
        self.scale(factor, factor)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            path = event.mimeData().urls()[0].toLocalFile()
            self.fileDropped.emit(path)

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if self.turret_mode and self.turret_item:
            scene_pos = self.mapToScene(event.pos())
            self.turret_item.update_aim(scene_pos)
        super().mouseMoveEvent(event)

    def resizeEvent(self, event):
        if self.turret_mode and self.turret_item:
            self._position_turret()
        super().resizeEvent(event)

    def toggle_turret(self, enable, theme):
        self.current_theme = theme
        if enable:
            if not self.turret_item:
                self.turret_item = TurretItem(theme)
                self.turret_item.setZValue(1000) # Always on top
                self.scene.addItem(self.turret_item)
            self.turret_mode = True
            self.setMouseTracking(True) # Need this for hover events without clicking
            self._position_turret()
        else:
            if self.turret_item:
                self.scene.removeItem(self.turret_item)
                self.turret_item = None
            self.turret_mode = False
            self.setMouseTracking(False)

    def update_turret_theme(self, theme):
        self.current_theme = theme
        if self.turret_item:
            self.turret_item.set_theme(theme)

    def _position_turret(self):
        if not self.turret_item: return
        # Position bottom-right of viewport
        vp_rect = self.viewport().rect()
        scene_pos = self.mapToScene(vp_rect.bottomRight())
        # Adjust for margin
        margin = 34 # radius + padding
        self.turret_item.setPos(scene_pos.x() - margin, scene_pos.y() - margin)


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
            icon_path = os.path.join(os.path.dirname(__file__), "TurretEye.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TurretEye")
            except: pass

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
        self.turret_active = False

        self.slideshow_active = False
        self.slideshow_timer = QTimer()
        self.slideshow_timer.timeout.connect(self.slideshow_next)
        self.slideshow_timer.setInterval(5000)

        # Thumb Cache (Stores (pixmap, info_text))
        self.thumb_cache = {}

        # UI Setup
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # View
        self.viewer = ImageViewer()
        self.viewer.fileDropped.connect(self.load_image_path)
        self.viewer.doubleClicked.connect(self.toggle_zoom_fit)
        self.main_layout.addWidget(self.viewer)

        # Overlay Counter (Floating label)
        self.counter_label = QLabel("", self.viewer)
        self.counter_label.setStyleSheet("background: transparent; color: white; font-weight: bold; font-family: 'Segoe UI'; font-size: 14px; padding: 5px;")

        # Controls
        self.control_bar = QWidget()
        self.control_layout = QHBoxLayout(self.control_bar)
        self.control_layout.setContentsMargins(10, 10, 10, 10)
        self.control_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.control_bar)

        # Status Bar
        self.status_bar = QLabel("")
        self.status_bar.setContentsMargins(5, 2, 5, 2)
        # Move Status bar to be below control bar (layout order: Viewer, Controls, Status)
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
            self.counter_label.move(self.width() - self.counter_label.width() - 20, 20)
        super().resizeEvent(event)

    def _create_buttons(self):
        # Icons as text like original
        btns = [
            ("◀", self.show_prev_image),
            ("▶", self.show_next_image),
            ("+", self.zoom_in),
            ("-", self.zoom_out),
            ("↺", self.rotate_left),
            ("↻", self.rotate_right),
            ("⛶", self.toggle_fullscreen_mode),
            ("☼", self.toggle_theme),
            ("Plik", self.select_file),
            ("Folder", self.select_folder),
            ("Zapisz", self.save_image_as),
            ("Edycja", self.open_edit_panel)
        ]

        for text, func in btns:
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(60, 40) if len(text) < 3 else btn.setFixedSize(80, 40)
            btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            btn.clicked.connect(func)
            self.control_layout.addWidget(btn)
            self.buttons.append(btn)

    def _bind_shortcuts(self):
        # Define shortcuts
        sc = [
            (Qt.Key.Key_Left, self.show_prev_image),
            (Qt.Key.Key_Right, self.show_next_image),
            (Qt.Key.Key_Plus, self.zoom_in),
            (Qt.Key.Key_Equal, self.zoom_in), # Often + is =
            (Qt.Key.Key_Minus, self.zoom_out),
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
            (Qt.Key.Key_Escape, self.exit_fullscreen_or_slideshow)
        ]
        for key, func in sc:
            if isinstance(key, str):
                QShortcut(QKeySequence(key), self).activated.connect(func)
            else:
                QShortcut(QKeySequence(key), self).activated.connect(func)

    def apply_theme(self):
        t = THEME_DARK if self.is_dark_theme else THEME_LIGHT
        # Apply to QApplication to ensure dialogs get it
        app = QApplication.instance()
        if app:
            app.setStyleSheet(f"""
                QWidget {{ background-color: {t['bg']}; color: {t['fg']}; font-family: 'Segoe UI'; }}
                QLabel {{ color: {t['fg']}; }}
                QPushButton {{
                    background-color: {t['btn_bg']};
                    color: {t['fg']};
                    border: none;
                    border-radius: 4px;
                    padding: 4px;
                }}
                QPushButton:hover {{ background-color: {t['hover_bg']}; }}
                QPushButton:pressed {{ background-color: {t['accent']}; color: white; }}

                QToolButton {{
                    background-color: {t['btn_bg']};
                    color: {t['fg']};
                    border: none;
                    border-radius: 6px;
                    padding: 4px;
                }}
                QToolButton:hover {{ background-color: {t['hover_bg']}; }}
                QToolButton:pressed {{ background-color: {t['accent']}; color: white; }}

                QDialog {{ background-color: {t['bg']}; }}

                QMenu {{ background-color: {t['bg']}; color: {t['fg']}; border: 1px solid {t['border']}; padding: 5px; }}
                QMenu::item {{ padding: 6px 20px; }}
                QMenu::item:selected {{ background-color: {t['hover_bg']}; }}

                QScrollBar:vertical {{
                    border: none;
                    background: {t['scroll_bg']};
                    width: 12px;
                    margin: 0px 0px 0px 0px;
                }}
                QScrollBar::handle:vertical {{
                    background: {t['scroll_handle']};
                    min-height: 20px;
                    border-radius: 6px;
                    margin: 2px;
                }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                    height: 0px;
                }}
                QScrollBar:horizontal {{
                    border: none;
                    background: {t['scroll_bg']};
                    height: 12px;
                    margin: 0px 0px 0px 0px;
                }}
                QScrollBar::handle:horizontal {{
                    background: {t['scroll_handle']};
                    min-width: 20px;
                    border-radius: 6px;
                    margin: 2px;
                }}
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                    width: 0px;
                }}
            """)

        # Update Canvas/Turret theme
        self.viewer.setBackgroundBrush(QBrush(QColor(t['bg'])))
        self.viewer.update_turret_theme(t)

        # Update Counter style override
        self.counter_label.setStyleSheet(f"background: {t['btn_bg']}; color: {t['fg']}; padding: 4px; border-radius: 4px;")

    def toggle_theme(self):
        self.is_dark_theme = not self.is_dark_theme
        self.apply_theme()

    def toggle_turret_mode(self):
        self.turret_active = not self.turret_active
        t = THEME_DARK if self.is_dark_theme else THEME_LIGHT
        self.viewer.toggle_turret(self.turret_active, t)

    def show_context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("Obróć w lewo", self.rotate_left)
        menu.addAction("Obróć w prawo", self.rotate_right)
        menu.addSeparator()
        menu.addAction("Pełny ekran", self.toggle_fullscreen_mode)
        menu.addAction("Cofnij", self.undo_edit)

        style_menu = menu.addMenu("Stylizacja AI")
        style_menu.addAction("Szkic", lambda: self.apply_style("sketch"))
        style_menu.addAction("Obraz olejny", lambda: self.apply_style("oil"))
        style_menu.addAction("Sepia", lambda: self.apply_style("sepia"))
        style_menu.addAction("Kontrast", lambda: self.apply_style("contrast"))
        style_menu.addAction("Czarno-biały", lambda: self.apply_style("bw"))

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
            QMessageBox.critical(self, "Error", str(e))

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
            self.counter_label.move(self.width() - self.counter_label.width() - 20, 20)
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
            self.showNormal()
        else:
            self.showFullScreen()

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Wybierz obraz", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff *.jfif *.svg *.cr2 *.nef *.arw *.dng *.ico)")
        if path:
            self.load_image_path(path)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Wybierz folder")
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
        path, _ = QFileDialog.getSaveFileName(self, "Zapisz jako", "", "PNG (*.png);;JPEG (*.jpg);;BMP (*.bmp)")
        if path:
            # We save the rotated version
            to_save = self.displayed_image
            if self.rotation:
                to_save = to_save.rotate(self.rotation, expand=True)
            to_save.convert("RGB").save(path)
            QMessageBox.information(self, "Zapisano", f"Zapisano do:\n{path}")

    def load_image_from_url(self):
        # Dialog
        d = QDialog(self)
        d.setWindowTitle("Wklej URL obrazu")
        d.resize(400, 150)
        l = QVBoxLayout(d)
        inp = QLineEdit()
        inp.setPlaceholderText("https://...")
        btn = QPushButton("Załaduj")
        l.addWidget(QLabel("URL:"))
        l.addWidget(inp)
        l.addWidget(btn)

        def do_load():
            url = inp.text()
            try:
                r = requests.get(url)
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
                self.status_bar.setText(f"URL: {url}")
                d.accept()
            except Exception as e:
                QMessageBox.critical(d, "Błąd", str(e))

        btn.clicked.connect(do_load)
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
        d.setWindowTitle("Edycja")
        layout = QVBoxLayout(d)

        def create_slider(name, initial, cb):
            layout.addWidget(QLabel(name))
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(20, 300) # 0.2 to 3.0
            s.setValue(int(initial * 100))
            s.valueChanged.connect(lambda v: cb(v/100.0))
            layout.addWidget(s)

        create_slider("Jasność", self.brightness, lambda v: self._queue_adjustment("b", v))
        create_slider("Nasycenie", self.saturation, lambda v: self._queue_adjustment("s", v))
        create_slider("Ostrość", self.sharpness, lambda v: self._queue_adjustment("sh", v))
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
        d.setWindowTitle("Skróty klawiszowe")
        d.resize(600, 500)
        l = QVBoxLayout(d)
        sa = QScrollArea()
        w = QWidget()
        gl = QGridLayout(w)

        shortcuts = [
            ("← / →", "Poprzedni / następny"), ("+ / -", "Zoom"), ("F", "Pełny ekran"),
            ("R / L", "Obrót"), ("Ctrl+U", "URL"), ("Ctrl+B", "Paleta"), ("Ctrl+L", "Lustro"),
            ("Alt+P/I", "PDF"), ("F10", "Pokaz slajdów"), ("Ctrl+Z/Y", "Cofnij/Ponów"),
            ("Ctrl+P", "Turret Mode"), ("Kółko", "Zoom"), ("LPM+Drag", "Pan")
        ]

        for i, (k, desc) in enumerate(shortcuts):
            gl.addWidget(QLabel(k), i, 0)
            gl.addWidget(QLabel(desc), i, 1)

        sa.setWidget(w)
        l.addWidget(sa)
        d.exec()

    def open_palette_window(self):
        if not self.displayed_image: return
        # Extract colors
        img = self.displayed_image.convert("RGB")
        img.thumbnail((200, 200))
        q = img.quantize(colors=5, method=Image.MEDIANCUT)
        palette = q.getpalette()[:15] # 5 colors * 3 channels

        d = QDialog(self)
        d.setWindowTitle("Paleta kolorów")
        l = QVBoxLayout(d)

        for i in range(0, len(palette), 3):
            r, g, b = palette[i:i+3]
            hex_c = f"#{r:02x}{g:02x}{b:02x}"
            row = QHBoxLayout()
            lbl_col = QLabel()
            lbl_col.setFixedSize(40, 40)
            lbl_col.setStyleSheet(f"background-color: {hex_c}; border: 1px solid gray;")
            row.addWidget(lbl_col)
            row.addWidget(QLabel(hex_c.upper()))
            l.addLayout(row)

        btn_save = QPushButton("Zapisz jako PNG")
        def save_pal():
            # Create palette image
            im_pal = Image.new("RGB", (500, 100), "#1c1c1c")
            draw = ImageDraw.Draw(im_pal)
            for j in range(5):
                r,g,b = palette[j*3:j*3+3]
                draw.rectangle([j*100, 0, (j+1)*100, 80], fill=(r,g,b))
                # Text drawing omitted for brevity, logic remains similar
            path, _ = QFileDialog.getSaveFileName(d, "Zapisz", "palette.png")
            if path: im_pal.save(path)

        btn_save.clicked.connect(save_pal)
        l.addWidget(btn_save)
        d.exec()

    def open_nav_window(self):
        if not self.image_list: return
        d = QDialog(self)
        d.setWindowTitle("Nawigacja")
        d.resize(800, 300)

        layout = QVBoxLayout(d)
        sa = QScrollArea()
        content = QWidget()
        grid = QGridLayout(content)

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
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
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
        d.exec()

    def nav_jump(self, idx, dialog):
        self.current_image_index = idx
        self._load_current_image()
        # dialog.accept() # Optional: close on click

    # --- PDF & Utils ---
    
    def export_to_pdf(self):
        if not self.displayed_image: return
        path, _ = QFileDialog.getSaveFileName(self, "Eksport PDF", "", "PDF (*.pdf)")
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
                QMessageBox.information(self, "Sukces", "PDF zapisany.")
            except Exception as e:
                QMessageBox.critical(self, "Błąd", str(e))

    def export_folder_to_pdf(self):
        if not self.image_list: return
        path, _ = QFileDialog.getSaveFileName(self, "Folder do PDF", "", "PDF (*.pdf)")
        if not path: return

        # Use QThread Worker to keep UI responsive AND give feedback
        self.worker = PdfExportWorker(self.image_list, path, self._open_image)
        self.worker.finished.connect(self._on_pdf_finished)
        self.worker.start()

        QMessageBox.information(self, "Info", "Eksport rozpoczęty w tle...")

    def _on_pdf_finished(self, msg):
        QMessageBox.information(self, "PDF Eksport", msg)

    def toggle_slideshow(self):
        self.slideshow_active = not self.slideshow_active
        if self.slideshow_active:
            self.showFullScreen()
            self.slideshow_timer.start()
        else:
            self.slideshow_timer.stop()
            self.showNormal()

    def slideshow_next(self):
        self.show_next_image()

    def exit_fullscreen_or_slideshow(self):
        if self.slideshow_active:
            self.toggle_slideshow()
        elif self.isFullScreen():
            self.showNormal()

    def load_last_session(self):
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, "rb") as f:
                    data = pickle.load(f)
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
            "rotation": self.rotation
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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TurretEyeApp()
    window.show()
    sys.exit(app.exec())
