#!/bin/sh
# Lift the game into src/ (macOS and Linux; relift.ps1 is the Windows one).
#
#   scripts/mac/relift.sh ppu          # the PPU code -> src/recomp (under a minute)
#   scripts/mac/relift.sh spu          # the 4 embedded SPU images and the Wws policy module -> src/spu
#   scripts/mac/relift.sh jobmods      # the 33 job modules (input/jobmods, else work/jobmods) -> src/spu/jobmod_*
#   scripts/mac/relift.sh fragments    # tools/job_fragments.json -> src/spu/pic_*
#   scripts/mac/relift.sh all          # all four
# Linux: scripts/linux/relift.sh (same steps).
#
# Reads input/EBOOT.ELF (or EBOOT_ELF=<path>), meta/, and work/jobmods. Python
# 3.10 or newer: ../.venv/bin/python when it exists, else python3 (PYTHON=...
# overrides). Logs in build/logs/relift-<what>.log. Run scripts/mac/build.sh
# (or scripts/linux/build.sh) after.
set -e
here=$(cd "$(dirname "$0")/../.." && pwd)
top=$(cd "$here/.." && pwd)
. "$here/scripts/unix/env.sh"
tools="$PS3KIT_DIR/tools"
spu="$here/src/spu"
elf=${EBOOT_ELF:-$here/input/EBOOT.ELF}
# the job modules: the launcher's installation cuts them out of the EBOOT.ELF into input/jobmods
jobmods="$here/input/jobmods"
[ -d "$jobmods" ] || jobmods="$WORK_DIR/jobmods"
if [ -z "$PYTHON" ]; then
    if [ -x "$top/.venv/bin/python" ]; then PYTHON="$top/.venv/bin/python"; else PYTHON=python3; fi
fi
mkdir -p "$here/build/logs"
# Job modules and fragments: functions using 17-64 SPU registers keep them in C
# locals, as relift.ps1 (ASCENSION_PLAN.md R6). SPU_LIFT_PROMOTE=0 for none.
promote=${SPU_LIFT_PROMOTE:-1}
band=${SPU_LIFT_PROMOTE_BAND:-17-64}

lift() {
    what=$1
    log="$here/build/logs/relift-$what.log"
    echo "relift $what (log: $log)"
    case $what in
    ppu)
        [ -f "$elf" ] || { echo "no $elf" >&2; exit 1; }
        # --reg-locals as relift.ps1: guest registers in C locals. --insn-switches:
        # the GOWA_* environment switches (the launcher's effects, the scheduler's wait).
        "$PYTHON" "$tools/ppu_lifter.py" "$elf" --functions "$here/meta/functions.json" \
            --hle-stubs "$here/meta/EBOOT.imports.json" --toc 0x81EF60 --code-end 0x62C4CC \
            --chunk-lines 150000 --reg-locals --insn-switches "$here/tools/ppu_switches.json" \
            --hle-hooks "$here/tools/ppu_hle_hooks.json" \
            -o "$here/src/recomp" > "$log" 2>&1 ;;
    spu)
        "$PYTHON" "$tools/build_spu_workloads.py" --images "$here/meta/spu" --lifted "$spu" \
            --out "$spu/spu_workloads.c" --register-fn ascension_spu_register_all --constructor \
            --title ascension --relift \
            --extra-funcs spu_wws_pm_at_0077CA80=0xA2C,0xA68,0x3368,0x3378 > "$log" 2>&1 ;;
    jobmods)
        # merged chunks and module 218's native functions, as relift.ps1
        SPU_LIFT_PROMOTE=$promote SPU_LIFT_PROMOTE_BAND=$band \
        LIFT_JOBMODS_MERGE=1 LIFT_NATIVE="$PS3KIT_DIR/libs/spu_hle/gowa_drawcmd/native_functions.txt" \
        "$PYTHON" "$tools/lift_jobmods.py" --jobmods "$jobmods" --out "$spu" \
            --register "$spu/jobmods_register.c" --symbol-prefix ascension \
            --extra-funcs-json "$here/tools/jobmods_extra_funcs.json" > "$log" 2>&1 ;;
    fragments)
        [ -f "$elf" ] || { echo "no $elf" >&2; exit 1; }
        SPU_LIFT_PROMOTE=$promote SPU_LIFT_PROMOTE_BAND=$band \
        "$PYTHON" "$tools/lift_spu_pic.py" --elf "$elf" --fragments "$here/tools/job_fragments.json" \
            --out "$spu" --register "$spu/pic_register.c" --symbol-prefix ascension > "$log" 2>&1 ;;
    *)
        echo "usage: $0 ppu|spu|jobmods|fragments|all" >&2; exit 2 ;;
    esac
    tail -n 2 "$log"
}

if [ "$1" = all ]; then
    for w in ppu spu jobmods fragments; do lift $w; done
else
    lift "${1:-}"
fi
