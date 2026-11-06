# Re-lift the PPU code, the SPU job modules or the position-independent code fragments.
#
#   .\scripts\windows\relift.ps1 ppu                           # the game's PPU code -> src\recomp (all of it recompiles)
#   .\scripts\windows\relift.ps1 jobmods                       # all 15 modules (all of them recompile)
#   .\scripts\windows\relift.ps1 jobmods -Only e9f3f00d551e    # one module: only it recompiles
#   .\scripts\windows\relift.ps1 fragments                     # tools\job_fragments.json -> src\spu\pic_*
#   .\scripts\windows\relift.ps1 fragments -Only 0x71c310       # one fragment (EAs, comma-separated): only it recompiles
#   .\scripts\windows\relift.ps1 post                          # SPU image 2 (the post-process round), with its stage hooks
#   .\scripts\windows\relift.ps1 images                        # all SPU images (policy module, tasks) as setup.py, then post
#
# Extra entries per module: tools\jobmods_extra_funcs.json. Run .\scripts\windows\build.ps1 after.
param(
    [Parameter(Mandatory)][ValidateSet("ppu", "jobmods", "fragments", "post", "images")][string]$What,
    [string]$Only = ""
)

. (Join-Path $PSScriptRoot "env.ps1")
$Work  = $Cfg.WORK_DIR
$Tools = Join-Path $Cfg.PS3KIT_DIR "tools"
$Spu   = Join-Path $Root "src\spu"
$Log   = Join-Path $Root "build\logs\relift-$What.log"

# Job modules and fragments: functions that use 17-64 SPU registers keep them
# in C locals (ps3kit tools\spu_lifter.py, promote_registers_df). Job replay
# -Base: whole LS identical; ~-2 % cycles a job (ps3kit docs\ASCENSION_PLAN.md
# R6, 2026-11-03). Every function promoted was not identical (R7). Set
# SPU_LIFT_PROMOTE yourself (0 for none) to override.
$promoteDefault = ($What -in "jobmods", "fragments") -and -not $env:SPU_LIFT_PROMOTE
if ($promoteDefault) { $env:SPU_LIFT_PROMOTE = "1"; $env:SPU_LIFT_PROMOTE_BAND = "17-64" }
# The sound modules past the resolver (ps3kit spu_lifter.py local_indirect_branches), inert until
# SPU_IBL=1. SPU_LIFT_IBL="" for none.
$iblDefault = ($What -eq "jobmods") -and ($null -eq $env:SPU_LIFT_IBL)
if ($iblDefault) { $env:SPU_LIFT_IBL = "31107645db58,3a88c1cb87a9" }

if ($What -eq "ppu") {
    # --reg-locals: each lifted function keeps the guest registers in C locals
    # and checks its guest accesses against a view of the memory globals read
    # at its entry (ps3kit tools\ppu_lifter.py, _localize_regs).
    python (Join-Path $Tools "ppu_lifter.py") (Join-Path $Work "disc\PS3_GAME\USRDIR\EBOOT.ELF") `
        --functions (Join-Path $Root "meta\functions.json") --hle-stubs (Join-Path $Root "meta\EBOOT.imports.json") `
        --toc 0x81EF60 --code-end 0x62C4CC --chunk-lines 150000 --reg-locals `
        --insn-switches (Join-Path $Root "tools\ppu_switches.json") `
        --hle-hooks (Join-Path $Root "tools\ppu_hle_hooks.json") `
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
} elseif ($What -eq "images") {
    # The SPU images (meta\spu: the Wws policy module, the tasks, image 2) as
    # tools\setup.py lifts them for the players. This PC's had been lifted on
    # 2026-10-17, before SPU_DIRECT: the policy module's branches went through
    # the drain loop (105 steps an interrupt, 16 after). Image 2 is relifted
    # with its native stages right after (as relift.ps1 post).
    python (Join-Path $Tools "build_spu_workloads.py") --images (Join-Path $Root "meta\spu") --lifted $Spu `
        --out (Join-Path $Spu "spu_workloads.c") --register-fn ascension_spu_register_all --constructor `
        --title ascension --relift --extra-funcs "spu_wws_pm_at_0077CA80=0xA2C,0xA68,0x3368,0x3378" 2>&1 | Tee-Object $Log
    & (Join-Path $PSScriptRoot "relift.ps1") post
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
if ($promoteDefault) { Remove-Item Env:SPU_LIFT_PROMOTE, Env:SPU_LIFT_PROMOTE_BAND }
if ($iblDefault) { Remove-Item Env:SPU_LIFT_IBL }
