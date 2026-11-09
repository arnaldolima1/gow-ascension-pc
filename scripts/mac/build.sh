#!/bin/sh
# Configure (the first time) and build into build/mac (macOS; build.ps1 is the
# Windows one). Log in build/logs/build[-<name>].log; prints the time, the first
# error lines and the last line.
#
#   scripts/mac/build.sh            # build
#   scripts/mac/build.sh <name>     # same, log named build-<name>.log
#   CONFIGURE=1 scripts/mac/build.sh   # run CMake again (after changing .env)
#
# Settings from .env (scripts/unix/env.sh); RPCS3_RSX=1 there links RPCS3's RSX
# (scripts/mac/build-gpu.sh first), and VKD3D_DIR=<prefix> builds the live
# draw engine's D3D12 on vkd3d (scripts/mac/build-vkd3d.sh first).
#
# Needs: brew install cmake ninja sdl2 glslang spirv-cross ffmpeg
# A build from scratch takes 20-40 minutes and wants 16 GB of memory; JOBS=<n>
# caps the parallel compiles (default: the CPU count, at most 6, as each lifted
# PPU unit takes 1-2 GB).
set -e
here=$(cd "$(dirname "$0")/../.." && pwd)
. "$here/scripts/unix/env.sh"
build="$here/build/mac"
logs="$here/build/logs"
mkdir -p "$logs"
log="$logs/build${1:+-$1}.log"

missing=""
for tool in cmake ninja; do command -v $tool >/dev/null 2>&1 || missing="$missing $tool"; done
for pkg in sdl2 glslang spirv-cross ffmpeg; do
    [ -d "$(brew --prefix 2>/dev/null)/opt/$pkg" ] || missing="$missing $pkg"
done
if [ -n "$missing" ]; then
    echo "missing:$missing  (brew install$missing)" >&2
    exit 1
fi

rpcs3="-DASCENSION_RPCS3_RSX=OFF"
if [ "$RPCS3_RSX" = 1 ]; then
    rpcs3="-DASCENSION_RPCS3_RSX=ON -DASCENSION_RPCS3_BUILD=$GPU_BUILD_DIR"
    if [ ! -f "$GPU_BUILD_DIR/libps3rsx.a" ]; then
        echo "RPCS3_RSX=1 needs $GPU_BUILD_DIR/libps3rsx.a: run scripts/mac/build-gpu.sh first" >&2
        exit 1
    fi
fi
vkd3d="-DPS3RECOMP_LIVE_DRAW_VKD3D=OFF"
if [ -n "$VKD3D_DIR" ]; then
    if [ ! -f "$VKD3D_DIR/include/vkd3d/vkd3d_dxgi1_4.h" ]; then
        echo "VKD3D_DIR=$VKD3D_DIR has no vkd3d: run scripts/mac/build-vkd3d.sh first" >&2
        exit 1
    fi
    vkd3d="-DPS3RECOMP_LIVE_DRAW_VKD3D=ON -DPS3RECOMP_VKD3D_DIR=$VKD3D_DIR"
fi
# RSX_VULKAN=1 in .env builds ps3kit's own Vulkan renderer (PS3_RSX=vulkan, on
# MoltenVK), as build.ps1 does on Windows
vulkan="-DPS3RECOMP_RSX_VULKAN=OFF"
[ "${RSX_VULKAN:-}" = 1 ] && vulkan="-DPS3RECOMP_RSX_VULKAN=ON"
if [ ! -f "$build/build.ninja" ] || [ "${CONFIGURE:-}" = 1 ]; then
    cmake -S "$here" -B "$build" -G Ninja -DCMAKE_BUILD_TYPE="$BUILD_TYPE" -DPS3RECOMP_DIR="$PS3KIT_DIR" \
        -DPS3RECOMP_FFMPEG_RUNTIME=ON -DPS3RECOMP_FFMPEG_INCLUDE_DIR="${FFMPEG_INCLUDE_DIR:-$(brew --prefix)/include}" \
        $rpcs3 $vkd3d $vulkan \
        > "$logs/configure.log" 2>&1 || { tail -n 20 "$logs/configure.log"; exit 1; }
fi

jobs=${JOBS:-$(sysctl -n hw.ncpu 2>/dev/null || nproc)}
[ -z "$JOBS" ] && [ "$jobs" -gt 6 ] && jobs=6
start=$(date +%s)
set +e
ninja -C "$build" -j "$jobs" > "$log" 2>&1
code=$?
set -e
secs=$(( $(date +%s) - start ))
if [ $code -eq 0 ]; then state=OK; else state=FAILED; fi
printf 'build %s in %d:%02d  (log: %s)\n' "$state" $((secs / 60)) $((secs % 60)) "$log"
grep -E "error:|FAILED:|fatal error|Undefined symbols" "$log" | head -n 15 | sed 's/^/  /'
echo "last line: $(tail -n 1 "$log")"
exit $code
