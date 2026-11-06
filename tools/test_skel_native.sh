#!/bin/sh
# host/skeleton_native.cpp against the lifted func_002A434C. Needs src/recomp.
# Real calls: run the level with GOWA_SKEL_CAP=<file>,600,64 first.
# usage: tools/test_skel_native.sh [capture|-] [random cases]
set -e
here="$(cd "$(dirname "$0")/.." && pwd)"
kit="${PS3KIT:-$here/../ps3kit}"
out="${TMPDIR:-/tmp}/test_skel_native.$$"
mkdir -p "$out"
trap 'rm -rf "$out"' EXIT
chunk="$here/src/recomp/ppu_recomp_004.cpp"
first=$(grep -n 'void func_[0-9A-F]*(ppu_context\* ctx) {' "$chunk" | head -1 | cut -d: -f1)
# the chunk's helpers, then the function with its gate out, under another name
{
    head -n $((first - 1)) "$chunk" | grep -v '^/\* func_\|^PPU_FMA_FN $' | sed '/^__attribute__((weak)) $/d'
    sed -n '/void func_002A434C(ppu_context\* ctx) {/,/^}/p' "$chunk" | grep -v 'gowa_skel_gate' |
        sed 's/void func_002A434C(ppu_context\* ctx)/extern "C" void lifted_002A434C(ppu_context* ctx)/'
} > "$out/lifted.cpp"
arch=""
[ "$(uname -m)" = arm64 ] && arch="-arch x86_64"
flags="$arch -std=c++17 -O2 -mavx2 -mbmi2 -mfma -ffp-contract=off -w -I$here/src/recomp -I$kit/include -I$kit/runtime/ppu -I$kit/runtime/memory"
clang++ $flags -c "$out/lifted.cpp" -o "$out/lifted.o"
clang++ $flags -c "$here/tools/test_skel_native.cpp" -o "$out/test.o"
clang++ $arch "$out/lifted.o" "$out/test.o" -o "$out/test"
"$out/test" "${1:--}" "${2:-20000}"
