"""Generate the small parts of the Castanyada skin.

* Chestnut burr antennas ("eriçons"): the antenna mount (disc + neck) is taken
  from the official pumpkin bat-wing antennas, so they clip on the same way.
  The burr itself is a flat-backed spiky medallion, split open at the front to
  show a chestnut. It stays inside the z range of the bat wing (-13.2..0 mm)
  so it does not get closer to the head than the original part.
* Chestnut tip ("la punta"): sits on top of the head like the pumpkin stem,
  reusing the stem's base so it follows the shape of the head.

Run from the repository root:
    python castanyada/tools/make_accessories.py
"""
import os
import sys

import numpy as np
import trimesh

sys.path.insert(0, os.path.dirname(__file__))
from sdf_common import box, decimate, mesh_from_field, smoothstep, to_mf, to_tm

OUT = "castanyada/stl"
EAR = "pumpkin/L_bat_ear_low.stl"
STEM = "pumpkin/Pumpkin_tail.stl"

# --- burr antenna (left one; the right one is mirrored) -------------------
Z_BACK, Z_FRONT = -13.2, 0.0       # same thickness range as the bat wing
MOUNT_CUT_Y = 14.0                 # keep the bat-wing mount below this height
NECK = (1.2, 12.0)                 # x, y of the mount neck
NECK_Z = (-9.7, -4.1)
BURR_C = (7.0, 70.0)               # burr centre (x, y)
BURR_R = 14.5
SPIKES, SPIKE_LEN = 14, 7.5
OPEN_R = 8.0                       # front opening that shows the chestnut


def seg_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    t = np.clip(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy), 0, 1)
    return np.hypot(px - ax - t * vx, py - ay - t * vy)


def burr_field(X, Y, Z):
    dx, dy = X - BURR_C[0], Y - BURR_C[1]
    r = np.hypot(dx, dy)
    th = np.arctan2(dy, dx)

    # domed husk, flat back
    rr = np.clip(r / BURR_R, 0, 1)
    z_top = Z_BACK + 11.0 * np.sqrt(1 - rr ** 2) + 0.6
    husk = np.maximum(r - BURR_R, Z - np.minimum(z_top, Z_FRONT - 1.0))

    # star of rim spikes, full height at the base so they print flat
    phase = np.abs(((th * SPIKES / (2 * np.pi)) % 1.0) - 0.5) * 2      # 1 at spike axis
    r_star = BURR_R - 2 + SPIKE_LEN * phase ** 3
    z_spike = Z_BACK + 7.5 - 0.45 * np.maximum(r - BURR_R, 0)
    spikes = np.maximum(r - r_star, Z - z_spike)
    F = np.minimum(husk, spikes)

    # prickly texture on the dome
    prick = np.maximum(np.sin(dx * 1.1) * np.sin(dy * 1.1) + np.sin((dx + dy) * 0.8) * 0.4, 0)
    F -= 0.9 * prick * smoothstep(BURR_R * 0.55, BURR_R * 0.75, r) * (1 - smoothstep(BURR_R - 1, BURR_R, r))

    # husk split open in four valves at the front
    r_open = OPEN_R + 2.8 * np.cos(4 * th + np.pi / 4)
    F = np.maximum(F, -np.maximum(r_open - r, (Z_BACK + 6.0) - Z))
    # the chestnut inside, with a small pointed tip
    cy = BURR_C[1] - 0.5
    ty = np.clip((Y - cy) / 9.0, -1, 1)
    half_w = 7.5 * (1 - 0.35 * np.maximum(ty, 0) ** 2)
    nut = np.sqrt((dx / half_w) ** 2 + ((Y - cy) / 8.5) ** 2 + ((Z - (Z_BACK + 6.5)) / 6.4) ** 2) - 1
    nut = np.maximum(nut * 6, Z - (Z_FRONT - 0.4))
    F = np.minimum(F, nut)

    # stem from the mount neck to the burr
    stem = seg_dist(X, Y, NECK[0], NECK[1] - 2, BURR_C[0] - 1.0, BURR_C[1] - BURR_R + 2) - 3.6
    stem = np.maximum(stem, np.maximum(NECK_Z[0] - Z, Z - NECK_Z[1]))
    F = np.minimum(F, stem)
    return np.maximum(F, Z_BACK - Z)


def make_burr():
    ear = to_mf(trimesh.load(EAR))
    mount = ear ^ box([-40, -40, -40], [40, MOUNT_CUT_Y, 40])
    burr = mesh_from_field(burr_field, [-15, MOUNT_CUT_Y - 6, Z_BACK - 1], [30, 95, Z_FRONT + 1], 0.15)
    left = to_tm(mount + to_mf(decimate(burr, 0.01)))
    right = left.copy()
    right.apply_transform(np.diag([-1, 1, 1, 1]))
    return left, right


# --- chestnut tip for the top of the head --------------------------------
TIP_BASE_CUT = 48.5               # keep the stem's head-fitting base below this
TIP_C = (3.3, 2.8)                # footprint centre (x, z)


def tip_field(X, Y, Z):
    dx, dz = X - TIP_C[0], Z - TIP_C[1]
    r = np.hypot(dx, dz)
    h = Y - 47.0
    # short rounded cone ending in a little nipple
    radius = 8.2 * np.clip(1 - h / 15.0, 0, 1) ** 0.8 + 1.6
    F = np.maximum(r - radius, np.maximum(46.0 - Y, Y - 63.0))
    # tuft of stiff hairs ("la flor"), fanning out from the top
    for i in range(7):
        a = 2 * np.pi * i / 7
        lean = 0.0 if i == 0 else 0.45
        tx, tz = TIP_C[0] + lean * 7 * np.cos(a), TIP_C[1] + lean * 7 * np.sin(a)
        if i == 0:
            tx, tz = TIP_C
        # segment from (TIP_C, 60) to (tx, 71)
        sx, sz, sy = tx - TIP_C[0], tz - TIP_C[1], 11.0
        px, pz, py = X - TIP_C[0], Z - TIP_C[1], Y - 60.0
        t = np.clip((px * sx + pz * sz + py * sy) / (sx * sx + sz * sz + sy * sy), 0, 1)
        d = np.sqrt((px - t * sx) ** 2 + (pz - t * sz) ** 2 + (py - t * sy) ** 2) - (0.95 - 0.25 * t)
        F = np.minimum(F, d)
    return F


def make_tip():
    stem = to_mf(trimesh.load(STEM))
    base = stem ^ box([-40, 0, -40], [40, TIP_BASE_CUT, 40])
    tip = mesh_from_field(tip_field, [-12, 45.0, -12], [19, 74, 18], 0.12)
    return to_tm(base + to_mf(decimate(tip, 0.01)))


def main():
    os.makedirs(OUT, exist_ok=True)
    left, right = make_burr()
    tip = make_tip()
    for name, m in (("Burr_antenna_L", left), ("Burr_antenna_R", right), ("Chestnut_tip", tip)):
        print(name, "faces", len(m.faces), "watertight", m.is_watertight,
              "volume cm3", round(m.volume / 1000, 1), "bounds", m.bounds.round(1).tolist())
        m.export(f"{OUT}/{name}.stl")


if __name__ == "__main__":
    main()
