# Milestones

What the game could do, and when. Brazilian Portuguese: [MILESTONES.pt-BR.md](MILESTONES.pt-BR.md); a new row goes in both files.

| Date | Milestone |
| --- | --- |
| 2026-10-15 | `EBOOT.BIN` decrypted, imports and functions found, 1.8 million lines of C++ lifted and compiled; the executable starts. |
| 2026-10-15 | Boots through the system checks and mounts the game's archives (`sys_lwcond_t` layout, files past 2 GB, Edge Zlib on the host). |
| 2026-10-15 | The intro screens render: the legal text, "Sony Computer Entertainment presents", Santa Monica Studio, the online-play notice (live draw engine). The same on macOS through Metal. |
| 2026-10-16 | The main renderer runs past its second frame: SPURS2 (32 workloads, tempArea, flags1), the frame's SPU post-process, GPU/SPU synchronization. |
| 2026-10-16 | Re-lifted with the v0.15 lifter (a spill-reload bug corrupted a heap at frame ~12): the loading screen. |
| 2026-10-16 | Past the loading screen (SPURS tasksets: duplicate starts, Taskset2 size and event flags, SPU-created tasks). |
| 2026-10-16 | The menus read: X16 font atlas, framebuffer sRGB and texture gamma, fragment `DDX`/`DDY` in the live draw engine. |
| 2026-10-17 | The opening cinematic plays with picture and sound (`cellVdec` with FFmpeg at run time; the "black screen" was the game's fade card waiting for it). |
| 2026-10-17 | Performance: the 15 Wws job modules lifted, a performance panel. First-use menus 5-6 → ~10 fps. |
| 2026-10-17 | Performance, part two: position-independent lifts of streamed job code, SSE4.1 for lifted SPU code. Menus ~10 → 26-55 fps, cinematic ~35 → 45-60 fps. |
| 2026-10-17 | RsxSync woken by GPU reports, SSE4.1 SPU ops, 381 job-module entries, the interpreter honouring interrupt enables. Cinematic video at 72-90% speed. |
| 2026-10-17 | **The cinematic at full speed and in sync** (29.98 fps), the end-of-loading stall gone, module 214 lifted whole (GPU reports wait for the post-process tasks, no lost task wakes, `cellVdec` holds AUs). |
| 2026-10-17 | The main menu renders (about 1 fps). |
| 2026-10-17 | **A launcher:** video, language, subtitles and mods; the game renders inside its window. |
| 2026-10-17 | **Main menu 1 -> 12 fps:** the 18 job modules the loading never streams lifted too (33 in all), streamed code found inside bigger GETs and by content. |
| 2026-10-17 | Brazilian Portuguese (voices from the US disc, text already on the EU disc); mods as recipes, Skip intro included. |
| 2026-10-18 | **The first level** (Kratos in chains): a lost-task race in the SPURS taskset scheduler fixed; the level loads and runs (~16 fps on live draw). |
| 2026-10-19 | **RPCS3's RSX as the renderer** (Windows and macOS): the game's GPU/SPU post-process rounds paced on the game's own progress. |
| 2026-10-19 | Main menu 12 → 28 fps on RPCS3's RSX: SPU transfers into surfaces the GPU protected were being dropped. |
| 2026-10-19 | **Level textures correct:** IO space handed back on unmap, so the scenery's vertex streams no longer read the command buffer. |
| 2026-10-20 | Level ~10 → ~15 fps: lifted SPU floats without the extended-range check (RPCS3's "approximate" rules), no local-store diagnostics in lifted code, contiguous job-module code lifted as one function, streamed code found by an index. |
| 2026-10-21 | Level ~15 → ~16.7 fps: each SPU on its own core, the main PPU thread on core 0. |
| 2026-10-21 | **SPU job replay:** recorded game jobs rerun outside the game and checked byte for byte by what they write, with timing and profiling. Module 218 (per-draw geometry) decoded: index decompression and position transform written natively, identical on the recorded jobs; the rest of the job goes native next. |
| 2026-10-22 | Level ~15 → ~17.5 fps: the main processor's recompiled code keeps the game's registers in local variables instead of memory (re-lifted; 1.5-1.8x on isolated functions). |
| 2026-10-23 | More SPU code that was still being interpreted is now recompiled, and two streamed pieces of the geometry job run natively. |
| 2026-10-23 | Launcher **Video → Effects**: depth of field, motion blur and MLAA can be turned off (the same patches RPCS3 offers, found in the 1.00 disc). Experimental: textures still glitch with them off. |
| 2026-10-23 | Level ~17.5 → ~22 fps: lifted SPU code built for AVX2, lighter SPU runtime. |
| 2026-10-23 | **The frame's edge-smoothing post-process runs natively:** its four heaviest SPU stages rewritten in C, identical to the original on 12 million checked calls; that work costs about half. |
| 2026-10-23 | **First boss fight reached** (13-21 fps while fighting). The profile there shows the SPU time spread over many small pieces, so the next work goes after costs every SPU job pays, not one function at a time. |
| 2026-11-03 | Measured on Windows against RPCS3 in the same first-level scene: 22 fps native, 35-40 on RPCS3. Two changes become the default: the RSX thread sleeps on an empty command queue instead of spinning (~8% shorter frames on a 4-core PC), and the SPUs pick their next work themselves (~1.6% shorter on the same PC). |
| 2026-11-03 | **The intermittent level freeze found and fixed:** a store from the main processor could be lost in the middle of an SPU's atomic operation, leaving the geometry lists waiting forever. The repro went from 3 freezes in 5 runs to none in 4. |
| 2026-11-04 | The first level's frame measured part by part: of ~50 ms, ~21 ms are the SPUs' geometry lists (EDGE) and ~9-12 ms the wait for the RSX thread between that geometry's two passes. |
| 2026-11-04 | **Runs on macOS again** (Apple Silicon, RPCS3's RSX), for testing: the RSX thread now recovers from corrupted command data instead of stopping the game. |
| 2026-11-04 | **Multiplayer reaches the warrior lobby** with the project's own server (in development, still private); the player's multiplayer profile is kept on their account. Online matches do not work yet. |
| 2026-11-04 | Two more defaults, each measured in-run on a 4-core PC: the game's main thread above normal priority (-2.7 ms a frame) and the frame's tail jobs spread over up to 4-5 SPUs (-2.1 ms). The main processor's code built with profile-guided optimization (PGO): ~10% shorter frames. |
| 2026-11-05 | **The `CopyLocalMemory offset error` freeze fixed:** an Edge Zlib counter, and a guard on the texture streaming table's hand-off. None in 40 level runs on 4 cores. |
| 2026-11-05 | **The RSX off the critical path:** its wait between EDGE's two geometry passes went from 9-12 ms to ~0.1 ms. The first level runs at ~24 fps on the whole PC and ~17-18 on 4 cores (was ~14-15); the frame is now ~55% SPU module 218, where the job manager's interrupts cost as much as the jobs' own code. |
| 2026-11-05 | Multiplayer: quick match gets past the player's location and picks its matchmaking server on the project's own server; the game connects and opens an SSL 3.0 session, which the server is learning to answer. |
