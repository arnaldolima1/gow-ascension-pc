"""Look inside the running game from lldb: dump guest memory, watch a guest address.

The guest's memory is the host process's, from `vm_base` (0x300000000 on the Mac build), so a
guest EA is host vm_base + EA. Attach without stopping the game for long:

    lldb -p $(pgrep -x AscensionRecomp) --batch -o "command script import tools/lldb_guest.py" \
        -o "script lldb_guest.dump(lldb.debugger, 0x70000000, 0x8000000, 'heap70.bin')"
    lldb -p $(pgrep -x AscensionRecomp) --batch -o "command script import tools/lldb_guest.py" \
        -o "script lldb_guest.watch(lldb.debugger, 0x71BB4B20, secs=20, write=True)"

`watch` stops at the first access (hardware watchpoint) and prints the host backtrace: lifted
PPU functions show as func_<EA>, SPU code as jobmod_<hash>_e<entry>_spu_func_<LS> (a DMA shows
as mfc_do_transfer under the job's function). The runtime's own page faults (EXC_BAD_ACCESS in
func_0040CE58 and others) are continued and counted.

Careful: with the RPCS3 RSX (PS3_RSX=rpcs3) the guest memory is RPCS3's vm at 0xb00000000, not
VM_BASE (pass the base you need), and stopping the process even briefly can kill the game (RSX
write faults after the detach, 2026-11-05): read what you need in one attach.

A running SPU_JOBCAP capture can be pointed elsewhere with lldb expressions on the statics of
ps3kit runtime/spu/spu_jobcap.c (s_dir, s_ovl, s_entry, s_ovl2, s_entry2, s_max, s_after_us,
s_skip, then s_jobs = 0 last), e.g. module 217 = `*(int*)&s_ovl = 217`, `*(unsigned*)&s_entry =
0xBB40`; the overlay ids and entries are in src/spu/jobmods_register.c.
Found this way (2026-11-04, ascension-online S9): module 217 builds the joint palette.
"""
import lldb, threading, time

VM_BASE = 0x300000000


def dump(debugger, ea, size, path, chunk=0x100000):
    p = debugger.GetSelectedTarget().GetProcess()
    ok = 0
    with open(path, "wb") as out:
        for off in range(0, size, chunk):
            e = lldb.SBError()
            b = p.ReadMemory(VM_BASE + ea + off, chunk, e)
            if e.Success() and b:
                out.write(b); ok += 1
            else:
                out.write(b"\0" * chunk)
    print("chunks read", ok, "of", (size + chunk - 1) // chunk)
    p.Detach()


def watch(debugger, ea, secs=20, write=True, size=4, nhits=1):
    debugger.SetAsync(False)
    t = debugger.GetSelectedTarget(); p = t.GetProcess()
    e = lldb.SBError()
    t.WatchAddress(VM_BASE + ea, size, not write, write, e)
    print("watch", e.Success(), e.GetCString(), flush=True)
    stop = [False]

    def timer():
        time.sleep(secs); stop[0] = True; p.SendAsyncInterrupt()
    threading.Thread(target=timer, daemon=True).start()
    hits = other = 0
    while not stop[0] and hits < nhits:
        p.Continue()
        for th in p:
            d = th.GetStopDescription(200) or ""
            if "atchpoint" in d:
                hits += 1
                print("HIT", d, flush=True)
                for f in list(th)[:25]:
                    print("   ", f.GetFunctionName() or hex(f.GetPC()), flush=True)
            elif th.GetStopReason() == lldb.eStopReasonException:
                other += 1
    print("hits", hits, "other stops", other, flush=True)
    t.DeleteAllWatchpoints()
    p.Detach()
