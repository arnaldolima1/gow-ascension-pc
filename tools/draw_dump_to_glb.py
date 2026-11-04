"""Turn RSX_DRAW_DUMP files (ps3kit gpu/rsx/Emu/RSX/Capture/rsx_draw_dump.cpp) into one textured GLB.

    python3 tools/draw_dump_to_glb.py <dump dir> [<dump dir> ...] --glb <out.glb>
        [--box x0,y0,z0,x1,y1,z1] [--strides 54,46] [--tex 1024] [--list]

For the 3D profile (ascension-online docs/ONLINE.md, S9.5): the lobby's warrior with its UVs and
colour textures. The files come from the player's own game and stay on that PC; nothing of the
game goes into git.

What a draw holds (2026-11-04, the multiplayer lobby):
- the colour pass of a character piece has attribute 0 = the EDGE output position (float3,
  interleaved, stride 54 or 46) and attribute 2 = the UV (float2, the model's own stream);
- its fragment textures change with the shader (5 to 11 units). The colour map is the DXT1 one
  with the most warm colour (skin, leather, red armour); the others are the normal map (DXT5,
  orange), grey gloss/occlusion maps, the environment reflection and a blue effect map.
- the colour map's companion is the DXT5 normal map (X in alpha, Y in green), rebuilt as RGB.
EDGE culls the back faces on the SPU, so one frame holds only the side the camera sees: give two
dumps (the warrior from the front and from the back) or one where he turns, and the copies are
joined into one piece per UV stream, one GLB node per piece.
"""
import argparse, glob, io, json, os, struct

DXT = {0x86: 1, 0x87: 2, 0x88: 3}   # CELL_GCM_TEXTURE_COMPRESSED_DXT1/23/45 (| LN 0x20, UN 0x40 masked)
TRIANGLES, TRIANGLE_STRIP = 5, 6     # rsx::primitive_type


def load_draw(path):
    j = json.load(open(path))
    b = open(path[:-5] + ".bin", "rb").read()
    return j, b


def attr(j, b, index, comps):
    """The vertices min_index..max_index of attribute <index> as float tuples (float32 only)."""
    a = next((a for a in j["attributes"] if a["index"] == index), None)
    if a is None or a["type"] != 2 or a["size"] < comps:
        return None
    n = j["max_index"] - j["min_index"] + 1
    st = a["stride"] or 0
    out = []
    for i in range(n):
        at = a["bin"] + i * st
        if at + 4 * comps > a["bin"] + a["bytes"]:
            break
        out.append(struct.unpack_from(">%df" % comps, b, at))
    return out


def triangles(j, b):
    size = 2 if j["index_type"] == 1 else 4
    count = j["index_count"]
    ind = struct.unpack_from(">%d%s" % (count, "H" if size == 2 else "I"), b, 0)
    base, lo = j["base_index"], j["min_index"]
    restart = j["restart_index"] if j["restart"] else None
    out = []
    if j["primitive"] == TRIANGLES:
        for i in range(0, count - 2, 3):
            t = ind[i:i + 3]
            if restart is None or restart not in t:
                out.append(tuple(x + base - lo for x in t))
    elif j["primitive"] == TRIANGLE_STRIP:
        run = []
        for x in ind:
            if restart is not None and x == restart:
                run = []
                continue
            run.append(x + base - lo)
            if len(run) >= 3:
                a, c, d = run[-3:]
                if a != c and c != d and a != d:
                    out.append((a, c, d) if len(run) % 2 else (c, a, d))
    return out


def decode(t, dump):
    from PIL import Image
    n = DXT.get(t["format"] & ~0x60)
    w, h = t["width"], t["height"]
    p = os.path.join(dump, t["file"])
    if not n or w < 16 or h < 16 or not os.path.exists(p):
        return None
    need = ((w + 3) // 4) * ((h + 3) // 4) * (8 if n == 1 else 16)
    d = open(p, "rb").read(need)
    if len(d) < need:
        return None
    return Image.frombuffer("RGBA", (w, h), d, "bcn", n)


def warmth(im):
    """Mean colourfulness of the warm pixels: the colour map scores high, normal/gloss/env/effect maps low."""
    small = im.convert("RGB").resize((64, 64))
    s = 0.0
    px = list(small.getdata())
    for r, g, b in px:
        if r >= b:   # the blue effect map and the orange normal map (DXT5, skipped) aside
            s += max(r, g, b) - min(r, g, b)
    return s / len(px)


def colour_map(j, dump, cache):
    best, score = None, 8.0   # below this nothing is colour
    for t in j["textures"]:
        if (t["format"] & ~0x60) != 0x86:
            continue
        key = os.path.join(dump, t["file"])
        if key not in cache:
            im = decode(t, dump)
            cache[key] = (im, warmth(im) if im else 0.0)
        im, s = cache[key]
        if im is not None and s > score:
            best, score = key, s
    return best


def normal_map(j, dump, cache):
    """The DXT5 map stored as X in alpha, Y in green (it looks orange): rebuilt as an RGB normal map."""
    best, size = None, 0
    for t in j["textures"]:
        if (t["format"] & ~0x60) != 0x88:
            continue
        key = "n:" + os.path.join(dump, t["file"])
        if key not in cache:
            im = decode(t, dump)
            ok = False
            if im is not None:
                r, g, b, a = (sum(c) / len(c) for c in zip(*im.resize((32, 32)).getdata()))
                ok = r > 170 and b < 110 and 90 < g < 170 and 90 < a < 170
            cache[key] = (to_normal(im) if ok else None, 0.0)
        if cache[key][0] is not None and t["width"] * t["height"] > size:
            best, size = key, t["width"] * t["height"]
    return best


def to_normal(im):
    from PIL import Image
    _, g, _, a = im.split()
    xs, ys = a.tobytes(), g.tobytes()
    z = bytearray(len(xs))
    for i in range(len(xs)):
        x, y = xs[i] / 127.5 - 1.0, ys[i] / 127.5 - 1.0
        z[i] = int((max(0.0, 1.0 - x * x - y * y) ** 0.5) * 127.5 + 127.5)
    return Image.merge("RGB", (a, g, Image.frombytes("L", im.size, bytes(z))))


def inside(P, box):
    step = max(1, len(P) // 24)
    return all(box[0][k] <= p[k] <= box[1][k] for p in P[::step] for k in range(3))


def normals(P, T):
    N = [[0.0, 0.0, 0.0] for _ in P]
    for a, b, c in T:
        ux, uy, uz = (P[b][k] - P[a][k] for k in range(3))
        vx, vy, vz = (P[c][k] - P[a][k] for k in range(3))
        n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
        for i in (a, b, c):
            for k in range(3):
                N[i][k] += n[k]
    out = []
    for n in N:
        l = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5 or 1.0
        out.append((n[0] / l, n[1] / l, n[2] / l))
    return out


def write_glb(path, pieces, images, tex_max):
    """pieces: [(name, P, UV, T, image key or None)]; images: {key: PIL image}."""
    bin_, views, accs, meshes, nodes, mats, imgs, texs = bytearray(), [], [], [], [], [], [], []

    def view(data, target=None):
        while len(bin_) % 4:
            bin_.append(0)
        v = {"buffer": 0, "byteOffset": len(bin_), "byteLength": len(data)}
        if target:
            v["target"] = target
        views.append(v)
        bin_.extend(data)
        return len(views) - 1

    def acc(data, comp, count, typ, target, mn=None, mx=None):
        a = {"bufferView": view(data, target), "componentType": comp, "count": count, "type": typ}
        if mn is not None:
            a["min"], a["max"] = mn, mx
        accs.append(a)
        return len(accs) - 1

    img_of = {}

    def image(key):
        if key not in img_of:
            im = images[key].convert("RGB")
            if max(im.size) > tex_max:
                im = im.resize((min(im.width, tex_max), min(im.height, tex_max)))
            png = io.BytesIO()
            im.save(png, "PNG", optimize=True)
            imgs.append({"bufferView": view(png.getvalue()), "mimeType": "image/png"})
            texs.append({"source": len(imgs) - 1, "sampler": 0})
            img_of[key] = len(texs) - 1
        return img_of[key]

    mat_of = {}
    for colour, normal in sorted({p[4] for p in pieces if p[4][0]}, key=str):
        m = {"name": os.path.basename(colour), "pbrMetallicRoughness": {
            "baseColorTexture": {"index": image(colour)}, "metallicFactor": 0.0, "roughnessFactor": 0.75},
            "doubleSided": True}
        if normal:
            m["normalTexture"] = {"index": image(normal)}
        mats.append(m)
        mat_of[(colour, normal)] = len(mats) - 1
    mats.append({"name": "plain", "pbrMetallicRoughness": {"baseColorFactor": [0.6, 0.55, 0.5, 1],
                 "metallicFactor": 0.0, "roughnessFactor": 0.9}, "doubleSided": True})
    plain = len(mats) - 1

    for name, P, UV, T, key in pieces:
        used = sorted({i for t in T for i in t})
        remap = {o: n for n, o in enumerate(used)}
        T2 = [tuple(remap[i] for i in t) for t in T]
        PP = [P[i] for i in used]
        NN = normals(PP, T2)
        attrs = {
            "POSITION": acc(struct.pack("<%df" % (3 * len(PP)), *[c for p in PP for c in p]), 5126, len(PP), "VEC3",
                            34962, [min(p[k] for p in PP) for k in range(3)], [max(p[k] for p in PP) for k in range(3)]),
            "NORMAL": acc(struct.pack("<%df" % (3 * len(NN)), *[c for n in NN for c in n]), 5126, len(NN), "VEC3", 34962),
        }
        if UV and key[0]:
            uu = [UV[i] for i in used]
            attrs["TEXCOORD_0"] = acc(struct.pack("<%df" % (2 * len(uu)), *[c for u in uu for c in u[:2]]), 5126,
                                      len(uu), "VEC2", 34962)
        flat = [i for t in T2 for i in t]
        ind = acc(struct.pack("<%dI" % len(flat), *flat), 5125, len(flat), "SCALAR", 34963)
        meshes.append({"name": name, "primitives": [{"attributes": attrs, "indices": ind,
                       "material": mat_of.get(key, plain) if UV else plain}]})
        nodes.append({"name": name, "mesh": len(meshes) - 1})

    while len(bin_) % 4:
        bin_.append(0)
    gltf = {"asset": {"version": "2.0", "generator": "ascension draw_dump_to_glb.py"},
            "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes,
            "materials": mats, "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": len(bin_)}]}
    if imgs:
        gltf.update(images=imgs, textures=texs, samplers=[{"magFilter": 9729, "minFilter": 9987}])
    js = json.dumps(gltf, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(bin_))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(bin_), 0x004E4942) + bin_
    open(path, "wb").write(out)
    return len(out)


def yaw_fit(src, dst):
    """The turn about the vertical axis plus the shift that best maps src onto dst (lists of xyz)."""
    import math
    n = len(src)
    cs = [sum(p[k] for p in src) / n for k in range(3)]
    cd = [sum(p[k] for p in dst) / n for k in range(3)]
    num = den = 0.0
    for p, q in zip(src, dst):
        ax, az, bx, bz = p[0] - cs[0], p[2] - cs[2], q[0] - cd[0], q[2] - cd[2]
        num += ax * bz - az * bx
        den += ax * bx + az * bz
    th = math.atan2(num, den)
    return (math.cos(th), math.sin(th), cs, cd)


def apply(tf, p):
    c, s_, cs, cd = tf
    x, y, z = p[0] - cs[0], p[1] - cs[1], p[2] - cs[2]
    return (c * x - s_ * z + cd[0], y + cd[1], s_ * x + c * z + cd[2])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dumps", nargs="+", help="one or more RSX_DRAW_DUMP folders (e.g. the warrior seen from the front and from the back)")
    ap.add_argument("--glb", required=False)
    ap.add_argument("--box", default="-0.7,0.4,-5.2,0.6,2.9,-4.1",
                    help="keep the pieces inside this box (default: the warrior of the multiplayer lobby)")
    ap.add_argument("--strides", default="54,46", help="attribute 0 strides of the colour pass")
    ap.add_argument("--tex", type=int, default=1024, help="largest texture side in the GLB")
    ap.add_argument("--list", action="store_true", help="print the pieces and their colour map")
    a = ap.parse_args()
    v = [float(x) for x in a.box.split(",")]
    box = (v[:3], v[3:])
    strides = {int(x) for x in a.strides.split(",")}

    # EDGE culls the back-facing triangles on the SPU, so one frame holds only what the camera sees,
    # and its index/vertex output sits in a ring that moves every frame. The UV stream is the
    # model's own: its address names the piece and the vertex numbers inside it are stable. Every
    # copy of a piece (any frame, any dump) is turned onto the first one about the vertical axis
    # (the warrior turned in the lobby) using the vertices both hold; then the vertices and the
    # triangles are joined.
    cache, ref, uvs, tris, look, order = {}, {}, {}, {}, {}, []
    for dump in a.dumps:
        files = sorted(glob.glob(os.path.join(dump, "draw_*.json")), key=os.path.getmtime, reverse=True)
        last_tf = None
        for f in files:
            try:
                j, b = load_draw(f)
            except (OSError, ValueError):
                continue   # the ring was being written when the game closed
            at = {x["index"]: x for x in j["attributes"]}
            if 0 not in at or at[0]["stride"] not in strides or 2 not in at:
                continue
            P = attr(j, b, 0, 3)
            if not P or not inside(P, box):
                continue
            UV = attr(j, b, 2, 2)
            if not UV:
                continue
            key, lo = at[2]["offset"], j["min_index"]
            n = min(len(P), len(UV))
            if key not in ref:
                ref[key], uvs[key], tris[key] = {}, {}, set()
                look[key] = (dump, j)
                order.append(key)
                tf = last_tf if ref and last_tf else None
            else:
                shared = [i for i in range(n) if lo + i in ref[key]]
                if len(shared) >= 6:
                    tf = yaw_fit([P[i] for i in shared], [ref[key][lo + i] for i in shared])
                    err = max(sum((x - y) ** 2 for x, y in zip(apply(tf, P[i]), ref[key][lo + i])) for i in shared) ** 0.5
                    if err > 0.08:
                        continue   # another pose, too far to join
                    last_tf = tf
                else:
                    tf = last_tf
            R, U = ref[key], uvs[key]
            for i in range(n):
                if lo + i not in R:
                    R[lo + i] = apply(tf, P[i]) if tf else P[i]
                    U[lo + i] = UV[i]
            for t in triangles(j, b):
                if max(t) < n:
                    t = tuple(lo + x for x in t)
                    tris[key].add(min(t[i:] + t[:i] for i in range(3)))   # same triangle, same winding

    pieces, images = [], {}
    for key in order:
        if not tris[key]:
            continue
        idx = sorted(ref[key])
        at_ = {o: k for k, o in enumerate(idx)}
        P = [ref[key][o] for o in idx]
        UV = [uvs[key][o] for o in idx]
        T = [tuple(at_[x] for x in t) for t in sorted(tris[key])]
        dump, j = look[key]
        mats = (colour_map(j, dump, cache), normal_map(j, dump, cache))
        for k in mats:
            if k:
                images[k] = cache[k][0]
        pieces.append(("piece_%08X" % key, P, UV, T, mats))
        if a.list:
            print("piece_%08X  %5d verts  %5d tris  colour %s" % (key, len(P), len(T), mats[0]))
    print("%d pieces, %d texture maps (colour + normal), %d triangles" % (len(pieces), len(images), sum(len(p[3]) for p in pieces)))
    if a.glb and pieces:
        n = write_glb(a.glb, pieces, images, a.tex)
        print("wrote %s (%.1f MB)" % (a.glb, n / 1e6))


if __name__ == "__main__":
    main()
