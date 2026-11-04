"""List the blocks of a God of War: Ascension WAD (from the player's own disc).

    python3 tools/wad_list.py R_SPARTANAVS00.WAD [--prefix MG_] [--dump N]

Layout (read 2026-11-04, ascension-online SPEC S9): a flat list of blocks, each
a 64-byte header (u16 tag, u16 flags, u32 size, char name[56], big-endian)
followed by `size` bytes, the next header at the 16-byte boundary after it.
Tags: 0x1 a resource (the name's prefix says which: MDL_ model, MG_ mesh
group, MAT_ material, ANM_ animation, PTC_/PEM_ particles...), 0x2/0x3
GroupStart/GroupEnd, 0x15 the WAD's name. Textures live in the .TS beside it.
Extract the WAD with tools/psarc_replace.py <PSARC> --cat /WAD/PS3_BE/<name>.WAD.
"""
import argparse, collections, struct

def blocks(data):
    off = 0
    while off + 64 <= len(data):
        tag, flags, size = struct.unpack(">HHI", data[off:off + 8])
        name = data[off + 8:off + 64].split(b"\0")[0].decode("latin1", "replace")
        yield off, tag, flags, size, name, data[off + 64:off + 64 + size]
        off = (off + 64 + size + 15) & ~15

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wad")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--dump", type=int, default=0, help="hex of the first N bytes of each listed block")
    a = ap.parse_args()
    data = open(a.wad, "rb").read()
    count = collections.Counter()
    for off, tag, flags, size, name, body in blocks(data):
        count[(tag, name.split("_")[0] if tag == 1 else name)] += 1
        if a.prefix and name.startswith(a.prefix):
            print(f"{off:#010x} tag={tag:#x} flags={flags:#06x} size={size:8} {name}")
            if a.dump:
                print("   ", body[:a.dump].hex(" "))
    if not a.prefix:
        for (tag, p), n in count.most_common():
            print(f"tag {tag:#x} {p or '(no name)':24} {n}")

if __name__ == "__main__":
    main()
