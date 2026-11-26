"""Fenêtre principale avec effet Mica, MapView, pilules flottantes, HUD et overlay."""

from __future__ import annotations

import ctypes
import sys
from ctypes import Structure, byref, c_int, c_long, sizeof
from ctypes import wintypes

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.tiles import TILE_LABELS, TileType
from core.world import WorldMap
from gui.hud_bar import HudBar
from gui.map_view import MapView
from gui.new_map_overlay import NewMapOverlay


# ── Structures DWM (Windows) ─────────────────────────────────────────

class MARGINS(Structure):
    _fields_ = [
        ("cxLeftWidth", c_int),
        ("cxRightWidth", c_int),
        ("cyTopHeight", c_int),
        ("cyBottomHeight", c_int),
    ]


DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMSBT_MAINWINDOW = 2


# ── Fenêtre principale ───────────────────────────────────────────────

class MainWindow(QMainWindow):
    """Fenêtre principale de l'application avec MapView, HUD, pilules d'info et Mica."""

    def __init__(self, world: WorldMap | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Evolutionary Simulation of Life")

        initial_launch = world is None
        if world is None:
            world = WorldMap.blank(512)

        self.world = world
        self._hover_coords: tuple[int, int, int] = (-1, -1, -1)
        self._current_zoom: float = 1.0

        # Widget central
        self._central = QWidget(self)
        self._central.setObjectName("centralWidget")
        self.setCentralWidget(self._central)

        layout = QVBoxLayout(self._central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Carte de jeu
        self.map_view = MapView(world, self._central)
        layout.addWidget(self.map_view, stretch=1)

        # Barre HUD (ATH) en bas
        self.hud = HudBar(world.size, self._central)
        layout.addWidget(self.hud)

        # ── Pilules flottantes discrètes en haut de la carte ───────────
        self._build_top_pills()

        # Overlay flottant de configuration du monde
        self.overlay = NewMapOverlay(self._central)
        self.overlay.map_created.connect(self._on_map_created)
        self.overlay.cancelled.connect(self._on_overlay_cancelled)

        # ── Connexions signaux ────────────────────────────────────────
        self.hud.tool_selected.connect(self.map_view.set_tool)
        self.hud.brush_shape_changed.connect(self.map_view.set_brush_shape)
        self.hud.brush_size_changed.connect(self.map_view.set_brush_size)
        self.hud.undo_requested.connect(self.map_view.undo)

        self.map_view.brush_size_changed.connect(self.hud.update_brush_size)
        self.map_view.hover_info_changed.connect(self._on_hover_info)
        self.map_view.zoom_changed.connect(self._on_zoom_changed)
        self.map_view.undo_availability_changed.connect(self._on_undo_changed)

        self.hud.new_map_requested.connect(self._on_new_map_requested)
        self.hud.save_requested.connect(self._on_save)
        self.hud.load_requested.connect(self._on_load)

        # Effet visuel Windows Mica
        self._setup_backdrop()

        if initial_launch:
            self.overlay.open_overlay(allow_cancel=False)
        else:
            self.overlay.close_overlay()

    # ── Pilules flottantes supérieures ────────────────────────────────

    def _build_top_pills(self) -> None:
        # Pilule gauche : Coordonnées, biome survolé, zoom, taille du monde
        self._status_pill = QFrame(self.map_view)
        self._status_pill.setObjectName("floatingPill")
        self._status_pill.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        status_lay = QHBoxLayout(self._status_pill)
        status_lay.setContentsMargins(12, 6, 12, 6)
        status_lay.setSpacing(8)

        self._status_label = QLabel()
        self._status_label.setObjectName("pillLabel")
        status_lay.addWidget(self._status_label)
        self._refresh_status_pill()

        # Pilule droite : Raccourcis rapides (Annuler, Recentrer)
        self._actions_pill = QFrame(self.map_view)
        self._actions_pill.setObjectName("floatingPill")
        act_lay = QHBoxLayout(self._actions_pill)
        act_lay.setContentsMargins(8, 4, 8, 4)
        act_lay.setSpacing(6)

        self._top_undo_btn = QPushButton("\u21b6 Annuler")
        self._top_undo_btn.setObjectName("pillBtn")
        self._top_undo_btn.setEnabled(False)
        self._top_undo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._top_undo_btn.setToolTip("Annuler (Ctrl+Z)")
        self._top_undo_btn.clicked.connect(self.map_view.undo)
        act_lay.addWidget(self._top_undo_btn)

        recenter_btn = QPushButton("\u2316 Recentrer")
        recenter_btn.setObjectName("pillBtn")
        recenter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        recenter_btn.setToolTip("Recentrer la caméra sur la carte (F)")
        recenter_btn.clicked.connect(self.map_view.recenter)
        act_lay.addWidget(recenter_btn)

        hint = QLabel("Molette : Zoom \u00b7 Clic molette : D\u00e9placer \u00b7 Maj+Molette : Pinceau")
        hint.setObjectName("pillHint")
        act_lay.addWidget(hint)

        pill_qss = """
            #floatingPill {
                background-color: rgba(14, 17, 25, 200);
                border: 1px solid rgba(255, 255, 255, 24);
                border-radius: 10px;
            }
            #pillLabel {
                color: #d8e1ee;
                font-size: 11px;
                font-weight: 500;
            }
            #pillHint {
                color: #7e8aa1;
                font-size: 11px;
                padding-left: 4px;
            }
            #pillBtn {
                background-color: rgba(255, 255, 255, 14);
                color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 6px;
                padding: 3px 9px;
                font-size: 11px;
                font-weight: 500;
            }
            #pillBtn:hover {
                background-color: rgba(76, 139, 245, 55);
                border-color: rgba(100, 156, 248, 120);
                color: #ffffff;
            }
            #pillBtn:disabled {
                color: #566073;
                background-color: transparent;
                border-color: rgba(255, 255, 255, 8);
            }
        """
        self._status_pill.setStyleSheet(pill_qss)
        self._actions_pill.setStyleSheet(pill_qss)

    def _position_pills(self) -> None:
        margin = 12
        self._status_pill.adjustSize()
        self._status_pill.move(margin, margin)

        self._actions_pill.adjustSize()
        ax = max(margin, self.map_view.width() - self._actions_pill.width() - margin)
        self._actions_pill.move(ax, margin)

    def _refresh_status_pill(self) -> None:
        tx, ty, tile_val = self._hover_coords
        size_txt = f"{self.world.size}\u00d7{self.world.size}"
        zoom_txt = f"Zoom {self._current_zoom:.2f}\u00d7"
        if tx >= 0 and tile_val >= 0:
            biome = TILE_LABELS.get(TileType(tile_val), "—")
            self._status_label.setText(
                f"{size_txt}  \u00b7  X: {tx}  Y: {ty}  \u00b7  {biome}  \u00b7  {zoom_txt}"
            )
        else:
            self._status_label.setText(f"{size_txt}  \u00b7  Hors carte  \u00b7  {zoom_txt}")
        self._status_pill.adjustSize()

    # ── Événements & Slots ────────────────────────────────────────────

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_pills()
        if hasattr(self, "overlay"):
            self.overlay.setGeometry(self._central.rect())

    def _on_hover_info(self, tx: int, ty: int, tile_val: int) -> None:
        self._hover_coords = (tx, ty, tile_val)
        self._refresh_status_pill()

    def _on_zoom_changed(self, zoom: float) -> None:
        self._current_zoom = zoom
        self._refresh_status_pill()

    def _on_undo_changed(self, can_undo: bool) -> None:
        self.hud.set_undo_enabled(can_undo)
        self._top_undo_btn.setEnabled(can_undo)

    # ── Gestion de l'overlay et des cartes ────────────────────────────

    def _on_new_map_requested(self) -> None:
        self.overlay.setGeometry(self._central.rect())
        self.overlay.open_overlay(allow_cancel=True)

    def _on_overlay_cancelled(self) -> None:
        self.overlay.close_overlay()

    def _on_map_created(
        self, size: int, mode: str, path: str | None, seed: int | None
    ) -> None:
        if mode == "blank":
            new_world = WorldMap.blank(size)
        elif mode == "archipelago":
            new_world = WorldMap.archipelago(size, seed=seed)
        elif mode == "load" and path:
            new_world = WorldMap.from_file(path)
        else:
            new_world = WorldMap.blank(size)

        self.world = new_world
        self.map_view.set_world(new_world)
        self.hud.set_world_size_label(new_world.size)
        self._refresh_status_pill()
        self.overlay.close_overlay()
        self.map_view.setFocus()

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Sauvegarder la carte", "", "Cartes NumPy (*.npz)"
        )
        if path:
            if not path.endswith(".npz"):
                path += ".npz"
            self.world.save(path)

    def _on_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Charger une carte", "", "Cartes NumPy (*.npz)"
        )
        if path:
            self.world = WorldMap.from_file(path)
            self.map_view.set_world(self.world)
            self.hud.set_world_size_label(self.world.size)
            self._refresh_status_pill()

    # ── Effet visuel Mica ─────────────────────────────────────────────

    def _setup_backdrop(self) -> None:
        mica_applied = False

        if sys.platform == "win32":
            try:
                self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                hwnd = int(self.winId())
                mica_applied = self._apply_windows_mica(hwnd)
            except Exception:
                mica_applied = False

        if mica_applied:
            self._central.setAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground, True
            )
            self.setStyleSheet(
                """
                QMainWindow { background: transparent; color: #ffffff; }
                #centralWidget { background: transparent; }
                """
            )
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self.setStyleSheet(
                """
                QMainWindow { background-color: #151821; color: #ffffff; }
                #centralWidget { background-color: #151821; }
                """
            )

    def _apply_windows_mica(self, hwnd: int) -> bool:
        dwmapi = ctypes.WinDLL("dwmapi")

        dwmapi.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, wintypes.LPCVOID, wintypes.DWORD,
        ]
        dwmapi.DwmSetWindowAttribute.restype = c_long
        dwmapi.DwmExtendFrameIntoClientArea.argtypes = [
            wintypes.HWND, ctypes.POINTER(MARGINS),
        ]
        dwmapi.DwmExtendFrameIntoClientArea.restype = c_long

        handle = wintypes.HWND(hwnd)

        dark_mode = c_int(1)
        dwmapi.DwmSetWindowAttribute(
            handle, DWMWA_USE_IMMERSIVE_DARK_MODE,
            byref(dark_mode), sizeof(dark_mode),
        )

        backdrop = c_int(DWMSBT_MAINWINDOW)
        hr = dwmapi.DwmSetWindowAttribute(
            handle, DWMWA_SYSTEMBACKDROP_TYPE,
            byref(backdrop), sizeof(backdrop),
        )
        if hr != 0:
            return False

        margins = MARGINS(-1, -1, -1, -1)
        hr2 = dwmapi.DwmExtendFrameIntoClientArea(handle, byref(margins))
        return hr2 == 0
