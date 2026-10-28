"""Generate the small parts of the Castanyada skin.

* Chestnut burr antennas ("eriçons"): the antenna mount (disc + neck) is taken
  from the official pumpkin bat-wing antennas, so they clip on the same way.
  A brown stem ends in a closed burr, as it grows on the tree: a flat-backed
  dome covered in small blunt spikes. It stays inside the z range of the bat
  wing (-13.2..0 mm) so it does not get closer to the head than the original.
* Chestnut tip ("la punta"): optional alternative to the headscarf, sits on
  top of the bare head like the pumpkin stem, reusing the stem's base so it
  follows the shape of the head.

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
BURR_R = 14.0                      # husk radius in the antenna plane
BURR_H = 9.6                       # husk height above the flat back
N_SPIKES = 190
SPIKE_LEN, SPIKE_R = 3.4, 0.75     # small, blunt spikes (printable, not sharp)
STEM_END = (BURR_C[0] - 0.5, BURR_C[1] - BURR_R + 1.5)   # the stalk enters the burr here


def seg_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    t = np.clip(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy), 0, 1)
    return np.hypot(px - ax - t * vx, py - ay - t * vy)


def spike_points():
    """Spike roots spread evenly over the domed husk, with their normals."""
    k = np.arange(N_SPIKES) + 0.5
    uz = 1 - k / N_SPIKES                      # upper hemisphere only
    phi = k * np.pi * (3 - np.sqrt(5))         # golden angle
    rho = np.sqrt(1 - uz ** 2)
    u = np.c_[rho * np.cos(phi), rho * np.sin(phi), uz]
    root = np.c_[BURR_C[0] + BURR_R * u[:, 0], BURR_C[1] + BURR_R * u[:, 1], Z_BACK + BURR_H * u[:, 2]]
    n = np.c_[u[:, 0] / BURR_R, u[:, 1] / BURR_R, u[:, 2] / BURR_H]
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    # no spikes where the stem joins the husk
    free = np.hypot(root[:, 0] - BURR_C[0], root[:, 1] - STEM_END[1]) > 5.0
    root, n = root[free], n[free]
    # spikes may not poke out of the bat-wing thickness range
    length = np.minimum(SPIKE_LEN, (Z_FRONT - 0.3 - root[:, 2]) / np.maximum(n[:, 2], 1e-3))
    return root, n, length


SPIKE_ROOT, SPIKE_N, SPIKE_L = spike_points()


def burr_field(X, Y, Z):
    from scipy.spatial import cKDTree
    X, Y, Z = np.broadcast_arrays(X, Y, Z)
    P = np.stack([X, Y, Z], -1).reshape(-1, 3)

    # closed husk: half ellipsoid on the flat back
    e = np.sqrt(((P[:, 0] - BURR_C[0]) / BURR_R) ** 2 + ((P[:, 1] - BURR_C[1]) / BURR_R) ** 2
                + ((P[:, 2] - Z_BACK) / BURR_H) ** 2)
    F = (e - 1) * BURR_H

    # little spikes all over it (only the 3 nearest ones matter)
    near = e < 1 + (SPIKE_LEN + 1) / BURR_H
    if near.any():
        q = P[near]
        _, idx = cKDTree(SPIKE_ROOT).query(q, k=3)
        best = np.full(len(q), 1e3)
        for c in range(3):
            i = idx[:, c]
            v = q - SPIKE_ROOT[i]
            h = np.einsum("ij,ij->i", v, SPIKE_N[i])
            rad = np.linalg.norm(v - h[:, None] * SPIKE_N[i], axis=1)
            L = SPIKE_L[i]
            cone = np.maximum(rad - SPIKE_R * np.clip(1 - h / L, 0, 1) - 0.25, np.maximum(h - L, -h - 1.0))
            best = np.minimum(best, cone)
        F[near] = np.minimum(F[near], best)

    # brown stem from the mount neck up into the burr
    stem = seg_dist(P[:, 0], P[:, 1], NECK[0], NECK[1] - 2, *STEM_END) - 3.6
    stem = np.maximum(stem, np.maximum(NECK_Z[0] - P[:, 2], P[:, 2] - NECK_Z[1]))
    F = np.minimum(F, stem)
    F = np.maximum(F, Z_BACK - P[:, 2])
    return F.reshape(X.shape)


def make_burr():
    ear = to_mf(trimesh.load(EAR))
    mount = ear ^ box([-40, -40, -40], [40, MOUNT_CUT_Y, 40])
    burr = mesh_from_field(burr_field, [-15, MOUNT_CUT_Y - 6, Z_BACK - 1], [30, 95, Z_FRONT + 1], 0.15)
    left = to_tm(mount + to_mf(decimate(burr, 0.02)))
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
