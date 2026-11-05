# PPU-only profile-guided optimization, the whole way (docs/PPU_PGO.md):
#
#   .\scripts\windows\pgo-ppu.ps1                 # instrumented build, training run, profile-guided build
#   .\scripts\windows\pgo-ppu.ps1 -Swap base      # put the executable from before PGO back (A/B)
#   .\scripts\windows\pgo-ppu.ps1 -Swap pgo       # and the profile-guided one again
#   .\scripts\windows\pgo-ppu.ps1 -MetaOnly       # rewrite ppu.json (the players' build checks it)
# For the players: work\launcher-tauri\pack_kit.py --pgo build\pgo\<Name> puts the
# profile and ppu.json in the kit; tools\setup.py uses them when the lift matches.
#
# 1. Copies the current executable/map/pdb to build\pgo\<Name>\base.
# 2. ASCENSION_PPU_PGO=GENERATE and a build: only the generated PPU sources get
#    counters (all 13 recompile: a long build).
# 3. A level run (-Level, -Seconds 330) with the default settings; the profile
#    is written at 300 s (host/pgo_flush.cpp). Hands off: the run presses the
#    buttons itself. Its fps is not a result (the counters slow it down).
# 4. llvm-profdata merge (the one beside the configured clang-cl).
# 5. ASCENSION_PPU_PGO=USE with that profile and a build (all 13 again): the
#    executable this leaves in build\win is the profile-guided one, also kept in
#    build\pgo\<Name>\pgo.
# On a failure it configures OFF and puts the base executable back (the next
# build.ps1 then recompiles the PPU sources once more).
# Any later relift.ps1 ppu makes the profile stale: train again.
param(
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Name = "pgo1",
    [ValidateSet("", "base", "pgo")][string]$Swap = "",
    [int]$TrainSeconds = 330,
    [int]$FlushSeconds = 300,
    [switch]$MetaOnly,                # only (re)write build\pgo\<Name>\ppu.json from today's src\recomp
    [switch]$Spu                      # also the lifted SPU code and the runtime library (ASCENSION_PGO_SPU)
)
# Not "Stop": vcvars64.bat prints a harmless "vswhere.exe is not recognized" on
# stderr, which Windows PowerShell 5.1 turns into a terminating error under
# Stop. Failures are caught by $LASTEXITCODE and the explicit throws below.
$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "env.ps1")
$buildDir = Join-Path $Root "build\win"
$logDir   = Join-Path $Root "build\logs"
$caseDir  = Join-Path $Root "build\pgo\$Name"
$files    = @("AscensionRecomp.exe", "AscensionRecomp.map", "AscensionRecomp.pdb")

function Copy-Exe([string]$from, [string]$to) {
    New-Item -ItemType Directory -Force $to | Out-Null
    foreach ($f in $files) {
        $p = Join-Path $from $f
        if (Test-Path -LiteralPath $p) { Copy-Item -LiteralPath $p -Destination (Join-Path $to $f) -Force }
    }
}

# ppu.json beside the profile: each generated PPU file's SHA-256 and clang's
# version. The players' build (tools/setup.py) uses the profile only when its
# fresh lift has exactly these files (pack_kit.py --pgo ships both).
function Write-PgoMeta([string]$dir) {
    $files = [ordered]@{}
    Get-ChildItem (Join-Path $Root "src\recomp") -File | Where-Object { $_.Name -match '^ppu_recomp.*\.(cpp|h)$' } |
        Sort-Object Name | ForEach-Object { $files[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower() }
    $clang = (cmd /c "`"$($Cfg.VCVARS)`" >nul 2>&1 && clang-cl --version" | Select-Object -First 1)
    [ordered]@{ clang = "$clang"; files = $files } | ConvertTo-Json -Depth 4 |
        Set-Content -Encoding ascii (Join-Path $dir "ppu.json")
}
if ($MetaOnly) { Write-PgoMeta $caseDir; Write-Host "wrote $caseDir\ppu.json"; exit 0 }

if (Get-Process AscensionRecomp -ErrorAction SilentlyContinue) { throw "Close the running game first." }

if ($Swap) {
    $src = Join-Path $caseDir $Swap
    if (-not (Test-Path (Join-Path $src "AscensionRecomp.exe"))) { throw "No $src\AscensionRecomp.exe" }
    Copy-Exe $src $buildDir
    Write-Host "build\win now runs the '$Swap' executable of $Name."
    exit 0
}

if (Test-Path -LiteralPath $caseDir) { throw "build\pgo\$Name exists already; choose another -Name." }
if (-not (Test-Path (Join-Path $buildDir "AscensionRecomp.exe"))) { throw "Build the normal game first." }
if (Select-String -Path (Join-Path $buildDir "CMakeCache.txt") -Pattern '^ASCENSION_PPU_PGO:STRING=(GENERATE|USE)$') {
    throw "build\win is already in a PGO mode: start from ASCENSION_PPU_PGO=OFF."
}
New-Item -ItemType Directory -Force $caseDir, $logDir | Out-Null
Copy-Exe $buildDir (Join-Path $caseDir "base")

$compiler = & python -I (Join-Path $Root "tools\resolve_cmake_compiler.py") $buildDir
if ($LASTEXITCODE -ne 0 -or -not $compiler) { throw "Cannot resolve the game's configured compiler." }
$profdata = Join-Path (Split-Path -Parent ([string]$compiler)) "llvm-profdata.exe"
if (-not (Test-Path -LiteralPath $profdata)) { throw "No llvm-profdata beside $compiler" }

$raw    = Join-Path $caseDir "ppu.profraw"
$merged = Join-Path $caseDir "ppu.profdata"

function Set-PgoMode([string]$Mode, [string]$Extra = "") {
    $log = Join-Path $logDir "$Name-configure-$Mode.log"
    $spuFlag = if ($Spu -and $Mode -ne "OFF") { "-DASCENSION_PGO_SPU=ON" } else { "-DASCENSION_PGO_SPU=OFF" }
    cmd /c "`"$($Cfg.VCVARS)`" >nul && cmake -S `"$Root`" -B `"$buildDir`" -DASCENSION_PPU_PGO=$Mode $spuFlag $Extra" 2>&1 | Out-File -Encoding utf8 $log
    if ($LASTEXITCODE -ne 0) { Get-Content -LiteralPath $log -Tail 15; throw "cmake ($Mode) failed: $log" }
}

$t0 = Get-Date
$ok = $false
try {
    Write-Host "[1/4] instrumented build (all PPU sources)..."
    Set-PgoMode "GENERATE"
    & (Join-Path $PSScriptRoot "build.ps1") -Name "$Name-generate"
    if ($LASTEXITCODE -ne 0) { throw "Instrumented build failed: build\logs\build-$Name-generate.log" }

    Write-Host "[2/4] training run, $TrainSeconds s (hands off; its fps is not a result)..."
    & (Join-Path $PSScriptRoot "run.ps1") -Level -Seconds $TrainSeconds -Name "$Name-train" `
        -Env @{ LLVM_PROFILE_FILE = $raw; ASCENSION_PGO_FLUSH_SECONDS = "$FlushSeconds"; LD_PERF_OVERLAY = "1" }
    $gameLog = Join-Path $logDir "$Name-train.log"
    # Serious failures only: the boot-time "FIFO error: possible desync" comes in every run.
    $bad = Select-String -LiteralPath $gameLog -Pattern '\[foreign-fault\]|Access violation|(?:CopyLocalMemory|MoveLocalMemory).*offset error|STACKOVERFLOW|Thread terminated due to fatal error'
    if ($bad) { $bad | Select-Object -First 3 | ForEach-Object { Write-Host "  $($_.Line)" }; throw "The training run failed; the profile is not used." }
    if (-not (Select-String -LiteralPath $gameLog -Pattern '\[pgo\] profile write completed: result=0')) { throw "The profile was not written (no '[pgo] profile write completed: result=0')." }
    if (-not (Test-Path -LiteralPath $raw) -or (Get-Item -LiteralPath $raw).Length -eq 0) { throw "The profile file is missing or empty." }

    Write-Host "[3/4] merging the profile..."
    & $profdata merge $raw -o $merged 2>&1 | Out-File -Encoding utf8 (Join-Path $logDir "$Name-merge.log")
    if ($LASTEXITCODE -ne 0) { throw "llvm-profdata merge failed: build\logs\$Name-merge.log" }
    & $profdata show $merged 2>&1 | Out-File -Encoding utf8 (Join-Path $logDir "$Name-profile-summary.txt")
    Write-PgoMeta $caseDir

    Write-Host "[4/4] profile-guided build (all PPU sources)..."
    Set-PgoMode "USE" "-DASCENSION_PPU_PROFILE=`"$merged`""
    & (Join-Path $PSScriptRoot "build.ps1") -Name "$Name-use"
    if ($LASTEXITCODE -ne 0) { throw "Profile-guided build failed: build\logs\build-$Name-use.log" }
    Copy-Exe $buildDir (Join-Path $caseDir "pgo")
    $ok = $true
} finally {
    if (-not $ok) {
        $left = Get-Process AscensionRecomp -ErrorAction SilentlyContinue | Where-Object { $_.StartTime -ge $t0 }
        if ($left) { $left | Stop-Process -Force; $left | Wait-Process -Timeout 30 -ErrorAction SilentlyContinue }
        try { Set-PgoMode "OFF" } finally {
            # The restore once failed on a still-running game: the next run then
            # saved the instrumented executable as its "base".
            Copy-Exe (Join-Path $caseDir "base") $buildDir
            $same = (Get-FileHash (Join-Path $caseDir "base\AscensionRecomp.exe")).Hash -eq (Get-FileHash (Join-Path $buildDir "AscensionRecomp.exe")).Hash
            if (-not $same) { Write-Host "WARNING: build\win\AscensionRecomp.exe is NOT the base executable: run build.ps1 before anything else." }
        }
        Write-Host "PGO stopped: build\win is back to OFF with the base executable (the next build.ps1 recompiles the PPU sources)."
    }
}
$min = [int]((Get-Date) - $t0).TotalMinutes
Write-Host "PGO done in $min min: build\win runs the profile-guided executable (build\pgo\$Name\pgo); the old one is in build\pgo\$Name\base."
Write-Host "build\win stays in ASCENSION_PPU_PGO=USE: later builds keep using build\pgo\$Name\ppu.profdata."
