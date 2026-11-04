"""Lay the per-frame dependency chain out in time, from a run log.

usage: python tools/frame_timeline.py build/logs/<run>.log [--frames 200] [--show 3]

Run the game with (scripts/windows/run.ps1 -Env @{...}):
    SPU_ATOM_EA=99AA80 SPU_ATOM_EA_MAX=1 PPU_WWATCH=99AA80 PPU_WWATCH_LEN=0x80
    PPU_WWATCH_MAX=300000 GCM_REPORTLOG=1000000   [VDEC_TIMELOG=1] [SPU_TASK_TIMELOG=1]
The 128-byte line at 0x99AA80 holds the frame's dependency counters
(0x99AA84 + 4f), MeshProc's (0x99AAA4), the EDGE lists' (0x99AAB0 + 4i) and the
frame slots the render thread waits on (0x99AAC0 + 4i); the PPU starts frame f
by writing f to 0x99AAA0. For the last --frames frames, prints the median time
from the frame's start to each link: the GPU's last report of the frame, the
RsxSync workload (wid 18), MeshProc (wid 14), the EDGE lists (wid 15-17), and the
video picture taken (VDEC_TIMELOG). --show prints the raw events of that many
frames too. With SPURS_WID_TIMELOG=<us> it also prints, per workload, the SPU
time its policy-module runs took in a frame and when they started and ended.
With RSX_FIFO_TIMELOG=<from s>[:<for s>] (ps3kit gpu/bridge) it keeps the frames
inside that window and splits the RSX thread's time between the EDGE passes
into waits (FIFO empty, semaphore, report hold, ZCULL sync, flip) and drawing.
"""
import argparse
import bisect
import collections
import re
import statistics


def parse(path):
    ev = []
    for l in open(path, encoding="utf-8", errors="ignore"):
        m = re.search(r"\[atom-ea\] t=(\d+)us PUTLLC OK lr=0x(\w+) ea=0x\w+ wid=(\d+) RAM=(.*)", l)
        if m:
            ev.append((int(m.group(1)), "S", (int(m.group(3)), m.group(2), m.group(4).split()))); continue
        m = re.search(r"\[ww\] t=(\d+)us 0x(\w+) <- 0x(\w+) .*guest-fn=0x(\w+)", l)
        if m:
            ev.append((int(m.group(1)), "P", (int(m.group(2), 16), int(m.group(3), 16), m.group(4)))); continue
        m = re.search(r"\[GET_REPORT\] t=(\d+)us type=(\d+) off=0x(\w+)", l)
        if m:
            ev.append((int(m.group(1)), "R", (int(m.group(2)), int(m.group(3), 16)))); continue
        m = re.search(r"\[rsx-report\] t=(\d+)us ea=0x(\w+) awaited=(\d)", l)
        if m:
            ev.append((int(m.group(1)), "G", (int(m.group(2), 16), int(m.group(3))))); continue
        m = re.search(r"\[rsx-fifo\] t=(\d+)us (\w+) a=0x(\w+) b=0x(\w+) d=(\d+)us", l)
        if m:
            ev.append((int(m.group(1)), "F", (m.group(2), int(m.group(3), 16), int(m.group(4), 16), int(m.group(5))))); continue
        m = re.search(r"\[vdec-time\] t=(\d+)us", l)
        if m:
            ev.append((int(m.group(1)), "V", ())); continue
        m = re.search(r"\[wid-time\] t=(\d+)us d=(\d+)us wid=(\d+) spu=(\d+)", l)
        if m:
            ev.append((int(m.group(1)), "W", (int(m.group(3)), int(m.group(4)), int(m.group(2))))); continue
        m = re.search(r"\[task-time\] t=(\d+)us (enter|exit) task=(\d+)", l)
        if m:
            ev.append((int(m.group(1)), "T", (int(m.group(3)), m.group(2))))
    ev.sort()
    return ev


def edge_passes(seg, s, wruns):
    """The EDGE list of the frame (wid 15-17, one per frame in turn) runs in two
    passes of long runs, the second released by RsxSync. Their spans, the gap
    between them, how idle the SPUs were in that gap, and the RSX reports in it."""
    out = {}
    lg = sorted((x[0], x[0] + x[2][2]) for x in seg if x[1] == "W" and x[2][0] in (15, 16, 17) and x[2][2] >= 500)
    if not lg:
        return out
    p1 = [r for r in lg if r[0] < lg[0][0] + 3000]
    p1e = max(r[1] for r in p1)
    p2 = [r for r in lg if r[0] > p1e]
    rel = lambda t: (t - s) / 1000
    out["EDGE pass 1 start"] = rel(lg[0][0])
    out["EDGE pass 1 end"] = rel(p1e)
    long_end = [x[0] + x[2][2] for x in seg if x[1] == "W" and x[2][2] >= 500]
    if p2:
        p2s, p2e = p2[0][0], max(r[1] for r in p2)
        out["EDGE pass 2 start"] = rel(p2s)
        out["EDGE pass 2 end"] = rel(p2e)
        out["gap pass 1 -> 2"] = (p2s - p1e) / 1000
        nspu = len({r[3] for r in wruns[-5000:]}) or 6
        lo = bisect.bisect_left(wruns, (p1e - 30000,))
        hi = bisect.bisect_left(wruns, (p2s,))
        busy = sum(max(0, min(e, p2s) - max(b, p1e)) for b, e, _, _ in wruns[lo:hi] if e > p1e)
        out["SPU busy % in that gap"] = 100 * busy / max(1, (p2s - p1e) * nspu)
        g = [x[0] for x in seg if x[1] == "G" and p1e <= x[0] < p2s]
        if g:
            out["RSX report in gap (first)"] = rel(g[0])
            out["RSX report in gap (last)"] = rel(g[-1])
            out["last report -> pass 2"] = (p2s - g[-1]) / 1000
    if long_end:
        out["last long SPU run end"] = rel(max(long_end))
    if p2:
        out.update(rsx_split(seg, p1e, p2s, g[0] if p2 and g else None))
    return out


# RSX_FIFO_TIMELOG: each wait is logged at its end with its length; "run" ends an idle FIFO
FIFO_WAITS = {"run": "idle (FIFO empty)", "sema": "semaphore acquire", "hold": "report hold",
              "zsync": "ZCULL sync", "flip": "flip"}


def rsx_split(seg, a, b, first_report):
    """What the RSX thread did between EDGE pass 1's end (a) and pass 2's start
    (b), and before the first awaited report in the gap: ms in each
    wait, the rest is drawing. Also when the put first moved after pass 1."""
    f = [x for x in seg if x[1] == "F"]
    if not f:
        return {}
    out = {}
    spans = [("gap", a, b)]
    if first_report:
        spans.append(("before 1st awaited report", a, first_report))
    for name, lo, hi in spans:
        if hi <= lo:
            continue
        used = 0
        for k, label in FIFO_WAITS.items():
            ms = sum(max(0, min(hi, x[0]) - max(lo, x[0] - x[2][3])) for x in f if x[2][0] == k) / 1000
            used += ms
            out[f"RSX {name}: {label}"] = ms
        out[f"RSX {name}: drawing"] = max(0.0, (hi - lo) / 1000 - used)
    puts = [x[0] for x in f if x[2][0] == "put" and x[0] >= a]
    if puts:
        out["put moves, first after pass 1"] = (puts[0] - a) / 1000
    out["put moves in the gap"] = sum(1 for x in f if x[2][0] == "put" and a <= x[0] < b)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("--end-us", type=int, default=0,
                    help="only frames that start before this log time (us), e.g. where a capped log stops")
    a = ap.parse_args()
    ev = parse(a.log)
    starts = [e[0] for e in ev if e[1] == "P" and e[2][0] == 0x99AAA0]
    fifo = [e[0] for e in ev if e[1] == "F"]
    if fifo:   # RSX_FIFO_TIMELOG logs a window: keep the frames inside it
        starts = [t for t in starts if fifo[0] <= t <= fifo[-1]]
    if len(starts) < 3:
        raise SystemExit("no frame starts (PPU writes to 0x99AAA0) in the log: see the usage for the variables")
    if a.end_us:
        starts = [t for t in starts if t < a.end_us]
    starts = starts[-(a.frames + 1):]
    wruns = sorted((x[0], x[0] + x[2][2], x[2][0], x[2][1]) for x in ev if x[1] == "W")
    rows = []
    wids = collections.defaultdict(list)   # wid -> per frame (busy ms, first start, last end)
    for fi, (s, e) in enumerate(zip(starts, starts[1:])):
        seg = [x for x in ev if s <= x[0] < e]
        rel = lambda x: (x[0] - s) / 1000

        def first(pred):
            return next((rel(x) for x in seg if pred(x)), None)

        def last(pred):
            v = [rel(x) for x in seg if pred(x)]
            return v[-1] if v else None
        rows.append({
            "frame": (e - s) / 1000,
            "gpu last report": first(lambda x: x[1] == "R" and x[2][0] == 255),
            "RsxSync (wid 18)": first(lambda x: x[1] == "S" and x[2][0] == 18),
            "MeshProc done (wid 14)": last(lambda x: x[1] == "S" and x[2][0] == 14),
            "EDGE done (wid 15-17)": last(lambda x: x[1] == "S" and x[2][0] in (15, 16, 17)),
            "video picture": first(lambda x: x[1] == "V"),
            "tasks first wake": first(lambda x: x[1] == "T" and x[2][1] == "exit"),
            "tasks last park": last(lambda x: x[1] == "T" and x[2][1] == "enter"),
            "RSX report, first awaited": first(lambda x: x[1] == "G" and x[2][1]),
        })
        rows[-1].update(edge_passes(seg, s, wruns))
        # time each task spent out of WAIT_SIGNAL in this frame
        busy, out = collections.Counter(), {}
        for x in seg:
            if x[1] != "T":
                continue
            tid, what = x[2]
            if what == "exit":
                out[tid] = x[0]
            elif tid in out:
                busy[tid] += x[0] - out.pop(tid)
        rows[-1]["task busy sum"] = sum(busy.values()) / 1000 if busy else None
        per = collections.defaultdict(lambda: [0.0, None, None])
        for x in seg:
            if x[1] != "W":
                continue
            w, _, d = x[2]
            p = per[w]
            p[0] += d / 1000
            p[1] = rel(x) if p[1] is None else p[1]
            p[2] = rel(x) + d / 1000
        for w, p in per.items():
            wids[w].append(p)
        if fi >= len(starts) - 1 - a.show:
            print(f"--- frame of {(e - s) / 1000:.1f} ms")
            for x in seg:
                kind = {"G": "RSX", "R": "GPU", "S": "SPU", "P": "PPU", "V": "VID", "T": "TSK", "W": "WID"}[x[1]]
                if x[1] == "W":
                    print(f"  {rel(x):7.2f} WID wid={x[2][0]} spu={x[2][1]} ran {x[2][2] / 1000:.2f} ms")
                    continue
                print(f"  {rel(x):7.2f} {kind} {x[2] if x[1] != 'S' else ('wid', x[2][0], 'lr', x[2][1])}")
    print(f"{len(rows)} frames; ms from the frame's start (median, and in how many frames it happened):")
    keys = list(dict.fromkeys(k for r in rows for k in r))
    w = max(24, *(len(k) for k in keys))
    for k in keys:
        v = [r[k] for r in rows if r.get(k) is not None]
        if v:
            print(f"  {k:{w}} {statistics.median(v):7.1f}   ({len(v)}/{len(rows)})")
    if wids:
        print("workload runs per frame (SPURS_WID_TIMELOG; median ms: SPU time, first start, last end):")
        for w in sorted(wids, key=lambda w: -statistics.median([p[0] for p in wids[w]])):
            v = wids[w]
            print(f"  wid {w:3}  busy {statistics.median([p[0] for p in v]):7.1f}  first {statistics.median([p[1] for p in v]):7.1f}"
                  f"  last end {statistics.median([p[2] for p in v]):7.1f}   ({len(v)}/{len(rows)})")
    fr = sorted(r["frame"] for r in rows)
    print("frame time p10/p50/p90:", f"{fr[len(fr)//10]:.1f} / {fr[len(fr)//2]:.1f} / {fr[len(fr)*9//10]:.1f} ms")


if __name__ == "__main__":
    main()
