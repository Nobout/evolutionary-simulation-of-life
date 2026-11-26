"""Barre d'outils inférieure moderne (ATH / HUD) façon WorldBox."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.tiles import TILE_BASE_COLORS, TILE_LABELS, TileType


def _make_swatch_icon(rgb: tuple[int, int, int], size: int = 16) -> QIcon:
    """Crée une pastille couleur nette aux bords arrondis pour les boutons de biome."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QColor(*rgb))
    painter.setPen(QColor(255, 255, 255, 110))
    painter.drawRoundedRect(1, 1, size - 2, size - 2, 4, 4)
    painter.end()
    return QIcon(pixmap)


def _v_divider() -> QFrame:
    line = QFrame()
    line.setObjectName("hudDivider")
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFixedWidth(1)
    return line


class HudBar(QWidget):
    """Barre inférieure divisée en un sélecteur vertical à gauche (Maps / Entité / Partie)
    et un contenu contextuel moderne à droite.
    """

    tool_selected = Signal(object)     # TileType value, -1 (gomme) ou None
    brush_shape_changed = Signal(str)  # "circle" | "square"
    brush_size_changed = Signal(int)   # 1..50
    undo_requested = Signal()
    new_map_requested = Signal()
    save_requested = Signal()
    load_requested = Signal()

    def __init__(self, map_size: int = 512, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("hudBar")
        self.setFixedHeight(112)

        self._active_tool: int | None = None

        main_lay = QHBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # ── Sélecteur d'onglets vertical (gauche) ─────────────────────
        tab_widget = QWidget()
        tab_widget.setObjectName("tabSelector")
        tab_widget.setFixedWidth(114)
        tab_lay = QVBoxLayout(tab_widget)
        tab_lay.setContentsMargins(6, 8, 6, 8)
        tab_lay.setSpacing(4)

        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tab_btns: list[QPushButton] = []

        for idx, label in enumerate(["\u25c8  Maps", "\u2726  Entit\u00e9", "\u2699  Partie"]):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setObjectName("tabButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._tab_group.addButton(btn, idx)
            tab_lay.addWidget(btn)
            self._tab_btns.append(btn)

        self._tab_btns[0].setChecked(True)
        tab_lay.addStretch()
        main_lay.addWidget(tab_widget)

        # ── Contenu dynamique (droite) ────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.setObjectName("stackContent")

        self._stack.addWidget(self._build_maps_panel())
        self._stack.addWidget(self._build_entity_panel())
        self._stack.addWidget(self._build_game_panel(map_size))

        main_lay.addWidget(self._stack, stretch=1)

        self._tab_group.idClicked.connect(self._stack.setCurrentIndex)
        self._apply_global_style()

    # ── Panneau Maps ──────────────────────────────────────────────────

    def _build_maps_panel(self) -> QWidget:
        panel = QWidget()
        root_lay = QHBoxLayout(panel)
        root_lay.setContentsMargins(16, 10, 16, 10)
        root_lay.setSpacing(16)

        # Section 1 : Pinceaux de terrain + Gomme
        terrain_col = QVBoxLayout()
        terrain_col.setSpacing(6)
        terrain_title = QLabel("TERRAFORMING")
        terrain_title.setObjectName("sectionTitle")
        terrain_col.addWidget(terrain_title)

        tools_lay = QHBoxLayout()
        tools_lay.setSpacing(6)

        self._tool_group = QButtonGroup(self)
        # Non-exclusif géré manuellement pour pouvoir cliquer à nouveau et désélectionner
        self._tool_group.setExclusive(False)
        self._tool_btns: dict[int, QPushButton] = {}

        for tile_type in TileType:
            btn = QPushButton(TILE_LABELS[tile_type])
            btn.setObjectName("tileToolBtn")
            btn.setIcon(_make_swatch_icon(TILE_BASE_COLORS[tile_type], 16))
            btn.setCheckable(True)
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            tid = int(tile_type)
            self._tool_group.addButton(btn, tid)
            self._tool_btns[tid] = btn
            tools_lay.addWidget(btn)

        eraser = QPushButton("\u232b  Gomme")
        eraser.setObjectName("eraserBtn")
        eraser.setCheckable(True)
        eraser.setFixedHeight(36)
        eraser.setCursor(Qt.CursorShape.PointingHandCursor)
        eraser.setToolTip("Effacer les terres pour revenir à l'Océan profond")
        self._tool_group.addButton(eraser, -1)
        self._tool_btns[-1] = eraser
        tools_lay.addWidget(eraser)

        terrain_col.addLayout(tools_lay)
        terrain_col.addStretch()
        root_lay.addLayout(terrain_col)

        root_lay.addWidget(_v_divider())

        # Section 2 : Forme & Taille du pinceau
        brush_col = QVBoxLayout()
        brush_col.setSpacing(6)
        brush_title = QLabel("PINCEAU")
        brush_title.setObjectName("sectionTitle")
        brush_col.addWidget(brush_title)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(10)

        # Segmented shape control
        shape_box = QFrame()
        shape_box.setObjectName("segmentedBox")
        shape_lay = QHBoxLayout(shape_box)
        shape_lay.setContentsMargins(2, 2, 2, 2)
        shape_lay.setSpacing(2)

        self._shape_group = QButtonGroup(self)
        self._shape_group.setExclusive(True)

        self._circle_btn = QPushButton("\u25cf Rond")
        self._circle_btn.setObjectName("segBtn")
        self._circle_btn.setCheckable(True)
        self._circle_btn.setChecked(True)
        self._circle_btn.setFixedHeight(28)
        self._circle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._shape_group.addButton(self._circle_btn, 0)
        shape_lay.addWidget(self._circle_btn)

        self._square_btn = QPushButton("\u25a0 Carré")
        self._square_btn.setObjectName("segBtn")
        self._square_btn.setCheckable(True)
        self._square_btn.setFixedHeight(28)
        self._square_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._shape_group.addButton(self._square_btn, 1)
        shape_lay.addWidget(self._square_btn)

        controls_row.addWidget(shape_box)

        # Slider + boutons - / + + badge taille
        self._dec_btn = QPushButton("-")
        self._dec_btn.setObjectName("stepBtn")
        self._dec_btn.setFixedSize(26, 28)
        self._dec_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dec_btn.clicked.connect(lambda: self._emit_slider_step(-1))
        controls_row.addWidget(self._dec_btn)

        self._size_slider = QSlider(Qt.Orientation.Horizontal)
        self._size_slider.setObjectName("brushSlider")
        self._size_slider.setRange(1, 50)
        self._size_slider.setValue(3)
        self._size_slider.setFixedWidth(115)
        self._size_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._size_slider.setToolTip("Taille du pinceau (Maj + Molette)")
        controls_row.addWidget(self._size_slider)

        self._inc_btn = QPushButton("+")
        self._inc_btn.setObjectName("stepBtn")
        self._inc_btn.setFixedSize(26, 28)
        self._inc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._inc_btn.clicked.connect(lambda: self._emit_slider_step(1))
        controls_row.addWidget(self._inc_btn)

        self._size_badge = QLabel("r = 3")
        self._size_badge.setObjectName("sizeBadge")
        self._size_badge.setFixedWidth(48)
        self._size_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        controls_row.addWidget(self._size_badge)

        brush_col.addLayout(controls_row)
        brush_col.addStretch()
        root_lay.addLayout(brush_col)

        root_lay.addWidget(_v_divider())

        # Section 3 : Annulation rapide
        action_col = QVBoxLayout()
        action_col.setSpacing(6)
        action_title = QLabel("HISTORIQUE")
        action_title.setObjectName("sectionTitle")
        action_col.addWidget(action_title)

        self._undo_btn = QPushButton("\u21b6  Annuler")
        self._undo_btn.setObjectName("actionBtn")
        self._undo_btn.setFixedHeight(34)
        self._undo_btn.setEnabled(False)
        self._undo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._undo_btn.setToolTip("Annuler le dernier coup de pinceau (Ctrl+Z)")
        self._undo_btn.clicked.connect(self.undo_requested.emit)
        action_col.addWidget(self._undo_btn)
        action_col.addStretch()
        root_lay.addLayout(action_col)

        root_lay.addStretch()

        # Connexions
        self._tool_group.idClicked.connect(self._on_tool_clicked)
        self._shape_group.idClicked.connect(
            lambda sid: self.brush_shape_changed.emit("circle" if sid == 0 else "square")
        )
        self._size_slider.valueChanged.connect(self._on_slider_changed)
        return panel

    # ── Panneau Entité ────────────────────────────────────────────────

    def _build_entity_panel(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(6)

        badge = QLabel("PROCHAINEMENT")
        badge.setObjectName("soonBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(badge, alignment=Qt.AlignmentFlag.AlignCenter)

        lbl = QLabel("Les créatures, espèces et humains seront ajoutés prochainement.")
        lbl.setObjectName("mutedNotice")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        return panel

    # ── Panneau Partie ────────────────────────────────────────────────

    def _build_game_panel(self, map_size: int) -> QWidget:
        panel = QWidget()
        lay = QHBoxLayout(panel)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        # Groupe Carte
        map_col = QVBoxLayout()
        map_col.setSpacing(6)
        map_title = QLabel("GESTION DU MONDE")
        map_title.setObjectName("sectionTitle")
        map_col.addWidget(map_title)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        for label, signal in [
            ("\u2726  Nouvelle carte", self.new_map_requested),
            ("Sauvegarder (.npz)", self.save_requested),
            ("Charger (.npz)", self.load_requested),
        ]:
            btn = QPushButton(label)
            btn.setObjectName("actionBtn")
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(signal.emit)
            btn_row.addWidget(btn)

        map_col.addLayout(btn_row)
        map_col.addStretch()
        lay.addLayout(map_col)

        lay.addWidget(_v_divider())

        # Groupe Infos & futur temps
        info_col = QVBoxLayout()
        info_col.setSpacing(6)
        info_title = QLabel("SIMULATION")
        info_title.setObjectName("sectionTitle")
        info_col.addWidget(info_title)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)
        self._map_size_pill = QLabel(f"Monde : {map_size} \u00d7 {map_size}")
        self._map_size_pill.setObjectName("infoPill")
        meta_row.addWidget(self._map_size_pill)

        time_hint = QLabel("Contrôles du temps (Pause / Vitesse) — Bientôt disponible")
        time_hint.setObjectName("mutedNotice")
        meta_row.addWidget(time_hint)
        info_col.addLayout(meta_row)
        info_col.addStretch()
        lay.addLayout(info_col)

        lay.addStretch()
        return panel

    # ── API publique ──────────────────────────────────────────────────

    def update_brush_size(self, size: int) -> None:
        """Synchronise le slider et l'indicateur lorsque Maj+Molette est utilisé."""
        if self._size_slider.value() != size:
            self._size_slider.blockSignals(True)
            self._size_slider.setValue(size)
            self._size_slider.blockSignals(False)
        self._size_badge.setText(f"r = {size}")

    def set_undo_enabled(self, enabled: bool) -> None:
        self._undo_btn.setEnabled(enabled)

    def set_world_size_label(self, size: int) -> None:
        self._map_size_pill.setText(f"Monde : {size} \u00d7 {size}")

    # ── Slots privés ──────────────────────────────────────────────────

    def _on_tool_clicked(self, tool_id: int) -> None:
        if self._active_tool == tool_id:
            # Re-cliquer sur l'outil actif le désélectionne
            self._tool_btns[tool_id].setChecked(False)
            self._active_tool = None
        else:
            for tid, btn in self._tool_btns.items():
                btn.setChecked(tid == tool_id)
            self._active_tool = tool_id
        self.tool_selected.emit(self._active_tool)

    def _on_slider_changed(self, value: int) -> None:
        self._size_badge.setText(f"r = {value}")
        self.brush_size_changed.emit(value)

    def _emit_slider_step(self, delta: int) -> None:
        self._size_slider.setValue(max(1, min(50, self._size_slider.value() + delta)))

    # ── Feuille de style QSS ──────────────────────────────────────────

    def _apply_global_style(self) -> None:
        self.setStyleSheet(
            """
            #hudBar {
                background-color: rgba(16, 19, 28, 228);
                border-top: 1px solid rgba(255, 255, 255, 26);
            }
            #tabSelector {
                background-color: rgba(12, 14, 21, 240);
                border-right: 1px solid rgba(255, 255, 255, 16);
            }
            #tabButton {
                background-color: transparent;
                color: #8f9bb3;
                border: none;
                border-left: 3px solid transparent;
                border-radius: 5px;
                padding: 7px 10px;
                text-align: left;
                font-size: 12px;
                font-weight: 500;
            }
            #tabButton:hover {
                color: #e4e9f2;
                background-color: rgba(255, 255, 255, 10);
            }
            #tabButton:checked {
                color: #ffffff;
                background-color: rgba(76, 139, 245, 28);
                border-left: 3px solid #4c8bf5;
                font-weight: 600;
            }
            #hudDivider {
                background-color: rgba(255, 255, 255, 18);
                margin-top: 8px;
                margin-bottom: 8px;
            }
            #sectionTitle {
                color: #7c889e;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            #tileToolBtn, #eraserBtn {
                background-color: rgba(34, 38, 52, 220);
                color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 22);
                border-radius: 7px;
                padding: 4px 11px;
                font-size: 12px;
                font-weight: 500;
            }
            #tileToolBtn:hover, #eraserBtn:hover {
                background-color: rgba(48, 54, 72, 235);
                border-color: rgba(255, 255, 255, 65);
                color: #ffffff;
            }
            #tileToolBtn:checked {
                background-color: rgba(76, 139, 245, 52);
                border: 1.5px solid #649cf8;
                color: #ffffff;
            }
            #eraserBtn:checked {
                background-color: rgba(220, 75, 75, 55);
                border: 1.5px solid #ef6c6c;
                color: #ffffff;
            }
            #segmentedBox {
                background-color: rgba(12, 14, 21, 200);
                border: 1px solid rgba(255, 255, 255, 18);
                border-radius: 7px;
            }
            #segBtn {
                background-color: transparent;
                color: #9aa5b8;
                border: none;
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 500;
            }
            #segBtn:hover {
                color: #ffffff;
            }
            #segBtn:checked {
                background-color: rgba(76, 139, 245, 75);
                color: #ffffff;
                font-weight: 600;
            }
            #stepBtn {
                background-color: rgba(34, 38, 52, 220);
                color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 22);
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            #stepBtn:hover {
                background-color: rgba(52, 58, 76, 235);
            }
            #brushSlider::groove:horizontal {
                background: rgba(255, 255, 255, 22);
                height: 4px;
                border-radius: 2px;
            }
            #brushSlider::sub-page:horizontal {
                background: #4c8bf5;
                height: 4px;
                border-radius: 2px;
            }
            #brushSlider::handle:horizontal {
                background: #ffffff;
                border: 2px solid #4c8bf5;
                width: 12px;
                height: 12px;
                margin: -5px 0;
                border-radius: 7px;
            }
            #sizeBadge, #infoPill {
                background-color: rgba(255, 255, 255, 14);
                color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 18);
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 600;
            }
            #actionBtn {
                background-color: rgba(36, 41, 56, 225);
                color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 24);
                border-radius: 7px;
                padding: 5px 14px;
                font-size: 12px;
                font-weight: 500;
            }
            #actionBtn:hover {
                background-color: rgba(54, 61, 82, 235);
                border-color: rgba(255, 255, 255, 55);
                color: #ffffff;
            }
            #actionBtn:disabled {
                background-color: rgba(24, 27, 37, 140);
                color: #5b6476;
                border-color: rgba(255, 255, 255, 10);
            }
            #soonBadge {
                background-color: rgba(76, 139, 245, 36);
                color: #82b1ff;
                border: 1px solid rgba(76, 139, 245, 70);
                border-radius: 10px;
                padding: 2px 10px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            #mutedNotice {
                color: #7d899e;
                font-size: 12px;
            }
            """
        )
