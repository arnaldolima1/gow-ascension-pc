# Optional PPU-only profile-guided compilation

**How to run it now (2026-11-04):** `scripts/windows/pgo-ppu.ps1` does the whole
thing (instrumented build, a 330 s level run with the default settings, merge,
profile-guided build) and keeps the executable from before in
`build/pgo/<Name>/base`; `-Swap base|pgo` puts either one in `build/win` for an
A/B. The `train-ppu-pgo.ps1` described below (training only, with the
2026-10-30 experimental switches and a fault check that rejected the boot-time
FIFO desync every run) was not brought over, nor the streaming/scheduler copies
of chunks 006/007.

The scheduler experiments and current three-module SPU probe did not produce
the roughly 9.6 ms median reduction needed for 30 FPS. The exact-instruction
profile spreads PPU work across many small sites rather than one dominant
calculation. PGO is a broader code-generation candidate, not a promised gain.

The [Clang manual](https://clang.llvm.org/docs/UsersManual.html#profile-guided-optimization)
documents instrumenting a program, collecting execution counts, merging them
with llvm-profdata, and recompiling using that profile. The current game uses
Visual Studio clang-cl **19.1.5**. A separate LLVM 23 installation also exists;
do not mix its profile tools into this workflow.

The CMake cache on this machine keeps the bare name `clang-cl` rather than
an absolute path. `tools/resolve_cmake_compiler.py` resolves the compiler from
the generated CMake compiler record and matches Ninja's actual command when
old records coexist. It never silently selects the other LLVM from PATH.
Regression checks cover bare/absolute paths, spaces and stale records.

## Build options

`cmake/AscensionPgo.cmake` leaves the normal build unchanged by default:

- `ASCENSION_PPU_PGO=OFF`: existing compilation flags.
- `ASCENSION_PPU_PGO=GENERATE`: instrument only the generated PPU sources,
  including the streaming/scheduler build copies, with atomic counters.
  Resolve and link the profiling runtime belonging to the configured compiler.
  SPU, RSX and normal host/runtime compilation flags stay unchanged.
- `ASCENSION_PPU_PGO=USE`: compile those PPU sources with
  `ASCENSION_PPU_PROFILE=<absolute merged .profdata path>`. Fail configuration
  if the file is missing. No profiling writer/runtime is added in this mode.

This changes neither guest algorithms nor the existing floating-point flags.
Atomic instrumentation and the profile writer are training costs, not final
gameplay costs. Training FPS cannot be used as the optimized result.

## Prepared training

Run `scripts/windows/train-ppu-pgo.ps1` from a normal PGO=OFF build. It:

1. Saves the current executable/map/PDB under `build/pgo/<Name>` and records
   their binary identity, compiler version and generated PPU input hashes.
2. Configures GENERATE and rebuilds the PPU; build/configuration logs go to
   `build/logs`. This is a substantial rebuild, not an incremental micro-test.
3. Runs the automatic opening scene for 300 seconds. Streaming synchronization
   and fast PPU waits stay on. All unsuccessful scheduler experiments, causal
   delays and job probes/captures are off.
4. `host/pgo_flush.cpp`, linked only into GENERATE builds, writes the profile
   after 240 seconds. This is necessary because the bounded game runner stops
   the process forcibly and cannot rely on the profiling runtime's atexit hook.
5. Rejects detected runtime faults or an unsuccessful flush, merges using
   llvm-profdata beside the configured compiler, and writes a profile summary.
6. In `finally`, configures OFF and restores the saved executable/map/PDB,
   including on training/build failure. It stops only a matching build executable
   started during this training if one remains. No save is reset.

An instrumented build can start the level more slowly. Review the gameplay log
to confirm it reached actual play before the profile was flushed. Collection
success alone does not establish useful training coverage. Review metadata and
profile counts before the separate USE build. Check recorded source hashes
before applying the data to changed generated code.

No optimized gameplay result exists yet. A subsequent USE build needs a clean
same-scene performance comparison and rendering/runtime checks; compilation
success is not acceptance of a 30 FPS claim. The original executable remains
available for restoring or comparing.

## Light validation

`tools/test_ppu_pgo.py` uses the actual CMake module and profile-writer source
in a tiny isolated project, built by the configured VS clang-cl. It verifies
atomic training, a successful explicit flush before `_Exit` (no atexit flush),
real profile counts/merge, USE and OFF builds with the same checksum, and
rejection of a missing profile. It also contains isolated PowerShell workflow
mocks for success and build/runtime failure restoration. Those mocks are
currently skipped because the child PowerShell execution policy blocks script
files; the policy is not changed. The training script passes PowerShell parsing;
full game training/restoration still needs the user-run workflow.
