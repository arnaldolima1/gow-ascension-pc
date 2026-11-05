# One player of a two-instance online test on this PC (ascension-online docs/ONLINE.md
# O.3f): the capture server must be up (config.capture.toml). Player 1 (Teste1) is
# the host: start it first and pick quick match first; then player 2 (Teste2).
#
#   .\scripts\windows\online2.ps1 -Player 1
#   .\scripts\windows\online2.ps1 -Player 2 -Env @{ PS3_PEEK = "..." }
#
# Player 2 uses gamedata2\ for its saves and its hdd1 cache (copy gamedata\dev_hdd0
# and dev_hdd1 there once), so the two never write the same FIOS cache. Data from build\online: tss-dev.bin and tus\TesteN_1.bin
# (ascension-online tools\tss.py and tools\make_tus_profile.py).
param(
    [ValidateSet(1, 2)][int]$Player = 1,
    $Env = @{},
    [string]$Name = ""
)
. (Join-Path $PSScriptRoot "env.ps1")
$o = Join-Path $Root "build\online"
foreach ($f in "tss-dev.bin", "tus\Teste$($Player)_1.bin") {
    if (-not (Test-Path (Join-Path $o $f))) { Write-Error "missing $o\$f"; exit 1 }
}
$e = @{
    PS3_NET_ONLINE = "1"; PSNR_SERVER = "127.0.0.1:36100"; PS3_NET_DNS = "127.0.0.1"
    PS3_NET_HOSTS = "*.scea.com=127.0.0.1"; PS3_NP_ONLINE_ID = "Teste$Player"
    GOWA_ONLINE_PASS = "1"; GOWA_TSS_PLAIN = "1"; GOWA_GAMELOG = "1"; PS3_NET_TRACE = "1"
    PS3_NP_TSS = (Join-Path $o "tss-dev.bin"); PS3_NP_TUS_DIR = (Join-Path $o "tus")
    PS3_NP_SIGNALING_SERVER = "127.0.0.1:36110"; PS3_NET_P2P_PORT = [string](3657 + $Player)
    PS3_WINDOW_SIZE = "640x360"; LD_PERF_OVERLAY = "1"
}
if ($Player -eq 2) {
    $g = Join-Path $Root "gamedata2"
    if (-not (Test-Path (Join-Path $g "dev_hdd0"))) { Write-Error "copy gamedata\dev_hdd0 and dev_hdd1 into $g first"; exit 1 }
    $e["PS3_GAMEDATA_ROOT"] = $g
    # hdd0 = the disc folder, as player 1 gets by default (update data, read);
    # hdd1 (the FIOS cache, written) and the saves are this player's own.
    $e["PS3_HDD0_ROOT"] = Join-Path $Cfg.WORK_DIR "disc"
    $e["PS3_HDD1_ROOT"] = Join-Path $g "dev_hdd1"
}
if ($Env -is [string]) {
    foreach ($kv in ($Env -split ";")) { if ($kv -match "^\s*([^=]+)=(.*)$") { $e[$Matches[1].Trim()] = $Matches[2] } }
} else { foreach ($k in $Env.Keys) { $e[$k] = [string]$Env[$k] } }
if (-not $Name) { $Name = "online-p$Player" }
& (Join-Path $PSScriptRoot "run.ps1") -Menu -Seconds 0 -Save keep -Name $Name -Env $e
