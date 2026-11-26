"""Générateur procédural d'archipels réalistes en NumPy pur.

Produit des archipels de 1 à 8 îles de tailles hétérogènes aux côtes
organiques, avec plateau continental irrégulier, progression cohérente
des biomes et fondu naturel vers l'océan profond en bordure de carte.

Aucune dépendance à PySide6.
"""

from __future__ import annotations

import math

import numpy as np

from core.tiles import TileType


def _sample_value_noise(
    x: np.ndarray,
    y: np.ndarray,
    perm: np.ndarray,
) -> np.ndarray:
    """Bruit de valeur 2D à interpolation quintique d'Hermite (6t^5 - 15t^4 + 10t^3)."""
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    fx = x - x0
    fy = y - y0

    wx = fx * fx * fx * (fx * (fx * 6.0 - 15.0) + 10.0)
    wy = fy * fy * fy * (fy * (fy * 6.0 - 15.0) + 10.0)

    rx0 = x0 & 255
    rx1 = (x0 + 1) & 255
    ry0 = y0 & 255
    ry1 = (y0 + 1) & 255

    v00 = perm[ry0, rx0]
    v10 = perm[ry0, rx1]
    v01 = perm[ry1, rx0]
    v11 = perm[ry1, rx1]

    v0 = v00 + wx * (v10 - v00)
    v1 = v01 + wx * (v11 - v01)
    return v0 + wy * (v1 - v0)


def _fbm(
    x: np.ndarray,
    y: np.ndarray,
    perm: np.ndarray,
    base_freq: float,
    octaves: int = 4,
    persistence: float = 0.48,
    lacunarity: float = 2.05,
) -> np.ndarray:
    """Bruit fractal multi-octaves (Fractional Brownian Motion) normalisé dans [0, 1]."""
    total = np.zeros_like(x, dtype=np.float32)
    freq = base_freq
    amp = 1.0
    max_amp = 0.0

    for _ in range(octaves):
        total += amp * _sample_value_noise(x * freq, y * freq, perm)
        max_amp += amp
        amp *= persistence
        freq *= lacunarity

    return total / max_amp


def _choose_island_specs(
    size: int,
    rng: np.random.Generator,
) -> list[tuple[float, float, float, float, float, float]]:
    """Tire entre 1 et 8 îles aux tailles et élévations hétérogènes.

    Retourne une liste de tuples ``(cx, cy, radius, aspect, angle, peak_height)``.
    """
    n_islands = int(rng.integers(1, 9))  # 1 à 8 îles incluses

    # Tailles hétérogènes : au moins une grande île principale, puis tailles variées
    radii: list[float] = [float(rng.uniform(0.22, 0.30)) * size]
    for _ in range(n_islands - 1):
        # Mélange de petits îlots et d'îles moyennes / grandes
        tier = float(rng.random())
        if tier < 0.42:
            r_frac = float(rng.uniform(0.055, 0.095))
        elif tier < 0.80:
            r_frac = float(rng.uniform(0.11, 0.175))
        else:
            r_frac = float(rng.uniform(0.18, 0.24))
        radii.append(r_frac * size)

    radii.sort(reverse=True)

    specs: list[tuple[float, float, float, float, float, float]] = []
    placed: list[tuple[float, float, float]] = []

    for idx, radius in enumerate(radii):
        # Marge de sécurité pour que les côtes ne touchent jamais la bordure
        margin = min(size * 0.42, max(radius * 1.10 + size * 0.05, size * 0.13))
        best_cx = size * 0.5
        best_cy = size * 0.5
        best_score = -1.0

        for _ in range(36):
            cx = float(rng.uniform(margin, size - margin))
            cy = float(rng.uniform(margin, size - margin))
            if not placed:
                best_cx, best_cy = cx, cy
                break
            min_ratio = min(
                math.hypot(cx - px, cy - py) / (radius + pr)
                for px, py, pr in placed
            )
            if min_ratio > best_score:
                best_score = min_ratio
                best_cx, best_cy = cx, cy
            # Suffisamment espacé pour former un bel archipel distinct
            if min_ratio > 0.78:
                break

        placed.append((best_cx, best_cy, radius))

        aspect = float(rng.uniform(0.58, 0.96))
        angle = float(rng.uniform(0.0, math.pi))

        # Seules les grandes îles principales culminent assez haut pour des montagnes
        if idx == 0 or radius >= size * 0.175:
            peak = float(rng.uniform(0.88, 1.00))
        elif radius >= size * 0.11:
            peak = float(rng.uniform(0.64, 0.74))
        else:
            peak = float(rng.uniform(0.46, 0.57))

        specs.append((best_cx, best_cy, radius, aspect, angle, peak))

    return specs


def generate_archipelago(
    size: int,
    seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Génère un archipel complet et retourne ``(grid_uint8, elevation_float32)``.

    Parameters
    ----------
    size : int
        Dimension carrée de la carte (ex. 256, 512, 1024, 2048).
    seed : int | None
        Graine aléatoire optionnelle pour reproductibilité.
    """
    rng = np.random.default_rng(seed)

    # Tables de permutation indépendantes
    p_fbm = rng.random((256, 256), dtype=np.float32)
    p_warp_x = rng.random((256, 256), dtype=np.float32)
    p_warp_y = rng.random((256, 256), dtype=np.float32)
    p_shelf = rng.random((256, 256), dtype=np.float32)
    p_edge = rng.random((256, 256), dtype=np.float32)

    y, x = np.mgrid[0:size, 0:size].astype(np.float32)

    # 1. Domain Warping organique pour des côtes découpées et naturelles
    macro_s = 2.6 / size
    macro_amp = size * 0.135

    wx = x + (_sample_value_noise(x * macro_s, y * macro_s, p_warp_x) - 0.5) * macro_amp
    wy = y + (_sample_value_noise(x * macro_s + 13.7, y * macro_s + 6.2, p_warp_y) - 0.5) * macro_amp

    # 2. Champ d'archipel : 1 à 8 îles anisotropes déformées par harmoniques angulaires
    island_specs = _choose_island_specs(size, rng)
    island_field = np.zeros((size, size), dtype=np.float32)
    warp_pad = int(math.ceil(macro_amp * 0.65)) + 8

    for cx, cy, radius, aspect, angle, peak in island_specs:
        # Fenêtre locale englobante pour éviter des calculs inutiles sur les grandes cartes
        reach = int(math.ceil(radius * 1.45)) + warp_pad
        x0 = max(0, int(cx) - reach)
        x1 = min(size, int(cx) + reach + 1)
        y0 = max(0, int(cy) - reach)
        y1 = min(size, int(cy) + reach + 1)
        if x0 >= x1 or y0 >= y1:
            continue

        ct = math.cos(angle)
        st = math.sin(angle)
        dx = wx[y0:y1, x0:x1] - cx
        dy = wy[y0:y1, x0:x1] - cy

        rx = (dx * ct + dy * st) / radius
        ry = (-dx * st + dy * ct) / (radius * aspect)

        dist = np.sqrt(rx * rx + ry * ry)

        # Perturbation angulaire (péninsules/golfes supplémentaires)
        phi = np.arctan2(ry, rx)
        a2 = float(rng.uniform(0.0, 2.0 * math.pi))
        a3 = float(rng.uniform(0.0, 2.0 * math.pi))
        lobe = 1.0 + 0.16 * np.cos(2.0 * phi + a2) + 0.10 * np.cos(3.0 * phi + a3)
        dist = dist / lobe

        # Profil en dôme large : terres généreuses avec transition douce vers la côte
        falloff = np.clip(1.0 - np.power(np.clip(dist, 0.0, 1.0), 1.55), 0.0, 1.0)
        falloff = falloff * falloff * (3.0 - 2.0 * falloff)

        sub = island_field[y0:y1, x0:x1]
        np.maximum(sub, falloff * peak, out=sub)

    # 3. Modulation par bruit multi-octaves FBM (reliefs intérieurs & découpage côtier)
    fbm_detail = _fbm(wx, wy, p_fbm, base_freq=4.8 / size, octaves=4, persistence=0.48)
    elevation = island_field * (0.68 + 0.56 * fbm_detail)

    # 4. Garde de bordure douce & bruitée (transition 100 % invisible avec l'océan infini)
    edge_dist = np.minimum(
        np.minimum(x, size - 1 - x),
        np.minimum(y, size - 1 - y),
    )
    edge_noise = (_sample_value_noise(x * (3.2 / size), y * (3.2 / size), p_edge) - 0.5) * (size * 0.04)
    edge_fade = np.clip((edge_dist - size * 0.02 + edge_noise) / (size * 0.085), 0.0, 1.0)
    edge_fade = edge_fade * edge_fade * (3.0 - 2.0 * edge_fade)
    elevation *= edge_fade

    # 5. Lissage spatial séparable (2 passes) pour des transitions continues et propres
    for _ in range(2):
        hs = elevation.copy()
        hs[1:-1, :] = 0.25 * elevation[:-2, :] + 0.5 * elevation[1:-1, :] + 0.25 * elevation[2:, :]
        elevation[:, 1:-1] = 0.25 * hs[:, :-2] + 0.5 * hs[:, 1:-1] + 0.25 * hs[:, 2:]

    # Calibrage doux sans forcer les petites îles à atteindre le niveau montagne
    e_max = float(elevation.max())
    if e_max > 0.05:
        target_max = max(spec[5] for spec in island_specs)
        elevation = np.clip(elevation * (target_max / e_max), 0.0, 1.0)

    # 6. Plateau continental asymétrique : l'océan peu profond suit uniquement les îles
    shelf_noise = _fbm(x, y, p_shelf, base_freq=2.6 / size, octaves=2, persistence=0.5)
    t_beach = 0.34
    shelf_width = 0.055 + 0.14 * shelf_noise
    t_shallow = t_beach - shelf_width

    # 7. Seuillage des biomes (Océan profond -> Peu profond -> Plage -> Plaine -> Forêt -> Montagne)
    grid = np.full((size, size), TileType.DEEP_OCEAN, dtype=np.uint8)
    grid[elevation >= t_shallow] = TileType.SHALLOW_OCEAN
    grid[elevation >= t_beach] = TileType.BEACH
    grid[elevation >= 0.41] = TileType.PLAINS
    grid[elevation >= 0.56] = TileType.FOREST
    grid[elevation >= 0.77] = TileType.MOUNTAIN

    # 8. Filtrage morphologique des micro-artefacts
    # Suppression des micro-îlots isolés de 1-2 tuiles en mer
    for _ in range(2):
        is_land = (grid >= TileType.BEACH).astype(np.int8)
        nbr = np.zeros_like(is_land, dtype=np.int8)
        nbr[1:-1, 1:-1] = (
            is_land[:-2, :-2] + is_land[:-2, 1:-1] + is_land[:-2, 2:]
            + is_land[1:-1, :-2] + is_land[1:-1, 2:]
            + is_land[2:, :-2] + is_land[2:, 1:-1] + is_land[2:, 2:]
        )
        isolated = (is_land == 1) & (nbr <= 2)
        grid[isolated] = TileType.SHALLOW_OCEAN

    # Suppression des pixels isolés de montagne
    is_mnt = (grid == TileType.MOUNTAIN).astype(np.int8)
    if np.any(is_mnt):
        nbr_m = np.zeros_like(is_mnt, dtype=np.int8)
        nbr_m[1:-1, 1:-1] = (
            is_mnt[:-2, :-2] + is_mnt[:-2, 1:-1] + is_mnt[:-2, 2:]
            + is_mnt[1:-1, :-2] + is_mnt[1:-1, 2:]
            + is_mnt[2:, :-2] + is_mnt[2:, 1:-1] + is_mnt[2:, 2:]
        )
        grid[(is_mnt == 1) & (nbr_m <= 1)] = TileType.FOREST

    return grid, elevation
