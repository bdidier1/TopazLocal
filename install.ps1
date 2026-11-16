# =============================================================
#  Topaz Local - Installeur des dependances
#  Telecharge ffmpeg, Real-ESRGAN et RIFE (accelerations GPU).
#  Idempotent : relançable sans risque, ne re-telecharge rien
#  qui est deja installe.
# =============================================================
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root  = $PSScriptRoot
$tools = Join-Path $root "tools"
$dl    = Join-Path $root "downloads"

function Info($m){ Write-Host $m -ForegroundColor Cyan }
function Ok($m){ Write-Host $m -ForegroundColor Green }
function Warn($m){ Write-Host $m -ForegroundColor Yellow }

Write-Host ""
Write-Host "============================================================"
Write-Host "  Installation de Topaz Local"
Write-Host "============================================================"
Write-Host ""

# -- Dossiers ------------------------------------------------------------
foreach ($d in @($tools, $dl, (Join-Path $root "output"), (Join-Path $root "jobs"), (Join-Path $root "preview"))) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

# -- Verifications systeme ----------------------------------------------
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Warn "  [!] Python 3 introuvable. Installe-le depuis https://python.org"
    Warn "      (coche 'Add Python to PATH' pendant l'installation)."
} else {
    Ok ("  [OK] " + (python --version 2>&1))
}
if (-not (Test-Path "$env:SystemRoot\System32\vulkan-1.dll")) {
    Warn "  [!] Vulkan introuvable. Mets a jour tes pilotes GPU (NVIDIA/AMD/Intel)."
} else {
    Ok "  [OK] Vulkan present (GPU pret pour l'IA)"
}
Write-Host ""

function Get-File($url, $out, $name) {
    if (Test-Path $out) { return }
    Info "  Telechargement de $name..."
    Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing
}

# -- 1) ffmpeg (+ NVENC) -------------------------------------------------
if (Test-Path (Join-Path $tools "ffmpeg.exe")) {
    Ok "  [1/3] ffmpeg deja installe"
} else {
    Info "  [1/3] ffmpeg (decodage / encodage video)"
    $zip = Join-Path $dl "ffmpeg.zip"
    Get-File "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" $zip "ffmpeg"
    $ex = Join-Path $dl "ffmpeg_x"
    Remove-Item $ex -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive -Path $zip -DestinationPath $ex -Force
    $ff = Get-ChildItem $ex -Recurse -Filter "ffmpeg.exe"  | Select-Object -First 1
    $fp = Get-ChildItem $ex -Recurse -Filter "ffprobe.exe" | Select-Object -First 1
    Copy-Item $ff.FullName (Join-Path $tools "ffmpeg.exe")  -Force
    Copy-Item $fp.FullName (Join-Path $tools "ffprobe.exe") -Force
    Remove-Item $ex -Recurse -Force -ErrorAction SilentlyContinue
    Ok "        ffmpeg installe"
}

# -- 2) Real-ESRGAN (super-resolution IA) --------------------------------
if (Test-Path (Join-Path $tools "realesrgan\realesrgan-ncnn-vulkan.exe")) {
    Ok "  [2/3] Real-ESRGAN deja installe"
} else {
    Info "  [2/3] Real-ESRGAN (super-resolution IA, GPU Vulkan)"
    $zip = Join-Path $dl "realesrgan.zip"
    Get-File "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip" $zip "Real-ESRGAN"
    Expand-Archive -Path $zip -DestinationPath (Join-Path $tools "realesrgan") -Force
    # images/videos d'exemple inutiles
    foreach ($j in @("input.jpg","input2.jpg","onepiece_demo.mp4")) {
        Remove-Item (Join-Path $tools "realesrgan\$j") -Force -ErrorAction SilentlyContinue
    }
    Ok "        Real-ESRGAN installe"
}

# -- 3) RIFE (interpolation de fps IA) -----------------------------------
if (Test-Path (Join-Path $tools "rife\rife-ncnn-vulkan.exe")) {
    Ok "  [3/3] RIFE deja installe"
} else {
    Info "  [3/3] RIFE (interpolation de fps IA, GPU Vulkan)"
    $zip = Join-Path $dl "rife.zip"
    Get-File "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-windows.zip" $zip "RIFE"
    $ex = Join-Path $dl "rife_x"
    Remove-Item $ex -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive -Path $zip -DestinationPath $ex -Force
    $base = (Get-ChildItem $ex -Directory | Select-Object -First 1).FullName
    $rdir = Join-Path $tools "rife"
    New-Item -ItemType Directory -Force $rdir | Out-Null
    Copy-Item (Join-Path $base "rife-ncnn-vulkan.exe") $rdir -Force
    Copy-Item (Join-Path $base "vcomp140.dll")         $rdir -Force
    Copy-Item (Join-Path $base "rife-v4.6")            $rdir -Recurse -Force
    Remove-Item $ex -Recurse -Force -ErrorAction SilentlyContinue
    Ok "        RIFE installe (modele v4.6)"
}

# -- Nettoyage -----------------------------------------------------------
Remove-Item $dl -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Ok "============================================================"
Ok "  Installation terminee !"
Ok "  Lance l'application avec :  Topaz Local.bat"
Ok "============================================================"
Write-Host ""
