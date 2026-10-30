"""Guard for the PPU crash at lr=0x0043D17C (work/reports/PPU-43D17C-2026-10-29.md).

func_00439658 (guest 0x4396E0, lwz r6,0(r31)) reads through an address built
from node8 + u32[node8+0x14] + (desc[+0x10] << 4) that, now and then, lands in
uncommitted guest space. The emitter's own error contract is used instead of
crashing: *out (r27) = 0xC00A0003 and return through its epilogue; the walker at
0x43D180 tests the sign bit and propagates it. Applied to the generated
src/recomp (the file holding func_00439658; relift.ps1 runs it after a PPU
lift). Byte-level, idempotent. Windows only: ppu_guest_ea_committed lives in
ps3kit's boot_main.cpp under _WIN32.
"""
import glob
import os
import sys

ARG = sys.argv[1] if len(sys.argv) > 1 else "src/recomp"
MARK = b"/* GOWA guard 43D17C */"
FUNC = b"void func_00439658(ppu_context* ctx) {"
SITE = b"        _g6 = vm_read32(_g31 + 0x0);"
GUARD = (b"        " + MARK + b" if (!ppu_guest_ea_committed((uint32_t)_g31, 6)) { "
         b"static int _n; if (_n++ < 8) fprintf(stderr, \"[guard-43D17C] ea=0x%08X uncommitted: emitter fails 0xC00A0003\\n\", (uint32_t)_g31); "
         b"vm_write32(_g27 + 0x0, 0xC00A0003u); goto loc_0043A2E8; }\n")
DECL = b'extern "C" int ppu_guest_ea_committed(uint32_t ea, uint32_t size);\n'

paths = sorted(glob.glob(os.path.join(ARG, "ppu_recomp_*.cpp"))) if os.path.isdir(ARG) else [ARG]
PATH = next((q for q in paths if FUNC in open(q, "rb").read()), None)
if PATH is None:
    sys.exit("func_00439658 not found under " + ARG)
data = open(PATH, "rb").read()
NL = b"\r\n" if b"\r\n" in data[:4096] else b"\n"
GUARD = GUARD[:-1] + NL
DECL = DECL[:-1] + NL
if MARK in data:
    print("already patched"); sys.exit(0)
f = data.index(FUNC)
end = data.index(b"\nvoid func_", f + len(FUNC))
s = data.index(SITE, f)
assert s < end, "site not inside func_00439658"
data = data[:s] + GUARD + data[s:]
inc = data.index(b'#include "ppu_recomp.h"' + NL) + len(b'#include "ppu_recomp.h"' + NL)
data = data[:inc] + DECL + data[inc:]
open(PATH, "wb").write(data)
print("patched at byte", s)
