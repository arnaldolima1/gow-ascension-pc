#!/bin/sh
# The first level on the Mac from a new game, with no save (run.ps1 -Level is
# the Windows one, from a save): the intro, the main menu, Single player, a new
# game, then Cross every 5 s through the opening (Kratos in chains, ~140 s) to
# the first fight (the Fury, ~260 s). One instance at a time: a running one is
# killed first. Log in ../work/run.log; fps = FLIP_STATS' guest flip requests.
#
#   scripts/mac/run-level.sh [seconds]          # default 360
#   RSX_ENGINE_DRAW_PROF=1 scripts/mac/run-level.sh 400
#
# The first Cross at 14 s matters: runs without it (no input, or the intro cut
# short by the skip-intro mod or by Cross at other times) froze at ~30 s on
# 2026-11-10, the PPU waiting forever in func_003E798C on an SPU job (to fix).
# Extra environment switches pass through. ASCENSION_ISO overrides the disc.
set -e
here=$(cd "$(dirname "$0")/../.." && pwd)
work=${ASCENSION_WORK:-$here/../work}
secs=${1:-360}
iso=${ASCENSION_ISO:-/Volumes/Externo/isos/God of War - Ascension.iso}
exe="$here/build/mac/AscensionRecomp"
[ -x "$exe" ] || { echo "no $exe: scripts/mac/build.sh first" >&2; exit 1; }

pkill -9 -f "$exe" 2>/dev/null || true
for i in 1 2 3 4 5; do pgrep -f "$exe" >/dev/null || break; sleep 1; done
if pgrep -f "$exe" >/dev/null; then echo "an instance is still running" >&2; exit 1; fi

mkdir -p "$work/disc" "$work/hdd0"
work=$(cd "$work" && pwd)
[ -d "$work/disc/PS3_GAME" ] || hdiutil attach -readonly -nobrowse -mountpoint "$work/disc" "$iso" >/dev/null

pad="14:0x4000,15:0x0000,24:0x4000,25:0x0000,27:0x4000,28:0x0000,30:0x4000,31:0x0000,33:0x4000,34:0x0000"
t=45
while [ $t -le $((secs - 5)) ]; do pad="$pad,$t:0x4000,$((t + 1)):0x0000"; t=$((t + 5)); done

cd "$work"
PAD_SCRIPT="$pad" FLIP_STATS=${FLIP_STATS:-1} RSX_ENGINE_GPU_VFETCH=${RSX_ENGINE_GPU_VFETCH:-1} \
PS3_VFS_ROOT="$work/disc" PS3_HDD0_ROOT="$work/hdd0" PS3_RSX=${PS3_RSX:-vulkan} \
PS3_WINDOW_SIZE=${PS3_WINDOW_SIZE:-960x540} PS3_VOLUME=${PS3_VOLUME:-1} \
    "$exe" "$here/input/EBOOT.ELF" > "$work/run.log" 2>&1 &
pid=$!
echo "AscensionRecomp (pid $pid) for $secs s; log: $work/run.log"
waited=0
while [ $waited -lt "$secs" ] && kill -0 $pid 2>/dev/null; do sleep 5; waited=$((waited + 5)); done
kill -9 $pid 2>/dev/null || true
wait $pid 2>/dev/null || true
echo "fps (guest flips a second, last minute):"
grep 'guest flip requests' "$work/run.log" | tail -12 | sed 's/.*queued in the FIFO /  /' | tr '\n' ' '
echo
