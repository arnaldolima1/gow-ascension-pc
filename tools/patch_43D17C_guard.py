"""Guards for the PPU crash at lr=0x0043D17C (work/reports/PPU-43D17C-2026-10-29.md).

func_00439658 reads through addresses built from scene-node fields (node8 +
u32[node8+0x14] + (desc[+0x10] << 4), and a block base derived the same way)
that, now and then, land in uncommitted guest space. Two sites have faulted:

  read   guest 0x4396E0, lwz r6,0(r31)            (vm_read32, the first five runs)
  copy   loc_00439C68, the 16-byte block copy loop (vm_read64, 10-29 23:53)

Before each, an unreadable range takes the emitter's own error contract
instead of crashing: *out (r27) = 0xC00A0003 and return through its epilogue;
the walker at 0x43D180 tests the sign bit and propagates it. Applied to the
generated src/recomp (the file holding func_00439658; relift.ps1 runs it after
a PPU lift). Byte-level, idempotent per guard. Windows only:
ppu_guest_ea_committed lives in ps3kit's boot_main.cpp under _WIN32.
"""
import glob
import os
import sys

ARG = sys.argv[1] if len(sys.argv) > 1 else "src/recomp"
FUNC = b"void func_00439658(ppu_context* ctx) {"
DECL = b'extern "C" int ppu_guest_ea_committed(uint32_t ea, uint32_t size);'
FAIL = b"vm_write32(_g27 + 0x0, 0xC00A0003u); goto loc_0043A2E8;"

# (mark, anchor, what must follow the anchor, guard code); the guard goes
# right after the anchor.
GUARDS = [
    (b"/* GOWA guard 43D17C */", b"", b"        _g6 = vm_read32(_g31 + 0x0);",
     b"        /* GOWA guard 43D17C */ if (!ppu_guest_ea_committed((uint32_t)_g31, 6)) { "
     b"static int _n; if (_n++ < 8) fprintf(stderr, \"[guard-43D17C] ea=0x%08X uncommitted: emitter fails 0xC00A0003\\n\", (uint32_t)_g31); "
     + FAIL + b" }"),
    (b"/* GOWA guard 43D17C copy */", b"        _g4 = vm_read64(_g1 + 0xC0);", b"loc_00439C68:",
     b"        /* GOWA guard 43D17C copy */ { const uint32_t _o = (uint32_t)(_g3 << 4), _s = (uint32_t)(_g4 + _o), _d = (uint32_t)(_g19 + _o); "
     b"if (_ctr != 0 && (_ctr > 0x10000 || !ppu_guest_ea_committed(_s, (uint32_t)_ctr * 16u) || !ppu_guest_ea_committed(_d, (uint32_t)_ctr * 16u))) { "
     b"static int _n; if (_n++ < 8) fprintf(stderr, \"[guard-43D17C] copy src=0x%08X dst=0x%08X n=%u uncommitted: emitter fails 0xC00A0003\\n\", _s, _d, (unsigned)_ctr); "
     + FAIL + b" } }"),
]

paths = sorted(glob.glob(os.path.join(ARG, "ppu_recomp_*.cpp"))) if os.path.isdir(ARG) else [ARG]
PATH = next((q for q in paths if FUNC in open(q, "rb").read()), None)
if PATH is None:
    sys.exit("func_00439658 not found under " + ARG)
data = open(PATH, "rb").read()
NL = b"\r\n" if b"\r\n" in data[:4096] else b"\n"

done = 0
for mark, anchor, follow, code in GUARDS:
    if mark in data:
        continue
    f = data.index(FUNC)
    end = data.index(b"\nvoid func_", f + len(FUNC))
    key = anchor + NL + follow if anchor else follow
    s = data.index(key, f)
    assert s < end, "site not inside func_00439658: " + mark.decode()
    at = s + len(anchor + NL) if anchor else s
    data = data[:at] + code + NL + data[at:]
    done += 1
if DECL not in data:
    inc = data.index(b'#include "ppu_recomp.h"' + NL) + len(b'#include "ppu_recomp.h"' + NL)
    data = data[:inc] + DECL + NL + data[inc:]
if done:
    open(PATH, "wb").write(data)
print("patched %d guard(s) in %s" % (done, PATH) if done else "already patched")
