"""Panneau flottant moderne (Overlay) de configuration et génération d'une carte."""

from __future__ import annotations

import hashlib
import random

from PySide6.QtCore import QEasingCurve, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_SIZES = [
    (256, "256 \u00d7 256", "Rapide"),
    (512, "512 \u00d7 512", "Standard"),
    (1024, "1024 \u00d7 1024", "Grand"),
    (2048, "2048 \u00d7 2048", "Immense"),
]

_MODES = [
    (
        "archipelago",
        "Archipel proc\u00e9dural",
        "1 \u00e0 8 \u00eeles organiques avec c\u00f4tes d\u00e9coup\u00e9es et biomes coh\u00e9rents",
    ),
    (
        "blank",
        "Carte vierge",
        "\u00c9tendue d'oc\u00e9an profond pr\u00eate pour le terraforming manuel",
    ),
    (
        "load",
        "Charger une carte (.npz)",
        "Importer un monde sauvegard\u00e9 pr\u00e9c\u00e9demment",
    ),
]


def _parse_seed(raw: str) -> int | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return abs(int(text))
    except ValueError:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
        return int(digest, 16)


class NewMapOverlay(QWidget):
    """Carte centrale flottante posée au-dessus de la fenêtre principale."""

    # Émet (taille, mode, chemin_fichier | None, seed | None)
    map_created = Signal(int, str, object, object)
    cancelled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("newMapOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._file_path: str | None = None
        self._veil_alpha: int = 210
        self._fade_anim: QVariantAnimation | None = None

        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.setContentsMargins(24, 24, 24, 24)

        # ── Carte flottante sombre translucide ────────────────────────
        self._card = QFrame(self)
        self._card.setObjectName("floatingCard")
        self._card.setFixedWidth(510)

        card_layout = QVBoxLayout(self._card)
        card_layout.setSpacing(18)
        card_layout.setContentsMargins(28, 26, 28, 26)

        # En-tête
        header_lay = QVBoxLayout()
        header_lay.setSpacing(4)

        badge = QLabel("NOUVEAU MONDE")
        badge.setObjectName("headerBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_lay.addWidget(badge, alignment=Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Evolutionary Simulation of Life")
        title.setObjectName("cardTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_lay.addWidget(title)

        subtitle = QLabel("Configurez les dimensions et le relief initial de votre écosystème")
        subtitle.setObjectName("cardSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_lay.addWidget(subtitle)
        card_layout.addLayout(header_lay)

        # ── 1. Taille de la carte (4 cartes pill cliquables) ──────────
        size_section = QVBoxLayout()
        size_section.setSpacing(8)
        size_lbl = QLabel("DIMENSIONS DE LA CARTE")
        size_lbl.setObjectName("sectionLabel")
        size_section.addWidget(size_lbl)

        size_row = QHBoxLayout()
        size_row.setSpacing(8)
        self._size_group = QButtonGroup(self)
        self._size_group.setExclusive(True)

        for idx, (val, dim_txt, tag_txt) in enumerate(_SIZES):
            btn = QPushButton(f"{dim_txt}\n{tag_txt}")
            btn.setObjectName("sizeCardBtn")
            btn.setCheckable(True)
            btn.setFixedHeight(52)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._size_group.addButton(btn, val)
            size_row.addWidget(btn)
            if idx == 1:  # 512 × 512 par défaut
                btn.setChecked(True)

        size_section.addLayout(size_row)
        card_layout.addLayout(size_section)

        # ── 2. Mode de génération ─────────────────────────────────────
        mode_section = QVBoxLayout()
        mode_section.setSpacing(8)
        mode_lbl = QLabel("MODE DE GÉNÉRATION")
        mode_lbl.setObjectName("sectionLabel")
        mode_section.addWidget(mode_lbl)

        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_keys = ["archipelago", "blank", "load"]

        for idx, (key, m_title, m_desc) in enumerate(_MODES):
            btn = QPushButton(f"{m_title}\n{m_desc}")
            btn.setObjectName("modeCardBtn")
            btn.setCheckable(True)
            btn.setFixedHeight(52)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._mode_group.addButton(btn, idx)
            mode_section.addWidget(btn)
            if idx == 0:
                btn.setChecked(True)

        # Options contextuelles (Graine pour archipel / Fichier pour chargement)
        self._seed_row = QWidget()
        seed_lay = QHBoxLayout(self._seed_row)
        seed_lay.setContentsMargins(2, 4, 2, 0)
        seed_lay.setSpacing(8)
        seed_txt = QLabel("Graine (optionnel) :")
        seed_txt.setObjectName("subFieldLabel")
        seed_lay.addWidget(seed_txt)

        self._seed_input = QLineEdit()
        self._seed_input.setObjectName("seedInput")
        self._seed_input.setPlaceholderText("Aléatoire (laisser vide)")
        seed_lay.addWidget(self._seed_input, stretch=1)

        rand_btn = QPushButton("Aléatoire")
        rand_btn.setObjectName("secondaryBtn")
        rand_btn.setFixedHeight(30)
        rand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rand_btn.clicked.connect(
            lambda: self._seed_input.setText(str(random.randint(1, 999999)))
        )
        seed_lay.addWidget(rand_btn)
        mode_section.addWidget(self._seed_row)

        self._load_row = QWidget()
        load_lay = QHBoxLayout(self._load_row)
        load_lay.setContentsMargins(2, 4, 2, 0)
        load_lay.setSpacing(8)

        self._path_label = QLabel("Aucun fichier sélectionné")
        self._path_label.setObjectName("pathLabel")
        load_lay.addWidget(self._path_label, stretch=1)

        self._browse_btn = QPushButton("Parcourir\u2026")
        self._browse_btn.setObjectName("secondaryBtn")
        self._browse_btn.setFixedHeight(30)
        self._browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._browse_btn.clicked.connect(self._browse_file)
        load_lay.addWidget(self._browse_btn)
        self._load_row.hide()
        mode_section.addWidget(self._load_row)

        card_layout.addLayout(mode_section)

        # ── 3. Boutons d'action ───────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self._cancel_btn = QPushButton("Annuler")
        self._cancel_btn.setObjectName("cancelBtn")
        self._cancel_btn.setFixedHeight(40)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._cancel_btn.hide()
        btn_layout.addWidget(self._cancel_btn)

        self._generate_btn = QPushButton("Générer le monde")
        self._generate_btn.setObjectName("generateBtn")
        self._generate_btn.setFixedHeight(40)
        self._generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._generate_btn.clicked.connect(self._on_generate)
        btn_layout.addWidget(self._generate_btn, stretch=1)

        card_layout.addLayout(btn_layout)

        main_layout.addWidget(self._card)

        self._mode_group.idClicked.connect(self._on_mode_changed)
        self._apply_style()

    # ── API publique ──────────────────────────────────────────────────

    def open_overlay(self, allow_cancel: bool = False) -> None:
        """Affiche l'overlay avec une transition douce du voile."""
        self._cancel_btn.setVisible(allow_cancel)
        self._generate_btn.setEnabled(True)
        self._generate_btn.setText("Générer le monde")
        self._on_mode_changed(self._mode_group.checkedId())

        self._veil_alpha = 0
        self.show()
        self.raise_()
        self.setFocus()

        if self._fade_anim is not None:
            self._fade_anim.stop()
            self._fade_anim.deleteLater()
        anim = QVariantAnimation(self)
        anim.setDuration(180)
        anim.setStartValue(0)
        anim.setEndValue(210)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self._on_fade_step)
        self._fade_anim = anim
        anim.start()

    def close_overlay(self) -> None:
        """Masque l'overlay."""
        if self._fade_anim is not None:
            self._fade_anim.stop()
        self.hide()

    # ── Événements Qt ─────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(8, 10, 16, self._veil_alpha))
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        event.accept()

    # ── Slots privés ──────────────────────────────────────────────────

    def _on_fade_step(self, val: int) -> None:
        self._veil_alpha = int(val)
        self.update()

    def _on_mode_changed(self, mode_id: int) -> None:
        mode = self._mode_keys[mode_id] if 0 <= mode_id < 3 else "archipelago"
        is_archi = mode == "archipelago"
        is_load = mode == "load"
        self._seed_row.setVisible(is_archi)
        self._load_row.setVisible(is_load)

        for btn in self._size_group.buttons():
            btn.setEnabled(not is_load)

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Charger une carte", "", "Cartes NumPy (*.npz)"
        )
        if path:
            self._file_path = path
            self._path_label.setText(path)
            self._path_label.setStyleSheet("color: #cfd8dc; font-size: 11px;")

    def _on_generate(self) -> None:
        mode_id = self._mode_group.checkedId()
        mode = self._mode_keys[mode_id] if 0 <= mode_id < 3 else "archipelago"

        if mode == "load" and not self._file_path:
            self._path_label.setText("\u26a0 Veuillez sélectionner un fichier .npz valide.")
            self._path_label.setStyleSheet("color: #ff7676; font-size: 11px;")
            return

        size = self._size_group.checkedId()
        if size <= 0:
            size = 512

        seed = _parse_seed(self._seed_input.text()) if mode == "archipelago" else None

        self._generate_btn.setEnabled(False)
        self._generate_btn.setText("Génération du monde\u2026")
        QApplication.processEvents()

        self.map_created.emit(size, mode, self._file_path, seed)

    def _on_cancel(self) -> None:
        self.close_overlay()
        self.cancelled.emit()

    # ── Feuille de style QSS ──────────────────────────────────────────

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            #floatingCard {
                background-color: rgba(20, 23, 33, 245);
                border: 1px solid rgba(255, 255, 255, 32);
                border-radius: 16px;
            }
            #headerBadge {
                background-color: rgba(76, 139, 245, 34);
                color: #8ab4ff;
                border: 1px solid rgba(76, 139, 245, 75);
                border-radius: 9px;
                padding: 2px 10px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1.2px;
            }
            #cardTitle {
                color: #ffffff;
                font-size: 19px;
                font-weight: 700;
                letter-spacing: 0.3px;
            }
            #cardSubtitle {
                color: #8b97ad;
                font-size: 12px;
                margin-bottom: 4px;
            }
            #sectionLabel {
                color: #7d89a0;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            #sizeCardBtn {
                background-color: rgba(31, 35, 49, 220);
                color: #c5cedc;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 9px;
                font-size: 11px;
                font-weight: 600;
                padding: 4px;
            }
            #sizeCardBtn:hover {
                background-color: rgba(44, 50, 70, 235);
                border-color: rgba(255, 255, 255, 55);
                color: #ffffff;
            }
            #sizeCardBtn:checked {
                background-color: rgba(76, 139, 245, 48);
                border: 1.5px solid #5c96f7;
                color: #ffffff;
            }
            #sizeCardBtn:disabled {
                background-color: rgba(24, 27, 37, 130);
                color: #555e70;
                border-color: rgba(255, 255, 255, 10);
            }
            #modeCardBtn {
                background-color: rgba(31, 35, 49, 220);
                color: #d6deea;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 9px;
                text-align: left;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 500;
            }
            #modeCardBtn:hover {
                background-color: rgba(44, 50, 70, 235);
                border-color: rgba(255, 255, 255, 55);
                color: #ffffff;
            }
            #modeCardBtn:checked {
                background-color: rgba(76, 139, 245, 44);
                border: 1.5px solid #5c96f7;
                color: #ffffff;
            }
            #subFieldLabel {
                color: #9ba6ba;
                font-size: 12px;
            }
            #seedInput {
                background-color: rgba(13, 15, 23, 220);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 24);
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 12px;
            }
            #seedInput:focus {
                border-color: #5c96f7;
            }
            #pathLabel {
                color: #8b97ad;
                font-size: 11px;
            }
            #secondaryBtn, #cancelBtn {
                background-color: rgba(42, 47, 64, 220);
                color: #dce3ee;
                border: 1px solid rgba(255, 255, 255, 24);
                border-radius: 7px;
                padding: 5px 14px;
                font-size: 12px;
                font-weight: 500;
            }
            #secondaryBtn:hover, #cancelBtn:hover {
                background-color: rgba(58, 64, 86, 235);
                color: #ffffff;
            }
            #generateBtn {
                background-color: #3a78e0;
                color: #ffffff;
                border: 1px solid rgba(130, 180, 255, 80);
                border-radius: 8px;
                font-size: 13px;
                font-weight: 700;
                padding: 6px 18px;
            }
            #generateBtn:hover {
                background-color: #4d89ee;
            }
            #generateBtn:pressed {
                background-color: #2f66c4;
            }
            #generateBtn:disabled {
                background-color: #253859;
                color: #8296b8;
                border-color: transparent;
            }
            """
        )
