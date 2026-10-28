"""Small helpers shared by the Castanyada skin generators."""
import numpy as np
import trimesh
import manifold3d as mf
from skimage.measure import marching_cubes


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def grid_axes(lo, hi, res):
    return [np.arange(lo[i], hi[i] + res, res) for i in range(3)]


def sample(field_fn, axes, chunk=20):
    """Sample field_fn(X, Y, Z) (negative inside) on the grid given by axes."""
    xs, ys, zs = axes
    vol = np.empty((len(xs), len(ys), len(zs)), np.float32)
    Y, Z = np.meshgrid(ys, zs, indexing="ij")
    for i0 in range(0, len(xs), chunk):
        X = xs[i0:i0 + chunk][:, None, None]
        vol[i0:i0 + chunk] = field_fn(X, Y[None], Z[None])
    return vol


def mesh_from_volume(vol, axes):
    """Marching cubes on a sampled field; the border is forced outside so the mesh is closed."""
    # keep samples off the iso level, otherwise marching cubes emits collapsed
    # triangles that break the mesh once it is written to STL
    vol = np.where(np.abs(vol) < 0.02, np.where(vol < 0, -0.02, 0.02), vol).astype(np.float32)
    vol[0] = vol[-1] = 10
    vol[:, 0] = vol[:, -1] = 10
    vol[:, :, 0] = vol[:, :, -1] = 10
    res = axes[0][1] - axes[0][0]
    v, f, _, _ = marching_cubes(vol, level=0.0, spacing=(res, res, res))
    v += [a[0] for a in axes]
    m = trimesh.Trimesh(v, f[:, ::-1], process=True)
    if m.volume < 0:
        m.invert()
    return m


def mesh_from_field(field_fn, lo, hi, res):
    axes = grid_axes(lo, hi, res)
    return mesh_from_volume(sample(field_fn, axes), axes)


def signed_distance_of(solid, axes):
    """Signed distance (negative inside) of a manifold solid, sampled on the grid.

    The solid is rasterised slice by slice along y, then turned into a
    distance field with an exact Euclidean distance transform.
    """
    from PIL import Image, ImageDraw
    from scipy.ndimage import distance_transform_edt
    xs, ys, zs = axes
    res = xs[1] - xs[0]
    occ = np.zeros((len(xs), len(ys), len(zs)), bool)
    rot = solid.rotate([90, 0, 0])            # (x, y, z) -> (x, -z, y)
    for j, y in enumerate(ys):
        mask = np.zeros((len(zs), len(xs)), bool)
        for poly in rot.slice(float(y)).to_polygons():
            img = Image.new("1", (len(xs), len(zs)), 0)
            pts = [((px - xs[0]) / res, (-pz - zs[0]) / res) for px, pz in poly]
            if len(pts) >= 3:
                ImageDraw.Draw(img).polygon(pts, fill=1)
                mask ^= np.array(img, bool)
        occ[:, j, :] = mask.T
    d_out = distance_transform_edt(~occ).astype(np.float32)
    d_in = distance_transform_edt(occ).astype(np.float32)
    return (d_out - d_in) * res


def decimate(m, tolerance=0.04):
    """Reduce the triangle count while keeping the mesh manifold (deviation <= tolerance mm)."""
    return to_tm(to_mf(m).simplify(tolerance))


def to_mf(m):
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                               tri_verts=np.asarray(m.faces, np.uint32)))


def to_tm(M):
    me = M.to_mesh()
    return trimesh.Trimesh(me.vert_properties[:, :3], me.tri_verts, process=True)


def box(lo, hi):
    lo = np.asarray(lo, float)
    hi = np.asarray(hi, float)
    return mf.Manifold.cube((hi - lo).tolist()).translate(lo.tolist())
