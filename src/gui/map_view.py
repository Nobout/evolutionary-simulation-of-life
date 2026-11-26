"""Vue de la carte : rendu QImage depuis NumPy, caméra fluide et pinceau pixelisé."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QEasingCurve, QLineF, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from core.tiles import (
    TILE_BASE_COLORS,
    TileType,
    compute_tile_variation,
    generate_color_map,
    render_region_colors,
)
from core.world import WorldMap

# Couleur de fond « océan profond infini » hors carte
_BG_COLOR = QColor(11, 30, 86)


class MapView(QWidget):
    """Affichage interactif de la carte avec caméra, peinture et curseur aligné sur la grille."""

    brush_size_changed = Signal(int)
    hover_info_changed = Signal(int, int, int)  # (tx, ty, tile_type) ou (-1, -1, -1)
    zoom_changed = Signal(float)
    undo_availability_changed = Signal(bool)

    def __init__(self, world: WorldMap, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.world = world

        # Caméra (en coordonnées tuiles)
        self.cam_x: float = world.size / 2.0
        self.cam_y: float = world.size / 2.0
        self.zoom: float = 2.0  # pixels par tuile

        # Animation fluide de recentrage
        self._recenter_anim: QVariantAnimation | None = None
        self._anim_start_state: tuple[float, float, float] = (0.0, 0.0, 1.0)
        self._anim_end_state: tuple[float, float, float] = (0.0, 0.0, 1.0)

        # Outil actif : valeur TileType, -1 (gomme) ou None (navigation seule)
        self._tool: int | None = None
        self._brush_shape: str = "circle"
        self._brush_size: int = 3

        # État d'interaction souris
        self._panning: bool = False
        self._pan_start = QPointF()
        self._painting: bool = False

        # Cache de rendu
        self._variation: np.ndarray | None = None
        self._color_buffer: np.ndarray | None = None
        self._image: QImage | None = None
        self._initial_fit_done: bool = False

        # Cache des masques relatifs de pinceau pour un contour instantané
        self._brush_cache: dict[
            tuple[int, str],
            tuple[list[tuple[int, int, int, int]], list[tuple[int, int]]],
        ] = {}

        self._precompute_variation()
        self._rebuild_image()

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ── API publique ──────────────────────────────────────────────────

    def set_world(self, world: WorldMap) -> None:
        """Remplace la carte affichée (nouvelle partie / chargement)."""
        self._stop_recenter_anim()
        self.world = world
        self.cam_x = world.size / 2.0
        self.cam_y = world.size / 2.0
        self._precompute_variation()
        self._rebuild_image()
        self._initial_fit_done = False
        self._fit_to_view()
        self._initial_fit_done = True
        self.zoom_changed.emit(self.zoom)
        self.undo_availability_changed.emit(self.world.can_undo)
        self.update()

    def set_tool(self, tool: int | None) -> None:
        self._tool = tool
        self.update()

    def set_brush_shape(self, shape: str) -> None:
        self._brush_shape = shape
        self.update()

    def set_brush_size(self, size: int) -> None:
        clamped = max(1, min(50, size))
        if clamped != self._brush_size:
            self._brush_size = clamped
            self.brush_size_changed.emit(self._brush_size)
            self.update()

    def undo(self) -> bool:
        """Annule le dernier coup de pinceau et rafraîchit la zone modifiée."""
        restored = self.world.undo()
        if restored is None:
            return False
        self._refresh_region_from_coords(restored)
        self.undo_availability_changed.emit(self.world.can_undo)
        self.update()
        return True

    def recenter(self) -> None:
        """Recentre et ajuste avec fluidité la vue sur l'ensemble de la carte."""
        if self.width() <= 0 or self.height() <= 0:
            return
        target_zoom = max(0.25, min(self.width(), self.height()) / self.world.size * 0.9)
        target_x = self.world.size / 2.0
        target_y = self.world.size / 2.0

        self._stop_recenter_anim()
        self._anim_start_state = (self.cam_x, self.cam_y, self.zoom)
        self._anim_end_state = (target_x, target_y, target_zoom)

        anim = QVariantAnimation(self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self._on_recenter_step)
        self._recenter_anim = anim
        anim.start()

    # ── Rendu interne ─────────────────────────────────────────────────

    def _stop_recenter_anim(self) -> None:
        if self._recenter_anim is not None:
            self._recenter_anim.stop()
            self._recenter_anim.deleteLater()
            self._recenter_anim = None

    def _on_recenter_step(self, t: float) -> None:
        sx, sy, sz = self._anim_start_state
        ex, ey, ez = self._anim_end_state
        self.cam_x = sx + (ex - sx) * t
        self.cam_y = sy + (ey - sy) * t
        self.zoom = sz + (ez - sz) * t
        self.zoom_changed.emit(self.zoom)
        self.update()

    def _precompute_variation(self) -> None:
        self._variation = compute_tile_variation(self.world.size, self.world.size)

    def _rebuild_image(self) -> None:
        """Reconstruit entièrement le buffer couleur et le QImage."""
        self._color_buffer = generate_color_map(
            self.world.grid, self._variation, self.world.elevation
        )
        self._refresh_qimage()

    def _refresh_qimage(self) -> None:
        """Met à jour l'enveloppe QImage sans copie mémoire inutile."""
        h, w = self._color_buffer.shape[:2]
        self._image = QImage(
            self._color_buffer.data, w, h, w * 4, QImage.Format.Format_RGBA8888
        )

    def _refresh_region_from_coords(self, coords: list[tuple[int, int]]) -> None:
        """Met à jour uniquement le rectangle englobant des tuiles modifiées."""
        if (
            not coords
            or self._color_buffer is None
            or self._variation is None
        ):
            return
        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]
        x_min = max(0, min(xs))
        x_max = min(self.world.size, max(xs) + 1)
        y_min = max(0, min(ys))
        y_max = min(self.world.size, max(ys) + 1)

        self._color_buffer[y_min:y_max, x_min:x_max] = render_region_colors(
            self.world.grid,
            self._variation,
            self.world.elevation,
            y_min,
            y_max,
            x_min,
            x_max,
        )
        self._refresh_qimage()

    def _fit_to_view(self) -> None:
        if self.width() > 0 and self.height() > 0:
            self.zoom = min(self.width(), self.height()) / self.world.size * 0.9
            self.zoom = max(0.25, self.zoom)
            self.zoom_changed.emit(self.zoom)

    def _screen_to_tile(self, sx: float, sy: float) -> tuple[float, float]:
        """Convertit des coordonnées écran en coordonnées tuile réelles."""
        tx = self.cam_x + (sx - self.width() / 2.0) / self.zoom
        ty = self.cam_y + (sy - self.height() / 2.0) / self.zoom
        return tx, ty

    def _clamp_camera(self) -> None:
        """Contraint le centre de la caméra à l'intérieur de la carte."""
        self.cam_x = max(0.0, min(float(self.world.size), self.cam_x))
        self.cam_y = max(0.0, min(float(self.world.size), self.cam_y))

    def _emit_hover_info(self, screen_pos: QPointF) -> None:
        tx, ty = self._screen_to_tile(screen_pos.x(), screen_pos.y())
        ix, iy = int(np.floor(tx)), int(np.floor(ty))
        if 0 <= ix < self.world.size and 0 <= iy < self.world.size:
            tile_val = int(self.world.grid[iy, ix])
            self.hover_info_changed.emit(ix, iy, tile_val)
        else:
            self.hover_info_changed.emit(-1, -1, -1)

    def _paint_at(self, screen_pos: QPointF) -> None:
        """Applique le pinceau à la position écran donnée."""
        if self._tool is None:
            return
        tx, ty = self._screen_to_tile(screen_pos.x(), screen_pos.y())
        tile_x, tile_y = int(np.floor(tx)), int(np.floor(ty))

        paint_type = int(TileType.DEEP_OCEAN) if self._tool == -1 else self._tool
        changed = self.world.apply_brush(
            tile_x, tile_y, self._brush_size, paint_type, self._brush_shape
        )
        if changed:
            self._refresh_region_from_coords(changed)
            self.update()

    # ── Aperçu du pinceau aligné sur la grille ────────────────────────

    def _get_relative_brush_data(
        self, r: int, shape: str
    ) -> tuple[list[tuple[int, int, int, int]], list[tuple[int, int]]]:
        """Récupère ou calcule le masque relatif et les arêtes extérieures du pinceau."""
        key = (r, shape)
        if key in self._brush_cache:
            return self._brush_cache[key]

        dx = np.arange(-r, r + 1)
        dy = np.arange(-r, r + 1)
        if shape == "circle":
            in_b = (dx[None, :] ** 2 + dy[:, None] ** 2) <= (r * r)
        else:
            in_b = np.ones((2 * r + 1, 2 * r + 1), dtype=bool)

        padded = np.pad(in_b, 1, mode="constant", constant_values=False)
        top_m = padded[1:-1, 1:-1] & ~padded[:-2, 1:-1]
        bot_m = padded[1:-1, 1:-1] & ~padded[2:, 1:-1]
        lft_m = padded[1:-1, 1:-1] & ~padded[1:-1, :-2]
        rgt_m = padded[1:-1, 1:-1] & ~padded[1:-1, 2:]

        segs: list[tuple[int, int, int, int]] = []
        y_i, x_i = np.where(top_m)
        for x, y in zip(dx[x_i], dy[y_i]):
            segs.append((int(x), int(y), int(x + 1), int(y)))
        y_i, x_i = np.where(bot_m)
        for x, y in zip(dx[x_i], dy[y_i]):
            segs.append((int(x), int(y + 1), int(x + 1), int(y + 1)))
        y_i, x_i = np.where(lft_m)
        for x, y in zip(dx[x_i], dy[y_i]):
            segs.append((int(x), int(y), int(x), int(y + 1)))
        y_i, x_i = np.where(rgt_m)
        for x, y in zip(dx[x_i], dy[y_i]):
            segs.append((int(x + 1), int(y), int(x + 1), int(y + 1)))

        y_act, x_act = np.where(in_b)
        act_tiles = [(int(x), int(y)) for x, y in zip(dx[x_act], dy[y_act])]

        data = (segs, act_tiles)
        self._brush_cache[key] = data
        return data

    def _brush_tint_color(self) -> QColor:
        """Retourne une teinte translucide reflétant l'outil actif."""
        if self._tool == -1:
            return QColor(240, 95, 95, 45)
        if self._tool is not None:
            r, g, b = TILE_BASE_COLORS[TileType(self._tool)]
            return QColor(r, g, b, 55)
        return QColor(255, 255, 255, 26)

    def _draw_brush_preview(self, painter: QPainter, left: float, top: float) -> None:
        """Trace le contour exact en escalier des cases affectées par le pinceau."""
        if self._tool is None or not self.underMouse() or self._panning:
            return

        cursor_pos = self.mapFromGlobal(QCursor.pos())
        tile_fx, tile_fy = self._screen_to_tile(cursor_pos.x(), cursor_pos.y())
        ti_x, ti_y = int(np.floor(tile_fx)), int(np.floor(tile_fy))
        r = self._brush_size
        shape = self._brush_shape
        map_size = self.world.size

        if ti_x + r < 0 or ti_x - r >= map_size or ti_y + r < 0 or ti_y - r >= map_size:
            return

        fill_color = self._brush_tint_color()

        if ti_x - r >= 0 and ti_x + r < map_size and ti_y - r >= 0 and ti_y + r < map_size:
            segs, act_tiles = self._get_relative_brush_data(r, shape)
            for dx, dy in act_tiles:
                painter.fillRect(
                    QRectF(
                        (ti_x + dx - left) * self.zoom,
                        (ti_y + dy - top) * self.zoom,
                        self.zoom,
                        self.zoom,
                    ),
                    fill_color,
                )
            lines = [
                QLineF(
                    (ti_x + x1 - left) * self.zoom,
                    (ti_y + y1 - top) * self.zoom,
                    (ti_x + x2 - left) * self.zoom,
                    (ti_y + y2 - top) * self.zoom,
                )
                for x1, y1, x2, y2 in segs
            ]
        else:
            dx = np.arange(-r, r + 1)
            dy = np.arange(-r, r + 1)
            if shape == "circle":
                in_b = (dx[None, :] ** 2 + dy[:, None] ** 2) <= (r * r)
            else:
                in_b = np.ones((2 * r + 1, 2 * r + 1), dtype=bool)

            padded = np.pad(in_b, 1, mode="constant", constant_values=False)

            tx_all = ti_x + np.arange(-r - 1, r + 2)
            ty_all = ti_y + np.arange(-r - 1, r + 2)
            valid_x = (tx_all >= 0) & (tx_all < map_size)
            valid_y = (ty_all >= 0) & (ty_all < map_size)
            active = padded & (valid_y[:, None] & valid_x[None, :])

            top_m = active[1:-1, 1:-1] & ~active[:-2, 1:-1]
            bot_m = active[1:-1, 1:-1] & ~active[2:, 1:-1]
            lft_m = active[1:-1, 1:-1] & ~active[1:-1, :-2]
            rgt_m = active[1:-1, 1:-1] & ~active[1:-1, 2:]

            tx_in = ti_x + dx
            ty_in = ti_y + dy

            act_y, act_x = np.where(active[1:-1, 1:-1])
            for x, y in zip(tx_in[act_x], ty_in[act_y]):
                painter.fillRect(
                    QRectF(
                        (x - left) * self.zoom,
                        (y - top) * self.zoom,
                        self.zoom,
                        self.zoom,
                    ),
                    fill_color,
                )

            lines = []
            y_i, x_i = np.where(top_m)
            for x, y in zip(tx_in[x_i], ty_in[y_i]):
                lines.append(QLineF((x - left) * self.zoom, (y - top) * self.zoom, (x + 1 - left) * self.zoom, (y - top) * self.zoom))
            y_i, x_i = np.where(bot_m)
            for x, y in zip(tx_in[x_i], ty_in[y_i]):
                lines.append(QLineF((x - left) * self.zoom, (y + 1 - top) * self.zoom, (x + 1 - left) * self.zoom, (y + 1 - top) * self.zoom))
            y_i, x_i = np.where(lft_m)
            for x, y in zip(tx_in[x_i], ty_in[y_i]):
                lines.append(QLineF((x - left) * self.zoom, (y - top) * self.zoom, (x - left) * self.zoom, (y + 1 - top) * self.zoom))
            y_i, x_i = np.where(rgt_m)
            for x, y in zip(tx_in[x_i], ty_in[y_i]):
                lines.append(QLineF((x + 1 - left) * self.zoom, (y - top) * self.zoom, (x + 1 - left) * self.zoom, (y + 1 - top) * self.zoom))

        if lines:
            painter.setPen(QPen(QColor(0, 0, 0, 170), 2.5))
            painter.drawLines(lines)
            outline_color = QColor(255, 165, 165, 240) if self._tool == -1 else QColor(255, 255, 255, 240)
            painter.setPen(QPen(outline_color, 1.5))
            painter.drawLines(lines)

    # ── Événements Qt ─────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._initial_fit_done:
            self._fit_to_view()
            self._initial_fit_done = True

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.hover_info_changed.emit(-1, -1, -1)
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        vw, vh = self.width(), self.height()

        # Fond océan profond infini
        painter.fillRect(self.rect(), _BG_COLOR)

        half_w = vw / (2.0 * self.zoom)
        half_h = vh / (2.0 * self.zoom)
        left = self.cam_x - half_w
        top = self.cam_y - half_h

        src_l = max(0.0, left)
        src_t = max(0.0, top)
        src_r = min(float(self.world.size), self.cam_x + half_w)
        src_b = min(float(self.world.size), self.cam_y + half_h)

        if src_r > src_l and src_b > src_t and self._image:
            source = QRectF(src_l, src_t, src_r - src_l, src_b - src_t)
            dst_l = (src_l - left) * self.zoom
            dst_t = (src_t - top) * self.zoom
            dest = QRectF(
                dst_l, dst_t,
                (src_r - src_l) * self.zoom,
                (src_b - src_t) * self.zoom,
            )
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawImage(dest, self._image, source)

        # Bordure grise discontinue autour de la zone jouable
        border_l = (0 - left) * self.zoom
        border_t = (0 - top) * self.zoom
        border_sz = self.world.size * self.zoom
        painter.setPen(QPen(QColor(190, 200, 220, 140), 1.5, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(border_l, border_t, border_sz, border_sz))

        # Aperçu pixelisé du pinceau aligné sur la grille
        self._draw_brush_preview(painter, left, top)

        painter.end()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            delta = event.angleDelta().y()
            self.set_brush_size(self._brush_size + (1 if delta > 0 else -1))
            event.accept()
            return

        self._stop_recenter_anim()
        mouse = event.position()
        old_tx, old_ty = self._screen_to_tile(mouse.x(), mouse.y())

        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.zoom = max(0.25, min(128.0, self.zoom * factor))

        new_tx, new_ty = self._screen_to_tile(mouse.x(), mouse.y())
        self.cam_x += old_tx - new_tx
        self.cam_y += old_ty - new_ty

        self._clamp_camera()
        self.zoom_changed.emit(self.zoom)
        self._emit_hover_info(mouse)
        self.update()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._stop_recenter_anim()
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
            event.accept()
        elif event.button() == Qt.MouseButton.LeftButton and self._tool is not None:
            self._painting = True
            self.world.begin_stroke()
            self._paint_at(event.position())
            self._emit_hover_info(event.position())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._panning:
            delta = event.position() - self._pan_start
            self.cam_x -= delta.x() / self.zoom
            self.cam_y -= delta.y() / self.zoom
            self._pan_start = event.position()
            self._clamp_camera()
            self._emit_hover_info(event.position())
            self.update()
        elif self._painting and self._tool is not None:
            self._paint_at(event.position())
            self._emit_hover_info(event.position())
        else:
            self._emit_hover_info(event.position())
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
        elif event.button() == Qt.MouseButton.LeftButton and self._painting:
            self._painting = False
            self.world.end_stroke()
            self.undo_availability_changed.emit(self.world.can_undo)
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if (
            event.key() == Qt.Key.Key_Z
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.undo()
            event.accept()
        elif event.key() == Qt.Key.Key_F:
            self.recenter()
            event.accept()
        else:
            super().keyPressEvent(event)
