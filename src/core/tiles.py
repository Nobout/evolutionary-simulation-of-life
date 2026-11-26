"""Définition des types de tuiles, élévations nominales et rendu couleur enrichi."""

from __future__ import annotations

from enum import IntEnum

import numpy as np


class TileType(IntEnum):
    """Types de tuiles disponibles dans la simulation."""

    DEEP_OCEAN = 0
    SHALLOW_OCEAN = 1
    BEACH = 2
    PLAINS = 3
    FOREST = 4
    MOUNTAIN = 5


# Étiquettes d'affichage (interface utilisateur)
TILE_LABELS: dict[TileType, str] = {
    TileType.DEEP_OCEAN: "Océan profond",
    TileType.SHALLOW_OCEAN: "Océan peu profond",
    TileType.BEACH: "Plage",
    TileType.PLAINS: "Plaine",
    TileType.FOREST: "Forêt",
    TileType.MOUNTAIN: "Montagne",
}

# Couleurs de base (R, G, B) par type de tuile
TILE_BASE_COLORS: dict[TileType, tuple[int, int, int]] = {
    TileType.DEEP_OCEAN: (15, 42, 108),
    TileType.SHALLOW_OCEAN: (34, 138, 178),
    TileType.BEACH: (216, 194, 120),
    TileType.PLAINS: (158, 128, 78),
    TileType.FOREST: (92, 70, 42),
    TileType.MOUNTAIN: (88, 90, 98),
}

# Élévation nominale utilisée lors de l'édition manuelle (pinceau / carte vierge)
TILE_DEFAULT_ELEVATION: dict[TileType, float] = {
    TileType.DEEP_OCEAN: 0.08,
    TileType.SHALLOW_OCEAN: 0.28,
    TileType.BEACH: 0.39,
    TileType.PLAINS: 0.50,
    TileType.FOREST: 0.66,
    TileType.MOUNTAIN: 0.88,
}

# Intensité de la micro-variation déterministe par type
TILE_VARIATION_STRENGTH: dict[TileType, float] = {
    TileType.DEEP_OCEAN: 7.0,
    TileType.SHALLOW_OCEAN: 9.0,
    TileType.BEACH: 12.0,
    TileType.PLAINS: 11.0,
    TileType.FOREST: 10.0,
    TileType.MOUNTAIN: 12.0,
}

# Intensité du relief (hillshading) par type
_HILLSHADE_WEIGHT: dict[TileType, float] = {
    TileType.DEEP_OCEAN: 0.0,
    TileType.SHALLOW_OCEAN: 0.0,
    TileType.BEACH: 12.0,
    TileType.PLAINS: 24.0,
    TileType.FOREST: 30.0,
    TileType.MOUNTAIN: 52.0,
}


def compute_tile_variation(h: int, w: int) -> np.ndarray:
    """Pré-calcule un tableau de variation organique float32 dans ``[-1, 1]``.

    Combine un micro-bruit déterministe par coordonnée et une légère ondulation
    spatiale à plus grande échelle pour éviter l'aspect « grain TV ».
    """
    y, x = np.mgrid[0:h, 0:w]
    seed = x.astype(np.int64) * 374761393 + y.astype(np.int64) * 668265263
    seed = (seed ^ (seed >> 16)) & 0xFFFF
    micro = seed.astype(np.float32) / 32768.0 - 1.0

    # Ondulation organique douce (fréquences incommensurables)
    xf = x.astype(np.float32)
    yf = y.astype(np.float32)
    macro = (
        np.sin(xf * 0.071 + yf * 0.043) * 0.5
        + np.cos(xf * 0.037 - yf * 0.089) * 0.5
    ).astype(np.float32)

    return micro * 0.62 + macro * 0.38


def compute_hillshade(elevation: np.ndarray) -> np.ndarray:
    """Calcule un ombrage directionnel léger (lumière Nord-Ouest) dans ``[-1, 1]``."""
    h, w = elevation.shape
    dx = np.zeros((h, w), dtype=np.float32)
    dy = np.zeros((h, w), dtype=np.float32)
    if w > 1:
        dx[:, 1:] = elevation[:, 1:] - elevation[:, :-1]
    if h > 1:
        dy[1:, :] = elevation[1:, :] - elevation[:-1, :]

    # Lumière venant du Nord-Ouest : pente vers le Sud-Est = plus sombre
    shade = -(dx + dy) * 32.0
    return np.clip(shade, -1.0, 1.0)


def derive_elevation_from_grid(grid: np.ndarray) -> np.ndarray:
    """Reconstruit une carte d'élévation lissée à partir d'une grille de tuiles."""
    elev = np.zeros(grid.shape, dtype=np.float32)
    for tile_type, val in TILE_DEFAULT_ELEVATION.items():
        elev[grid == tile_type] = val
    # Lissage léger (2 passes) pour adoucir les marches lors d'un rechargement ancien format
    for _ in range(2):
        tmp = elev.copy()
        tmp[1:-1, :] = 0.25 * elev[:-2, :] + 0.5 * elev[1:-1, :] + 0.25 * elev[2:, :]
        elev[:, 1:-1] = 0.25 * tmp[:, :-2] + 0.5 * tmp[:, 1:-1] + 0.25 * tmp[:, 2:]
    return elev


def generate_color_map(
    grid: np.ndarray,
    variation: np.ndarray | None = None,
    elevation: np.ndarray | None = None,
) -> np.ndarray:
    """Génère un buffer RGBA *uint8* ``(h, w, 4)`` avec variation organique et relief."""
    h, w = grid.shape
    if variation is None:
        variation = compute_tile_variation(h, w)

    colors = np.zeros((h, w, 4), dtype=np.uint8)
    colors[:, :, 3] = 255

    # Calcul du relief si une carte d'altitude est disponible
    shade = compute_hillshade(elevation) if elevation is not None else None

    for tile_type in TileType:
        mask = grid == tile_type
        if not np.any(mask):
            continue

        r_base, g_base, b_base = TILE_BASE_COLORS[tile_type]
        delta = variation[mask] * TILE_VARIATION_STRENGTH[tile_type]

        if elevation is not None:
            e_vals = elevation[mask]
            # Dégradés subtils selon la profondeur / altitude
            if tile_type == TileType.DEEP_OCEAN:
                # Plus sombre vers les abysses, légèrement plus clair près du plateau
                depth_t = np.clip(e_vals / 0.28, 0.0, 1.0)
                r = (11.0 + depth_t * 11.0) + delta * 0.7
                g = (30.0 + depth_t * 24.0) + delta * 0.8
                b = (86.0 + depth_t * 42.0) + delta
            elif tile_type == TileType.SHALLOW_OCEAN:
                # Plus clair et turquoise tout près du rivage
                shallow_t = np.clip((e_vals - 0.16) / 0.22, 0.0, 1.0)
                r = (26.0 + shallow_t * 24.0) + delta * 0.8
                g = (116.0 + shallow_t * 44.0) + delta
                b = (162.0 + shallow_t * 32.0) + delta
            elif tile_type == TileType.MOUNTAIN:
                # Sommets les plus élevés légèrement plus clairs (roche alpine)
                peak_t = np.clip((e_vals - 0.76) / 0.24, 0.0, 1.0)
                hill = shade[mask] * _HILLSHADE_WEIGHT[tile_type]
                r = r_base + peak_t * 36.0 + delta + hill
                g = g_base + peak_t * 37.0 + delta + hill
                b = b_base + peak_t * 40.0 + delta + hill
            else:
                hill = shade[mask] * _HILLSHADE_WEIGHT[tile_type]
                r = r_base + delta + hill
                g = g_base + delta + hill
                b = b_base + delta + hill
        else:
            r = r_base + delta
            g = g_base + delta
            b = b_base + delta

        colors[mask, 0] = np.clip(r, 0, 255).astype(np.uint8)
        colors[mask, 1] = np.clip(g, 0, 255).astype(np.uint8)
        colors[mask, 2] = np.clip(b, 0, 255).astype(np.uint8)

    return colors


def render_region_colors(
    grid: np.ndarray,
    variation: np.ndarray,
    elevation: np.ndarray,
    y_min: int,
    y_max: int,
    x_min: int,
    x_max: int,
) -> np.ndarray:
    """Rend uniquement une sous-région ``[y_min:y_max, x_min:x_max]`` en RGBA *uint8*."""
    h, w = grid.shape
    pad_y0 = max(0, y_min - 1)
    pad_y1 = min(h, y_max + 1)
    pad_x0 = max(0, x_min - 1)
    pad_x1 = min(w, x_max + 1)

    sub_colors = generate_color_map(
        grid[pad_y0:pad_y1, pad_x0:pad_x1],
        variation[pad_y0:pad_y1, pad_x0:pad_x1],
        elevation[pad_y0:pad_y1, pad_x0:pad_x1],
    )
    oy0 = y_min - pad_y0
    ox0 = x_min - pad_x0
    return sub_colors[oy0 : oy0 + (y_max - y_min), ox0 : ox0 + (x_max - x_min)]
