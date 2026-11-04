"""Turn GOWA_MESH_DUMP files (ps3kit gowa_drawcmd hooks.c) into Wavefront OBJ, to look at.

    python3 tools/mesh_dump_to_obj.py <dump dir> [--min-tris 50] [--out <dir>] [--first N] [--last N] [--latest N] [--quiet]
        [--box x0,y0,z0,x1,y1,z1] [--glb <file>]

mesh_<n>.idx: u16 big-endian triangle-list indices; mesh_<n>.pos: x y z w
big-endian floats, one vertex each. One OBJ per mesh, plus all.obj with every
mesh of at least --min-tris triangles. For the 3D profile (ascension-online
SPEC S9); the files come from the player's own game and stay on that PC.
"""
import argparse, json, pathlib, struct

def load(idx, pos):
    ib = idx.read_bytes(); pb = pos.read_bytes()
    ind = struct.unpack(">%dH" % (len(ib) // 2), ib[: len(ib) // 2 * 2])
    nv = len(pb) // 16
    verts = [struct.unpack(">4f", pb[i * 16:i * 16 + 16])[:3] for i in range(nv)]
    tris = [ind[i:i + 3] for i in range(0, len(ind) - 2, 3) if max(ind[i:i + 3]) < nv]
    return verts, tris

def write_glb(path, meshes):
    """meshes: [(name, verts, tris)] -> one GLB, one node per mesh (pieces stay separate)."""
    bin_, views, accs, gmeshes, nodes = bytearray(), [], [], [], []
    def add(data, target, comp, count, typ, mn=None, mx=None):
        while len(bin_) % 4: bin_.append(0)
        views.append({"buffer": 0, "byteOffset": len(bin_), "byteLength": len(data), "target": target})
        bin_.extend(data)
        a = {"bufferView": len(views) - 1, "componentType": comp, "count": count, "type": typ}
        if mn is not None: a["min"], a["max"] = mn, mx
        accs.append(a); return len(accs) - 1
    for name, v, t in meshes:
        used = sorted({i for tri in t for i in tri}); remap = {o: n for n, o in enumerate(used)}
        vv = [v[i] for i in used]
        pos = add(struct.pack("<%df" % (3 * len(vv)), *[c for p in vv for c in p]), 34962, 5126, len(vv), "VEC3",
                  [min(p[k] for p in vv) for k in range(3)], [max(p[k] for p in vv) for k in range(3)])
        flat = [remap[i] for tri in t for i in tri]
        ind = add(struct.pack("<%dI" % len(flat), *flat), 34963, 5125, len(flat), "SCALAR")
        gmeshes.append({"name": name, "primitives": [{"attributes": {"POSITION": pos}, "indices": ind}]})
        nodes.append({"name": name, "mesh": len(gmeshes) - 1})
    while len(bin_) % 4: bin_.append(0)
    doc = {"asset": {"version": "2.0", "generator": "ascension tools/mesh_dump_to_obj.py"},
           "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": gmeshes,
           "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": len(bin_)}]}
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(bin_))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(bin_), 0x004E4942) + bytes(bin_)
    pathlib.Path(path).write_bytes(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir"); ap.add_argument("--min-tris", type=int, default=50); ap.add_argument("--out")
    ap.add_argument("--first", type=int, default=0); ap.add_argument("--last", type=int, default=1 << 30)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--latest", type=int, help="only the N newest meshes by file time (GOWA_MESH_DUMP is a ring)")
    ap.add_argument("--glb", help="also write the meshes of at least --min-tris triangles to this GLB, one node each")
    ap.add_argument("--box", help="keep only meshes inside x0,y0,z0,x1,y1,z1")
    a = ap.parse_args()
    src = pathlib.Path(a.dir); out = pathlib.Path(a.out or src / "obj"); out.mkdir(exist_ok=True)
    allv, allf, base, glb = [], [], 0, []
    box = [float(c) for c in a.box.split(",")] if a.box else None
    files = sorted(src.glob("mesh_*.idx"))
    if a.latest:
        files = sorted(files, key=lambda f: f.with_suffix(".pos").stat().st_mtime_ns if f.with_suffix(".pos").exists() else 0)[-a.latest:]
    for idx in files:
        n = int(idx.stem.split("_")[1])
        if n < a.first or n > a.last: continue
        pos = idx.with_suffix(".pos")
        if not pos.exists(): continue
        v, t = load(idx, pos)
        if not t: continue
        if box:
            u = [v[i] for i in {i for tri in t for i in tri}]
            if not all(box[k] <= p[k] <= box[k + 3] for p in u for k in range(3)): continue
        with open(out / (idx.stem + ".obj"), "w") as f:
            f.writelines(f"v {x} {y} {z}\n" for x, y, z in v)
            f.writelines(f"f {i+1} {j+1} {k+1}\n" for i, j, k in t)
        if len(t) >= a.min_tris:
            allf += [(i + base, j + base, k + base) for i, j, k in t]; allv += v; base += len(v)
            glb.append((idx.stem, v, t))
        if not a.quiet: print(f"{idx.stem}: {len(v)} vertices, {len(t)} triangles")
    with open(out / "all.obj", "w") as f:
        f.writelines(f"v {x} {y} {z}\n" for x, y, z in allv)
        f.writelines(f"f {i+1} {j+1} {k+1}\n" for i, j, k in allf)
    print(f"{out}/all.obj: {len(allv)} vertices, {len(allf)} triangles")
    if a.glb:
        write_glb(a.glb, glb); print(f"{a.glb}: {len(glb)} meshes")

if __name__ == "__main__":
    main()
