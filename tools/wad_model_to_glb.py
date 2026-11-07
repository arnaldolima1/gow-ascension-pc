"""A model straight from the player's own WAD (no game running): EDGE segments to GLB.

    python3 tools/wad_model_to_glb.py R_SPARTANAVS00.WAD --mg MG_70b97feb_0 --glb body.glb
        [--ts R_SPARTANAVS00.TS] [--decaps] [--no-normals] [--no-orm] [--pose JOBCAP] [--list]

For the 3D profile (ascension-online docs/ONLINE.md, S9). Read 2026-11-04 against the RSX and SPU
job captures (RSX_DRAW_DUMP, SPU_JOBCAP); the files come from the player's disc and stay on that PC.

A mesh group (MG_ block, loaded in place: the RSX reads its UV streams from it) holds:
- u32 version/count, u32 size, ... +0x10 u32 submesh count N, +0x20 N u32 submesh offsets, then
  per-segment bounding records (ffff0000 + 4 floats);
- per segment an EDGE `EdgeGeomSpuConfigInfo` (16 bytes at C: flags, hole size, input/secondary/
  output/delta format ids, indexes and skinning flavour, skinning matrix format, u16 numVertexes,
  u16 numIndexes, u32 0xFFFFFFFF), then self-relative pointers (target = field address + s32):
  C+0x10 compressed indices (size u16 at C+0x18), C+0x20 vertex stream (size u16 at C+0x28),
  C+0x40 skin indices/weights (size u16 at C+0x3C), C+0x60 three s32 fixed-point offsets;
- vertex records of 12 bytes (the input stream description, 48 bytes): position as three u16
  fixed point (0 integer bits, 16 fraction bits; position = (raw + offset) / 65536, metres, the
  bind pose with the arms out), a unit-vector normal (3 bytes) and tangent (3 bytes);
- indices in EDGE's compressed format (ascension-native/render/geometry/indices.h);
- before the segment, the RSX attribute table: entries (u32 size, s32 self-relative pointer,
  u32 tag), tag byte 0 the role (0x0A texcoord 0 = RSX attribute 2, 0x0B texcoord 1, 0x09 colour)
  and stride = (tag >> 9) & 0x7F; the UVs are float2, not packed. The segments of one part share
  the stream, each after the vertices of the ones before it.
Segments with flags 0x86 have another vertex format (shadow geometry?) and are skipped.

Textures: a TX<hash>.<hash>.dds block holds a DDS header at +0x50 and the small mip levels after
it (+0xD8); +0x3C is the offset of the large levels in the .TS beside the WAD (0xFFFFFFFF: all in
the WAD), +0x40 the number of levels kept in the WAD. A MAT_ block names its textures; the first
is the colour map. Which material a segment uses: the MG_ block's header has u16 submesh count at
+0x10 and u16 material count at +0x16; every part of a submesh ends its header in u32 0x17, a float
and a u16 slot into the material list of the MDL_ group that names the mesh group (the empty MAT_
references after the MDL_ block, in order); a material's normal map is its DXT5 texture with X in
alpha and Y in green (rebuilt as RGB). For the warrior (MDL_70b97feb): 0 head, 1 outer eye,
2/6 skin (glowanimmat3/1), 3 ambient eye, 4 face skin (glowanimmat2), 5 decapitation caps.
"""
import argparse, io, os, re, struct

import wad_list


def u16(d, o): return struct.unpack_from(">H", d, o)[0]
def u32(d, o): return struct.unpack_from(">I", d, o)[0]
def s32(d, o): return struct.unpack_from(">i", d, o)[0]


def segments(mg):
    out = []
    for c in range(0, len(mg) - 0x70, 16):
        nv, ni = u16(mg, c + 8), u16(mg, c + 10)
        if not nv or not ni or ni % 3 or u32(mg, c + 12) != 0xFFFFFFFF:
            continue
        ip, isz = c + 0x10 + s32(mg, c + 0x10), u16(mg, c + 0x18)
        vp, vsz = c + 0x20 + s32(mg, c + 0x20), u16(mg, c + 0x28)
        if not (0 <= ip < len(mg) and 0 <= vp < len(mg) and isz and vsz) or not nv * 6 <= vsz <= nv * 64:
            continue
        out.append(dict(c=c, flags=mg[c], nv=nv, ni=ni, ip=ip, isz=isz, vp=vp, vsz=vsz))
    marks = part_materials(mg)
    for g in out:
        g["mat"] = next((m for p, m in reversed(marks) if p < g["c"]), None)
    return out


def part_materials(mg):
    """Each part header ends in u32 0x17, a float, u16 material slot, u16 0, u16 1, u16 0; the segments
    that follow (up to the next part) use that slot of the model's material list."""
    return [(p, u16(mg, p + 8)) for p in range(0, len(mg) - 16, 4)
            if u32(mg, p) == 0x17 and mg[p + 10:p + 12] == b"\0\0" and u32(mg, p + 12) == 0x10000]


def edge_indices(s, num_indexes):
    """EDGE compressed indices -> triangles (ps3kit indices.h)."""
    num_refs, bias, mask_bytes = struct.unpack_from(">HHH", s, 0)
    ref_bits = s[6]
    tris = num_indexes // 3
    codes_at = 8 + mask_bytes
    refs_at = codes_at + ((2 * tris + 7) >> 3)
    refs, lane = [], [0] * 8
    for i in range(num_refs):
        bit = i * ref_bits
        q = refs_at + bit // 8
        w = s[q] << 16 | s[q + 1] << 8 | s[q + 2]
        f = (w >> (24 - ref_bits - bit % 8)) & ((1 << ref_bits) - 1) if ref_bits else 0
        lane[i & 7] = (lane[i & 7] + f - bias) & 0xFFFF
        refs.append(lane[i & 7])
    state = {"r": 0, "new": 0, "k": 0}

    def x():
        k = state["k"]
        state["k"] = k + 1
        if (s[8 + k // 8] >> (7 - k % 8)) & 1:
            v = refs[state["r"]]
            state["r"] += 1
        else:
            v = state["new"]
            state["new"] += 1
        return v

    out, p = [], None
    for t in range(tris):
        code = (s[codes_at + t // 4] >> (6 - 2 * (t % 4))) & 3
        if code == 3:
            tri = (x(), x(), x())
        elif code == 0:
            tri = (p[0], p[2], x())
        elif code == 1:
            tri = (p[2], p[1], x())
        else:
            tri = (p[1], p[0], x())
        out.append(tri)
        p = tri
    return out


def uv_stream(mg, c):
    """The texcoord-0 entry of the RSX attribute table before the segment: (offset, stride)."""
    best = None
    for p in range(max(4, c - 0x400), c, 4):
        tag = u32(mg, p)
        if tag >> 24 == 0x0A and ((tag >> 16) & 0xFF) >= 0x10:
            t = p - 4 + s32(mg, p - 4)
            if 0 <= t < len(mg):
                best = (t, (tag >> 9) & 0x7F)
    return best


def pieces(mg, tag, pose_dir=None):
    out, used, segs = [], {}, segments(mg)
    pose = None
    if pose_dir:
        import lobby_pose
        pose = lobby_pose.Pose(pose_dir, mg, segs)
    rigid = []
    for g in segs:
        # The segments of one part share its texcoord stream, one after the other.
        uv = uv_stream(mg, g["c"])
        if uv:
            skip = used.get(uv, 0)
            used[uv] = skip + g["nv"]
            uv = (uv[0] + uv[1] * skip, uv[1])
        if g["flags"] != 0x87:
            continue
        try:
            T = edge_indices(mg[g["ip"]:g["ip"] + g["isz"] + 64], g["ni"])
        except IndexError:
            continue
        nv = g["nv"]
        off = struct.unpack_from(">3i", mg, g["c"] + 0x60)
        P = [tuple((r + o) / 65536.0 for r, o in zip(struct.unpack_from(">3H", mg, g["vp"] + 12 * i), off))
             for i in range(nv)]
        UV = [struct.unpack_from(">2f", mg, uv[0] + uv[1] * i) for i in range(nv)] if uv else None
        T = [t for t in T if max(t) < nv]
        if T:
            if pose:
                posed = pose.skin(g, P)
                if posed is None:
                    rigid.append(len(out))
                else:
                    P = posed
            out.append(("%s_%05X" % (tag, g["c"]), P, UV, T, g["mat"]))
    for i in rigid:   # after every skinned piece: they borrow its matrices
        n, P, UV, T, mat = out[i]
        out[i] = (n, pose.rigid(P), UV, T, mat)
    return out


def texture(blocks, ts, name):
    """A TX block's top level as a PIL image (DXT1/3/5), the large levels read from the .TS."""
    from PIL import Image
    data = next(d for o, t, f, s, n, d in blocks if n == name and s)
    h, w = struct.unpack_from("<II", data, 0x50 + 12)
    fourcc = data[0x50 + 84:0x50 + 88]
    n = {b"DXT1": 1, b"DXT3": 2, b"DXT5": 3}[fourcc]
    size = ((w + 3) // 4) * ((h + 3) // 4) * (8 if n == 1 else 16)
    at = u32(data, 0x3C)
    raw = data[0xD8:0xD8 + size] if at == 0xFFFFFFFF else ts[at:at + size]
    return Image.frombuffer("RGBA", (w, h), raw, "bcn", n)


def model_materials(blocks, mg_name):
    """The material list of the MDL_ group that names this mesh group: the MAT_ references (empty
    blocks) after the MDL_ block, in order; a part's slot indexes it."""
    for i, b in enumerate(blocks):
        if b[4].startswith("MDL_") and b[3]:
            refs = []
            for k in range(i + 1, len(blocks)):
                if blocks[k][1] != 1 or blocks[k][3]:
                    break
                refs.append(blocks[k][4])
            if mg_name in refs:
                return [r for r in refs if r.startswith("MAT_")]
    return []


def normal_texture(blocks, ts, txs, images):
    """The material's normal map: its DXT5 texture stored as X in alpha, Y in green (it looks
    orange: R 255, B 0), rebuilt as an RGB tangent-space map; images is the cache."""
    import draw_dump_to_glb as G
    for tx in txs:
        key = "n:" + tx
        if key in images:
            return key
        data = next((d for o, t, f, s, n, d in blocks if n == tx and s), None)
        if not data or data[0x50 + 84:0x50 + 88] != b"DXT5":
            continue
        im = texture(blocks, ts, tx)
        r, g, b, al = (sum(c) / len(c) for c in zip(*im.resize((32, 32)).getdata()))
        if r > 200 and b < 60 and 90 < g < 170 and 90 < al < 170:
            images[key] = G.to_normal(im)
            return key
    return None


def material_roles(blocks, mat):
    """{role: texture} of a MAT_ block: each texture name follows a header whose bytes are the
    role, the texture unit and 0x51. Roles read on the warrior: 0x02 colour, 0x07 normal map,
    0x09 specular (grey), 0x0B ambient occlusion, 0x14 a grey shading layer, 0x03 an 8x8 white
    default, 0x0E/0x04/0x0F/0x33 the animated effects (glow mask, a decal and its mask, the blue
    veins), off in the lobby."""
    data = next(d for o, t, f, s, n, d in blocks if n == mat and s)
    out = {}
    for m in re.finditer(rb"TX[0-9A-F]{8}\.[0-9A-F]{8}\.dds", data):
        p = data.rfind(b"\x51\x00\x00\x00", 0, m.start())
        if p >= 2:
            out.setdefault(data[p - 2], m.group().decode())
    return out


def orm_texture(blocks, ts, roles, images):
    """glTF occlusion (R) + roughness (G) from the AO (0x0B) and specular (0x09) maps."""
    from PIL import Image
    ao_tx, sp_tx = roles.get(0x0B), roles.get(0x09)
    key = "orm:%s:%s" % (ao_tx, sp_tx)
    if key in images:
        return key
    try:
        sp = texture(blocks, ts, sp_tx).convert("L") if sp_tx else None
    except (StopIteration, KeyError, ValueError):
        sp = None
    try:
        ao = texture(blocks, ts, ao_tx).convert("L") if ao_tx else None
    except (StopIteration, KeyError, ValueError):
        ao = None
    if sp is None and ao is None:
        return None
    size = (sp or ao).size
    ao = ao.resize(size) if ao else Image.new("L", size, 255)
    # more specular, smoother: the grey map's mean (~0.27) gives roughness ~0.7
    rough = sp.point(lambda v: int(255 * max(0.25, min(1.0, 0.95 - 0.9 * v / 255)))) if sp else Image.new("L", size, 190)
    images[key] = Image.merge("RGB", (ao, rough, Image.new("L", size, 0)))
    return key


def material_textures(blocks, mat):
    data = next(d for o, t, f, s, n, d in blocks if n == mat and s)
    return [m.group().decode() for m in re.finditer(rb"TX[0-9A-F]{8}\.[0-9A-F]{8}\.dds", data)]


def main():
    import draw_dump_to_glb as G
    ap = argparse.ArgumentParser()
    ap.add_argument("wad")
    ap.add_argument("--mg", action="append", help="mesh group block name (repeat); default: every MG_ block")
    ap.add_argument("--glb")
    ap.add_argument("--ts", help="the .TS beside the WAD (textures' large levels)")
    ap.add_argument("--pose", help="an SPU_JOBCAP dir: the pose the game had there (tools/lobby_pose.py); default the bind pose")
    ap.add_argument("--no-normals", action="store_true", help="no normal maps")
    ap.add_argument("--no-orm", action="store_true", help="no occlusion/roughness maps")
    ap.add_argument("--decaps", action="store_true", help="keep the decapitation caps (hidden in game until a cut)")
    ap.add_argument("--tex", type=int, default=1024)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    wad = open(a.wad, "rb").read()
    blocks = list(wad_list.blocks(wad))
    if a.list:
        for o, t, f, s, n, d in blocks:
            if n.startswith("MG_") and s:
                segs = segments(d)
                print("%-28s %8d bytes  %3d segments  %6d vertices  %6d triangles" % (
                    n, s, len(segs), sum(g["nv"] for g in segs), sum(g["ni"] for g in segs) // 3))
        return
    names = a.mg or [n for o, t, f, s, n, d in blocks if n.startswith("MG_") and s]
    ts = open(a.ts, "rb").read() if a.ts else None
    images, glb_pieces = {}, []
    for o, t, f, s, n, d in blocks:
        if n not in names or not s:
            continue
        mats = model_materials(blocks, n)
        for name, P, UV, T, slot in pieces(d, n, a.pose):
            mat = mats[slot] if slot is not None and slot < len(mats) else None
            # Decapitation caps are drawn only when a limb or the head comes off.
            if mat and "decaps" in mat and not a.decaps:
                continue
            key = (None, None)
            if ts and mat:
                txs = material_textures(blocks, mat)
                roles = material_roles(blocks, mat)
                colour = roles.get(0x02) or (txs[0] if txs else None)
                if colour:
                    if colour not in images:
                        images[colour] = texture(blocks, ts, colour)
                    nm = None if a.no_normals else normal_texture(blocks, ts, [roles[0x07]] if 0x07 in roles else txs, images)
                    orm = None if a.no_orm else orm_texture(blocks, ts, roles, images)
                    key = (colour, nm, orm) if orm else (colour, nm)
            glb_pieces.append((name, P, UV, T, key))
    out = glb_pieces
    print("%d pieces, %d triangles" % (len(out), sum(len(p[3]) for p in out)))
    if a.glb and out:
        size = G.write_glb(a.glb, glb_pieces, images, a.tex)
        print("wrote %s (%.1f MB)" % (a.glb, size / 1e6))


if __name__ == "__main__":
    main()
