# Bench of the post-process round's stage functions (SPU image 2, ps3kit
# ascension-native\render\post_process): reruns captured calls instead of the game, times
# them and compares their result with the capture.
#
#   .\scripts\windows\postbench.ps1                       # work\post_cases\level2, 200 runs a record
#   .\scripts\windows\postbench.ps1 -Name merged -Out     # also write each result to build\logs\<Name>-out\
#   .\scripts\windows\postbench.ps1 -Compare base,merged  # compare two -Out runs, record by record
#   .\scripts\windows\postbench.ps1 -Native 7CD0          # the native version of that stage (GOWA_POST_NATIVE)
#   .\scripts\windows\postbench.ps1 -Compare lift,nat -Abi -Only 9340   # one stage; r2, r4..r79 not compared
#
# The capture's own "after" state can carry DMA that landed during the call in
# the game, so two builds are compared with each other (-Out, then -Compare).
param(
    [string]$Name = "postbench",
    [string]$Cases = "",
    [int]$Runs = 200,
    [switch]$Out,
    [string]$Native = "",
    [string[]]$Compare = @(),
    [switch]$Abi,
    [string]$Only = "",
    [int]$TimeoutSec = 180
)

. (Join-Path $PSScriptRoot "env.ps1")
$Logs = Join-Path $Root "build\logs"

if ($Compare.Count -eq 2) {
    $a = Join-Path $Logs "$($Compare[0])-out"
    $b = Join-Path $Logs "$($Compare[1])-out"
    $same = 0; $diff = 0
    foreach ($f in Get-ChildItem $a -Filter "k$($Only)*.out") {
        $g = Join-Path $b $f.Name
        if (-not (Test-Path $g)) { Write-Host "$($f.Name): missing in $($Compare[1])"; $diff++; continue }
        $x = [IO.File]::ReadAllBytes($f.FullName); $y = [IO.File]::ReadAllBytes($g)
        $n = 0; $first = -1
        for ($i = 0; $i -lt $x.Length; $i++) {
            # -Abi: a native stage writes r3 only; r2 and r4..r79 are not compared
            if ($Abi -and (($i -ge 32 -and $i -lt 48) -or ($i -ge 64 -and $i -lt 1280))) { continue }
            # 0x7170 returns nothing in r3 (the lift leaves scratch there)
            if ($Abi -and $f.Name -like "k7170_*" -and $i -ge 48 -and $i -lt 64) { continue }
            if ($x[$i] -ne $y[$i]) { $n++; if ($first -lt 0) { $first = $i } }
        }
        if ($n) {
            $where = if ($first -lt 2048) { "register r$([int][Math]::Floor($first / 16))" } else { "local store 0x{0:X5}" -f ($first - 2048) }
            Write-Host "$($f.Name): $n bytes differ, first in $where"; $diff++
        } else { $same++ }
    }
    Write-Host "$same identical, $diff different"
    exit [int]($diff -ne 0)
}

if (-not $Cases) { $Cases = Join-Path $Cfg.WORK_DIR "post_cases\level2" }
$Exe = Join-Path $Root "build\win\AscensionRecomp.exe"
$Elf = Join-Path $Cfg.WORK_DIR "disc\PS3_GAME\USRDIR\EBOOT.ELF"
$Log = Join-Path $Logs "$Name.log"
$env:GOWA_POST_BENCH = "$Cases,$Runs"
if ($Out) {
    $od = Join-Path $Logs "$Name-out"
    New-Item -ItemType Directory -Force $od | Out-Null
    $env:GOWA_POST_BENCH_OUT = $od
}
$env:GOWA_POST_NATIVE = if ($Native) { $Native } else { "none" }   # the game's default is all
try {
    $p = Start-Process -FilePath $Exe -ArgumentList "`"$Elf`"" -WorkingDirectory $Root -NoNewWindow -PassThru `
        -RedirectStandardError $Log -RedirectStandardOutput (Join-Path $Logs "$Name-stdout.log")
    if (-not $p.WaitForExit($TimeoutSec * 1000)) { $p.Kill(); Write-Host "timeout after $TimeoutSec s" }
} finally {
    Remove-Item Env:GOWA_POST_BENCH, Env:GOWA_POST_BENCH_OUT, Env:GOWA_POST_NATIVE -ErrorAction SilentlyContinue
}
Select-String -Path $Log -Pattern "records" | ForEach-Object { $_.Line }
Write-Host "log: $Log"
