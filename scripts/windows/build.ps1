# Build AscensionRecomp.exe (ninja in build\win) and log it. The settings
# come from .env (scripts\windows\env.ps1).
#
#   .\scripts\windows\build.ps1                 # log: build\logs\build.log
#   .\scripts\windows\build.ps1 -Name sse41     # log: build\logs\build-sse41.log
#   .\scripts\windows\build.ps1 -Configure      # run CMake again with .env's settings first
#
# CMake runs by itself the first time (no build\win\build.ninja). Prints how
# long it took, the error lines if any, and the last line of the log; the
# exit code is ninja's.
param([string]$Name = "", [switch]$Configure)

. (Join-Path $PSScriptRoot "env.ps1")
$Build = Join-Path $Root "build\win"
$Logs  = Join-Path $Root "build\logs"
New-Item -ItemType Directory -Force $Logs | Out-Null
$Log = Join-Path $Logs ($(if ($Name) { "build-$Name.log" } else { "build.log" }))

if ($Configure -or -not (Test-Path (Join-Path $Build "build.ninja"))) {
    if ($Cfg.RPCS3_RSX -and -not (Test-Path (Join-Path $Cfg.GPU_BUILD_DIR "ps3rsx.lib"))) {
        Write-Host "RPCS3_RSX=1 needs $($Cfg.GPU_BUILD_DIR)\ps3rsx.lib: run .\scripts\windows\build-gpu.ps1 first"
        exit 1
    }
    $onoff = { param($b) if ($b) { "ON" } else { "OFF" } }
    $cmakeArgs = @(
        "-S", "`"$Root`"", "-B", "`"$Build`"", "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=$($Cfg.BUILD_TYPE)",
        "-DASCENSION_SPU_LAB_FLAGS=`"$($env:SPU_LAB_FLAGS)`"",
        "-DCMAKE_C_COMPILER=clang-cl", "-DCMAKE_CXX_COMPILER=clang-cl",
        "-DPS3RECOMP_DIR=`"$($Cfg.PS3KIT_DIR)`"",
        "-DPS3RECOMP_FFMPEG_RUNTIME=ON", "-DPS3RECOMP_FFMPEG_INCLUDE_DIR=`"$($Cfg.FFMPEG_INCLUDE_DIR)`"",
        "-DASCENSION_SPU_FMA=$(& $onoff $Cfg.SPU_FMA)",
        "-DASCENSION_PPU_AVX2=$(& $onoff $Cfg.PPU_AVX2)",
        "-DASCENSION_SPU_AVX2=$(& $onoff $Cfg.SPU_AVX2)",
        "-DASCENSION_NATIVE=$(& $onoff $Cfg.NATIVE)",
        "-DASCENSION_SPU_XFLOAT_APPROX=$(& $onoff $Cfg.SPU_XFLOAT_APPROX)",
        "-DASCENSION_SPU_LS_HOOKS=$(& $onoff $Cfg.SPU_LS_HOOKS)",
        "-DASCENSION_RPCS3_RSX=$(& $onoff $Cfg.RPCS3_RSX)",
        "-DASCENSION_RPCS3_BUILD=`"$($Cfg.GPU_BUILD_DIR)`"",
        "-DPS3RECOMP_RSX_VULKAN=$(& $onoff $Cfg.RSX_VULKAN)"
    ) -join " "
    $ConfLog = Join-Path $Logs "configure.log"
    Write-Host "configuring build\win (log: $ConfLog)"
    cmd /c "`"$($Cfg.VCVARS)`" >nul && cmake $cmakeArgs" 2>&1 | Out-File -Encoding utf8 $ConfLog
    if ($LASTEXITCODE -ne 0) { Get-Content $ConfLog -Tail 20; exit $LASTEXITCODE }
}

$jobs = if ($Cfg.JOBS) { "-j $($Cfg.JOBS)" } else { "" }
$sw = [Diagnostics.Stopwatch]::StartNew()
cmd /c "`"$($Cfg.VCVARS)`" >nul && ninja -C `"$Build`" $jobs" 2>&1 | Out-File -Encoding utf8 $Log
$code = $LASTEXITCODE
$sw.Stop()

$errors = Select-String -Path $Log -Pattern "error:|FAILED:|fatal error|LNK\d{4}" | Select-Object -First 15
Write-Host ("build {0} in {1:mm\:ss}  (log: {2})" -f $(if ($code -eq 0) { "OK" } else { "FAILED" }), $sw.Elapsed, $Log)
if ($errors) { $errors | ForEach-Object { Write-Host "  $($_.Line)" } }
Write-Host ("last line: " + (Get-Content $Log -Tail 1))
exit $code
