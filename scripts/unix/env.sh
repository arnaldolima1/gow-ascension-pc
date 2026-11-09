#!/bin/sh
# Build settings from .env in the repository root (local, never committed).
# Source it from the other scripts after setting $here (the ascension/ folder):
#
#   . "$here/scripts/unix/env.sh"
#
# Sets PS3KIT_DIR, WORK_DIR, BUILD_TYPE, JOBS, RPCS3_RSX, RSX_VULKAN, GPU_BUILD_DIR,
# FFMPEG_INCLUDE_DIR, VKD3D_DIR (paths made absolute). Stops when .env or a
# setting the build needs is missing.

env_file="$here/.env"
[ -f "$env_file" ] || { echo "missing $env_file" >&2; exit 1; }
while IFS= read -r line || [ -n "$line" ]; do
    line=$(printf '%s' "$line" | tr -d '\r')
    case "$line" in ''|'#'*) continue ;; esac
    key=${line%%=*}
    [ "$key" = "$line" ] && continue
    val=${line#*=}
    val=$(printf '%s' "$val" | sed -e 's/^ *//' -e 's/ *$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/")
    key=$(printf '%s' "$key" | tr -d ' ')
    case "$key" in
        PS3KIT_DIR|WORK_DIR|BUILD_TYPE|JOBS|RPCS3_RSX|RSX_VULKAN|GPU_BUILD_DIR|FFMPEG_INCLUDE_DIR|VKD3D_DIR) eval "$key=\$val" ;;
    esac
done < "$env_file"

abs() { case "$1" in /*) printf '%s' "$1" ;; '') ;; *) (cd "$here" && cd "$(dirname "$1")" 2>/dev/null && printf '%s/%s' "$(pwd)" "$(basename "$1")") ;; esac; }
for key in PS3KIT_DIR WORK_DIR BUILD_TYPE; do
    eval "v=\${$key:-}"
    [ -n "$v" ] || { echo "missing $key in $env_file" >&2; exit 1; }
done
PS3KIT_DIR=$(abs "$PS3KIT_DIR"); WORK_DIR=$(abs "$WORK_DIR")
GPU_BUILD_DIR=$(abs "${GPU_BUILD_DIR:-}"); FFMPEG_INCLUDE_DIR=$(abs "${FFMPEG_INCLUDE_DIR:-}")
VKD3D_DIR=$(abs "${VKD3D_DIR:-}")
RPCS3_RSX=${RPCS3:-${RPCS3_RSX:-0}}
JOBS=${JOBS:-}
[ -d "$PS3KIT_DIR" ] || { echo "PS3KIT_DIR not found: $PS3KIT_DIR" >&2; exit 1; }
if [ "$RPCS3_RSX" = 1 ] && [ -z "$GPU_BUILD_DIR" ]; then
    echo "RPCS3_RSX=1 needs GPU_BUILD_DIR in $env_file" >&2; exit 1
fi
