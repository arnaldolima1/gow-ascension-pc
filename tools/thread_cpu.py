"""Host CPU of every thread of a running AscensionRecomp, by name, over a few seconds.

usage: python tools/thread_cpu.py --pid <pid> [--secs 5] [--out file.txt]

Reads each thread's user and kernel time (GetThreadTimes) at the start and the end
of the window and prints, per thread, its CPU as % of one core split user/kernel,
then per name (the names ps3_perf_thread_self gives: "SPU worker", "SPU task", ...)
the sum in cores. A thread that waits for real uses ~0 %; one that waits by spinning
shows high CPU (user for pause loops, kernel for SwitchToThread / Sleep(0) loops).

It also prints each thread's context switches a second and the process's page faults
(soft and hard) a second, the two usual sources of kernel time that no syscall count shows.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import struct
import time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
TH32CS_SNAPTHREAD = 0x4
THREAD_QUERY_LIMITED_INFORMATION = 0x800


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD),
                ("th32OwnerProcessID", wt.DWORD), ("tpBasePri", wt.LONG),
                ("tpDeltaPri", wt.LONG), ("dwFlags", wt.DWORD)]


k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.OpenThread.restype = wt.HANDLE
k32.GetThreadDescription.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
k32.GetThreadDescription.restype = ctypes.c_long


def thread_ids(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32()
    te.dwSize = ctypes.sizeof(te)
    ids = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            ids.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return ids


def parse_spi(buf, pid):
    """(faults, hard faults, {tid: context switches}) of pid in a
    SYSTEM_PROCESS_INFORMATION buffer (x64 layout), or None if it is not there."""
    off = 0
    while off + 0x100 <= len(buf):
        nxt, nthreads = struct.unpack_from("<II", buf, off)
        if struct.unpack_from("<Q", buf, off + 0x50)[0] == pid:
            hard = struct.unpack_from("<I", buf, off + 0x10)[0]
            faults = struct.unpack_from("<I", buf, off + 0x80)[0]
            cs = {}
            for i in range(nthreads):
                t = off + 0x100 + i * 0x50
                cs[struct.unpack_from("<Q", buf, t + 0x30)[0]] = struct.unpack_from("<I", buf, t + 0x40)[0]
            return faults, hard, cs
        if not nxt:
            return None
        off += nxt
    return None


def proc_counters(pid):
    """parse_spi for the live system; None if the call fails (the CPU table still prints)."""
    try:
        nt = ctypes.WinDLL("ntdll")
        size = 1 << 22
        while size <= 1 << 28:
            buf = ctypes.create_string_buffer(size)
            need = wt.ULONG()
            st = nt.NtQuerySystemInformation(5, buf, size, ctypes.byref(need)) & 0xFFFFFFFF
            if st == 0:
                return parse_spi(buf.raw, pid)
            if st != 0xC0000004:       # STATUS_INFO_LENGTH_MISMATCH
                return None
            size *= 2
    except (OSError, struct.error):
        pass
    return None


def ft(f):
    return (f.dwHighDateTime << 32) | f.dwLowDateTime


def sample(pid, handles):
    out = {}
    for tid in thread_ids(pid):
        h = handles.get(tid)
        if h is None:
            h = k32.OpenThread(THREAD_QUERY_LIMITED_INFORMATION, False, tid)
            if not h:
                continue
            handles[tid] = h
        c, e, k, u = wt.FILETIME(), wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
        if k32.GetThreadTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
            out[tid] = (ft(u), ft(k))
    return out


def name(h):
    p = ctypes.c_wchar_p()
    if k32.GetThreadDescription(h, ctypes.byref(p)) >= 0 and p.value:
        s = p.value
        k32.LocalFree(p)
        return s
    return "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--secs", type=float, default=5)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    handles = {}
    t0 = time.perf_counter()
    s0 = sample(a.pid, handles)
    c0 = proc_counters(a.pid)
    time.sleep(a.secs)
    s1 = sample(a.pid, handles)
    c1 = proc_counters(a.pid)
    dt = (time.perf_counter() - t0) * 1e7      # 100 ns units

    rows = []
    for tid, (u1, k1) in s1.items():
        u0, k0 = s0.get(tid, (0, 0))
        rows.append((100.0 * (u1 - u0) / dt, 100.0 * (k1 - k0) / dt, tid, name(handles[tid])))
    rows.sort(key=lambda r: r[0] + r[1], reverse=True)

    lines = [f"thread CPU over {a.secs:g} s, % of one core (user + kernel)"]
    groups = {}
    for u, k, tid, n in rows:
        g = groups.setdefault(n, [0.0, 0.0, 0])
        g[0] += u; g[1] += k; g[2] += 1
        if u + k >= 0.5:
            sw = f"{(c1[2].get(tid, 0) - c0[2].get(tid, 0)) / a.secs:8.0f}/s" if c0 and c1 else ""
            lines.append(f"  {u + k:6.1f}%  user {u:5.1f}  kern {k:5.1f}  tid {tid:6d}  cs {sw}  {n}")
    lines.append("per name, cores (user + kernel):")
    for n, (u, k, c) in sorted(groups.items(), key=lambda kv: kv[1][0] + kv[1][1], reverse=True):
        lines.append(f"  {(u + k) / 100:5.2f}  user {u / 100:5.2f}  kern {k / 100:5.2f}  x{c:<3d} {n}")
    tu = sum(r[0] for r in rows); tk = sum(r[1] for r in rows)
    lines.append(f"  {(tu + tk) / 100:5.2f}  user {tu / 100:5.2f}  kern {tk / 100:5.2f}  total")
    if c0 and c1:
        lines.append(f"page faults {(c1[0] - c0[0]) / a.secs:.0f}/s (hard {(c1[1] - c0[1]) / a.secs:.0f}/s)")
    else:
        lines.append("page faults and context switches: not available")
    text = "\n".join(lines)
    print(text)
    if a.out:
        with open(a.out, "w") as f:
            f.write(text + "\n")
    for h in handles.values():
        k32.CloseHandle(h)


if __name__ == "__main__":
    main()
