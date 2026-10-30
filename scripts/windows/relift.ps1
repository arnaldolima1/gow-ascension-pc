# Re-lift the PPU code, the SPU job modules or the position-independent code fragments.
#
#   .\scripts\windows\relift.ps1 ppu                           # the game's PPU code -> src\recomp (all of it recompiles)
#   .\scripts\windows\relift.ps1 jobmods                       # all 15 modules (all of them recompile)
#   .\scripts\windows\relift.ps1 jobmods -Only e9f3f00d551e    # one module: only it recompiles
#   .\scripts\windows\relift.ps1 fragments                     # tools\job_fragments.json -> src\spu\pic_*
#   .\scripts\windows\relift.ps1 fragments -Only 0x71c310       # one fragment (EAs, comma-separated): only it recompiles
#   .\scripts\windows\relift.ps1 post                          # SPU image 2 (the post-process round), with its stage hooks
#
# Extra entries per module: tools\jobmods_extra_funcs.json. Run .\scripts\windows\build.ps1 after.
param(
    [Parameter(Mandatory)][ValidateSet("ppu", "jobmods", "fragments", "post")][string]$What,
    [string]$Only = ""
)

. (Join-Path $PSScriptRoot "env.ps1")
$Work  = $Cfg.WORK_DIR
$Tools = Join-Path $Cfg.PS3KIT_DIR "tools"
$Spu   = Join-Path $Root "src\spu"
$Log   = Join-Path $Root "build\logs\relift-$What.log"

if ($What -eq "ppu") {
    # --reg-locals: each lifted function keeps the guest registers in C locals
    # and checks its guest accesses against a view of the memory globals read
    # at its entry (ps3kit tools\ppu_lifter.py, _localize_regs).
    python (Join-Path $Tools "ppu_lifter.py") (Join-Path $Work "disc\PS3_GAME\USRDIR\EBOOT.ELF") `
        --functions (Join-Path $Root "meta\functions.json") --hle-stubs (Join-Path $Root "meta\EBOOT.imports.json") `
        --toc 0x81EF60 --code-end 0x62C4CC --chunk-lines 150000 --reg-locals `
        --insn-switches (Join-Path $Root "tools\ppu_switches.json") `
        -o (Join-Path $Root "src\recomp") 2>&1 | Tee-Object $Log
    # The 0x4396E0 read guard (lr 0x43D17C crash); needs ps3kit's Windows-only
    # ppu_guest_ea_committed, so relift.sh does not apply it.
    python (Join-Path $Root "tools\patch_43D17C_guard.py") (Join-Path $Root "src\recomp") 2>&1 | Tee-Object -Append $Log
} elseif ($What -eq "jobmods") {
    # the launcher's installation cuts them out of the EBOOT.ELF into input\jobmods
    $mods = Join-Path $Root "input\jobmods"
    if (-not (Test-Path $mods)) { $mods = Join-Path $Work "jobmods" }
    # Contiguous chunks lift as one C function (~10 -> ~12 fps in the level),
    # and module 218's functions with a native version call it (ps3kit
    # libs\spu_hle\gowa_drawcmd\native_functions.txt).
    $env:LIFT_JOBMODS_MERGE = "1"
    $env:LIFT_NATIVE = Join-Path $Cfg.PS3KIT_DIR "libs\spu_hle\gowa_drawcmd\native_functions.txt"
    if ($Only) {
        # Lift one module in a scratch folder and copy only its sources over:
        # rewriting all of them would make every module recompile.
        $tmp = Join-Path $env:TEMP "ascension-relift"
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $tmp
        New-Item -ItemType Directory -Force "$tmp\in", "$tmp\out" | Out-Null
        $bin = Get-ChildItem $mods -Filter "jobmod_$Only*.bin" | Select-Object -First 1
        if (-not $bin) { Write-Error "no work\jobmods\jobmod_$Only*.bin"; exit 1 }
        Copy-Item $bin.FullName "$tmp\in"
        python (Join-Path $Tools "lift_jobmods.py") --jobmods "$tmp\in" --out "$tmp\out" --register "$tmp\out\reg.c" `
            --symbol-prefix ascension --extra-funcs-json (Join-Path $Root "tools\jobmods_extra_funcs.json") 2>&1 | Tee-Object $Log
        $name = $bin.BaseName
        Copy-Item "$tmp\out\$name\spu_recomp.c", "$tmp\out\$name\spu_recomp.h" (Join-Path $Spu $name)
        Write-Host "copied $name into src\spu"
    } else {
        python (Join-Path $Tools "lift_jobmods.py") --jobmods $mods --out $Spu --register (Join-Path $Spu "jobmods_register.c") `
            --symbol-prefix ascension --extra-funcs-json (Join-Path $Root "tools\jobmods_extra_funcs.json") 2>&1 | Tee-Object $Log
    }
} elseif ($What -eq "post") {
    # The post-process round's image: its stage functions come through ps3kit
    # libs\spu_hle\gowa_post (capture, bench, native versions).
    $img = "spu_0001_at_0067F580"
    $elf = Join-Path $Root "meta\spu\$img.elf"
    $out = Join-Path $Spu $img
    $nat = @()
    foreach ($l in Get-Content (Join-Path $Cfg.PS3KIT_DIR "libs\spu_hle\gowa_post\native_functions.txt")) {
        if ($l -match '^\s*(0x[0-9A-Fa-f]+)\s+(\S+)') { $nat += "--native"; $nat += "$($Matches[1])=$($Matches[2])" }
    }
    # --merge-chunks: each stage's loops become gotos in one C function instead
    # of a chunk per function with every register stored to ctx on each edge.
    # SPU_LIFT_PROMOTE_FUNCS: the hot call-free functions of the round with
    # their SPU registers in C locals (0x9E60 9.1 -> 6.5 us a call, identical);
    # set it yourself to override.
    $promoteSet = [bool]$env:SPU_LIFT_PROMOTE_FUNCS
    if (-not $promoteSet) { $env:SPU_LIFT_PROMOTE_FUNCS = "9E60,B730,87D0,8E20" }
    python (Join-Path $Tools "spu_lifter.py") $elf --auto-functions $elf --symbol-prefix "${img}_" -o $out --merge-chunks @nat 2>&1 | Tee-Object $Log
    if (-not $promoteSet) { Remove-Item Env:SPU_LIFT_PROMOTE_FUNCS }
    # The includes as build_spu_workloads.py leaves them (resolved by -I).
    foreach ($f in "spu_recomp.c", "spu_recomp.h") {
        $path = Join-Path $out $f
        (Get-Content -Raw $path).Replace('#include "../../runtime/spu/', '#include "') | Set-Content -NoNewline -Encoding utf8 $path
    }
} else {
    python (Join-Path $Tools "lift_spu_pic.py") --elf (Join-Path $Work "disc\PS3_GAME\USRDIR\EBOOT.ELF") `
        --fragments (Join-Path $Root "tools\job_fragments.json") --out $Spu --register (Join-Path $Spu "pic_register.c") `
        --symbol-prefix ascension @(if ($Only) { "--only", $Only }) 2>&1 | Tee-Object $Log
}
