"""Build a guarded copy of the BCES01741 1.00 PPU TU; leave the lift untouched.

Two official waits use 0x967028 although dispatch increments 0x967024.
The other three sites modify the table at *(u32*)0x96E174 while the SPU job
may hold a full-table snapshot. The hook precedes guest register localization.
"""
import argparse
import re
from pathlib import Path

SITES = ("00366DB8", "00366E18", "0036DD1C", "0036EEF8", "003707D8")
DECL = '\nextern "C" void ascension_texstream_wait(ppu_context*, uint32_t);\n'


def patch(source):
    if "ascension_texstream_wait" in source:
        raise ValueError("input already contains the streaming guard")
    include = '#include "ppu_recomp.h"'
    if source.count(include) != 1:
        raise ValueError("expected one ppu_recomp.h include")
    # Fail closed on another lift/version; do not attach these fixed addresses
    # to an unrecognized TU just because a function name happens to exist.
    for site in SITES:
        pattern = rf"^void func_{site}\(ppu_context\* ctx\) \{{\r?\n"
        matches = list(re.finditer(pattern, source, re.M))
        if len(matches) != 1:
            raise ValueError(f"expected one function {site}, got {len(matches)}")
        start = matches[0].end()
        end = source.find("\nvoid func_", start)
        body = source[start:end if end >= 0 else None]
        marker = "vm_read16(_g3 + 0x7028)" if site in SITES[:2] else "-0x1E8C"
        if marker not in body:
            raise ValueError(f"function {site} lacks its BCES01741 marker {marker}")
        source = source[:start] + f"        ascension_texstream_wait(ctx, 0x{site}u);\n" + source[start:]
    return source.replace(include, include + DECL, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fallback", action="store_true",
                        help="on an unrecognized TU, write it unchanged and warn instead of failing "
                             "(the build: a player's lift that differs must still build)")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("source and output must be different files")
    text = args.source.read_bytes().decode("latin-1")
    try:
        result = patch(text)
    except ValueError as e:
        if not args.fallback:
            raise
        print(f"WARNING: streaming guard NOT applied ({e}); {args.output} is the lift unchanged")
        result = text
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result.encode("latin-1"))
    if result is not text:
        print(f"Streaming guards: {len(SITES)} sites -> {args.output}")


if __name__ == "__main__":
    main()
