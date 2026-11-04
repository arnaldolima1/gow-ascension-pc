"""Lab for the animation decoder port (ascension-online docs/ONLINE.md S9.6a): fit the animated
fields of an act against the game's own sampler (SPU module 216), from captured jobs.

1. Capture module 216 in the MP lobby (the warrior plays uiEquipIdle there):
     SPU_JOBCAP=<dir>,216,DDA8,300,0,<seconds until the lobby>
   (or point a running capture at it with lldb, tools/lldb_guest.py).
2. Pick one job per distinct bitstream window and copy them as job_0000.sjc, job_0001.sjc, ...:
     python tools/anm_lab.py pick <capture dir> <lab dir> --window-lsa 0x16fa0
3. Replay them interpreted with a trace of kernel 0x1B's loads/stores (ps3kit SPU_ITRACE_EA):
     SPU_JOB_REPLAY=<lab dir>,5,1 SPU_NOLIFT_IMG=216 SPU_ITRACE_MOD=43f35c02
     SPU_ITRACE_LO=6DC0 SPU_ITRACE_HI=7000 SPU_ITRACE_EA=1 SPU_ITRACE_MAX=20000000
     <exe> input/EBOOT.ELF 2> <lab dir>/trace.log
4. Fit every field (bit split into x, y, z and v = q * step + min per component):
     python tools/anm_lab.py fit <lab dir> [--act-data-ea <EA of the act's skeleton data D>]
   D is where the act's skeleton data sits in the game's memory (the window GETs read D+0x1ED0..);
   in the 2026-11-04 Mac run D = 0x77FE7F80 (uiEquipIdle). The first frame record of the windows
   was at D+0x1EDC; records are 34 bytes. Without --act-data-ea the record alignment is found
   from the data (the one of the 34 where field 0 fits exactly).

Findings so far (2026-11-04): fields 0, 1, 2, 18, 24-30 fit exactly; 3-17 and 19-23 do not (not sign,
not component order): probably deltas over a base in sections 0x1D/0x1E.
"""
import argparse, glob, os, re, shutil, struct

WIDTHS = [0x1a, 0x1a, 4, 0, 7, 0, 0x10, 0xf, 0x13, 0x10, 0xc, 9, 0xc, 0xc, 3, 4, 5, 5, 0xc, 5, 6, 6, 6, 6,
          8, 8, 3, 3, 2, 0, 9, 0]       # uiEquipIdle, frame set 0: the 0x0B section's header bytes
RECORD = 34


def chunks(path):
    d = open(path, "rb").read(); off = 16
    while off + 16 <= len(d):
        tag, a, b, size = struct.unpack_from("<IIII", d, off)
        yield tag, a, b, d[off + 16:off + 16 + size]
        off += 16 + size
        if tag == 4:
            break


def window(path, lsa):
    for tag, a, b, data in chunks(path):
        if tag == 2 and a == lsa and len(data) == 96:
            return b, data
    return None


def pick(src, dst, lsa):
    os.makedirs(dst, exist_ok=True)
    seen, n = set(), 0
    for p in sorted(glob.glob(os.path.join(src, "job_*.sjc"))):
        w = window(p, lsa)
        if w and w[0] not in seen:
            seen.add(w[0])
            shutil.copy(p, os.path.join(dst, "job_%04d.sjc" % n)); n += 1
    print("%d jobs with distinct windows -> %s" % (n, dst))


def trace_jobs(log):
    pat = re.compile(r"\[itrace-ea\] pc=([0-9A-F]{5}) S ([0-9A-F]{5}) ([0-9A-F]{32})")
    jobs, cur = [], []
    for line in open(log, "rb"):
        l = line.decode("latin1")
        if l.startswith("[replay] job_") and ("HALTED" in l or "returned" in l):
            jobs.append(cur); cur = []
            continue
        m = pat.search(l)
        if m:
            cur.append((int(m.group(1), 16), int(m.group(2), 16), bytes.fromhex(m.group(3))))
    return jobs


def first_invocation(stores):
    inv, prev = {}, 0
    for pc, ea, v in stores:
        if inv and ea < prev - 0x80 and ea <= 0x34C00:
            break
        inv[ea] = v; prev = ea
    return inv


def fit_field0(lab, jobs, r0, lsa, out_base):
    samples = []
    for n, st in enumerate(jobs):
        w, data = window(os.path.join(lab, "job_%04d.sjc" % n), lsa)
        rec = r0 + RECORD * ((w - r0) // RECORD)
        while rec < w:
            rec += RECORD
        o = rec - w
        if o + 2 * RECORD > len(data):
            continue
        inv = first_invocation(st)
        for fi in range(2):
            ea = out_base + 16 * fi
            if ea in inv:
                x = int.from_bytes(data[o + RECORD * fi:o + RECORD * fi + 4], "big") >> (32 - WIDTHS[0])
                samples.append((x, struct.unpack(">4f", inv[ea])[:3]))
    if len(samples) < 6:
        return 9.0
    best = 9.0
    for a in range(WIDTHS[0] + 1):
        for b in range(WIDTHS[0] + 1 - a):
            c = WIDTHS[0] - a - b
            f = lambda x: (x >> (b + c), (x >> c) & ((1 << b) - 1), x & ((1 << c) - 1))
            best = min(best, max(lsq([(f(x)[k], v[k]) for x, v in samples])[2] for k in range(3)))
    return best


def lsq(pts):
    n = len(pts); sx = sum(p for p, _ in pts); sy = sum(q for _, q in pts)
    sxx = sum(p * p for p, _ in pts); sxy = sum(p * q for p, q in pts)
    den = n * sxx - sx * sx
    if den == 0:
        return 0.0, sy / n, max(abs(q - sy / n) for _, q in pts)
    s = (n * sxy - sx * sy) / den; m = (sy - s * sx) / n
    return s, m, max(abs(q - (s * p + m)) for p, q in pts)


def fit(lab, D, lsa, out_base=0x34BE0):
    jobs = trace_jobs(os.path.join(lab, "trace.log"))
    if D is None:                       # find the record alignment: the one where field 0 fits
        w0 = window(os.path.join(lab, "job_0000.sjc"), lsa)[0]
        best = None
        for k in range(RECORD):
            err = fit_field0(lab, jobs, w0 + k, lsa, out_base)
            if best is None or err < best[0]:
                best = (err, w0 + k)
        r0 = best[1]
        print("record alignment found: first record at EA %#x (field 0 error %.1e)" % (r0, best[0]))
    else:
        r0 = D + 0x1EDC
    per = []
    for n, st in enumerate(jobs):
        w, data = window(os.path.join(lab, "job_%04d.sjc" % n), lsa)
        rec = r0 + RECORD * ((w - r0) // RECORD)
        while rec < w:
            rec += RECORD
        per.append((first_invocation(st), data, rec - w))
    boff = 0
    for i, wd in enumerate(WIDTHS):
        samples = []
        for inv, data, o in per:
            for fi in range(2):
                ea = out_base + 32 * i + 16 * fi
                if ea in inv:
                    r = int.from_bytes(data[o + RECORD * fi:o + RECORD * fi + RECORD], "big")
                    x = (r >> (8 * RECORD - boff - wd)) & ((1 << wd) - 1) if wd else 0
                    samples.append((x, struct.unpack(">4f", inv[ea])[:3]))
        best = None
        for a in range(wd + 1):
            for b in range(wd + 1 - a):
                c = wd - a - b
                f = lambda x: (x >> (b + c), (x >> c) & ((1 << b) - 1), x & ((1 << c) - 1))
                res = [lsq([(f(x)[k], v[k]) for x, v in samples]) for k in range(3)]
                err = max(e for _, _, e in res)
                if best is None or err < best[0]:
                    best = (err, (a, b, c), [(s, m) for s, m, _ in res])
        print("field %2d w%2d bit%3d err %.1e split %s %s" % (i, wd, boff, best[0], best[1],
              ["%.4g*q%+.4g" % (s, m) for s, m in best[2]]))
        boff += wd


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("pick"); p.add_argument("src"); p.add_argument("dst"); p.add_argument("--window-lsa", type=lambda x: int(x, 0), default=0x16FA0)
    f = sub.add_parser("fit"); f.add_argument("lab"); f.add_argument("--act-data-ea", type=lambda x: int(x, 0), default=None, help="default: found from the data")
    f.add_argument("--window-lsa", type=lambda x: int(x, 0), default=0x16FA0)
    a = ap.parse_args()
    if a.cmd == "pick":
        pick(a.src, a.dst, a.window_lsa)
    elif a.cmd == "fit":
        fit(a.lab, a.act_data_ea, a.window_lsa)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
