# Streaming-table handoff investigation (2026-10-30)

Scope: BCES01741 disc version 1.00, the executable used by this port. The Edge
zlib counter fix in ps3kit is preserved. This change is a separate candidate
correctness fix; it has not yet passed an in-game run.

## Local evidence

`30fps-corrected.log` first reports an invalid local-memory destination at line
61581, then repeated copy errors, then a write fault at guest 0xD0000000 on the
RSX thread (`crash-6140.dmp`). No post-warm-up causal windows survive.

The first message belongs to guest `func_00374EBC` (MoveLocalMemory). It compares
destination plus size with `*(u32*)0x009BDF88`, before handing the move to the
copy routines. These messages are the game's own range assertions, not proof
that RSX FIFO decoding first corrupted the arguments. The lifted trap after an
assertion is ignored, so the title proceeds to issue the invalid move.

The streaming path has a concrete handoff mismatch:

1. `func_00366C24` builds the UpdateTexStreaming arguments. At 0x00366D64 it
   selects the name at 0x0063D858; the table pointer comes from
   `*(u32*)0x0096E174`, and the entry count is 0xA28.
2. The same function passes **0x00967024** in r10 to `func_003B37C0`.
3. `func_003B37C0` preserves r10 as r27, then at 0x003B3874..0x003B3884 uses
   lwarx/stwcx to add `job_count << 16` to that word. Thus pending jobs occupy
   its first big-endian halfword. The module bytes at EA 0x006B4C80 match
   `jobmod_e9f3f00d551e_e12D8.bin`, registered as module 229, entry 0x52D8.
4. Both `func_00366DB8` and `func_00366E18` instead poll the halfword at
   **0x00967028**, four bytes later. That wait does not observe this job counter.
5. PPU functions `0036DD1C`, `0036EEF8` and `003707D8` read the shared table
   pointer and modify its entries (flags, allocation/streaming state). Their
   entry guards prevent those writes while the old SPU table snapshot is in
   flight. The two official wait/maintenance entries are guarded as well.

This matches the mechanism independently documented for the US 1.04 executable
in [the other port's streaming handoff diagnosis](https://github.com/otavix010/gow-ascension-pc/blob/main/port/gowa_offline.cpp).
Its addresses were not copied into this build: the addresses above were mapped
from this port's ELF and generated code. Whether this race caused the specific
new crash still requires the guarded game run and its overlap logs.

## Implementation

`tools/patch_texstream_sync.py` creates a build-local copy of PPU chunk 006 and
adds calls at the five function entries, before registers are localized. It
rejects missing/version-mismatched sites and already-patched inputs. The
original lift is left byte-for-byte intact. CMake preserves the chunk's
compiler flags; only that chunk and the small host guard should recompile.

`host/texstream_sync.cpp` waits on the actual counter with acquire loads. It does
not change guest registers, tables, counter values or completion events. It
briefly pauses then yields. A two-second timeout prints the pending count,
legacy count, caller and table pointer and aborts instead of permitting unsafe
table mutation. `GOWA_TEXSTREAM_SYNC=0` disables the guard for a controlled
bisection. A banner verifies that the new executable has the guard; up to 32
wait records show `pending`, `legacy` and elapsed microseconds. `pending>0` with
`legacy=0` demonstrates an overlap the original wait would miss.

## Validation and next check

`tools/test_texstream_sync.py` compiles and runs the production host guard
without the game. Its fixture deliberately commits an old snapshot after a PPU
write, reproducing the lost update, then proves that the guard orders the write
after the delayed commit. All five sites, default/on/off modes, low-halfword
flags, context preservation and deterministic timeout handling pass. Patch
round-trip equality checks that no other generated guest statements change.
These fixtures do not establish live-game correctness or performance.

Next: build the game with `scripts/windows/build.ps1 -Name texstream-sync`, then
repeat `measure-30fps.ps1 -Name 30fps-stream-sync`. Inspect `[texstream-sync]`
records and the first memory/FIFO error (if any). A clean short run is progress,
not proof of whole-game stability or 30 FPS.

## First in-game validation

`30fps-stream-sync.log` completed its 180-second user run with no copy-offset
errors, FIFO errors, guard timeouts or foreign-fault crash found. Its executable
SHA-256 is `1DB1463B52643FEF6CC790F4A1DFD14B4B68EA0B9FC53E566A30BF6B936DED37`.
The guard logged real overlaps at the table writers: pending=1, legacy=0,
including waits up to 4,631 microseconds in the first 32 reported waits. This
confirms that the original counter read missed live work. One clean run does
not establish that every memory-corruption source is fixed.

After warm-up, 11 no-delay windows have FPS median 17.55, frame-median 55.49 ms,
and median window-p90 63.28 ms. Valid neighboring comparisons: RSX +4 ms gives
-0.19 ms median frame effect (4 pairs, quartiles -1.47/+0.66); PPU +4 ms gives
+4.12 ms (3 pairs, quartiles +3.50/+5.78); module 218 +10 us/job gives +0.48 ms
(3 pairs, quartiles -0.76/+2.41). For this scene/build the PPU is the next
critical-path target; the sample does not separate PPU computation from waits.
These FPS are not a controlled before/after estimate of the guard's cost.

Next: profile the corrected run without causal delays or job timing, including
the main PPU and per-thread CPU time, before choosing the PPU optimization.
