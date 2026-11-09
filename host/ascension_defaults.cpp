// Runtime defaults for God of War: Ascension, set before main() runs.
//
// Each is an environment switch ps3recomp reads on first use. A value already
// set in the environment wins, so any of them can still be turned off for a
// run (set it to 0).
//
//   PS3_EDGE_ZLIB_HLE  the Edge Zlib inflate queue is serviced on the host:
//                      the SPU path cannot serve it yet, and without it the
//                      archives never load.
//   RSX_LIVE_DRAW      the live NV4097 draw engine. The default D3D12 path
//                      records none of this title's draws (every present
//                      had draws=0: a black window); the live engine draws
//                      the intro screens correctly.
//   LD_SWIN            0: a texture smaller than the surface it aliases reads
//                      the whole surface, not a copy of its top-left
//                      corner (live draw's surface_window, from upstream).
//                      With the window the menu's depth of field blurred the
//                      whole scene and shook from frame to frame; without it
//                      the picture is close to RPCS3's.
//   GCM_PARK_WAIT_MS   how long a parked FIFO waits to be patched before the
//                      runtime follows `put` (ps3recomp's default is 50 ms).
//                      This title's SPU jobs fill a frame and patch the park
//                      after `put` has moved; following it early skips the
//                      frame. It is always patched here, so the wait has no
//                      end in practice (10 min): at 2000 ms a slow stretch
//                      (GOWA_NATIVE_CHECK=1 at the level load, 2026-11-09) let
//                      the walker jump to `put`, dropping the frame's commands
//                      and a Wws counter with them, and the PPU spun on that
//                      counter for the rest of the run.
//   GCM_SEMA_ACQUIRE   a FIFO SEMAPHORE_ACQUIRE really waits. After each
//                      frame's reports the GPU waits for the label the SPU
//                      post-process tasks write when they finish the frame;
//                      without the wait it runs ahead, RsxSync overwrites the
//                      tasks' descriptor before the slow ones read it, and a
//                      round loses its decrements.
//   GCM_PARK_SPU_HOLD_MS  a park the vblank handler has patched (the next
//                      frame's segment) is held while SPURS tasks are still
//                      running, up to this long. The first frame has no
//                      post-process ACQUIRE: the game relies on the RSX taking
//                      a frame's time, and without the hold frame 2's reports
//                      landed while round 1 still ran, so round 2 never began.
//   GCM_REPORT_SPU_HOLD_MS  a GET_REPORT waits, up to this long, while SPURS
//                      tasks are out of WAIT_SIGNAL or have a signal pending.
//                      RsxSync turns each report into a signal for the
//                      post-process tasks; when the PPU side is quick (job
//                      module 214 lifted) the GPU's next report reached
//                      RsxSync before the tasks had started the round, its
//                      signal was eaten by their barriers, and the game
//                      stopped at the end of loading every time.
//   GCM_ROUND_GATE     with RPCS3's RSX, the placeholder report after each
//                      frame report waits until RsxSync has read every frame
//                      report it was polling and the post-process round in
//                      its descriptor (0x9BAC30) has written its label. A
//                      PS3's RSX takes a frame's time, so a round always ends
//                      before the next one is signalled; a recompiled one
//                      does not, and the next round's signal was lost in the
//                      tasks' barriers (the Mac never reached the loading
//                      screen). It waits on the game's own progress, not on
//                      a clock.
//   GCM_ROUND_RING     RsxSync's ring of 18 frame reports (RSX IO offset
//                      0x1ED00, EA 0x1101ED00 or 0x7001ED00 as the runtime
//                      lays the heap out): only those are watched. Another job polls reports at
//                      0x1124xxxx/0x1126xxxx without reading them again, and
//                      the gate waited a second for each. RsxSync reads its
//                      reports in order, so the one after the last it read is
//                      awaited even before it polls it (on Windows the RSX
//                      wrote it while RsxSync still acted on the one before).
//   SPURS_READY_LEVEL  readyCount is a level, as the real kernel treats it.
//                      The Wws job managers zero their own count once their
//                      jobs are stored; consuming it per admission left
//                      RsxSync's round-2 job unrun until a later kick, which
//                      never came (the render thread waits on frame slot
//                      0x99AAC8 for it).
//   SPURS_MAXCONT      up to five SPUs on the main menu's Wws job lists
//                      (wid 3, 16 jobs a frame, and the EDGE lists, wid
//                      15-17, one a frame), which the game gives one SPU
//                      each. Recompiled SPU code runs them several times
//                      slower than a real SPU, and one after the other they
//                      held the menu at 14 fps; shared, it runs at ~33. The
//                      Wws manager keeps a progress lane per SPU, so a list
//                      is built to be shared. In the first level wid 13 ran
//                      on one SPU half the time while the PPU waited; up to
//                      three: ~14.5 -> ~15.4 fps. Six on every list hung it.
//   SPURS_IDLE_BACKOFF_MAX  0: a workload that ran and found nothing is not
//                      skipped for up to 16 kernel passes (~16 ms) after;
//                      work the PPU stores meanwhile waited for it. First
//                      level ~13.4 -> ~14.5 fps.
//   SPU_REJOIN         the interpreter rejoins job module 204's lifted code
//                      (jobmod_31107645db58, the level-load job) between LS
//                      0x9700 and 0x1C000, which it otherwise only does with
//                      interrupts off. Run interpreted (~95M instructions per
//                      5 s) it held the main loop at ~55 ms an iteration: the
//                      loading movies played at 50-75% with stuttering audio.
//   SPU_REJOIN_CALL    that rejoined code runs in a drain of the interpreter's
//                      own, so its host return resumes interpretation at the
//                      right pc instead of unwinding past the interpreted
//                      caller.
//   LD_PERF_OVERLAY    frame rate, frame time, speed, CPU and GPU use in the
//                      top-right corner of the window. Off by default here; the
//                      launcher's "FPS counter" sets it to 1.
//   PS3_VERBOSE=0      the per-frame log lines (task creation and joins, SPU
//                      dispatch, viewport changes, events) stay quiet: every
//                      guest thread writes them through one FILE lock, and
//                      they cost the main thread several percent of its time.
//                      Set PS3_VERBOSE=1 to get them back when investigating.
//   GOWA_UNLOCK_FPS    the game steps by real time (RPCS3's Unlock FPS patch),
//                      with PS3_FRAME_LIMIT=60; =0 turns it off.
//   GOWA_LOADER_TPF    the level loader keeps its own time per frame under the
//                      unlock (else loading took 19 s instead of 4).
//   GOWA_LOAD_UNPACED  loading-screen frames are not held by the frame limit.
//   GOWA_GOD_MODE      Kratos takes no damage from hits (the developers' God
//                      Mode check, never switched on in the retail game).
//                      TEST DEFAULT, to be turned off before a release: on
//                      so Kratos survives the fight bench in performance
//                      runs (asked for on 2026-11-09).
//
// The OS environment is used directly, not getenv(): the boot harness routes
// getenv through a cache that also remembers a miss, so asking first would pin
// the variable as unset before it is set.
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <stdlib.h>
#include <unistd.h>
#include <sys/stat.h>
#endif
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <string>

namespace {

// The logical CPUs this process may run on (its affinity mask), else the host's.
unsigned logical_cpus()
{
#ifdef _WIN32
    DWORD_PTR proc = 0, sys = 0;
    if (GetProcessAffinityMask(GetCurrentProcess(), &proc, &sys) && proc) {
        unsigned n = 0;
        for (; proc; proc &= proc - 1) n++;
        return n;
    }
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    return si.dwNumberOfProcessors;
#else
    const long n = sysconf(_SC_NPROCESSORS_ONLN);
    return n > 0 ? (unsigned)n : 1u;
#endif
}

void set_default(const char* name, const char* value)
{
#ifdef _WIN32
    // set but empty counts as set (the launcher's PS3_OVERLAY_FONT= keeps Cinzel off)
    SetLastError(0);
    if (GetEnvironmentVariableA(name, nullptr, 0) || GetLastError() != ERROR_ENVVAR_NOT_FOUND) return;
    SetEnvironmentVariableA(name, value);
#else
    if (getenv(name)) return;
    setenv(name, value, 0);
#endif
    // PS3_DEFAULTS_SET (",A,B,"): the switches set here rather than by the user, so
    // an in-run A/B with CAUSAL_KEEP_DEFAULTS=1 keeps them on in both windows and
    // toggles only the one under test (ps3kit include/ps3emu/causal_gate.h).
    static std::string s_set = ",";
    s_set += name;
    s_set += ',';
#ifdef _WIN32
    SetEnvironmentVariableA("PS3_DEFAULTS_SET", s_set.c_str());
#else
    setenv("PS3_DEFAULTS_SET", s_set.c_str(), 1);
#endif
}

// On by default, for a switch the lifted code tests as "set" (getenv != NULL,
// tools/ppu_switches.json): a user's NAME=0 is taken off the environment
// instead, so that 0 turns it off there too. Read without getenv: boot_main's
// cached getenv keeps the first answer, even "not set", for the whole run.
static void default_on_set_switch(const char* name)
{
#ifdef _WIN32
    char v[4] = {0};
    const DWORD n = GetEnvironmentVariableA(name, v, sizeof v);
    if (!(n == 1 && v[0] == '0')) { set_default(name, "1"); return; }
    SetEnvironmentVariableA(name, nullptr);
    _putenv_s(name, "");                 // the CRT's copy as well ("" removes it)
#else
    const char* v = getenv(name);
    if (!v || strcmp(v, "0") != 0) { set_default(name, "1"); return; }
    unsetenv(name);
#endif
}

struct AscensionDefaults {
    AscensionDefaults()
    {
        set_default("PS3_EDGE_ZLIB_HLE", "1");
        set_default("RSX_LIVE_DRAW", "1");
        // ps3kit's Vulkan renderer: the frame's copy into main memory for the
        // SPU MLAA round stays on the GPU (AA done there, SMAA by default)
        // instead of a whole-target readback each frame, which held the RSX
        // thread ~8 ms a frame on the GPU. Corridor 24.5 -> 28.6 fps
        // (2026-11-08, wsites / wsites-mirror runs).
        {
            const char* r = getenv("PS3_RSX");
            if (r && !strcmp(r, "vulkan")) set_default("RSX_ENGINE_GPU_MIRROR", "1");
        }
        set_default("LD_SWIN", "0");
        set_default("GCM_PARK_WAIT_MS", "600000");
        set_default("GCM_SEMA_ACQUIRE", "1");
        set_default("GCM_PARK_SPU_HOLD_MS", "1000");
        set_default("GCM_REPORT_SPU_HOLD_MS", "50");
        set_default("GCM_ROUND_GATE", "9BAC30");
        set_default("GCM_ROUND_RING", "io:1ED00,18");
        set_default("SPURS_READY_LEVEL", "1");
        // wid 9-12 (RenJobSet: modules 217, 225, 201, 227) up to four/five
        // SPUs: the main thread's frame waits on a scheduler item those lists
        // bring to zero, and with one SPU each they ran strictly in turn
        // (~6.5 ms a frame). In-run A/B, first level, 4 cores / 8 threads:
        // -2.11 ms a frame (+0.6 fps), no hang (2026-11-04, ps3kit
        // docs/ASCENSION_PLAN.md S9; first measured 2026-10-30, 19 -> 20-21 fps).
        set_default("SPURS_MAXCONT", "3=5,9=4,10=4,11=4,12=5,13=3,15=5,16=5,17=5");
        set_default("SPURS_IDLE_BACKOFF_MAX", "0");
        // SPU n on physical core n + 1, alone: its contexts' local stores and
        // lifted code stay in that core's caches. First level ~14.8 -> ~15.6
        // fps, module 218's job 72 -> 65 us.
        set_default("SPURS_PIN", "1");
        // Alecto's arena: workload 13 (RenderJobs, ~9 SPU-ms a frame) off the
        // four SPUs the EDGE list runs on, so it neither takes an EDGE slot nor
        // shares those cores' caches. 46.6 -> 48.3/48.8 fps (two runs of 13-14
        // gameplay windows each). Pinning anything else the same way loses:
        // 13:4-5;3,8,9,10,14:4-5 -> 44.5, 13:4-5;11,12:4-5 -> 46.8.
        // With 12 logical CPUs or more, a 7th SPU that the Wws job manager
        // sees as SPU 3 (a job list has progress lanes for six) takes
        // RenJobSet (wid 9-12) off SPU 3. Whole PC (16 threads), in-run A/B,
        // first level: -1.05 ms a frame (quartiles -2.21 / -0.65), +0.65 fps;
        // wid 13 on the 7th too gave the same. Below 12 a 7th SPU thread only
        // competes for the cores (otavix010 saw the same). 2026-11-05, ps3kit
        // docs/ASCENSION_PLAN.md S14 A1/A2. Placed before the plain lanes so
        // they do not win.
        // ... superseded on the same hosts by the EDGE lists outside SPURS
        // (plan step 3.1): GOWA_WWS_EXEC runs workloads 15-17 on four host
        // workers of its own (job.c), so SPURS keeps four SPUs and RenderJobs
        // (wid 13) leaves SPUs 0-1 to the rest. Alternating level runs, whole
        // PC: base 27 / 26 against 29 / 27 fps (2026-11-05, S15); 8 level runs
        // with it, no hang. The alias above stays for GOWA_WWS_EXEC=0.
        // The executor is Windows-only (job.c's workers): elsewhere the alias.
        // 8 logical CPUs too (4 cores, -Affinity FF, 2026-11-06 S17 K5): 19 fps
        // without it against 21-22 with it (12 level runs, the four below on or
        // off alike); the 7-SPU alias stays a 12-CPU setup for GOWA_WWS_EXEC=0.
        if (logical_cpus() >= 8) {
#ifdef _WIN32
            set_default("GOWA_WWS_EXEC", "15,16,17");
            char wv[64] = {0};
            const DWORD wn = GetEnvironmentVariableA("GOWA_WWS_EXEC", wv, sizeof wv);
            const bool no_exec = wn == 0 || wn >= sizeof wv || wv[0] == '0';
#else
            const bool no_exec = true;
#endif
            if (no_exec) {
                if (logical_cpus() >= 12) {
                set_default("SPURS_NSPUS", "7");
                set_default("SPURS_SPU_ALIAS", "6:3");
                set_default("SPURS_WID_LANES", "9-12:0-2,4-6;13:4-5");
                }
            } else {
                // Six SPUs, not four: with 4 or 5 the mix stays silent (AUDIO_PEAK 0,
                // port ring empty), with 6 it plays (2026-11-06 S17). Why is not
                // known: which workload or task needs the sixth was not found. Every
                // number measured with four since S15 was taken with no sound
                // running. RenderJobs keeps the 13:4-5 lanes.
                set_default("SPURS_NSPUS", "6");
                // its workers sleep on their event instead of yielding: in-run
                // A/B -0.91 ms a frame (quartiles -1.22 / -0.56), +0.70 fps
                set_default("GOWA_WWS_SLEEP", "1");
                // and its lane/ticket stores wake the PPU job scheduler's wait
                // (GOWA_PPU_SCHED_WAIT), which no SPU write reached any more:
                // in-run A/B -1.26 ms a frame (quartiles -1.64 / -0.85)
                set_default("GOWA_WWS_SCHED_KICK", "1");
                // the PPU's Wws barrier (func_00466E28) calls syscall 1021 in its
                // spin (tools/ppu_switches.json): in-run A/B -1.52 ms a frame
                // (quartiles -1.90 / -0.70), +0.96 fps; it never had to sleep,
                // the gain is the spin leaving the lanes' line alone
                set_default("GOWA_WWS_BARRIER_WAIT", "1");
                // the batch-job poll in func_00464F0C's spin (syscall 1022 at
                // 0x464AD8) pauses while the executor has not moved: in-run A/B
                // -1.20 ms a frame (quartiles -1.48 / -0.95), +0.90 fps
                set_default("GOWA_WWS_POLL_PAUSE", "1");
                // a worker keeps the module its last job loaded and copies only
                // the part jobs write (the last 0x1000 bytes) instead of all of
                // it (module 218: 53 KB a job, ~2.4 GB/s of memcpy, the "rep
                // movsb" ~5 % of each worker): =check found the rest identical
                // on 2.6M level and 1M menu jobs; alternating level runs 27.0 /
                // 27.4 against 26.0 / 26.7 fps (2026-11-07, km*).
                set_default("GOWA_WWS_KEEP_MODULE", "1");
            }
        }
        set_default("SPURS_WID_LANES", "13:4-5");
        // MFC commands without the full path's diagnostic switches (spu_dma.h).
        // In-run A/B, first level: whole PC -0.88 ms a frame (quartiles -1.26 /
        // -0.46), 4 cores / 8 threads -1.34 ms (-1.97 / -1.13). S14 A3/A4.
        set_default("SPU_DMA_LEAN", "1");
        // A Wws job that stops itself (module 759d's bytecode interpreter on a
        // bad opcode) no longer freezes its list: its lane is freed and the
        // manager's context dropped (ascension-native/render/geometry/job.c,
        // ps3_title_spurs_pm_abort). The BATCHJOB freeze: 7 of 8 plays past the
        // first level's test spot on 2026-11-06. Rehearsed with SPU_IB_INJECT at
        // three points, no freeze; not yet seen firing in a real play.
        set_default("GOWA_WWS_HALT_RELEASE", "1");
        // The Wws interrupt handler's register save/restore stubs at LS 0x3FEC0
        // decoded once a thread, not word by word every interrupt: whole PC
        // -0.43 ms a frame (quartiles -0.91 / -0.21), 0 refused. S14 A6.
        set_default("SPU_SMC_FAST", "1");
        // The code-fragment scan of large GETs learns per (image, 4 KB LS page)
        // instead of per image: the Wws policy module loads code, so it scanned
        // every data block it fetched too. In-run A/B, first level: whole PC
        // -1.44 ms a frame (quartiles -1.71 / -0.84), 4 cores / 8 threads
        // -2.48 ms (-2.78 / -2.03); 5 level runs with it, no hang, no lifted
        // entry lost (2026-11-05, ps3kit docs/ASCENSION_PLAN.md S15).
        set_default("SPU_OVL_SCAN_BY_LSA", "1");
        // An XInput slot found empty is asked again after 1 s, not every 4 ms
        // sweep on the main PPU thread (XInputGetState on an empty slot is
        // slow). In-run A/B, first level, whole PC: -1.61 ms a frame
        // (quartiles -2.43 / -0.67), +0.96 fps (2026-11-05, S15). A pad
        // plugged in mid-game is seen within a second.
        set_default("PS3_PAD_ABSENT_MS", "1000");
        // A PPU store to a line an SPU once reserved goes without the lock-line
        // stripe when its sequence count and the line's live bit say nothing ran
        // there (spu_coherency.c spu_coh_store_opt); ~280k such stores a second,
        // 98 % to lines no SPU holds. In-run A/B, first level, whole PC: -2.02 ms
        // a frame (quartiles -2.46 / -1.49), +1.14 fps; level runs with it: no
        // hang, no copy error (2026-11-05, S15).
        set_default("PS3_COH_STORE_OPT", "1");
        // The PPU's indirect calls (vtables, callbacks) skip the dispatcher's
        // ~15 diagnostic checks when none is set (ppu_loader.cpp): in-run A/B,
        // first level, whole PC: -1.46 ms a frame (quartiles -1.69 / -1.25),
        // +1.07 fps (2026-11-06, S15).
        set_default("PPU_ICALL_FAST", "1");
        // ... and the lifted code's own store slow path takes it too (its copy
        // of VM_WRITE_COH in ppu_loader.cpp had been left on the locked path:
        // ~295k stores a second, 0x970F80 alone ~185k): in-run A/B -2.41 ms a
        // frame (quartiles -2.49 / -2.04), +1.88 fps (2026-11-06, S15).
        set_default("COH_LOADER_OPT", "1");
        // The main PPU thread on core 0, which SPURS_PIN leaves free: it
        // waits on the SPUs and kicks their next jobs. ~15.8 -> ~16.7 fps.
        set_default("PS3_PIN_PPU", "1");
        // ... at above-normal priority. On 4 cores / 8 threads the RSX sat
        // ~32 ms of a 90 ms frame waiting for the PPU to hand over the next
        // frame (RSX_FIFO_TIMELOG): the PPU woke late from its SPU waits among
        // ~11 busy threads. In-run A/B, first level: 4 cores -5.3 ms a frame
        // (+1.3 fps) against a null run's -2.1 (that null still carried the
        // RSX-wait bias fixed with CAUSAL_KEEP_DEFAULTS), 16 threads -0.6 ms;
        // no hang (2026-11-04, ps3kit docs/ASCENSION_PLAN.md S6).
        set_default("PS3_PPU_PRIO", "1");
        // The main thread's usleep(30) poll of the frame counter (0x99AAC4,
        // lr 0x3E8378, ~5800 a second, each a 30 us spin) waits for an SPU's
        // write to it instead. Menu: main thread 86 -> 69 % of a core, fps
        // the same (menu and first level, in-run A/B).
        set_default("PS3_PPU_POLL_WAIT", "3E8378:99AAC4");
        // The RSX thread's hold for the SPU post-process round sleeps until
        // the round's label is written instead of spinning with a yield. With
        // 8 logical CPUs, menu frame -0.6 ms (+0.9 fps); first level and 12
        // CPUs the same.
        set_default("PS3_RSX_HOLD_WAIT", "1");
        // On an empty FIFO the RSX thread sleeps until the put, a flush or a
        // flip moves, instead of a yield loop that was ~45 % of its samples in
        // the first level. 4 cores / 8 threads: frame 72.2 -> 66.2 ms, p90
        // 80.1 -> 71.7 ms, the RSX thread 0.90 -> 0.37 cores; 16 threads: the
        // same (2026-11-03, ps3kit docs/ASCENSION_PLAN.md).
        set_default("PS3_RSX_IDLE_WAIT", "1");
        // Esc closed the window mid-game on the Mac (the process kept running
        // with no window); the game has its own pause menu
        set_default("PS3_ESC_QUITS", "0");
        // A SPURS worker takes its next workload itself instead of waking the
        // coordinator: in-run A/B, first level, frame -0.38 ms (16 threads) and
        // -1.48 ms (4 cores / 8 threads), no hang (2026-11-03).
        set_default("SPURS_SELF_SELECT", "1");
        // A PPU store to a line an SPU ever reserved takes the lock-line lock,
        // so a PUTLLC's whole-line copy cannot undo it. The game re-arms its
        // EDGE wake counters (0x0099AA80) with plain stores; a lost re-arm
        // froze it (no EDGE list ready, the PPU spinning in its job
        // scheduler). 6 cores with 5 SPU workers: froze 3 runs of 5 without,
        // 0 of 4 with, same frame time (2026-11-03).
        set_default("PS3_COH_STORE_LOCK", "1");
        // The streaming table's PPU/SPU hand-off (host/texstream_sync.cpp,
        // docs/TEXSTREAM_SYNC.md): the PPU's waits read 0x967028 while the
        // streaming jobs are counted at 0x967024, so it could rewrite the table
        // under an SPU job's snapshot: "CopyLocalMemory offset error", then a
        // freeze, in 2 of 28 level runs. With the guard, 20 level runs on 4 cores:
        // 0 copy errors, overlaps caught in every run (4-32, waits up to 18 ms),
        // fps unchanged (2026-11-05, ps3kit docs/ASCENSION_PLAN.md S12 Q3).
        set_default("GOWA_TEXSTREAM_SYNC", "1");
        // The job scheduler's not-ready turn (0x416AAC, tools/ppu_switches.json)
        // sleeps until an SPU's next write instead of scanning its table again:
        // menu at 8 logical CPUs -1.0 ms a frame, +1.3 fps; first level the same.
        set_default("GOWA_PPU_SCHED_WAIT", "1");
        // 60 fps (plan L-1, 2026-11-09): the game steps by real time (the
        // "Unlock FPS" patch, GOWA_UNLOCK_FPS: the user checked walk and fight
        // speed), capped at 60 (PS3_FRAME_LIMIT; the limiter no longer sleeps a
        // period every other frame below the cap: fight 24 with or without it).
        // The unlock had cut the level loader's time per frame from 3.3 ms to
        // 0.2 ms and the cap starved the loading screen of frames: the sync load
        // took 19 s (unlock) and 69 s (unlock + cap) against 4.2 s. GOWA_LOADER_TPF
        // gives the loader its own frame time back (ascension-native
        // game/loader_gate.cpp, tools/ppu_native_gates.json) and GOWA_LOAD_UNPACED
        // leaves loading-screen frames unpaced (the game's shell state 0x0083D0D8,
        // ps3_title_frame_unpaced): 4.5 s with both (logs lgate1-3).
        // Plain FIFO method headers go to the draw engine in one run (ps3kit
        // 93b0149c, plan A4): walker 16.6 -> 15.1 us a draw in the fight, picture
        // checked in the menu and the fight (2026-11-09).
        set_default("RSX_ENGINE_FIFO_FAST", "1");
        default_on_set_switch("GOWA_UNLOCK_FPS");
        set_default("PS3_FRAME_LIMIT", "60");
        set_default("GOWA_LOADER_TPF", "1");
        set_default("GOWA_LOAD_UNPACED", "1");
        set_default("SPU_REJOIN", "204:9700-1C000");
        set_default("SPU_REJOIN_CALL", "1");
        // Off unless asked for: the launcher's "FPS counter" (LD_PERF_OVERLAY=1)
        // still turns the corner panel on. The default is off because it is drawn
        // over the game and a run started outside the launcher (a test .cmd) got it
        // on screen without being asked.
        set_default("LD_PERF_OVERLAY", "0");
        // RPCS3's performance overlay in the launcher's style: its Cinzel and
        // palette (text, panel, gold titles).
        set_default("PS3_OVERLAY_COLORS", "#E2B86AFF,#0B090899,#E2B86AFF,#00000000");
        set_default_overlay_font();
        set_default_shader_cache();
        set_default("PS3_VERBOSE", "0");
        // TEST DEFAULT (2026-11-09): Kratos must not die in the fight bench
        // during performance runs. Turn it off before a release.
        set_default("GOWA_GOD_MODE", "1");
        // Five SPU workers instead of the title's six on a host with 8 logical
        // CPUs or fewer: the sixth competes with the PPU and RSX threads for
        // cores (as RPCS3's "Max SPURS threads"). First level at 8 logical
        // CPUs: 18 fps both ways, 6.84 -> 6.43 cores; at 12: 27 -> 26 fps,
        // 8.10 -> 7.10 cores, so 12 or more keep six.
        // Removed 2026-11-06 (S17): with five SPUs the game has no sound.
    }

    // ps3kit's Vulkan renderer: its translated shaders (SPIR-V) and the
    // driver's compiled pipelines kept on disk beside the executable
    // (shader_cache/vulkan/), so a second run does not compile them again
    // in the middle of play (a fight compiled for ~20 s at 1-4 fps on
    // 2026-11-08, fight4 run). The RPCS3 renderer keeps its own cache.
    static void set_default_shader_cache()
    {
        const char* r = getenv("PS3_RSX");
        if (!r || strcmp(r, "vulkan")) return;
        char exe[4096] = {0};
#ifdef _WIN32
        if (!GetModuleFileNameA(nullptr, exe, sizeof(exe))) return;
#elif defined(__APPLE__)
        uint32_t n = sizeof(exe);
        if (_NSGetExecutablePath(exe, &n)) return;
#else
        if (readlink("/proc/self/exe", exe, sizeof(exe) - 1) <= 0) return;
#endif
        std::string dir = exe;
        const auto slash = dir.find_last_of("/\\");
        if (slash == std::string::npos) return;
        dir.resize(slash);
        const std::string parts[3] = { dir + "/shader_cache", dir + "/shader_cache/vulkan",
                                       dir + "/shader_cache/vulkan/spirv" };
        for (const std::string& d : parts) {
#ifdef _WIN32
            CreateDirectoryA(d.c_str(), nullptr);
#else
            mkdir(d.c_str(), 0755);
#endif
        }
        set_default("PS3RECOMP_SPIRV_CACHE", parts[2].c_str());
        set_default("PS3RECOMP_VK_PIPELINE_CACHE", (parts[1] + "/pipelines.bin").c_str());
    }

    // launcher/Cinzel-Black.ttf beside a build in build/<platform>/ (the
    // launcher passes its own copy).
    static void set_default_overlay_font()
    {
        char exe[4096] = {0};
#ifdef _WIN32
        if (!GetModuleFileNameA(nullptr, exe, sizeof(exe))) return;
#elif defined(__APPLE__)
        uint32_t n = sizeof(exe);
        if (_NSGetExecutablePath(exe, &n)) return;
#else
        if (readlink("/proc/self/exe", exe, sizeof(exe) - 1) <= 0) return;
#endif
        std::string dir = exe;
        for (int up = 0; up < 3; up++) {
            const auto slash = dir.find_last_of("/\\");
            if (slash == std::string::npos) return;
            dir.resize(slash);
        }
        const std::string font = dir + "/launcher/Cinzel-Black.ttf";
        if (FILE* f = fopen(font.c_str(), "rb")) {
            fclose(f);
            set_default("PS3_OVERLAY_FONT", font.c_str());
        }
    }
} s_defaults;

}  // namespace

// Lifted SPU functions left to the interpreter unless SPU_NOLIFT says
// otherwise. None now: job module 214 (jobmod_e9f3f00d551e) from 0x4418 used
// to be kept interpreted because lifting it stopped the game at the end of
// loading; that was the report race GCM_REPORT_SPU_HOLD_MS closes (the lift
// itself checked out under SPU_SHADOW). Read by the runtime's registration,
// which runs in static constructors, so it is a constant and not an
// environment default.
extern "C" const char* const spu_title_nolift = nullptr;
