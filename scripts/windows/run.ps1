# Run the game for a while, with the window visible, and summarise the log.
#
#   .\scripts\windows\run.ps1                          # 120 s, no save (first-use menus)
#   .\scripts\windows\run.ps1 -Save backup -Seconds 90 # work\save-backup in place: straight to the cinematic
#   .\scripts\windows\run.ps1 -Name cin -Env @{ VDEC_TIMELOG = "1"; PS3_HLE_HIST = "5" }
#   .\scripts\windows\run.ps1 -Profile -ProfileAt 45   # sample the busiest threads at 45 s
#   .\scripts\windows\run.ps1 -Seconds 0 -Save keep    # play: runs until you close the window
#   .\scripts\windows\run.ps1 -Menu -Seconds 60        # straight to the main menu (~15 s)
#   .\scripts\windows\run.ps1 -Level -Seconds 150      # into the first level (~100 s), on RPCS3's RSX
#
# -Save fresh  : move the current save aside (work\save-moved\<time>) so the
#                first-use config menus show up (the default)
# -Save backup : as fresh, then copy work\save-backup in (skips those menus)
# -Save keep   : leave the save alone
# -CaptureAt N : presses F12 in the game window at N s: one frame's draws,
#                shaders and surfaces land in captures\cap_<frame>\.
# -Menu        : save-backup, the launcher's composed mods (skip intro) and
#                one X press (14 s) that skips the opening cinematic; the menu is up in
#                ~15 s. More presses enter the second menu (Single Player).
# -Level       : as -Menu, with the presses that start the game: the first level
#                (Kratos chained) is up in ~100 s.
# -D3d12       : live draw D3D12 draws (RSX_LIVE_DRAW) in place of RPCS3's RSX, the
#                default (PS3_RSX=rpcs3; the build needs RPCS3_RSX=1). -Rpcs3 is still
#                taken and changes nothing.
# -Vulkan      : ps3kit's own Vulkan renderer (PS3_RSX=vulkan; the build needs
#                RSX_VULKAN=1 in .env). -VkFps logs its fps line every 5 s.
# -NoShaderCache: no RPCS3 shader cache. By default the runs share the
#                launcher's (gamedata\shader_cache, PS3_SHADER_CACHE): the shaders
#                compiled before load behind a loading screen at the start.
# -Affinity HEX: the game's logical CPUs (process affinity mask, set as soon as
#                it is up): a smaller PC on this one, e.g. FF = 4 cores / 8 threads,
#                3F = 3 cores / 6 threads. SPU pins (SPURS_PIN) outside it are dropped.
# -ThreadCpuAt N: at N s, every thread's host CPU (user/kernel) over 5 s, by thread
#                name (tools\thread_cpu.py), into build\logs\<Name>-cpu.txt.
# The log is build\logs\<Name>.log; tools\log_summary.py prints the summary,
# and with -Profile the resolved profile is build\logs\<Name>-prof.txt.
param(
    [int]$Seconds = 120,
    [ValidateSet("fresh", "backup", "keep")][string]$Save = "fresh",
    [string]$Name = "run",
    $Env = @{},                         # hashtable, or "NAME=value;NAME2=value2"
    [switch]$Profile,
    [int]$ProfileAt = 45,
    [int]$ProfileThreads = 4,
    [ValidateSet("prof", "profip")][string]$ProfileVerb = "prof",   # profip: exclusive time per instruction
    [switch]$Menu,
    [switch]$Level,
    [switch]$Rpcs3,                     # the default; kept for old command lines
    [switch]$D3d12,
    [switch]$Vulkan,
    [switch]$VkFps,
    [switch]$NoShaderCache,
    [int]$CaptureAt = 0,                # press F12 (frame capture into captures\) at this second
    [int]$ThreadCpuAt = 0,              # per-thread host CPU over 5 s from this second
    [string]$Affinity = ""              # process affinity mask (hex), a smaller PC
)

. (Join-Path $PSScriptRoot "env.ps1")
$Work    = $Cfg.WORK_DIR
$Exe     = Join-Path $Root "build\win\AscensionRecomp.exe"
$Elf     = Join-Path $Work "disc\PS3_GAME\USRDIR\EBOOT.ELF"
$Logs    = Join-Path $Root "build\logs"
$SaveDir = Join-Path $Root "gamedata\dev_hdd0\home\00000001\savedata"
$Slot    = Join-Path $SaveDir "BCES01741-SYSDATA"
New-Item -ItemType Directory -Force $Logs, $SaveDir | Out-Null
$Log = Join-Path $Logs "$Name.log"

if ($Level) { $Menu = $true }
if ($Menu) {
    if (-not $PSBoundParameters.ContainsKey("Save")) { $Save = "backup" }
    if ($Env -is [string]) { $Env = $Env + ";" } else { $Env = $Env.Clone() }
    $pad = if ($Level) { "14:0x4000,15:0x0000,24:0x4000,25:0x0000,27:0x4000,28:0x0000,30:0x4000,31:0x0000,33:0x4000,34:0x0000" }
           else { "14:0x4000,15:0x0000" }
    $menuEnv = @{ PAD_SCRIPT = $pad }
    $gen = Join-Path $env:APPDATA "ascension-launcher\generated"
    if (Test-Path $gen) { $menuEnv["PS3_MODS"] = $gen } else { Write-Host "no launcher mods at $($gen): the intro screens will play" }
    if ($Env -is [string]) { foreach ($k in $menuEnv.Keys) { $Env += "$k=$($menuEnv[$k]);" } }
    else { foreach ($k in $menuEnv.Keys) { if (-not $Env.ContainsKey($k)) { $Env[$k] = $menuEnv[$k] } } }
}
if ($Save -ne "keep" -and (Test-Path $Slot)) {
    $dest = Join-Path $Work ("save-moved\" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    New-Item -ItemType Directory -Force $dest | Out-Null
    Move-Item $Slot $dest
    Write-Host "save moved to $dest"
}
# A run killed while FIOS rewrites its HDD cache leaves cache.idx zero-filled,
# and every later boot loops re-reading it on a black screen: move it aside
# (the game builds a new one).
$Fios = Join-Path $Work "disc\cache\BCES01741\fios"
$FiosIdx = Join-Path $Fios "cache.idx"
if (Test-Path $FiosIdx) {
    $head = [byte[]]::new(64)
    $fs = [IO.File]::OpenRead($FiosIdx); $nread = $fs.Read($head, 0, 64); $fs.Close()
    if ($nread -eq 0 -or -not ($head[0..($nread - 1)] | Where-Object { $_ -ne 0 })) {
        $dest = Join-Path $Work ("save-moved\fios-broken-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
        New-Item -ItemType Directory -Force $dest | Out-Null
        Get-ChildItem $Fios | Move-Item -Destination $dest
        Write-Host "FIOS cache.idx was zero-filled (a killed run): moved to $dest"
    }
}
if ($Save -eq "backup") {
    Copy-Item -Recurse (Join-Path $Work "save-backup\BCES01741-SYSDATA") $SaveDir
    Write-Host "save-backup copied in"
}

if ($Env -is [string]) {
    $h = @{}
    foreach ($kv in ($Env -split ";")) { if ($kv -match "^\s*([^=]+)=(.*)$") { $h[$Matches[1].Trim()] = $Matches[2] } }
    $Env = $h
} elseif (-not $Menu) { $Env = $Env.Clone() }
# RPCS3's RSX for every run, not only -Menu/-Level ones, unless -D3d12.
if ($Vulkan -and -not $Env.ContainsKey("PS3_RSX")) { $Env["PS3_RSX"] = "vulkan" }
if ($VkFps -and -not $Env.ContainsKey("PS3RECOMP_VK_FPS")) { $Env["PS3RECOMP_VK_FPS"] = "1" }
if (-not $D3d12 -and -not $Env.ContainsKey("PS3_RSX")) { $Env["PS3_RSX"] = "rpcs3" }
if (-not $Env.ContainsKey("PS3_SHADER_CACHE")) {
    $Env["PS3_SHADER_CACHE"] = if ($NoShaderCache) { "0" } else { Join-Path $Root "gamedata\shader_cache" }
}
# The game inherits this process's environment; restore it afterwards.
$saved = @{}
foreach ($k in $Env.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); [Environment]::SetEnvironmentVariable($k, [string]$Env[$k]) }
$dbg = Join-Path $Logs "$Name-dbg.txt"
if ($Profile) {
    Remove-Item -ErrorAction SilentlyContinue $dbg, "$dbg.out"
    $saved["PS3_DEBUG"] = $env:PS3_DEBUG; $env:PS3_DEBUG = $dbg
}

$t0 = Get-Date
$p = Start-Process cmd.exe -ArgumentList "/c `"`"$Exe`" `"$Elf`" > `"$Log`" 2>&1`"" -WorkingDirectory $Root -PassThru -WindowStyle Hidden
foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
Write-Host $(if ($Seconds -le 0) { "running until closed (log: $Log)" } else { "running for $Seconds s (log: $Log)" })

if ($Affinity) {
    # as early as the process shows, before the SPU threads start
    for ($i = 0; $i -lt 100 -and -not $game; $i++) {
        $game = Get-Process AscensionRecomp -ErrorAction SilentlyContinue | Sort-Object StartTime -Descending | Select-Object -First 1
        if (-not $game) { Start-Sleep -Milliseconds 20 }
    }
    if ($game) { $game.ProcessorAffinity = [IntPtr][Convert]::ToInt64($Affinity, 16); Write-Host "affinity 0x$Affinity" }
}
Start-Sleep -Seconds 2
$game = Get-Process AscensionRecomp -ErrorAction SilentlyContinue | Sort-Object StartTime -Descending | Select-Object -First 1
if ($Profile -and $game) {
    $wait = $ProfileAt - ((Get-Date) - $t0).TotalSeconds
    if ($wait -gt 0) { Start-Sleep -Seconds $wait }
    python -I (Join-Path $Root "tools\profile_threads.py") --pid $game.Id --dbg $dbg --threads $ProfileThreads `
        --verb $ProfileVerb --map (Join-Path $Root "build\win\AscensionRecomp.map") --out (Join-Path $Logs "$Name-prof.txt")
}
if ($ThreadCpuAt -gt 0 -and $game) {
    $wait = $ThreadCpuAt - ((Get-Date) - $t0).TotalSeconds
    if ($wait -gt 0) { Start-Sleep -Seconds $wait }
    python -I (Join-Path $Root "tools\thread_cpu.py") --pid $game.Id --secs 5 --out (Join-Path $Logs "$Name-cpu.txt")
}
if ($CaptureAt -gt 0 -and $game) {
    $wait = $CaptureAt - ((Get-Date) - $t0).TotalSeconds
    if ($wait -gt 0) { Start-Sleep -Seconds $wait }
    Add-Type -Namespace RunPs1 -Name Keys -MemberDefinition @"
[DllImport("user32.dll")] public static extern void keybd_event(byte k, byte s, uint f, System.UIntPtr e);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(System.IntPtr h);
"@
    $game.Refresh()
    [RunPs1.Keys]::SetForegroundWindow($game.MainWindowHandle) | Out-Null
    Start-Sleep -Milliseconds 300
    [RunPs1.Keys]::keybd_event(0x7B, 0, 0, [System.UIntPtr]::Zero)
    Start-Sleep -Milliseconds 150
    [RunPs1.Keys]::keybd_event(0x7B, 0, 2, [System.UIntPtr]::Zero)
    Write-Host "F12 sent at $([int]((Get-Date) - $t0).TotalSeconds) s"
}
if ($Seconds -le 0) {
    # -Seconds 0: play; wait until the game is closed, never kill it.
    if ($game) { Write-Host "playing: close the game window when done"; Wait-Process -Id $game.Id }
} else {
    $left = $Seconds - ((Get-Date) - $t0).TotalSeconds
    if ($left -gt 0 -and $game) { Wait-Process -Id $game.Id -Timeout $left -ErrorAction SilentlyContinue }
    Get-Process AscensionRecomp -ErrorAction SilentlyContinue | Stop-Process -Force
}
Start-Sleep -Milliseconds 500

python -I (Join-Path $Root "tools\log_summary.py") $Log
