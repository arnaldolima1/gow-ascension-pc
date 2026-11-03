#!/usr/bin/env python3
"""SPU code that fell to the interpreter, turned into entries for the next lift.

A run with SPU_INTERP_LOG=<file> (ps3kit runtime/spu/spu_channels.c) writes one
line per (image, overlay, entry) the interpreter ran:

    img=<image id> ovl=<overlay> start=0x<LS pc> steps=<n> calls=<n>

The overlay is the job module's image id: 200 + its index in the generated
src/spu/jobmods_register.c. For each job module entry this tool:

  - adds it to tools/jobmods_extra_funcs.json when the lift has no function
    there (the next `setup.py spu` lifts it);
  - reports it as REFUSED when the lift already has that function: the runtime
    declined to rejoin it (an interrupt window, `SPU_PROBE_LOG=1` says why), so
    another lift does not help;
  - reports entries outside job modules (main images, code fragments) for a
    hand-made fix in job_fragments.json or the image's own entries.

Usage:
    python tools/interp_entries.py build/logs/interp-*.txt            # report
    python tools/interp_entries.py build/logs/interp-*.txt --write    # and update the json
"""
import argparse, json, os, re, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = re.compile(r"img=(-?\d+) ovl=(-?\d+) start=0x([0-9A-Fa-f]+) steps=(\d+) calls=(\d+)")
REG = re.compile(r"spu_begin_image\((\d+)\);\s*(jobmod_\w+?)_spu_recomp_register\(\)")


def load_log(paths):
    """(ovl, pc) -> [steps, calls, img], summed over the files."""
    out = defaultdict(lambda: [0, 0, None])
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = LINE.search(line)
                if not m:
                    continue
                img, ovl, pc, steps, calls = int(m[1]), int(m[2]), int(m[3], 16), int(m[4]), int(m[5])
                e = out[(ovl, pc)]
                e[0] += steps
                e[1] += calls
                e[2] = img
    return out


def load_modules(src):
    """overlay id -> (module name, size, lifted function addresses)."""
    reg = os.path.join(src, "spu", "jobmods_register.c")
    man = os.path.join(src, "spu", "jobmods_manifest.json")
    if not os.path.exists(reg):
        sys.exit(f"{reg} not found: lift the job modules first (setup.py spu)")
    with open(reg, encoding="utf-8") as f:
        ids = {int(i): name for i, name in REG.findall(f.read())}
    sizes = {}
    if os.path.exists(man):
        with open(man, encoding="utf-8") as f:
            sizes = {m["name"]: m["size"] for m in json.load(f)}
    mods = {}
    for ovl, name in ids.items():
        funcs = set()
        c = os.path.join(src, "spu", name, "spu_recomp.c")
        if os.path.exists(c):
            with open(c, encoding="utf-8", errors="replace") as f:
                for m in re.finditer(rf"^\w[\w ]*\b{re.escape(name)}_spu_func_([0-9A-Fa-f]{{8}})\(", f.read(), re.M):
                    funcs.add(int(m[1], 16))
        mods[ovl] = (name, sizes.get(name), funcs)
    return mods


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="+", help="SPU_INTERP_LOG files (several runs are summed)")
    ap.add_argument("--src", default=os.path.join(ROOT, "src"), help="the lifted sources (default: src)")
    ap.add_argument("--json", default=os.path.join(ROOT, "tools", "jobmods_extra_funcs.json"))
    ap.add_argument("--min-steps", type=int, default=0,
                    help="leave out entries that ran fewer interpreted instructions than this")
    ap.add_argument("--write", action="store_true", help="add the missing entries to --json")
    a = ap.parse_args()

    log = load_log(a.logs)
    if not log:
        sys.exit("no img=/ovl=/start= lines in the logs")
    mods = load_modules(a.src)
    with open(a.json, encoding="utf-8") as f:
        extra = json.load(f)

    total = sum(e[0] for e in log.values())
    add, refused, other = defaultdict(list), [], []
    for (ovl, pc), (steps, calls, img) in sorted(log.items(), key=lambda kv: -kv[1][0]):
        if steps < a.min_steps:
            continue
        mod = mods.get(ovl)
        if not mod:
            other.append((ovl, pc, steps, calls, img))
            continue
        name, size, funcs = mod
        if size is not None and not (0x4000 <= pc < 0x4000 + size):
            other.append((ovl, pc, steps, calls, img))
        elif pc in funcs:
            refused.append((name, pc, steps, calls))
        elif pc not in {int(x, 0) for x in extra.get(name, [])}:
            add[name].append((pc, steps, calls))

    def pct(s):
        return f"{100.0 * s / total:5.1f}%" if total else "  -  "

    print(f"{len(log)} entries, {total} interpreted instructions in all")
    print(f"\nnew lift entries ({sum(len(v) for v in add.values())}):")
    for name, items in add.items():
        for pc, steps, calls in items:
            print(f"  {pct(steps)}  {name} 0x{pc:X}  steps={steps} calls={calls}")
    print(f"\nREFUSED: already lifted, the runtime declined them ({len(refused)}; SPU_PROBE_LOG=1 says why):")
    for name, pc, steps, calls in refused:
        print(f"  {pct(steps)}  {name} 0x{pc:X}  steps={steps} calls={calls}")
    print(f"\noutside the job modules, by hand ({len(other)}):")
    for ovl, pc, steps, calls, img in other:
        print(f"  {pct(steps)}  img={img} ovl={ovl} 0x{pc:X}  steps={steps} calls={calls}")

    if a.write and add:
        for name, items in add.items():
            have = [int(x, 0) for x in extra.get(name, [])]
            extra[name] = [hex(x) for x in sorted(set(have) | {pc for pc, _, _ in items})]
        with open(a.json, "w", encoding="utf-8", newline="\n") as f:
            json.dump(extra, f, indent=1)
            f.write("\n")
        print(f"\n{a.json} updated: run the SPU lift again (setup.py spu, or relift spu).")
    elif add:
        print("\n(--write adds them to the json)")


if __name__ == "__main__":
    main()
