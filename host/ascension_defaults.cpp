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
//                      frame.
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
#endif
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif
#include <stdint.h>
#include <stdio.h>
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
    setenv(name, value, 0);
#endif
}

struct AscensionDefaults {
    AscensionDefaults()
    {
        set_default("PS3_EDGE_ZLIB_HLE", "1");
        set_default("RSX_LIVE_DRAW", "1");
        set_default("LD_SWIN", "0");
        set_default("GCM_PARK_WAIT_MS", "2000");
        set_default("GCM_SEMA_ACQUIRE", "1");
        set_default("GCM_PARK_SPU_HOLD_MS", "1000");
        set_default("GCM_REPORT_SPU_HOLD_MS", "50");
        set_default("GCM_ROUND_GATE", "9BAC30");
        set_default("GCM_ROUND_RING", "io:1ED00,18");
        set_default("SPURS_READY_LEVEL", "1");
        set_default("SPURS_MAXCONT", "3=5,13=3,15=5,16=5,17=5");
        set_default("SPURS_IDLE_BACKOFF_MAX", "0");
        // SPU n on physical core n + 1, alone: its contexts' local stores and
        // lifted code stay in that core's caches. First level ~14.8 -> ~15.6
        // fps, module 218's job 72 -> 65 us.
        set_default("SPURS_PIN", "1");
        // The main PPU thread on core 0, which SPURS_PIN leaves free: it
        // waits on the SPUs and kicks their next jobs. ~15.8 -> ~16.7 fps.
        set_default("PS3_PIN_PPU", "1");
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
        // The job scheduler's not-ready turn (0x416AAC, tools/ppu_switches.json)
        // sleeps until an SPU's next write instead of scanning its table again:
        // menu at 8 logical CPUs -1.0 ms a frame, +1.3 fps; first level the same.
        set_default("GOWA_PPU_SCHED_WAIT", "1");
        // The game measures its frame time with a one-vblank floor (59.94 Hz,
        // func_002B3C48): correct up to 60 fps, fast above. PS3_FRAME_LIMIT=60
        // caps it; not a default while the game stays below 60 (menu 42 with
        // it against 48 without, one run each).
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
        set_default("PS3_VERBOSE", "0");
        // Five SPU workers instead of the title's six on a host with 8 logical
        // CPUs or fewer: the sixth competes with the PPU and RSX threads for
        // cores (as RPCS3's "Max SPURS threads"). First level at 8 logical
        // CPUs: 18 fps both ways, 6.84 -> 6.43 cores; at 12: 27 -> 26 fps,
        // 8.10 -> 7.10 cores, so 12 or more keep six.
        if (logical_cpus() <= 8)
            set_default("SPURS_NSPUS", "5");
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
