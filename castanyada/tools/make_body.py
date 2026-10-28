"""Generate the roasted-chestnut body shell of the Castanyada skin.

The fit to the robot is taken from the official Christmas tree body shell
(same inner cavity, same head/neck clearance, same front/back split plane at
z = 10.9 mm), so the chestnut snaps on exactly like the other body skins.
Around the head it also stays inside the outer envelope of the pumpkin skin,
so it never gets closer to the moving head than that skin does.

Needs: numpy, scipy, scikit-image, trimesh, manifold3d, pillow.

Run from the repository root:
    python castanyada/tools/make_body.py
"""
import os
import sys

import numpy as np
import manifold3d as mf
import trimesh

sys.path.insert(0, os.path.dirname(__file__))
from sdf_common import (box, decimate, grid_axes, mesh_from_volume, sample,
                        signed_distance_of, smoothstep, to_mf)

OUT = "castanyada/stl"
TREE = "Christmas_Tree_Skin/Christmas Tree Skin - Tree_base_{}.stl"
PUMPKIN = "pumpkin/Pumpkin_{}.stl"

Y_BOT, Y_TOP = -213.5, -45.0   # body shell height range (same as the pumpkin)
SPLIT_Z = 10.9                 # front/back split plane
PINS = [(87.0, -196.5), (98.0, -155.0), (88.0, -118.0)]  # 3 x 16 mm pins, mirrored in x
PIN_R, PIN_DEPTH = 1.6, 8.5
RES = 0.5                      # voxel size of the distance field (mm)
CLEARANCE = 0.25               # extra gap to the robot (mm)
ENVELOPE_Y = -70.0             # above this, stay inside the pumpkin skin's outer hull

# Chestnut silhouette: t = 0 at the base, 1 at the top of the shell.
T_KNOTS = [0.0, 0.02, 0.06, 0.12, 0.20, 0.30, 0.45, 0.60, 0.75, 0.87, 0.94, 0.985, 1.005, 1.03]
HALF_X  = [100, 108, 114, 118, 120.5, 121, 118, 108, 92, 72, 58, 40, 24, 1]
FRONT_Z = [95, 102, 107, 110, 112, 112.5, 111, 108, 101, 90, 81, 75, 71, 56]
BACK_Z  = [92, 98, 103, 106, 107, 107.5, 106, 103, 97, 87, 79, 74, 70, 55]
PLAN_N = 2.3                   # superellipse exponent of the horizontal section

# Roasting cross cut ("el tall") on the front.
CUT_Y, CUT_ARM = -140.0, 44.0
HILUM_Y = -197.0               # top of the pale base scar of the chestnut


def chestnut_field(X, Y, Z):
    t = (Y - Y_BOT) / (Y_TOP - Y_BOT)
    a = np.interp(t, T_KNOTS, HALF_X)
    b = np.where(Z > 0, np.interp(t, T_KNOTS, FRONT_Z), np.interp(t, T_KNOTS, BACK_Z))
    ax, az = np.abs(X) / a, np.abs(Z) / b
    r = (ax ** PLAN_N + az ** PLAN_N) ** (1.0 / PLAN_N)
    scale = np.sqrt(a * b)
    F = (r - 1.0) * scale                       # ~ signed distance in mm

    # fine longitudinal striations of the shell, fading out on the base scar
    theta = np.arctan2(Z, X)
    stria = 0.3 * np.sin(theta * 110 + 0.8 * np.sin(theta * 7))
    F -= stria * smoothstep(HILUM_Y - 2, HILUM_Y + 8, Y)

    # pale, rough base scar ("la cicatriu"): bumpy texture + a small paint step
    bumps = 0.5 * (np.sin(X * 0.55) * np.sin(Z * 0.6) + np.sin((X + Z) * 0.37) * np.cos(Y * 0.8))
    F -= bumps * (1 - smoothstep(HILUM_Y - 3, HILUM_Y, Y))
    F += 0.8 * np.exp(-((Y - HILUM_Y) / 0.9) ** 2)

    # roasting cross cut, opened like a freshly roasted chestnut
    u, v = X, Y - CUT_Y
    p, q = (u + v) / np.sqrt(2), (u - v) / np.sqrt(2)
    d1 = np.sqrt(np.maximum(np.abs(p) - CUT_ARM, 0) ** 2 + q ** 2)
    d2 = np.sqrt(np.maximum(np.abs(q) - CUT_ARM, 0) ** 2 + p ** 2)
    d = np.minimum(d1, d2)
    s = np.clip(np.where(d1 < d2, np.abs(p), np.abs(q)) / CUT_ARM, 0, 1)
    w = 2.5 + 13.0 * (1 - s) ** 1.4             # opening half width
    front = smoothstep(30, 60, Z)
    inside = 1 / (1 + np.exp(-(w - d) / 0.7)) * front
    depth = 6.5 * (1 - 0.5 * s)
    flesh = 0.9 * np.sin(u * 0.45 + np.sin(v * 0.3)) * np.sin(v * 0.5) + 0.6 * np.sin((u - v) * 0.8)
    F += inside * (depth - flesh * (1 - s))
    # curled lips of the peeled shell along the cut
    F -= front * 2.6 * (1 - 0.6 * s) * np.exp(-((d - w - 1.2) / 1.8) ** 2)
    return F


def robot_clearance():
    """Inner cavity + head slot + base opening, derived from the tree shell."""
    tree = to_mf(trimesh.load(TREE.format("front"))) + to_mf(trimesh.load(TREE.format("back")))
    cav = sorted((tree.hull() - tree).decompose(), key=lambda m: -m.volume())[0]
    # hull - tree also catches the folds of the tree's outer bevel near the top;
    # keep only what lies within the footprint of the robot body
    widest = cav.rotate([90, 0, 0]).slice(-160.0).hull().offset(1.5, mf.JoinType.Round)
    prism = mf.Manifold.extrude(widest, 300).translate([0, 0, -260]).rotate([-90, 0, 0])
    cav = cav ^ prism

    # head / neck slot: the x = 0 section of the upper cavity, extruded across x
    sec = cav.rotate([0, 90, 0]).slice(0.0)
    slot = mf.Manifold.extrude(sec, 400).translate([0, 0, -200]).rotate([0, -90, 0])
    slot = slot ^ box([-300, -93, -300], [300, 0, 300])

    # open bottom: extend the lowest cavity section downwards
    low = cav.rotate([90, 0, 0])             # y -> z
    base_sec = low.slice(-211.0)
    base = mf.Manifold.extrude(base_sec, 30).translate([0, 0, -240]).rotate([-90, 0, 0])
    base = base ^ box([-300, -240, -300], [300, -208, 300])
    return cav + slot + base


def main():
    os.makedirs(OUT, exist_ok=True)
    axes = grid_axes([-128, Y_BOT - 3, -118], [128, Y_TOP + 3, 122], RES)
    print("sampling chestnut field ...")
    F = sample(chestnut_field, axes)
    print("rasterising robot clearance ...")
    F = np.maximum(F, CLEARANCE - signed_distance_of(robot_clearance(), axes))

    xs, ys, zs = axes
    X, Y, Z = xs[:, None, None], ys[None, :, None], zs[None, None, :]
    # near the head, never stick out further than the (tested) pumpkin skin
    pumpkin = to_mf(trimesh.load(PUMPKIN.format("front"))) + to_mf(trimesh.load(PUMPKIN.format("back")))
    # (ramped in below ENVELOPE_Y so it blends instead of leaving a step)
    F = np.maximum(F, signed_distance_of(pumpkin.hull(), axes) - np.maximum(ENVELOPE_Y - Y, 0))
    F = np.maximum(F, np.maximum(Y_BOT - Y, Y - (Y_TOP - 1.0)))
    pin = np.full(F.shape, 1e3, np.float32)
    for x, y in PINS:
        for sx in (-1, 1):
            d = np.sqrt((X - sx * x) ** 2 + (Y - y) ** 2) - PIN_R
            d = np.maximum(d, np.abs(Z - SPLIT_Z) - PIN_DEPTH)
            pin = np.minimum(pin, d)
    F = np.maximum(F, -pin)

    for name, side in (("Chestnut_body_front", Z - SPLIT_Z), ("Chestnut_body_back", SPLIT_Z - Z)):
        part = np.maximum(F, -side)
        m = mesh_from_volume(part, axes)
        m = max(m.split(only_watertight=False), key=lambda p: abs(p.volume))  # drop crumbs
        m = decimate(m, 0.04)
        print(name, "faces", len(m.faces), "watertight", m.is_watertight,
              "volume cm3", round(m.volume / 1000), "bounds", m.bounds.round(1).tolist())
        m.export(f"{OUT}/{name}.stl")


if __name__ == "__main__":
    main()
