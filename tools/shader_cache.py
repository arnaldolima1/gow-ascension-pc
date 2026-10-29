"""The RPCS3 renderer's shader cache and its packs, from the command line
(the launcher's Video page does the same; work/launcher-tauri/src-tauri/src/shaders.rs).

  python tools/shader_cache.py stats              what the cache holds
  python tools/shader_cache.py export <name>      the cache as gamedata/shader_packs/<name>.zip
  python tools/shader_cache.py import <zip|dir>   a pack (or an RPCS3 shaders_cache folder) into the packs
  python tools/shader_cache.py merge <pack>       a pack's shaders into the cache (a name in the packs, a .zip or a folder)
  python tools/shader_cache.py list               the packs
  python tools/shader_cache.py clear              empty the cache

--cache <dir> uses another cache folder (the one PS3_SHADER_CACHE names;
default gamedata/shader_cache)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'launcher'))
from app import shaders  # noqa: E402


def find_pack(name):
    p = Path(name)
    if p.exists():
        return p
    for cand in (shaders.PACK_DIR / name, shaders.PACK_DIR / f'{name}.zip'):
        if cand.is_file():
            return cand
    sys.exit(f'no pack {name} (neither a path nor in {shaders.PACK_DIR})')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=['stats', 'export', 'import', 'merge', 'list', 'clear'])
    ap.add_argument('arg', nargs='?')
    ap.add_argument('--cache', type=Path, default=shaders.CACHE_DIR)
    a = ap.parse_args()

    if a.command == 'stats':
        s = shaders.stats(a.cache)
        print(f'{shaders.cache_root(a.cache)}')
        print(f'  {s["pipelines"]} pipelines, {s["programs"]} programs, {s["bytes"] / 1024:.0f} KiB')
        for key, n in sorted(s['classes'].items()):
            print(f'  {key}: {n}')
    elif a.command == 'export':
        out, info = shaders.export_pack(a.arg or '', a.cache)
        print(f'{out}: {info["pipelines"]} pipelines, {info["programs"]} programs')
    elif a.command == 'import':
        if not a.arg:
            sys.exit('import: which .zip or folder?')
        out = shaders.import_pack(a.arg)
        info = shaders.pack_info(out)
        print(f'{out}: {info.get("pipelines", "?")} pipelines')
    elif a.command == 'merge':
        if not a.arg:
            sys.exit('merge: which pack?')
        added = shaders.merge_pack(find_pack(a.arg), a.cache)
        print(f'{added} new pipelines in {shaders.cache_root(a.cache)}')
    elif a.command == 'list':
        for name, info in shaders.list_packs():
            print(f'{name}: {info.get("pipelines", "?")} pipelines, {info.get("created", "")}')
    elif a.command == 'clear':
        shaders.clear_cache(a.cache)
        print(f'cleared {shaders.cache_root(a.cache)}')


if __name__ == '__main__':
    main()
