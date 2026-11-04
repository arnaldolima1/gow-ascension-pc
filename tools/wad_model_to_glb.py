"""A model straight from the player's own WAD (no game running): EDGE segments to GLB.

    python3 tools/wad_model_to_glb.py R_SPARTANAVS00.WAD --mg MG_70b97feb_0 --glb body.glb
        [--ts R_SPARTANAVS00.TS --material MAT_body_skin_layered] [--list]

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
- indices in EDGE's compressed format (ps3kit libs/spu_hle/gowa_drawcmd/indices.h);
- before the segment, the RSX attribute table: entries (u32 size, s32 self-relative pointer,
  u32 tag), tag byte 0 the role (0x0A texcoord 0 = RSX attribute 2, 0x0B texcoord 1, 0x09 colour)
  and stride = (tag >> 9) & 0x7F; the UVs are float2, not packed.
Segments with flags 0x86 have another vertex format (shadow geometry?) and are skipped.

Textures: a TX<hash>.<hash>.dds block holds a DDS header at +0x50 and the small mip levels after
it (+0xD8); +0x3C is the offset of the large levels in the .TS beside the WAD (0xFFFFFFFF: all in
the WAD), +0x40 the number of levels kept in the WAD. A MAT_ block names its textures; the first
is the colour map. Which material a segment uses is chosen by the game (the warrior's skin and
armour are equipment): not in the mesh group, still to read (S9.4).
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
    return out


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


def pieces(mg, tag):
    out = []
    for g in segments(mg):
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
        uv = uv_stream(mg, g["c"])
        UV = [struct.unpack_from(">2f", mg, uv[0] + uv[1] * i) for i in range(nv)] if uv else None
        T = [t for t in T if max(t) < nv]
        if T:
            out.append(("%s_%05X" % (tag, g["c"]), P, UV, T))
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
    ap.add_argument("--material", default="MAT_body_skin_layered",
                    help="colour map for the pieces whose UVs are negative (the body's skin atlas); a preview until S9.4")
    ap.add_argument("--head-material", help="colour map for the pieces whose UVs are in 0..1 (default: the first MAT_ of the model's group)")
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
    out = []
    for o, t, f, s, n, d in blocks:
        if n in names and s:
            out += pieces(d, n)
    # Which material a segment uses is the game's choice (S9.4). Until then: the body's pieces map
    # into the skin atlas with u in -1..0, the head's (face, eyes, mouth) with u in 0..1.
    images, skin_key, head_key = {}, (None, None), (None, None)
    if a.ts:
        ts = open(a.ts, "rb").read()
        head_mat = a.head_material
        if not head_mat:
            idx = next((i for i, b in enumerate(blocks) if b[4].startswith("MDL_") and b[3] and
                        any(b[4][4:].lower() in m.lower() for m in names)), None)
            if idx is not None:
                head_mat = next((blocks[k][4] for k in range(idx + 1, len(blocks)) if blocks[k][4].startswith("MAT_")), None)
        for mat, which in ((a.material, "skin"), (head_mat, "head")):
            try:
                tx = material_textures(blocks, mat)[0]
            except (StopIteration, IndexError, TypeError):
                continue
            images[tx] = texture(blocks, ts, tx)
            if which == "skin":
                skin_key = (tx, None)
            else:
                head_key = (tx, None)
    glb_pieces = [(n, P, UV, T, head_key if UV and head_key[0] and min(u[0] for u in UV) >= -0.001 else skin_key)
                  for n, P, UV, T in out]
    print("%d pieces, %d triangles" % (len(out), sum(len(p[3]) for p in out)))
    if a.glb and out:
        size = G.write_glb(a.glb, glb_pieces, images, a.tex)
        print("wrote %s (%.1f MB)" % (a.glb, size / 1e6))


if __name__ == "__main__":
    main()
