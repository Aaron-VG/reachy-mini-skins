"""Generate the castanyera headscarf ("mocador") of the Castanyada skin.

The scarf covers the top, sides and back of the head, frames the face and is
knotted under the chin, like the traditional castanyera selling chestnuts.
It is printed in two halves split around z = 21.5 mm, the same split as the
Christmas tree head cover. The halves overlap like two layers of fabric (the
outer layer of the back half laps over the front half), so the seam stays
discreet, and they are held on the head with thin double-sided tape.

The fit is taken from the inner surface of the Christmas tree head cover
(measured by ray casting from the middle of the head). The eye openings and
the antenna openings stay free.

Run from the repository root (takes about 5 minutes):
    python castanyada/tools/make_head.py

Needs: numpy, scipy, scikit-image, trimesh, manifold3d, pillow.
"""
import os
import sys

import numpy as np
import trimesh
from scipy import ndimage
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(__file__))
from sdf_common import decimate, grid_axes, mesh_from_volume, smoothstep, to_mf

OUT = "castanyada/stl"
TREE_TOP = "Christmas_Tree_Skin/Christmas Tree Skin - Tree_top_{}.stl"

CENTER = np.array([0.0, 0.0, -6.0])   # rays are cast from here
HEAD_BOTTOM = -47.5
RES = 0.4

SPLIT_Z = 21.5
CLEARANCE = 0.35                      # gap between scarf and head (mm)
THICK = 2.4                           # fabric thickness (mm)
HEM_Y = -45.0                         # lower edge of the scarf
FACE = dict(half_w=63.0, half_h=28.5, cy=1.5, n=4.0)   # face opening (eyes: x -54.5..49, y -21.5..22)
ANTENNA_HOLES = [(-53.0, 19.3, -36.1), (53.0, 19.3, -36.1)]
ANTENNA_OPEN_R = 16.0                 # keep the antenna mount free around each hole
ANTENNA_THIN_R = 30.0                 # thinner, smooth fabric around the antennas

LAP = 8.0                             # overlap of the two halves at the seam (mm)
LAP_LAYER = 1.2                       # thickness of each layer in the overlap (mm)
JOINT_GAP = 0.15                      # clearance between the halves, on each side (mm)

KNOT_C = (0.0, -34.0)                 # (x, y) of the chin knot on the front face


# --- head shape -------------------------------------------------------------

def head_radius_map(n_theta=181, n_phi=360):
    """Distance from CENTER to the inner surface of the tree head cover, per direction."""
    tree = to_mf(trimesh.load(TREE_TOP.format("front"))) + to_mf(trimesh.load(TREE_TOP.format("back")))
    th = np.linspace(0, np.pi, n_theta)
    ph = np.linspace(-np.pi, np.pi, n_phi, endpoint=False)
    r = np.full((n_theta, n_phi), np.nan)
    for i, a in enumerate(th):
        for j, b in enumerate(ph):
            d = np.array([np.sin(a) * np.cos(b), np.cos(a), np.sin(a) * np.sin(b)])
            if d[1] < -0.5:
                continue                      # straight through the open bottom
            hits = tree.ray_cast(CENTER.tolist(), (CENTER + 200 * d).tolist())
            if hits:
                r[i, j] = hits[0].distance * 200
    TH, PH = np.meshgrid(th, ph, indexing="ij")
    dy = np.cos(TH)
    # fill the eye/antenna holes and the open bottom by diffusion from their borders,
    # then close the bottom with the plane of the head's underside
    hole = np.isnan(r)
    r[hole] = np.nanmean(r)
    for _ in range(3000):
        avg = (np.roll(r, 1, 1) + np.roll(r, -1, 1) + np.vstack([r[:1], r[:-1]]) + np.vstack([r[1:], r[-1:]])) / 4
        r[hole] = avg[hole]
    plane = np.where(dy < -1e-6, (HEAD_BOTTOM - CENTER[1]) / np.minimum(dy, -1e-6), np.inf)
    r = np.minimum(r, plane)
    return th, ph, r


def head_signed_distance(axes, th, ph, rmap):
    xs, ys, zs = axes
    res = xs[1] - xs[0]
    occ = np.zeros((len(xs), len(ys), len(zs)), bool)
    Y, Z = np.meshgrid(ys - CENTER[1], zs - CENTER[2], indexing="ij")
    for i, x in enumerate(xs):
        X = x - CENTER[0]
        rho = np.sqrt(X * X + Y * Y + Z * Z)
        t = np.arccos(np.clip(Y / np.maximum(rho, 1e-9), -1, 1))
        p = np.arctan2(Z, X)
        ti = t / np.pi * (len(th) - 1)
        pj = (p + np.pi) / (2 * np.pi) * len(ph)
        rin = ndimage.map_coordinates(np.vstack([rmap, rmap[-1:]]), [ti, pj], order=1, mode="grid-wrap")
        occ[i] = rho < rin
    occ &= (ys[None, :, None] > HEAD_BOTTOM)
    d_out = ndimage.distance_transform_edt(~occ).astype(np.float32)
    d_in = ndimage.distance_transform_edt(occ).astype(np.float32)
    return (d_out - d_in) * res, occ


# --- the scarf --------------------------------------------------------------

def flower_relief(P):
    """Small five-petal flowers printed in relief (to paint a "mocador de flors")."""
    n = 220
    k = np.arange(n) + 0.5
    uy = 1 - 2 * k / n
    phi = k * np.pi * (3 - np.sqrt(5))
    rho = np.sqrt(1 - uy ** 2)
    dirs = np.c_[rho * np.cos(phi), uy, rho * np.sin(phi)]
    centers = CENTER + dirs * 70.0
    tree = cKDTree(dirs)
    u = (P - CENTER) / np.linalg.norm(P - CENTER, axis=1, keepdims=True)
    _, idx = tree.query(u)
    dvec = u - dirs[idx]
    # local tangent frame around each flower direction
    up = np.where(np.abs(dirs[idx, 1:2]) > 0.9, [[1.0, 0, 0]], [[0, 1.0, 0]])
    e1 = np.cross(up, dirs[idx]); e1 /= np.linalg.norm(e1, axis=1, keepdims=True)
    e2 = np.cross(dirs[idx], e1)
    rr = np.linalg.norm(P - CENTER, axis=1)
    a, b = np.einsum("ij,ij->i", dvec, e1) * rr, np.einsum("ij,ij->i", dvec, e2) * rr
    rad = np.hypot(a, b)
    ang = np.arctan2(b, a) + idx * 0.7
    petal = 3.6 * (0.45 + 0.55 * np.abs(np.cos(2.5 * ang)) ** 0.7)
    flower = np.clip((petal - rad) / 0.5, 0, 1) * 0.6
    heart = np.clip((1.1 - rad) / 0.4, 0, 1) * 0.35
    return np.maximum(flower, heart)


def knot_field(X, Y, Z, z_face):
    kx, ky = KNOT_C
    zc = z_face + CLEARANCE + THICK + 2.5
    knot = np.sqrt(((X - kx) / 8.5) ** 2 + ((Y - ky) / 6.5) ** 2 + ((Z - zc) / 5.0) ** 2) - 1
    F = knot * 5.0
    for s in (-1, 1):
        # two short tails hanging from the knot, kept above the head's lower edge
        ax, ay, bx, by = kx + s * 3.0, ky - 3.0, kx + s * 13.0, HEM_Y + 2.5
        vx, vy = bx - ax, by - ay
        t = np.clip(((X - ax) * vx + (Y - ay) * vy) / (vx * vx + vy * vy), 0, 1)
        d = np.hypot(X - ax - t * vx, Y - ay - t * vy)
        w = 4.2 - 1.2 * t
        tail = np.maximum(d - w, np.abs(Z - (z_face + CLEARANCE + THICK + 0.6)) - 1.6)
        F = np.minimum(F, tail)
    return F


def main():
    os.makedirs(OUT, exist_ok=True)
    print("measuring the head (ray casting, ~2 min) ...")
    th, ph, rmap = head_radius_map()
    axes = grid_axes([-92, HEAD_BOTTOM - 3, -74], [92, 66, 66], RES)
    xs, ys, zs = axes
    print("head distance field ...")
    dH, occ = head_signed_distance(axes, th, ph, rmap)

    # front face height along the chin, for the knot
    kx_i = np.argmin(np.abs(xs - KNOT_C[0]))
    ky_i = np.argmin(np.abs(ys - KNOT_C[1]))
    z_face = zs[np.nonzero(occ[kx_i, ky_i])[0].max()]

    shape = (len(xs), len(ys), len(zs))
    F = np.empty(shape, np.float32)
    back_side = np.empty(shape, np.float32)       # negative in the back half
    Yg, Zg = np.meshgrid(ys, zs, indexing="ij")
    print("scarf field ...")
    for i, x in enumerate(xs):
        X = np.full_like(Yg, x)
        Y, Z = Yg, Zg
        d = dH[i]
        P = np.stack([X, Y, Z], -1).reshape(-1, 3)

        # where the scarf is (positive inside the covered area)
        e_bot = Y - HEM_Y
        g = ((np.abs(X) / FACE["half_w"]) ** FACE["n"] + (np.abs(Y - FACE["cy"]) / FACE["half_h"]) ** FACE["n"]) ** (1 / FACE["n"])
        e_face = np.where(Z > 15, (g - 1) * FACE["half_h"], 1e3)
        d_ant = np.min([np.sqrt((X - a) ** 2 + (Y - b) ** 2 + (Z - c) ** 2) for a, b, c in ANTENNA_HOLES], axis=0)
        e = np.minimum(np.minimum(e_bot, e_face), d_ant - ANTENNA_OPEN_R)

        # fabric: soft folds converging on the knot, flowers, rolled hems
        calm = smoothstep(ANTENNA_OPEN_R, ANTENNA_THIN_R, d_ant)
        ang = np.arctan2(Y - KNOT_C[1], X - KNOT_C[0])
        folds = 0.45 * np.sin(ang * 11 + 0.08 * Z) * smoothstep(-50, 10, -np.hypot(X, Y - KNOT_C[1]) + 10) \
            + 0.3 * np.sin(0.21 * X + 0.17 * Z) * np.sin(0.19 * Y + 0.13 * X)
        flowers = flower_relief(P).reshape(Y.shape)
        hem = 1.1 * np.exp(-(np.maximum(e, 0) / 1.6) ** 2)
        T = (THICK - 0.8 * (1 - calm)) + calm * (folds + flowers) + hem
        shell = np.maximum(CLEARANCE - d, d - (CLEARANCE + T))
        shell = np.maximum(shell, -e)

        knot = np.maximum(knot_field(X, Y, Z, z_face), CLEARANCE - d)
        F[i] = np.minimum(shell, knot)

        # lap joint: the inner layer splits at SPLIT_Z, the outer layer LAP further forward
        mid = CLEARANCE + LAP_LAYER
        back_side[i] = np.minimum(Z - SPLIT_Z, np.maximum(Z - (SPLIT_Z + LAP), mid - d))

    for name, side in (("Headscarf_front", -back_side), ("Headscarf_back", back_side)):
        m = mesh_from_volume(np.maximum(F, side + JOINT_GAP), axes)
        m = max(m.split(only_watertight=False), key=lambda p: abs(p.volume))
        for tol in (0.05, 0.03, 0.015):            # coarsest simplification that stays watertight
            small = decimate(m, tol)
            small.export(f"{OUT}/{name}.stl")
            if trimesh.load(f"{OUT}/{name}.stl").is_watertight:
                break
        m = small
        print(name, "faces", len(m.faces), "watertight", m.is_watertight,
              "volume cm3", round(m.volume / 1000, 1), "bounds", m.bounds.round(1).tolist())
        m.export(f"{OUT}/{name}.stl")


if __name__ == "__main__":
    main()
