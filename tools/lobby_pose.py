"""The pose a model had in a running game, from an SPU job capture: its skinning palettes.

    python3 tools/wad_model_to_glb.py R_SPARTANAVS00.WAD --mg MG_70b97feb_0 --ts R_SPARTANAVS00.TS \
        --pose <SPU_JOBCAP dir> --glb warrior_lobby.glb

For the 3D profile (ascension-online docs/ONLINE.md, S9). Capture the jobs in the lobby with
SPU_JOBCAP=<dir>,218,AD98,1500 (ps3kit runtime/spu/spu_jobcap.c); the files stay on that PC.

Read 2026-11-04 against the RSX draw dump (the posed positions agree to ~1 mm):
- a record ("SJC1") holds the job's local store at its start (tag 1); the job's input DMA list is
  22 (size, EA) entries at LS 0x1CF50 (buffers from 0x11000) or 0x28F50 (from 0x1D000), the
  buffers back to back (ascension-native/gowa_drawcmd/NOTES.md);
- entry 11 is the segment's vertex stream, byte for byte the MG_ block's (that is how a job is tied
  to its segment), entry 10 its bone bytes (the MG_ block's skin stream, C+0x40);
- entries 6 and 7, back to back, are the palette: 64-byte records, a column-major 4x4 of big-endian
  floats (out = c0 * x + c1 * y + c2 * z + c3), world space;
- bone bytes are 8 a vertex: weight, bone, weight, bone ... (weight / 255), as ps3kit job.c
  `job_skin` (0xE550) reads them;
- the palette is two runs of the model's joint matrix array (one per entry), written in the
  segment's descriptor on the disc: C+0x34 u16 byte offsets of the two runs (joint * 64), C+0x38
  u16 their sizes in bytes; the joints are the skeleton's (the object block after `go<name>`:
  250 joints, records of u16 flags, first child, next sibling, parent at +0x24, names of 56 bytes
  at +0x7F4, 4x4 tables at +0x4BE0 (local, in the joints' own frames) and +0x8A60 (the inverse
  bind pose in world space)); in the lobby capture the array starts at EA 0x71BB48E0;
- a segment with no palette (the small rigid pieces of the head) is placed by the RSX vertex
  program, not the job: here each of its vertices takes the blended matrix of the nearest skinned
  vertex in the bind pose.
"""
import glob, os, struct

LS = 256 * 1024


def _local_store(path):
    data = open(path, "rb").read()
    if data[:4] != b"SJC1":
        return None
    off = 16
    while off + 16 <= len(data):
        tag, a, b, size = struct.unpack_from("<IIII", data, off)
        if tag == 1:
            return data[off + 16 + 2048:off + 16 + 2048 + LS]
        if tag == 4:
            break
        off += 16 + size
    return None


def _buffers(ls):
    for region, at in ((0x11000, 0x1CF50), (0x1D000, 0x28F50)):
        lsa, buf = region, {}
        for i in range(22):
            w0, ea = struct.unpack_from(">II", ls, at + 8 * i)
            size = w0 & 0xFFFF
            if size:
                buf[i] = ls[lsa:lsa + size]
            lsa += size
        yield buf


class Pose:
    def __init__(self, jobcap_dir, mg, segments):
        by_stream = {mg[g["vp"]:g["vp"] + 64]: g for g in segments}
        self.jobs = {}
        for path in sorted(glob.glob(os.path.join(jobcap_dir, "job_*.sjc"))):
            ls = _local_store(path)
            if ls is None:
                continue
            for buf in _buffers(ls):
                g = by_stream.get(buf.get(11, b"")[:64])
                if g and g["c"] not in self.jobs:   # the first frame's job for each segment
                    self.jobs[g["c"]] = buf
        self.mats = {}    # segment -> per-vertex blended 3x4 (rows), for the rigid pieces
        self.bind = {}

    def skin(self, g, P):
        buf = self.jobs.get(g["c"])
        if not buf or 6 not in buf or 10 not in buf:
            return None
        pal = buf[6] + buf.get(7, b"")
        cols = [struct.unpack_from(">16f", pal, 64 * i) for i in range(len(pal) // 64)]
        bones = buf[10]
        out, mats = [], []
        for i, p in enumerate(P):
            m = [0.0] * 12   # rows: m[4k..4k+3] = (x, y, z, translation) for output k
            for j in range(4):
                w, b = bones[8 * i + 2 * j], bones[8 * i + 2 * j + 1]
                if not w or b >= len(cols):
                    continue
                c, w = cols[b], w / 255.0
                for k in range(3):
                    m[4 * k] += w * c[k]
                    m[4 * k + 1] += w * c[4 + k]
                    m[4 * k + 2] += w * c[8 + k]
                    m[4 * k + 3] += w * c[12 + k]
            mats.append(m)
            out.append(_apply(m, p))
        self.mats[g["c"]], self.bind[g["c"]] = mats, P
        return out

    def rigid(self, P):
        """Each vertex by the matrix of the nearest skinned vertex (bind pose)."""
        ref = [(q, m) for c in self.mats for q, m in zip(self.bind[c], self.mats[c])]
        if not ref:
            return P
        out = []
        for p in P:
            q, m = min(ref, key=lambda r: (r[0][0] - p[0]) ** 2 + (r[0][1] - p[1]) ** 2 + (r[0][2] - p[2]) ** 2)
            out.append(_apply(m, p))
        return out


def _apply(m, p):
    return tuple(m[4 * k] * p[0] + m[4 * k + 1] * p[1] + m[4 * k + 2] * p[2] + m[4 * k + 3] for k in range(3))
