# Build settings from .env in the repository root (local, never committed).
# Dot-source it from the other scripts:
#
#   . (Join-Path $PSScriptRoot "env.ps1")
#
# Sets $Root (ascension/) and $Cfg (paths made absolute). Stops when .env or a
# setting the build needs is missing.

$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) { Write-Host "missing $envFile"; exit 1 }
$dotenv = @{}
foreach ($line in Get-Content $envFile) {
    $l = $line.Trim()
    if (-not $l -or $l.StartsWith("#")) { continue }
    $eq = $l.IndexOf("=")
    if ($eq -lt 1) { continue }
    $dotenv[$l.Substring(0, $eq).Trim()] = $l.Substring($eq + 1).Trim().Trim('"').Trim("'")
}

function Get-Setting([string]$Name, [switch]$Required) {
    $v = $dotenv[$Name]
    if ($Required -and -not $v) { Write-Host "missing $Name in $envFile"; exit 1 }
    return $v
}
function Resolve-Setting([string]$Path) {
    if (-not $Path) { return $Path }
    if ([IO.Path]::IsPathRooted($Path)) { return [IO.Path]::GetFullPath($Path) }
    return [IO.Path]::GetFullPath((Join-Path $Root $Path))
}

$Cfg = @{}
$Cfg.PS3KIT_DIR         = Resolve-Setting (Get-Setting "PS3KIT_DIR" -Required)
$Cfg.WORK_DIR           = Resolve-Setting (Get-Setting "WORK_DIR" -Required)
$Cfg.VCVARS             = Get-Setting "VCVARS" -Required
$Cfg.FFMPEG_INCLUDE_DIR = Resolve-Setting (Get-Setting "FFMPEG_INCLUDE_DIR" -Required)
$Cfg.BUILD_TYPE         = Get-Setting "BUILD_TYPE" -Required
$Cfg.JOBS               = Get-Setting "JOBS"
$Cfg.RPCS3_RSX          = (Get-Setting "RPCS3_RSX") -eq "1"
$Cfg.GPU_BUILD_DIR      = Resolve-Setting (Get-Setting "GPU_BUILD_DIR")
$Cfg.SPU_FMA            = (Get-Setting "SPU_FMA") -eq "1"
$Cfg.PPU_AVX2           = (Get-Setting "PPU_AVX2") -eq "1"        # lifted PPU code for AVX2/BMI2/FMA3
$Cfg.SPU_AVX2           = (Get-Setting "SPU_AVX2") -eq "1"        # lifted SPU code for AVX2
$Cfg.NATIVE             = (Get-Setting "NATIVE") -eq "1"          # lifted code for this CPU (-march=native, AVX-512)
$Cfg.SPU_XFLOAT_APPROX  = (Get-Setting "SPU_XFLOAT_APPROX") -ne "0"   # on unless .env says 0
$Cfg.SPU_LS_HOOKS       = (Get-Setting "SPU_LS_HOOKS") -eq "1"        # LS diagnostics in lifted code
$Cfg.RSX_VULKAN         = (Get-Setting "RSX_VULKAN") -eq "1"          # ps3kit's Vulkan renderer (PS3_RSX=vulkan)
$vk = Get-Setting "VULKAN_SDK"
if ($vk) { $env:VULKAN_SDK = $vk }
$Cfg.VULKAN_SDK = $vk
if ($Cfg.RPCS3_RSX -and -not $Cfg.GPU_BUILD_DIR) { Write-Host "RPCS3_RSX=1 needs GPU_BUILD_DIR in $envFile"; exit 1 }
foreach ($k in "PS3KIT_DIR", "WORK_DIR", "VCVARS") {
    if (-not (Test-Path $Cfg[$k])) { Write-Host "$k not found: $($Cfg[$k])"; exit 1 }
}
