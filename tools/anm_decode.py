"""God of War: Ascension animations (ANM_ blocks) -- the parts read so far, toward a pose from the disc.

    python3 tools/anm_decode.py R_SPARTANAVS00.WAD --anm ANM_heroa --act uiEquipIdle [--skel goheroa]

For the 3D profile (ascension-online docs/ONLINE.md S9.6a); read 2026-11-04 against the game's own
sampler, SPU job module 216 (jobmod_759dedc8269b, entry 0xDDA8), replayed with an instruction trace.
Work in progress: the per-format kernels are being ported one by one (see KERNELS).

ANM block (big-endian):
- +0x20 u16 number of data types (13 for the hero), +0x22 u16 number of groups; +0x30 the groups,
  u64 offsets; at +0xDE8 the data types, 8 bytes each (u16 type, u16 param, u32 offset of the type's
  descriptor in the block; type 0 = the skeleton).
- group: +0x28 u32 number of acts, +0x30 name, +0x6C u32 act offsets (from the group).
- act: +0x2C name; +0x68 one 20-byte descriptor per data type (+0x0C u32 data offset from the act,
  +0x10 float seconds per frame); the skeleton data D = act + its offset (0x1C0 in uiEquipIdle).
- skeleton data D: +0x10 magic 43 44 01 07 E2 EF D3 58, +0x18 u32 size, +0x1C u16 2, +0x1E u16 frames,
  +0x2C float frames per second, +0x32 u16 frames, +0x34 float 1/(frames-1), +0x38 float frames-1;
  +0x40 the frame sets, 16 bytes each: u32 offset (from D+0x10), u16 size and u16 flags, ...;
  the game reads only the set it needs.
- a frame set (at D+0x10+offset): a bit mask (16 bytes of 0xFF in the first set, 32 in the next),
  then the section descriptors (offsets count from their start):
  u8 kind, u8 kernel id, u16 count (bit 15 a flag; the low bits a count of channels or frames),
  u16 stride, u16 offset, and for kinds 4/6 more bytes (see SECTION_LEN).
  The kernel id indexes the module's function table at LS 0xE850 (KERNELS).
- the channel buffer the kernels fill: 48 bytes per animation joint (scale, rotation quaternion,
  translation, each a quad); a section's u16 destinations are byte offsets in it.

Skeleton descriptor (type 0's descriptor): +0x00 u32 16, ..., +0x10 magic 4A 48 01 0A E2 EF D3 58,
+0x18 u32 size, +0x1C u16 joints (250); +0x28 a table of u32 offsets (from +0x10): [1] the rest pose
(48 bytes a joint: scale xyz0, quaternion xyzw, translation xyz0, in animation order), [7] the inverse
bind pose (3x4, rows), [10] u32 name hashes, [11]/[13] the face channels' FNV-1 hashes.
Animation order is not the skeleton's: the inverse bind matrices match the skeleton block's inverse
bind table one to one for every skinned joint (map_to_skeleton).
"""
import argparse, struct

KERNELS = {  # id -> (LS entry in module 216, what it does)
    0x15: (0x5DB8, "constant float3: N u16 destinations, then N x 12-byte floats -> (x, y, z, 0)"),
    0x16: (0x5C08, "constant, 16-bit halves (shift + x 2^112), 48-byte groups -> quads"),
    0x18: (0x60A8, "constant, quantized (cuflt with a scale)"),
    0x19: (0x5ED8, "constant (seen in the second frame set)"),
    0x0B: (0x63F8, "animated"), 0x1B: (0x6DC0, "animated"), 0x1D: (0xAC80, "animated"),
    0x1E: (0xAE90, "animated"), 0x0F: (0x96B0, "animated"), 0x10: (0x9838, "animated"),
}
SECTION_LEN = {3: 8, 4: 10, 6: 14}

u16 = lambda b, o: struct.unpack_from(">H", b, o)[0]
u32 = lambda b, o: struct.unpack_from(">I", b, o)[0]
f32 = lambda b, o: struct.unpack_from(">f", b, o)[0]


def acts(anm):
    out = []
    for i in range(u16(anm, 0x22)):
        g = struct.unpack_from(">Q", anm, 0x30 + 8 * i)[0]
        if g + 0x70 > len(anm) or u32(anm, g + 0x28) > 4000:
            continue
        gname = anm[g + 0x30:g + 0x50].split(b"\0")[0].decode("latin1")
        for k in range(u32(anm, g + 0x28)):
            a = g + u32(anm, g + 0x6C + 4 * k)
            out.append((anm[a + 0x2C:a + 0x50].split(b"\0")[0].decode("latin1"), gname, a))
    return out


def skeleton_data(anm, act):
    return act + u32(anm, act + 0x68 + 0x0C)


def frame_sets(anm, D):
    out = []
    for o in range(D + 0x40, D + 0x40 + 16 * 64, 16):
        off, size = u32(anm, o), u32(anm, o + 4)
        if off == 0xFFFFFFFF or off == 0 or off >= u32(anm, D + 0x18):
            break
        out.append((D + 0x10 + off, size >> 16))
    return out


def sections(anm, s):
    """The set starts with a bit mask (16 bytes in the first set, more in later ones); the
    descriptors follow at the next 16-byte line whose first byte is kind 3, and their offsets
    count from there."""
    o = s + 0x10
    while anm[o] != 3:
        o += 16
    out, base = [], o
    while anm[o] in SECTION_LEN:
        kind, kid, count, stride, off = anm[o], anm[o + 1], u16(anm, o + 2), u16(anm, o + 4), u16(anm, o + 6)
        out.append(dict(kind=kind, kernel=kid, count=count, stride=stride, at=base + off, raw=anm[o:o + SECTION_LEN[kind]]))
        o += SECTION_LEN[kind]
    return out


def kernel_15(anm, sec, buf):
    """constant float3: destinations then values; buf maps byte offset -> quad"""
    n = sec["count"] & 0x7FFF
    dst = [u16(anm, sec["at"] + 2 * i) for i in range(n)]
    vals = sec["at"] + ((2 * n + 15) & ~15)
    for i in range(n):
        buf[dst[i]] = struct.unpack_from(">3f", anm, vals + 12 * i) + (0.0,)


def skeleton_descriptor(anm):
    base = u32(anm, 0xDE8 + 4)                 # data type 0's descriptor
    B = base + 0x10
    n = u16(anm, B + 0x0C)
    offs = struct.unpack_from(">14I", anm, B + 0x28)
    rest = [struct.unpack_from(">12f", anm, B + offs[1] + 48 * k) for k in range(n)]
    invbind = [struct.unpack_from(">12f", anm, B + offs[7] + 48 * k) for k in range(n)]
    hashes = struct.unpack_from(">%dI" % n, anm, B + offs[10])
    return dict(joints=n, rest=rest, invbind=invbind, hashes=hashes)


def map_to_skeleton(desc, skel_invbind, tol=1e-3):
    """animation joint -> skeleton joint, by the inverse bind matrices (skinned joints are unique)"""
    m = {}
    for k, r in enumerate(desc["invbind"]):
        hits = [j for j, T in enumerate(skel_invbind)
                if max(abs(r[4 * row + col] - T[col][row]) for row in range(3) for col in range(3)) < tol
                and max(abs(r[4 * row + 3] - T[3][row]) for row in range(3)) < tol]
        if len(hits) == 1:
            m[k] = hits[0]
    return m


def main():
    import wad_list
    ap = argparse.ArgumentParser()
    ap.add_argument("wad"); ap.add_argument("--anm", default="ANM_heroa"); ap.add_argument("--act", default="uiEquipIdle")
    a = ap.parse_args()
    blocks = list(wad_list.blocks(open(a.wad, "rb").read()))
    anm = next(d for o, t, f, s, n, d in blocks if n == a.anm and s)
    act = next(x for x in acts(anm) if x[0] == a.act)[2]
    D = skeleton_data(anm, act)
    print("act %s at %#x, skeleton data %#x, %d frames at %.1f fps" % (a.act, act, D, u16(anm, D + 0x32), f32(anm, D + 0x2C)))
    for s, size in frame_sets(anm, D):
        print("  frame set %#x (%d bytes)" % (s, size))
        for sec in sections(anm, s):
            k = KERNELS.get(sec["kernel"], (0, "?"))
            print("    kind %d kernel %#04x (%#06x %s) count %#06x stride %d at %#x" % (
                sec["kind"], sec["kernel"], k[0], k[1][:30], sec["count"], sec["stride"], sec["at"]))
    desc = skeleton_descriptor(anm)
    print("skeleton descriptor: %d joints" % desc["joints"])


if __name__ == "__main__":
    main()
