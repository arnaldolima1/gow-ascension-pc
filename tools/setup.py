#!/usr/bin/env python3
"""Make the game from the player's own files: what the launcher's Installation page runs after the disc part.

    python tools/setup.py                      # every step still to do
    python tools/setup.py --force              # every step again
    python tools/setup.py --steps meta,ppu     # some steps
    python tools/setup.py --hashes out.json    # the SHA-256 of what the steps generate (meta/, src/), to compare
                                               # two machines' outputs; nothing is made
    python tools/setup.py --hashes out.json --compare theirs.json   # and what differs from theirs

Reads input/EBOOT.ELF and input/jobmods/ (the launcher's installation makes them from the disc). The toolkit is
ps3kit/ inside this folder or beside it (--ps3kit). Needs only Python's standard library.

  meta       meta/: functions, imports, the embedded SPU images and the Wws policy module, from the EBOOT.ELF
  ppu        src/recomp: the PPU code lifted to C (with tools/ppu_switches.json)
  spu        src/spu: the SPU images, the post-process round (image 2, with ps3kit's native stages), the job
             modules and the code fragments, lifted to C
  configure  build/<platform>: CMake (Ninja); RPCS3's RSX when deps/rsx (or --rsx) holds a built ps3rsx
  compile    build/<platform>/AscensionRecomp: Ninja

A step whose inputs did not change since it last ran is skipped (a stamp in the folder it makes). Output for the
launcher: "[n/N] <step>" when a step starts, "  <what> (<s> s)" when it ends, "ERROR: <why>" before a failing exit.
On Windows the compiler is Visual Studio's (Build Tools with the C++ and Clang components), found with vswhere.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEPS = ['meta', 'ppu', 'spu', 'configure', 'compile']
WINDOWS, MAC = sys.platform == 'win32', sys.platform == 'darwin'
PLATFORM = 'win' if WINDOWS else 'mac' if MAC else 'linux'
EXE = 'AscensionRecomp.exe' if WINDOWS else 'AscensionRecomp'
# The post-process round's image: re-lifted with ps3kit's native stages over what build_spu_workloads makes
# (relift.ps1 post).
POST_IMAGE = 'spu_0001_at_0067F580'
POST_PROMOTE = '9E60,B730,87D0,8E20'


class Fail(Exception):
    pass


def path(*p):
    return os.path.join(ROOT, *p)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def tree_hash(paths, exts=None):
    """One hash over files (or folders, recursively), by relative name and content."""
    h = hashlib.sha256()
    for top in paths:
        if os.path.isfile(top):
            files = [top]
        else:
            files = [os.path.join(d, f) for d, _, fs in os.walk(top) for f in fs]
        for f in sorted(files):
            if exts and not f.endswith(exts):
                continue
            h.update(os.path.relpath(f, ROOT).replace('\\', '/').encode())
            h.update(sha256_file(f).encode())
    return h.hexdigest()


def stamp_ok(folder, value):
    try:
        return open(os.path.join(folder, '.setup-stamp')).read().strip() == value
    except OSError:
        return False


def stamp_write(folder, value):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, '.setup-stamp'), 'w') as f:
        f.write(value + '\n')


def run(cmd, env=None, cwd=None):
    """Run a command, its output passed through line by line (the launcher reads it)."""
    print('  > ' + ' '.join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd)), flush=True)
    p = subprocess.Popen(cmd, cwd=cwd or ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding='utf-8', errors='replace')
    for line in p.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    if p.wait() != 0:
        raise Fail(f'{os.path.basename(cmd[0])} {cmd[1] if len(cmd) > 1 else ""} exited with {p.returncode}')


def drop_appledouble():
    """macOS on a disk without extended attributes (exFAT, FAT): every file written gets a "._<name>" AppleDouble
    beside it (the com.apple.provenance attribute), and the build's globs take ._cellAudio.c for C. Removed here,
    by their header (00 05 16 07), never by name alone. Returns how many."""
    if not MAC:
        return 0
    n = 0
    for top in ('ps3kit', 'src', 'meta', 'host', 'tools', 'input', 'deps', 'mods-builtin', 'launcher'):
        for d, _, fs in os.walk(path(top)):
            for f in fs:
                if f.startswith('._'):
                    p = os.path.join(d, f)
                    try:
                        with open(p, 'rb') as h:
                            magic = h.read(4)
                        if magic == b'\x00\x05\x16\x07':
                            os.remove(p)
                            n += 1
                    except OSError:
                        pass
    return n


def find_ps3kit(given):
    for d in ([given] if given else []) + [path('ps3kit'), os.path.join(os.path.dirname(ROOT), 'ps3kit')]:
        if d and os.path.isfile(os.path.join(d, 'tools', 'ppu_lifter.py')):
            return os.path.abspath(d)
    raise Fail('ps3kit not found (ps3kit/ in this folder, beside it, or --ps3kit)')


def py(kit, tool):
    return [sys.executable, os.path.join(kit, 'tools', tool) if not tool.startswith(ROOT) else tool]


# ---------------------------------------------------------------- steps

def step_meta(a, kit):
    elf = path('input', 'EBOOT.ELF')
    meta = path('meta')
    os.makedirs(os.path.join(meta, 'spu'), exist_ok=True)
    run(py(kit, 'find_functions.py') + [elf, '--json', '-o', os.path.join(meta, 'functions.json')])
    run(py(kit, 'gen_imports.py') + [elf, '-o', os.path.join(meta, 'EBOOT.imports.json')])
    run(py(kit, 'extract_spu_images.py') + [elf, '-o', os.path.join(meta, 'spu')])
    run([sys.executable, path('tools', 'extract_spu_pm.py'), elf, os.path.join(meta, 'spu', 'spu_wws_pm_at_0077CA80.elf'),
         '--address', '0x77CA80', '--size', '12288', '--fnv', '0xC8D774963A96DCF2', '--kit', kit])
    return f"{len(json.load(open(os.path.join(meta, 'functions.json'))))} functions"


def step_ppu(a, kit):
    out = path('src', 'recomp')
    if os.path.isdir(out):
        shutil.rmtree(out)
    # --reg-locals: guest registers in C locals; --insn-switches: the GOWA_* environment switches
    run(py(kit, 'ppu_lifter.py') + [path('input', 'EBOOT.ELF'), '--functions', path('meta', 'functions.json'),
        '--hle-stubs', path('meta', 'EBOOT.imports.json'), '--toc', '0x81EF60', '--code-end', '0x62C4CC',
        '--chunk-lines', '150000', '--reg-locals', '--insn-switches', path('tools', 'ppu_switches.json'), '-o', out])
    return f"{len([f for f in os.listdir(out) if f.endswith(('.c', '.cpp'))])} source files"


def step_spu(a, kit):
    spu = path('src', 'spu')
    os.makedirs(spu, exist_ok=True)
    run(py(kit, 'build_spu_workloads.py') + ['--images', path('meta', 'spu'), '--lifted', spu,
        '--out', os.path.join(spu, 'spu_workloads.c'), '--register-fn', 'ascension_spu_register_all', '--constructor',
        '--title', 'ascension', '--relift', '--extra-funcs', 'spu_wws_pm_at_0077CA80=0xA2C,0xA68,0x3368,0x3378'])
    # the post-process round with ps3kit's native stage functions, as relift.ps1 post
    nat = []
    for line in open(os.path.join(kit, 'libs', 'spu_hle', 'gowa_post', 'native_functions.txt')):
        parts = line.split()
        if len(parts) >= 2 and parts[0].lower().startswith('0x'):
            nat += ['--native', f'{parts[0]}={parts[1]}']
    elf = path('meta', 'spu', POST_IMAGE + '.elf')
    out = os.path.join(spu, POST_IMAGE)
    env = dict(os.environ)
    env.setdefault('SPU_LIFT_PROMOTE_FUNCS', POST_PROMOTE)
    run(py(kit, 'spu_lifter.py') + [elf, '--auto-functions', elf, '--symbol-prefix', POST_IMAGE + '_', '-o', out,
        '--merge-chunks'] + nat, env=env)
    for f in ('spu_recomp.c', 'spu_recomp.h'):
        p = os.path.join(out, f)
        text = open(p, encoding='utf-8').read().replace('#include "../../runtime/spu/', '#include "')
        open(p, 'w', encoding='utf-8', newline='').write(text)
    # the job modules (merged chunks, module 218's native functions) and the code fragments
    env = dict(os.environ, LIFT_JOBMODS_MERGE='1',
               LIFT_NATIVE=os.path.join(kit, 'libs', 'spu_hle', 'gowa_drawcmd', 'native_functions.txt'))
    run(py(kit, 'lift_jobmods.py') + ['--jobmods', path('input', 'jobmods'), '--out', spu,
        '--register', os.path.join(spu, 'jobmods_register.c'), '--symbol-prefix', 'ascension',
        '--extra-funcs-json', path('tools', 'jobmods_extra_funcs.json')], env=env)
    run(py(kit, 'lift_spu_pic.py') + ['--elf', path('input', 'EBOOT.ELF'), '--fragments', path('tools', 'job_fragments.json'),
        '--out', spu, '--register', os.path.join(spu, 'pic_register.c'), '--symbol-prefix', 'ascension'])
    return f"{len([d for d in os.listdir(spu) if os.path.isdir(os.path.join(spu, d))])} SPU programs"


def msvc_env():
    """Windows: the environment of Visual Studio's vcvars64.bat, and its Clang on the PATH."""
    vswhere = os.path.join(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
                           'Microsoft Visual Studio', 'Installer', 'vswhere.exe')
    if not os.path.isfile(vswhere):
        raise Fail('Visual Studio Build Tools are not installed (no vswhere.exe)')
    vs = subprocess.run([vswhere, '-latest', '-products', '*', '-requires',
                         'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'],
                        capture_output=True, text=True).stdout.strip()
    vcvars = os.path.join(vs, 'VC', 'Auxiliary', 'Build', 'vcvars64.bat')
    if not vs or not os.path.isfile(vcvars):
        raise Fail("Visual Studio's C++ tools are not installed (no vcvars64.bat)")
    out = subprocess.run(f'"{vcvars}" >nul && set', shell=True, capture_output=True, text=True).stdout
    env = dict(line.split('=', 1) for line in out.splitlines() if '=' in line)
    # `set` keeps the parent's spelling: started from the launcher (Explorer's environment) it is Path, not PATH
    for k in [k for k in env if k.upper() == 'PATH' and k != 'PATH']:
        env['PATH'] = env.pop(k)
    llvm = os.path.join(vs, 'VC', 'Tools', 'Llvm', 'x64', 'bin')
    if os.path.isfile(os.path.join(llvm, 'clang-cl.exe')):
        env['PATH'] = llvm + os.pathsep + env.get('PATH', '')
    if not shutil.which('clang-cl', path=env.get('PATH')):
        raise Fail("Visual Studio's Clang is not installed (the C++ Clang tools component)")
    return env


def build_env():
    if WINDOWS:
        return msvc_env()
    env = dict(os.environ)
    # an app opened from the Finder has only /usr/bin:/bin:...: Homebrew's cmake and ninja are not on it
    extra = [d for d in ('/opt/homebrew/bin', '/usr/local/bin') if os.path.isdir(d)]
    env['PATH'] = os.pathsep.join(extra + [env.get('PATH', '/usr/bin:/bin')])
    return env


def ram_gb():
    """The host's memory in GB (0 when unknown)."""
    try:
        if WINDOWS:
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [('len', ctypes.c_ulong), ('load', ctypes.c_ulong), ('total', ctypes.c_ulonglong),
                            ('avail', ctypes.c_ulonglong), ('pt', ctypes.c_ulonglong), ('pa', ctypes.c_ulonglong),
                            ('vt', ctypes.c_ulonglong), ('va', ctypes.c_ulonglong), ('ve', ctypes.c_ulonglong)]
            st = Status()
            st.len = ctypes.sizeof(Status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return st.total / 2**30
        if MAC:
            return int(subprocess.run(['sysctl', '-n', 'hw.memsize'], capture_output=True, text=True).stdout) / 2**30
        return os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 2**30
    except (OSError, ValueError, AttributeError):
        return 0


def default_jobs():
    """Parallel compiles: each lifted PPU unit takes 1-2 GB and more alongside it, so one per 8 GB of memory, at
    most half the CPUs (a 16 GB Mac froze at six)."""
    cpus = os.cpu_count() or 2
    ram = ram_gb()
    return max(1, min(cpus // 2, int(ram // 8) if ram else 2))


def tool(env, name):
    found = shutil.which(name, path=env.get('PATH'))
    if not found:
        raise Fail(f'{name} not found')
    return found


def ffmpeg_include(given):
    for d in [given, path('deps', 'ffmpeg', 'include'), '/opt/homebrew/include', '/usr/local/include', '/usr/include']:
        if d and os.path.isfile(os.path.join(d, 'libavcodec', 'avcodec.h')):
            return d
    raise Fail('the FFmpeg headers were not found (deps/ffmpeg/include or --ffmpeg-include)')


def rsx_dir(given):
    d = given or path('deps', 'rsx')
    lib = 'ps3rsx.lib' if WINDOWS else 'libps3rsx.a'
    return d if os.path.isfile(os.path.join(d, lib)) and os.path.isfile(os.path.join(d, 'build.ninja')) else None


def cpu_avx2():
    """Whether this CPU has AVX2 (and with it FMA3 and BMI2: every x86 CPU with AVX2 has them, Haswell and Zen
    onwards). The game is compiled on the player's own machine, so its lifted code can use them."""
    if WINDOWS:
        import ctypes
        return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))   # PF_AVX2_INSTRUCTIONS_AVAILABLE
    if os.path.isfile('/proc/cpuinfo'):
        flags = open('/proc/cpuinfo').read()
        return all(f' {f}' in flags for f in ('avx2', 'fma', 'bmi2'))
    return False   # macOS: arm64, or an Intel Mac left as it is


def configure_args(a, kit):
    rsx = rsx_dir(a.rsx)
    avx2 = 'ON' if cpu_avx2() else 'OFF'
    args = ['-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', f'-DPS3RECOMP_DIR={kit}', f'-DPython3_EXECUTABLE={sys.executable}',
            '-DPS3RECOMP_FFMPEG_RUNTIME=ON', f'-DPS3RECOMP_FFMPEG_INCLUDE_DIR={ffmpeg_include(a.ffmpeg_include)}',
            f"-DASCENSION_NATIVE={'ON' if a.native else 'OFF'}",
            # the lifted PPU and SPU code for AVX2, BMI2 and FMA3 when this CPU has them (as the developers' .env)
            f'-DASCENSION_PPU_AVX2={avx2}', f'-DASCENSION_SPU_AVX2={avx2}']
    if WINDOWS:
        args += ['-DCMAKE_C_COMPILER=clang-cl', '-DCMAKE_CXX_COMPILER=clang-cl']
    if MAC:
        args += ['-DASCENSION_MACOS=ON']
    args += [f'-DASCENSION_RPCS3_RSX=ON', f'-DASCENSION_RPCS3_BUILD={rsx}'] if rsx else ['-DASCENSION_RPCS3_RSX=OFF']
    return args


def step_configure(a, kit):
    env = build_env()
    build = path('build', PLATFORM)
    os.makedirs(build, exist_ok=True)
    args = configure_args(a, kit)
    run([tool(env, 'cmake'), '-S', ROOT, '-B', build] + args, env=env)
    return "with RPCS3's RSX" if '-DASCENSION_RPCS3_RSX=ON' in args else "without RPCS3's RSX"


def copy_runtime_dlls(env, build):
    """Windows: beside the executable, the DLLs it loads that the player's system may lack: FFmpeg's (loaded at run
    time, ffmpeg_runtime.c) from deps/ffmpeg/bin, and the C++ runtime from Visual Studio's redistributable folder."""
    sources = [path('deps', 'ffmpeg', 'bin')]
    redist = env.get('VCToolsRedistDir', '')
    if redist and os.path.isdir(os.path.join(redist, 'x64')):
        sources += [os.path.join(redist, 'x64', d) for d in os.listdir(os.path.join(redist, 'x64')) if d.endswith('.CRT')]
    n = 0
    for d in sources:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.lower().endswith('.dll'):
                    shutil.copy2(os.path.join(d, f), os.path.join(build, f))
                    n += 1
    print(f'  {n} runtime DLLs beside {EXE}', flush=True)


def step_compile(a, kit):
    env = build_env()
    build = path('build', PLATFORM)
    # a build.ninja made while AppleDouble files were there names them: configure again without them
    ninja = os.path.join(build, 'build.ninja')
    if os.path.isfile(ninja) and '/._' in open(ninja, encoding='utf-8', errors='replace').read():
        print('  the build named AppleDouble files: configuring again', flush=True)
        step_configure(a, kit)
    # the 0x4396E0 read guard (lr 0x43D17C crash) on the lifted PPU code, as relift.ps1 does after a lift: byte-level
    # and idempotent, so it runs every time (the ppu step may have been skipped); Windows only, as its helper
    if WINDOWS:
        run([sys.executable, path('tools', 'patch_43D17C_guard.py'), path('src', 'recomp')])
    run([tool(env, 'ninja'), '-C', build, '-j', str(a.jobs)], env=env)
    exe = os.path.join(build, EXE)
    if not os.path.isfile(exe):
        raise Fail(f'the build ended without {EXE}')
    if WINDOWS:
        copy_runtime_dlls(env, build)
    return f'{EXE}, {os.path.getsize(exe) / 1e6:.0f} MB'


# ---------------------------------------------------------------- what each step reads, for its stamp

def inputs(step, a, kit):
    elf = sha256_file(path('input', 'EBOOT.ELF'))
    tools = tree_hash([os.path.join(kit, 'tools')], ('.py',))
    if step == 'meta':
        return elf + tools + tree_hash([path('tools', 'extract_spu_pm.py')])
    if step == 'ppu':
        return tree_hash([path('meta', 'functions.json'), path('meta', 'EBOOT.imports.json'), path('tools', 'ppu_switches.json')]) + elf + tools
    if step == 'spu':
        return (tree_hash([path('meta', 'spu'), path('input', 'jobmods'), path('tools', 'jobmods_extra_funcs.json'),
                           path('tools', 'job_fragments.json'), os.path.join(kit, 'libs', 'spu_hle', 'gowa_post', 'native_functions.txt'),
                           os.path.join(kit, 'libs', 'spu_hle', 'gowa_drawcmd', 'native_functions.txt')]) + elf + tools)
    if step == 'configure':
        return hashlib.sha256(' '.join(configure_args(a, kit)).encode()).hexdigest()
    return None


STAMP_DIR = {'meta': ('meta',), 'ppu': ('src', 'recomp'), 'spu': ('src', 'spu'), 'configure': ('build', PLATFORM)}
RUN = {'meta': step_meta, 'ppu': step_ppu, 'spu': step_spu, 'configure': step_configure, 'compile': step_compile}


TEXT = ('.c', '.cpp', '.h', '.json', '.txt')


def hashes(out):
    """Every generated file's SHA-256 by its path: meta/ and src/, to compare with another machine's (text with
    LF line ends)."""
    table = {}
    for top in (path('meta'), path('src')):
        for d, _, fs in os.walk(top):
            for f in fs:
                if f != '.setup-stamp':
                    p = os.path.join(d, f)
                    data = open(p, 'rb').read()
                    if f.endswith(TEXT):   # Windows writes the lifters' text with CRLF
                        data = data.replace(b'\r\n', b'\n')
                    table[os.path.relpath(p, ROOT).replace('\\', '/')] = hashlib.sha256(data).hexdigest()
    with open(out, 'w') as f:
        json.dump(dict(sorted(table.items())), f, indent=1)
    print(f'{len(table)} files -> {out}')
    return table


def compare(mine, ref_file):
    """What differs from another machine's --hashes file: 0 when nothing."""
    ref = json.load(open(ref_file))
    only_mine = sorted(set(mine) - set(ref))
    only_ref = sorted(set(ref) - set(mine))
    differ = sorted(k for k in set(mine) & set(ref) if mine[k] != ref[k])
    for title, items in (('only here', only_mine), (f'only in {os.path.basename(ref_file)}', only_ref), ('different', differ)):
        if items:
            print(f'{title}: {len(items)}')
            for k in items[:40]:
                print(f'  {k}')
    print('the same' if not (only_mine or only_ref or differ) else 'DIFFERENT')
    return 0 if not (only_mine or only_ref or differ) else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--steps', default=','.join(STEPS), help='comma-separated: ' + ', '.join(STEPS))
    ap.add_argument('--force', action='store_true', help='run the steps even when up to date')
    ap.add_argument('--ps3kit', help='the toolkit (default: ps3kit/ here or beside)')
    ap.add_argument('--rsx', help="a built ps3rsx (default: deps/rsx)")
    ap.add_argument('--ffmpeg-include', help='the FFmpeg headers (default: deps/ffmpeg/include, then the system)')
    ap.add_argument('--jobs', type=int, default=default_jobs(),
                    help='parallel compiles (default: one per 8 GB of memory, at most half the CPUs)')
    ap.add_argument('--native', action='store_true', help='the lifted code for this CPU only (-march=native)')
    ap.add_argument('--hashes', metavar='OUT', help='write the generated files\' hashes and stop')
    ap.add_argument('--compare', metavar='REF', help='with --hashes: list what differs from another --hashes file')
    a = ap.parse_args()
    if a.hashes:
        table = hashes(a.hashes)
        return compare(table, a.compare) if a.compare else 0
    steps = [s.strip() for s in a.steps.split(',') if s.strip()]
    for s in steps:
        if s not in STEPS:
            ap.error(f'no step {s}')
    try:
        kit = find_ps3kit(a.ps3kit)
        for need in (path('input', 'EBOOT.ELF'), path('input', 'jobmods')):
            if not os.path.exists(need):
                raise Fail(f'{os.path.relpath(need, ROOT)} is missing: install from the disc first')
        for i, s in enumerate(steps, 1):
            print(f'[{i}/{len(steps)}] {s}', flush=True)
            t0 = time.time()
            dropped = drop_appledouble()
            if dropped:
                print(f'  {dropped} AppleDouble files (._*) removed', flush=True)
            stamp = inputs(s, a, kit)
            folder = path(*STAMP_DIR[s]) if s in STAMP_DIR else None
            if folder and stamp and not a.force and stamp_ok(folder, stamp):
                print(f'  up to date ({time.time() - t0:.0f} s)', flush=True)
                continue
            what = RUN[s](a, kit)
            if folder and stamp:
                stamp_write(folder, stamp)
            print(f'  {what} ({time.time() - t0:.0f} s)', flush=True)
    except Fail as e:
        print(f'ERROR: {e}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
