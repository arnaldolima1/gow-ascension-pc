"""Turn GOWA_MESH_DUMP files (ps3kit gowa_drawcmd hooks.c) into Wavefront OBJ, to look at.

    python3 tools/mesh_dump_to_obj.py <dump dir> [--min-tris 50] [--out <dir>]

mesh_<n>.idx: u16 big-endian triangle-list indices; mesh_<n>.pos: x y z w
big-endian floats, one vertex each. One OBJ per mesh, plus all.obj with every
mesh of at least --min-tris triangles. For the 3D profile (ascension-online
SPEC S9); the files come from the player's own game and stay on that PC.
"""
import argparse, pathlib, struct

def load(idx, pos):
    ib = idx.read_bytes(); pb = pos.read_bytes()
    ind = struct.unpack(">%dH" % (len(ib) // 2), ib[: len(ib) // 2 * 2])
    nv = len(pb) // 16
    verts = [struct.unpack(">4f", pb[i * 16:i * 16 + 16])[:3] for i in range(nv)]
    tris = [ind[i:i + 3] for i in range(0, len(ind) - 2, 3) if max(ind[i:i + 3]) < nv]
    return verts, tris

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir"); ap.add_argument("--min-tris", type=int, default=50); ap.add_argument("--out")
    a = ap.parse_args()
    src = pathlib.Path(a.dir); out = pathlib.Path(a.out or src / "obj"); out.mkdir(exist_ok=True)
    allv, allf, base = [], [], 0
    for idx in sorted(src.glob("mesh_*.idx")):
        pos = idx.with_suffix(".pos")
        if not pos.exists(): continue
        v, t = load(idx, pos)
        if not t: continue
        with open(out / (idx.stem + ".obj"), "w") as f:
            f.writelines(f"v {x} {y} {z}\n" for x, y, z in v)
            f.writelines(f"f {i+1} {j+1} {k+1}\n" for i, j, k in t)
        if len(t) >= a.min_tris:
            allf += [(i + base, j + base, k + base) for i, j, k in t]; allv += v; base += len(v)
        print(f"{idx.stem}: {len(v)} vertices, {len(t)} triangles")
    with open(out / "all.obj", "w") as f:
        f.writelines(f"v {x} {y} {z}\n" for x, y, z in allv)
        f.writelines(f"f {i+1} {j+1} {k+1}\n" for i, j, k in allf)
    print(f"{out}/all.obj: {len(allv)} vertices, {len(allf)} triangles")

if __name__ == "__main__":
    main()
