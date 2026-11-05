"""Resolve the configured compiler without substituting another LLVM from PATH."""
import argparse
from pathlib import Path
import re
import sys


def resolve(build):
    cache = (build / "CMakeCache.txt").read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^CMAKE_CXX_COMPILER:[^=]+=(.+)$", cache, re.M)
    if not match:
        raise ValueError("CMAKE_CXX_COMPILER is missing from the build cache")
    cached = Path(match[1].strip())
    if cached.is_absolute() and cached.is_file():
        return cached
    # CMake accepts a bare compiler name in its cache, but records the resolved
    # toolchain in CMakeCXXCompiler.cmake. Match Ninja when old CMake versions
    # leave several compiler records in the build directory.
    rules = build / "CMakeFiles/rules.ninja"
    commands = rules.read_text(encoding="utf-8", errors="replace").replace("\\", "/").lower() if rules.is_file() else None
    candidates = set()
    for record in (build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"):
        match = re.search(r'^set\(CMAKE_CXX_COMPILER "([^"]+)"\)', record.read_text(encoding="utf-8", errors="replace"), re.M)
        if not match:
            continue
        candidate = Path(match[1])
        if candidate.is_absolute() and candidate.is_file() and (
                commands is None or candidate.as_posix().lower() in commands):
            candidates.add(candidate)
    if len(candidates) != 1:
        raise ValueError(f"Cannot uniquely resolve the configured compiler {cached!s}; found {len(candidates)} matching CMake records")
    return candidates.pop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    args = parser.parse_args()
    try:
        print(resolve(args.build.resolve()))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
