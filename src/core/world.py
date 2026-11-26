"""Modèle de données de la carte du monde (WorldMap).

Stocke la grille 2D sous forme de tableau NumPy *uint8* ainsi que la
carte d'élévation associée pour le rendu en relief.
Fournit les pinceaux d'édition, l'historique d'annulation et la
sauvegarde / chargement *.npz*.

Aucune dépendance à PySide6.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.tiles import (
    TILE_DEFAULT_ELEVATION,
    TileType,
    derive_elevation_from_grid,
)
from core.world_generator import generate_archipelago

# Nombre maximal d'entrées dans la pile d'annulation
MAX_UNDO_HISTORY = 50


class WorldMap:
    """Carte 2D carrée composée de tuiles."""

    def __init__(self, size: int) -> None:
        self.size = size
        self.grid = np.full((size, size), TileType.DEEP_OCEAN, dtype=np.uint8)
        self.elevation = np.full(
            (size, size),
            TILE_DEFAULT_ELEVATION[TileType.DEEP_OCEAN],
            dtype=np.float32,
        )
        self._undo_stack: list[dict[tuple[int, int], tuple[int, float]]] = []
        self._current_stroke: dict[tuple[int, int], tuple[int, float]] | None = None

    # ── Constructeurs alternatifs ─────────────────────────────────────

    @classmethod
    def blank(cls, size: int) -> WorldMap:
        """Carte vierge entièrement remplie d'Océan profond."""
        return cls(size)

    @classmethod
    def archipelago(cls, size: int, seed: int | None = None) -> WorldMap:
        """Carte avec un archipel réaliste généré procéduralement."""
        world = cls(size)
        world.grid, world.elevation = generate_archipelago(size, seed=seed)
        return world

    @classmethod
    def from_file(cls, path: str | Path) -> WorldMap:
        """Charge une carte depuis un fichier *.npz*."""
        data = np.load(str(path))
        grid = data["grid"].astype(np.uint8)
        world = cls(grid.shape[0])
        world.grid = grid
        if "elevation" in data:
            world.elevation = data["elevation"].astype(np.float32)
        else:
            world.elevation = derive_elevation_from_grid(grid)
        return world

    # ── Sauvegarde ────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Sauvegarde la carte et son élévation dans un fichier *.npz* compressé."""
        np.savez_compressed(str(path), grid=self.grid, elevation=self.elevation)

    # ── État de l'historique ──────────────────────────────────────────

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    # ── Pinceau & édition ─────────────────────────────────────────────

    def begin_stroke(self) -> None:
        """Démarre un nouveau coup de pinceau (regroupe l'annulation)."""
        self._current_stroke = {}

    def apply_brush(
        self,
        cx: int,
        cy: int,
        radius: int,
        tile_type: int,
        shape: str = "circle",
    ) -> list[tuple[int, int]]:
        """Applique le pinceau et retourne les positions *(x, y)* modifiées.

        Seules les tuiles situées à l'intérieur de la carte jouable et
        dont la valeur diffère de *tile_type* sont modifiées.
        """
        y_min = max(0, cy - radius)
        y_max = min(self.size, cy + radius + 1)
        x_min = max(0, cx - radius)
        x_max = min(self.size, cx + radius + 1)

        if y_min >= y_max or x_min >= x_max:
            return []

        ys, xs = np.mgrid[y_min:y_max, x_min:x_max]

        if shape == "circle":
            dist_sq = (xs - cx) ** 2 + (ys - cy) ** 2
            in_brush = dist_sq <= radius * radius
        else:  # square
            in_brush = np.ones(xs.shape, dtype=bool)

        cand_y = ys[in_brush]
        cand_x = xs[in_brush]

        old_vals = self.grid[cand_y, cand_x]
        diff = old_vals != tile_type
        changed_y = cand_y[diff]
        changed_x = cand_x[diff]
        old_changed = old_vals[diff]

        if len(changed_y) == 0:
            return []

        old_elevs = self.elevation[changed_y, changed_x]

        if self._current_stroke is not None:
            for i in range(len(changed_y)):
                pos = (int(changed_x[i]), int(changed_y[i]))
                if pos not in self._current_stroke:
                    self._current_stroke[pos] = (
                        int(old_changed[i]),
                        float(old_elevs[i]),
                    )

        target_elev = TILE_DEFAULT_ELEVATION[TileType(tile_type)]
        self.grid[changed_y, changed_x] = tile_type
        self.elevation[changed_y, changed_x] = target_elev
        return list(zip(changed_x.tolist(), changed_y.tolist()))

    def end_stroke(self) -> None:
        """Termine le coup de pinceau et empile l'annulation."""
        if self._current_stroke:
            self._undo_stack.append(self._current_stroke)
            if len(self._undo_stack) > MAX_UNDO_HISTORY:
                self._undo_stack.pop(0)
        self._current_stroke = None

    def undo(self) -> list[tuple[int, int]] | None:
        """Annule le dernier coup de pinceau.

        Retourne la liste des coordonnées restaurées ou *None* si la pile est vide.
        """
        if not self._undo_stack:
            return None
        stroke = self._undo_stack.pop()
        restored: list[tuple[int, int]] = []
        for (tx, ty), (old_val, old_elev) in stroke.items():
            self.grid[ty, tx] = old_val
            self.elevation[ty, tx] = old_elev
            restored.append((tx, ty))
        return restored
