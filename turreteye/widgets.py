# -*- coding: utf-8 -*-
import math

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPolygonF, QRadialGradient)
from PyQt6.QtWidgets import (QFrame, QGraphicsPixmapItem, QGraphicsScene,
                             QGraphicsView)

from .config import THEME_DARK

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

        self.turret_mode = False
        self.current_theme = THEME_DARK # Default fallback
        self.last_mouse_pos = QPoint(0, 0)
        self.turret_angle = 0
        self.turret_dist = 1000
        self.turret_text_str = "Are you still there?"

    def set_turret_text(self, text):
        self.turret_text_str = text
        if self.turret_mode: self.viewport().update()

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
        # Repaint foreground to update turret if needed (though it draws relative to view)
        if self.turret_mode: self.viewport().update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()
        else: event.ignore()

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
        if self.turret_mode:
            self.last_mouse_pos = event.pos()
            self.viewport().update() # Redraw foreground
        super().mouseMoveEvent(event)

    def toggle_turret(self, enable, theme):
        self.current_theme = theme
        self.turret_mode = enable
        self.setMouseTracking(enable)
        self.viewport().update()

    def update_turret_theme(self, theme):
        self.current_theme = theme
        if self.turret_mode: self.viewport().update()

    def drawForeground(self, painter, rect):
        if painter is None or not painter.isActive():
            return
        super().drawForeground(painter, rect)
        if not self.turret_mode:
            return

        # Reset transform to draw in viewport coordinates (HUD style)
        painter.save()
        painter.resetTransform()

        vp_w = self.viewport().width()
        vp_h = self.viewport().height()

        # Config
        scale = 0.75 # Slightly smaller as requested
        # Turret dimensions based on reference proportions
        # Oval body: Width ~ 60, Height ~ 100
        body_w = 60 * scale
        body_h = 100 * scale

        # Position: Bottom Right
        margin_right = 70
        margin_bottom = 80
        cx = vp_w - margin_right
        cy = vp_h - margin_bottom

        # ---------------------------------------------------------
        # Drawing: Vector Icon Style (Portal 2 Turret) - Refined
        # ---------------------------------------------------------

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Calculate Angles for Laser/Eye
        mx = self.last_mouse_pos.x()
        my = self.last_mouse_pos.y()
        eye_y = cy - body_h * 0.05
        dx = mx - cx
        dy = my - eye_y
        dist = math.hypot(dx, dy)
        angle = math.atan2(dy, dx)

        # --- LASER SIGHT (Draw First so it's behind body if overlapping, but usually in front) ---
        # Actually laser should originate from eye.
        painter.save()
        painter.translate(cx, eye_y)
        painter.rotate(math.degrees(angle))

        # Laser Line
        laser_pen = QPen(QColor(255, 0, 0, 180), 2)
        laser_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(laser_pen)
        painter.drawLine(0, 0, int(dist), 0) # Draw to mouse cursor

        # Laser Dot at cursor
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 0, 0, 200))
        painter.drawEllipse(QPointF(dist, 0), 3, 3)

        painter.restore()

        # --- LEGS (More mechanical look) ---
        painter.setPen(QPen(QColor("#1a1a1a"), 1))
        painter.setBrush(QColor("#2b2b2b"))

        # Helper to draw tapered leg
        def draw_leg(x1, y1, x2, y2, thickness_start, thickness_end):
            path = QPainterPath()
            vec_x = x2 - x1
            vec_y = y2 - y1
            l = math.hypot(vec_x, vec_y)
            if l == 0: return
            nx = -vec_y / l
            ny = vec_x / l

            p1 = QPointF(x1 + nx * thickness_start, y1 + ny * thickness_start)
            p2 = QPointF(x2 + nx * thickness_end, y2 + ny * thickness_end)
            p3 = QPointF(x2 - nx * thickness_end, y2 - ny * thickness_end)
            p4 = QPointF(x1 - nx * thickness_start, y1 - ny * thickness_start)

            path.moveTo(p1)
            path.lineTo(p2)
            path.lineTo(p3)
            path.lineTo(p4)
            path.closeSubpath()
            painter.drawPath(path)

        # Center Leg (Back)
        draw_leg(cx, cy + body_h * 0.2, cx, cy + body_h * 0.85, 4, 1.5)

        # Front Left
        draw_leg(cx - body_w * 0.25, cy + body_h * 0.3, cx - body_w * 1.1, cy + body_h * 0.9, 5, 2)

        # Front Right
        draw_leg(cx + body_w * 0.25, cy + body_h * 0.3, cx + body_w * 1.1, cy + body_h * 0.9, 5, 2)


        # --- BODY (Gradient Shading) ---
        body_rect = QRectF(cx - body_w/2, cy - body_h/2, body_w, body_h)

        # Main Body Gradient (White to Grey)
        grad = QLinearGradient(body_rect.topLeft(), body_rect.bottomRight())
        grad.setColorAt(0.0, QColor("#ffffff"))
        grad.setColorAt(0.4, QColor("#f0f0f0"))
        grad.setColorAt(1.0, QColor("#b0b0b0"))

        painter.setBrush(grad)
        painter.setPen(QPen(QColor("#555555"), 1)) # Subtle outline
        painter.drawEllipse(body_rect)

        # Center Vertical Divider (Subtle)
        painter.setPen(QPen(QColor("#444444"), 1.5))
        painter.drawLine(QPointF(cx, cy - body_h/2), QPointF(cx, cy + body_h/2))

        # Horizontal Divider (Equator) - roughly
        # painter.drawArc(body_rect, 0, 180 * 16) # Optional

        # Side Wings (Panels) - Separate shapes for depth
        # Animation: Open wings if close
        is_active = dist <= 150
        wing_offset = 20 * scale if is_active else 0

        wing_w = body_w * 0.35
        wing_h = body_h * 0.6

        # Guns (visible if open)
        if is_active:
            painter.setBrush(QColor("#111111"))
            painter.setPen(Qt.PenStyle.NoPen)
            # Left Gun
            painter.drawRect(QRectF(cx - body_w/2 - 10 * scale, cy - wing_h * 0.2, 8 * scale, wing_h * 0.4))
            # Right Gun
            painter.drawRect(QRectF(cx + body_w/2 + 2 * scale, cy - wing_h * 0.2, 8 * scale, wing_h * 0.4))

        painter.setBrush(QColor("#e0e0e0"))
        painter.setPen(QPen(QColor("#666666"), 1))

        # Left Wing
        painter.drawChord(QRectF(cx - body_w/2 - 5 - wing_offset, cy - wing_h/2, wing_w, wing_h), 90*16, 180*16)
        # Right Wing
        painter.drawChord(QRectF(cx + body_w/2 + 5 - wing_w + wing_offset, cy - wing_h/2, wing_w, wing_h), -90*16, 180*16)

        # --- EYE (Complex) ---
        eye_radius = body_w * 0.28

        # Black housing
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#111111"))
        painter.drawEllipse(QPointF(cx, eye_y), eye_radius, eye_radius)

        # Red Glow/Pupil
        # Dynamic pupil position based on mouse angle (subtle tracking)
        pupil_dist = eye_radius * 0.2
        px = cx + math.cos(angle) * pupil_dist
        py = eye_y + math.sin(angle) * pupil_dist

        pupil_radius = eye_radius * 0.5

        rad_grad = QRadialGradient(px, py, pupil_radius)
        rad_grad.setColorAt(0.0, QColor("#ff4444"))
        rad_grad.setColorAt(0.8, QColor("#aa0000"))
        rad_grad.setColorAt(1.0, QColor("#550000"))

        painter.setBrush(rad_grad)
        painter.drawEllipse(QPointF(px, py), pupil_radius, pupil_radius)

        # Shine
        painter.setBrush(QColor(255, 255, 255, 200))
        painter.drawEllipse(QPointF(px + pupil_radius*0.3, py - pupil_radius*0.3), pupil_radius*0.25, pupil_radius*0.25)

        # 6. Bubble Logic
        mx = self.last_mouse_pos.x()
        my = self.last_mouse_pos.y()
        dx = mx - cx
        dy = my - cy
        dist = math.hypot(dx, dy)

        if dist <= 150:
            bw, bh = 190, 40
            bx = int(cx - bw - 40)
            by = int(cy - body_h/2 - bh)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.current_theme["turret_bubble_fill"]))
            painter.drawRoundedRect(bx, by, bw, bh, 12, 12)

            # Tail
            tail = QPolygonF([
                QPointF(bx + bw - 20, by + bh),
                QPointF(cx - 20, cy - body_h/2 + 20),
                QPointF(bx + bw - 10, by + bh - 10)
            ])
            painter.drawPolygon(tail)

            painter.setPen(QColor(self.current_theme["turret_bubble_text"]))
            painter.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            painter.drawText(QRectF(bx, by, bw, bh), Qt.AlignmentFlag.AlignCenter, self.turret_text_str)

        painter.restore()

