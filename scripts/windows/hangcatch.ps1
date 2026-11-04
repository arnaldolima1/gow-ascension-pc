# Run the level until the game freezes, then ask the debug console (PS3_DEBUG)
# what it is doing, and close it.
#
#   .\scripts\windows\hangcatch.ps1 -Name hangc1 -Affinity FFF -Env @{ SPURS_NSPUS = "5" }
#
# A freeze is the `[perf] fps=` line stopping for -StallSec seconds once the
# level was reached (a 5-s window under 40 fps after the first minute). Then
# each of -Commands goes to the console in turn (mem <hex> <len>, threads,
# prof <host tid> <s>, ...; ps3kit runtime/ppu/tests/boot_main.cpp, "help").
# The answers are in build\logs\<Name>-dbg.txt.out and are printed at the end.
# 2026-11-03: -Affinity FFF with SPURS_NSPUS=5 froze 3 runs of 5 (ps3kit
# docs\ASCENSION_PLAN.md, "Open bugs").
param(
    [string]$Name = "hangcatch",
    [int]$Seconds = 300,
    [string]$Affinity = "",
    [hashtable]$Env = @{},
    [int]$StallSec = 20,
    [string[]]$Commands = @("mem 0099AA80 128", "mem 7001AD00 128", "threads")
)

. (Join-Path $PSScriptRoot "env.ps1")
$logs = Join-Path $Root "build\logs"
$dbg  = Join-Path $logs "$Name-dbg.txt"
$log  = Join-Path $logs "$Name.log"
Remove-Item -ErrorAction SilentlyContinue $dbg, "$dbg.out"

$vars = @{ LD_PERF_OVERLAY = "1" }
foreach ($k in $Env.Keys) { $vars[$k] = $Env[$k] }
$vars.PS3_DEBUG = $dbg
$job = Start-Job -ScriptBlock {
    param($root, $name, $seconds, $affinity, $vars)
    Set-Location $root
    $a = @{ Level = $true; Seconds = $seconds; Name = $name; Env = $vars }
    if ($affinity) { $a.Affinity = $affinity }
    & .\scripts\windows\run.ps1 @a *>&1 | Out-Null
} -ArgumentList $Root, $Name, $Seconds, $Affinity, $vars

$t0 = Get-Date; $inLevel = $false; $count = 0; $changed = Get-Date; $caught = $false
while (((Get-Date) - $t0).TotalSeconds -lt ($Seconds + 20) -and $job.State -eq "Running") {
    Start-Sleep 5
    if (-not (Test-Path $log)) { continue }
    $perf = @(Select-String $log -Pattern '\[perf\] fps=([\d.]+)')
    if ($perf.Count -ne $count) { $count = $perf.Count; $changed = Get-Date }
    if ($perf.Count -gt 12 -and [double]$perf[-1].Matches[0].Groups[1].Value -lt 40) { $inLevel = $true }
    if ($inLevel -and ((Get-Date) - $changed).TotalSeconds -gt $StallSec) {
        "freeze at {0:N0} s ({1} fps lines)" -f ((Get-Date) - $t0).TotalSeconds, $perf.Count
        foreach ($c in $Commands) { Set-Content -Path $dbg -Value $c -Encoding ascii; Start-Sleep 3 }
        $caught = $true
        break
    }
}
if (-not $caught) { "no freeze ({0} fps lines)" -f $count }
Get-Process AscensionRecomp -ErrorAction SilentlyContinue | Stop-Process -Force
Wait-Job $job -Timeout 30 | Out-Null; Remove-Job $job -Force
if (Test-Path "$dbg.out") { Get-Content "$dbg.out" }
