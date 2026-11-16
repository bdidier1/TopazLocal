#!/usr/bin/env bash
# =============================================================
#  Topaz Local - Installeur des dependances (Linux / Kali)
#  Telecharge ffmpeg, Real-ESRGAN et RIFE (builds Linux, GPU Vulkan).
#  Idempotent : relançable sans risque.
# =============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS="$ROOT/tools"
DL="$ROOT/downloads"

C_INFO='\033[36m'; C_OK='\033[32m'; C_WARN='\033[33m'; C_OFF='\033[0m'
info(){ echo -e "${C_INFO}$1${C_OFF}"; }
ok(){ echo -e "${C_OK}$1${C_OFF}"; }
warn(){ echo -e "${C_WARN}$1${C_OFF}"; }

echo
echo "============================================================"
echo "  Installation de Topaz Local (Linux)"
echo "============================================================"
echo

mkdir -p "$TOOLS" "$DL" "$ROOT/output" "$ROOT/jobs" "$ROOT/preview"

# -- Outils requis -------------------------------------------------------
for c in curl unzip tar; do
    command -v "$c" >/dev/null 2>&1 || warn "  [!] '$c' manquant  ->  sudo apt install $c"
done
if command -v python3 >/dev/null 2>&1; then
    ok "  [OK] $(python3 --version)"
else
    warn "  [!] python3 manquant  ->  sudo apt install python3 python3-tk"
fi
python3 -c 'import tkinter' 2>/dev/null && ok "  [OK] tkinter present" \
    || warn "  [!] tkinter manquant (selecteur de fichier)  ->  sudo apt install python3-tk"
if [ -e /usr/lib/x86_64-linux-gnu/libvulkan.so.1 ] || command -v vulkaninfo >/dev/null 2>&1; then
    ok "  [OK] Vulkan present (GPU pret pour l'IA)"
else
    warn "  [!] Vulkan manquant  ->  sudo apt install libvulkan1 mesa-vulkan-drivers"
    warn "      (pilotes proprietaires NVIDIA recommandes pour de bonnes perfs)"
fi
echo

dl(){ # url dest
    [ -f "$2" ] && return 0
    info "  Telechargement : $(basename "$2")"
    curl -L --fail --retry 3 -o "$2" "$1"
}

# -- 1) ffmpeg -----------------------------------------------------------
if [ -x "$TOOLS/ffmpeg" ]; then
    ok "  [1/3] ffmpeg deja installe"
else
    info "  [1/3] ffmpeg"
    dl "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz" "$DL/ffmpeg.tar.xz"
    rm -rf "$DL/ffx"; mkdir -p "$DL/ffx"; tar -xf "$DL/ffmpeg.tar.xz" -C "$DL/ffx"
    cp "$(find "$DL/ffx" -type f -name ffmpeg  | head -1)" "$TOOLS/ffmpeg"
    cp "$(find "$DL/ffx" -type f -name ffprobe | head -1)" "$TOOLS/ffprobe"
    chmod +x "$TOOLS/ffmpeg" "$TOOLS/ffprobe"
    rm -rf "$DL/ffx"
    ok "        ffmpeg installe"
fi

# -- 2) Real-ESRGAN ------------------------------------------------------
if [ -x "$TOOLS/realesrgan/realesrgan-ncnn-vulkan" ]; then
    ok "  [2/3] Real-ESRGAN deja installe"
else
    info "  [2/3] Real-ESRGAN (super-resolution IA)"
    dl "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip" "$DL/re.zip"
    rm -rf "$DL/rex"; mkdir -p "$DL/rex"; unzip -oq "$DL/re.zip" -d "$DL/rex"
    bindir="$(dirname "$(find "$DL/rex" -type f -name realesrgan-ncnn-vulkan | head -1)")"
    mkdir -p "$TOOLS/realesrgan"; cp -r "$bindir/." "$TOOLS/realesrgan/"
    chmod +x "$TOOLS/realesrgan/realesrgan-ncnn-vulkan"
    rm -f "$TOOLS/realesrgan/input.jpg" "$TOOLS/realesrgan/input2.jpg" "$TOOLS/realesrgan/onepiece_demo.mp4" 2>/dev/null || true
    rm -rf "$DL/rex"
    ok "        Real-ESRGAN installe"
fi

# -- 3) RIFE -------------------------------------------------------------
if [ -x "$TOOLS/rife/rife-ncnn-vulkan" ]; then
    ok "  [3/3] RIFE deja installe"
else
    info "  [3/3] RIFE (interpolation de fps IA)"
    dl "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-ubuntu.zip" "$DL/rife.zip"
    rm -rf "$DL/rifex"; mkdir -p "$DL/rifex"; unzip -oq "$DL/rife.zip" -d "$DL/rifex"
    base="$(dirname "$(find "$DL/rifex" -type f -name rife-ncnn-vulkan | head -1)")"
    mkdir -p "$TOOLS/rife"
    cp "$base/rife-ncnn-vulkan" "$TOOLS/rife/"; chmod +x "$TOOLS/rife/rife-ncnn-vulkan"
    cp -r "$base/rife-v4.6" "$TOOLS/rife/"
    rm -rf "$DL/rifex"
    ok "        RIFE installe (modele v4.6)"
fi

rm -rf "$DL"

echo
ok "============================================================"
ok "  Installation terminee !"
ok "  Lance l'application avec :  ./topaz-local.sh"
ok "  (ou : python3 server.py)"
ok "============================================================"
echo
