# -*- coding: utf-8 -*-
"""
Topaz Local - moteur d'amelioration video.

Pipeline (facon Topaz Video AI, version libre optimisee GPU) :
  1. ffprobe        -> analyse (resolution, fps, duree, audio)
  2. ffmpeg         -> extraction des images (PNG sans perte)
  3. Real-ESRGAN    -> super-resolution IA sur le GPU (Vulkan)
  4. ffmpeg + NVENC -> redimension cible + nettete + re-encodage materiel + audio

Aucune dependance pip : uniquement la bibliotheque standard + binaires dans tools/.
"""
import os
import re
import sys
import json
import time
import math
import shutil
import subprocess
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(ROOT, "tools")
# Suffixe des executables : .exe sous Windows, rien sous Linux/macOS
EXE = ".exe" if os.name == "nt" else ""
FFMPEG = os.path.join(TOOLS, "ffmpeg" + EXE)
FFPROBE = os.path.join(TOOLS, "ffprobe" + EXE)
REALESRGAN_DIR = os.path.join(TOOLS, "realesrgan")
REALESRGAN = os.path.join(REALESRGAN_DIR, "realesrgan-ncnn-vulkan" + EXE)
MODELS_DIR = os.path.join(REALESRGAN_DIR, "models")
RIFE_DIR = os.path.join(TOOLS, "rife")
RIFE = os.path.join(RIFE_DIR, "rife-ncnn-vulkan" + EXE)
RIFE_MODEL = os.path.join(RIFE_DIR, "rife-v4.6")
JOBS_DIR = os.path.join(ROOT, "jobs")
OUTPUT_DIR = os.path.join(ROOT, "output")
PREVIEW_DIR = os.path.join(ROOT, "preview")

# Empeche l'apparition de fenetres console pour les sous-processus (Windows)
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def open_path(path):
    """Ouvre un fichier ou un dossier avec l'application par defaut (multiplateforme)."""
    if os.name == "nt":
        os.startfile(path)  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _run(cmd):
    """Execute une commande et renvoie (code, stdout, stderr)."""
    p = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", creationflags=CREATE_NO_WINDOW,
    )
    return p.returncode, p.stdout, p.stderr


_ENC_CACHE = {}


def nvenc_available():
    """Teste une fois si l'encodeur materiel NVENC fonctionne avec ce pilote."""
    if "nvenc" in _ENC_CACHE:
        return _ENC_CACHE["nvenc"]
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error",
           "-f", "lavfi", "-i", "testsrc=size=64x64:rate=1:duration=1",
           "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-"]
    try:
        code, _, _ = _run(cmd)
        ok = (code == 0)
    except Exception:
        ok = False
    _ENC_CACHE["nvenc"] = ok
    return ok


def resolve_encoder(requested):
    """Renvoie (codec_ffmpeg, materiel?) en repliant sur le CPU si NVENC indispo."""
    if requested.endswith("nvenc") and not nvenc_available():
        return ("libx265" if "hevc" in requested else "libx264"), False
    if requested.endswith("nvenc"):
        return requested, True
    return requested, False


# ---------------------------------------------------------------------------
# 1. Analyse de la video
# ---------------------------------------------------------------------------
def probe(path):
    """Analyse une video et renvoie ses metadonnees."""
    cmd = [
        FFPROBE, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    code, out, err = _run(cmd)
    if code != 0:
        raise RuntimeError("Impossible de lire la video : " + (err or "fichier invalide"))
    data = json.loads(out)

    vstream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    astream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if vstream is None:
        raise RuntimeError("Aucune piste video trouvee dans ce fichier.")

    width = int(vstream.get("width", 0))
    height = int(vstream.get("height", 0))

    # frame rate (ex: "30000/1001")
    rate = vstream.get("avg_frame_rate") or vstream.get("r_frame_rate") or "0/0"
    try:
        num, den = rate.split("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except Exception:
        fps = 0.0
    if fps <= 0:
        fps = 30.0

    duration = 0.0
    for src in (vstream.get("duration"), data.get("format", {}).get("duration")):
        try:
            duration = float(src)
            if duration > 0:
                break
        except (TypeError, ValueError):
            continue

    # nombre d'images
    nb = 0
    for key in ("nb_frames",):
        try:
            nb = int(vstream.get(key, 0))
        except (TypeError, ValueError):
            nb = 0
        if nb > 0:
            break
    if nb <= 0:
        nb = int(math.ceil(duration * fps)) if duration > 0 else 0

    size = 0
    try:
        size = int(data.get("format", {}).get("size", 0))
    except (TypeError, ValueError):
        size = os.path.getsize(path)

    return {
        "path": path,
        "name": os.path.basename(path),
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "rate": rate,
        "duration": round(duration, 2),
        "frames": nb,
        "size": size,
        "vcodec": vstream.get("codec_name", "?"),
        "has_audio": astream is not None,
    }


# ---------------------------------------------------------------------------
# 2. Reglages automatiques "meilleure qualite"
# ---------------------------------------------------------------------------
def auto_settings(meta):
    """Choisit automatiquement les meilleurs reglages selon la source."""
    h = meta["height"]

    # Choix du modele + facteur natif selon la resolution source.
    if h <= 720:
        # Petite source : on peut se permettre le gros modele qualite (x4),
        # les images sont petites donc ca reste rapide.
        model, native = "realesrgan-x4plus", 4
    elif h <= 1500:
        # HD : modele rapide x2 (suffisant pour doubler vers ~4K).
        model, native = "realesr-animevideov3", 2
    else:
        # Deja tres haute resolution : pas d'upscale IA, juste nettoyage/nettete.
        model, native = None, 1

    target_h = min(h * native, 2160) if model else h

    return {
        "auto": True,
        "model": model,                 # None | realesrgan-x4plus | realesr-animevideov3
        "native_scale": native,
        "target_height": target_h,
        "sharpen": 30,                  # 0-100
        "denoise": 0,                   # 0-100 (l'IA debruite deja)
        # fps cible : au minimum 60 (fluidite), ou plus si la source est deja > 60
        "target_fps": max(60.0, float(round(meta["fps"] or 30))),
        "encoder": "h264_nvenc",        # h264_nvenc | hevc_nvenc
        "quality": 18,                  # cq NVENC (plus bas = meilleure qualite)
    }


def _even(n):
    n = int(round(n))
    return n - (n % 2)


def compute_output_dims(meta, settings):
    """Largeur/hauteur de sortie (paires, ratio conserve)."""
    w, h = meta["width"], meta["height"]
    target_h = int(settings.get("target_height") or h)
    ratio = target_h / h if h else 1.0
    return _even(w * ratio), _even(target_h)


# ---------------------------------------------------------------------------
# 3. Pipeline complet
# ---------------------------------------------------------------------------
class Cancelled(Exception):
    pass


def enhance(meta, settings, progress, should_cancel):
    """
    Lance le pipeline complet.
      progress(dict)        : callback de progression
      should_cancel()->bool : interrogation d'annulation
    Renvoie le chemin du fichier de sortie.
    """
    job_id = str(int(time.time() * 1000))
    work = os.path.join(JOBS_DIR, job_id)
    frames_in = os.path.join(work, "in")
    frames_out = os.path.join(work, "out")
    os.makedirs(frames_in, exist_ok=True)
    os.makedirs(frames_out, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total = meta["frames"] or 1
    started = time.time()
    state = {"proc": None}

    def emit(percent, stage, **extra):
        elapsed = time.time() - started
        eta = (elapsed / percent * (100 - percent)) if percent > 0.5 else 0
        info = {
            "percent": round(min(99.5 if percent < 100 else 100, percent), 1),
            "stage": stage,
            "elapsed": round(elapsed, 1),
            "eta": round(eta, 1),
        }
        info.update(extra)
        progress(info)

    def check():
        if should_cancel():
            p = state.get("proc")
            if p and p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
            raise Cancelled()

    def run_counting(cmd, count_dir, lo, hi, stage, count_total=None, cwd=None):
        """Lance un process et mappe le nb de fichiers produits sur [lo, hi]."""
        ct = count_total or total
        p = subprocess.Popen(
            cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
        state["proc"] = p
        while p.poll() is None:
            check()
            try:
                done = len(os.listdir(count_dir))
            except OSError:
                done = 0
            frac = min(1.0, done / ct) if ct else 0
            rate = done / max(0.001, time.time() - started)
            emit(lo + (hi - lo) * frac, stage,
                 frame=done, frames_total=ct, fps_proc=round(rate, 1))
            time.sleep(0.3)
        state["proc"] = None
        if p.returncode not in (0, None):
            raise RuntimeError(stage + " : echec (code %s)" % p.returncode)

    try:
        model = settings.get("model")
        src_fps = meta["fps"] or 30.0
        target_fps = float(settings.get("target_fps") or 0)
        if target_fps <= 0 and settings.get("interp"):   # compat ancien champ
            target_fps = src_fps * float(settings["interp"])
        do_interp = target_fps > src_fps * 1.01

        # Repartition dynamique de la barre selon les etapes activees.
        EXTRACT_HI, ENC_LO = 8.0, 90.0
        heavy = (["ai"] if model else []) + (["interp"] if do_interp else [])
        weights = {"ai": 3.0, "interp": 2.0}
        ranges, cur = {}, EXTRACT_HI
        tw = sum(weights[h] for h in heavy) or 1
        for h in heavy:
            span = (ENC_LO - EXTRACT_HI) * weights[h] / tw
            ranges[h] = (cur, cur + span)
            cur += span

        # -- Etape 0 : preparation ------------------------------------------
        emit(0.5, "Analyse", frame=0, frames_total=total)
        check()

        # -- Etape 1 : extraction des images (0 -> 8%) ----------------------
        extract_cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                       "-i", meta["path"]]
        vf_pre = []
        if int(settings.get("denoise", 0)) > 0:
            d = int(settings["denoise"]) / 100.0
            vf_pre.append("hqdn3d=%.1f:%.1f:%.1f:%.1f" % (4 * d, 3 * d, 6 * d, 6 * d))
        if vf_pre:
            extract_cmd += ["-vf", ",".join(vf_pre)]
        extract_cmd += ["-fps_mode", "passthrough", os.path.join(frames_in, "f%08d.png")]
        run_counting(extract_cmd, frames_in, 0, EXTRACT_HI, "Extraction des images")

        total = len(os.listdir(frames_in)) or total  # nb reel d'images source

        # -- Etape 2 : super-resolution IA (Real-ESRGAN, GPU) ---------------
        if model:
            scale = int(settings.get("native_scale", 4))
            ai_cmd = [REALESRGAN,
                      "-i", frames_in, "-o", frames_out,
                      "-n", model, "-s", str(scale),
                      "-m", MODELS_DIR, "-f", "png", "-g", "0"]
            lo, hi = ranges["ai"]
            run_counting(ai_cmd, frames_out, lo, hi, "Amelioration IA (GPU)")
            cur_dir = frames_out
            cur_h = meta["height"] * scale
        else:
            cur_dir = frames_in
            cur_h = meta["height"]
        check()

        # -- Etape 2b : interpolation de fps (RIFE, GPU) --------------------
        enc_total = total
        enc_rate = meta["rate"]
        out_fps = src_fps
        if do_interp:
            frames_interp = os.path.join(work, "interp")
            os.makedirs(frames_interp, exist_ok=True)
            target = max(2, int(round(total * target_fps / src_fps)))
            rife_cmd = [RIFE, "-i", cur_dir, "-o", frames_interp,
                        "-m", RIFE_MODEL, "-n", str(target),
                        "-f", "f%08d.png", "-g", "0"]
            if cur_h >= 1440:
                rife_cmd.append("-u")          # mode UHD pour les grandes images
            lo, hi = ranges["interp"]
            run_counting(rife_cmd, frames_interp, lo, hi,
                         "Interpolation IA (RIFE)", count_total=target)
            cur_dir = frames_interp
            enc_total = target
            # le fps de sortie cale exactement sur la duree de la source
            out_fps = src_fps * target / total
            enc_rate = "%.6f" % out_fps
        check()

        # -- Etape 3 : redimension + nettete + encodage (90 -> 100%) --------
        out_w, out_h = compute_output_dims(meta, settings)
        vf = ["scale=%d:%d:flags=lanczos" % (out_w, out_h)]
        sharp = int(settings.get("sharpen", 0))
        if sharp > 0:
            amount = sharp / 100.0 * 1.2
            vf.append("unsharp=5:5:%.3f:5:5:0.0" % amount)
        vf.append("format=yuv420p")

        out_name = os.path.splitext(meta["name"])[0] + "_topaz.mp4"
        out_path = os.path.join(OUTPUT_DIR, out_name)
        prog_file = os.path.join(work, "enc.txt")

        codec, hardware = resolve_encoder(settings.get("encoder", "h264_nvenc"))
        q = int(settings.get("quality", 18))
        if hardware:
            codec_args = ["-c:v", codec, "-preset", "p5", "-rc", "vbr",
                          "-cq", str(q), "-b:v", "0"]
        else:
            codec_args = ["-c:v", codec, "-preset", "fast", "-crf", str(q),
                          "-threads", "0"]

        enc_cmd = [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-progress", prog_file, "-nostats",
            "-framerate", enc_rate,
            "-i", os.path.join(cur_dir, "f%08d.png"),
            "-i", meta["path"],
            "-map", "0:v:0", "-map", "1:a:0?",
            "-vf", ",".join(vf),
        ] + codec_args + [
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-r", enc_rate, "-movflags", "+faststart",
            out_path,
        ]
        enc_stage = "Encodage GPU (NVENC)" if hardware else "Encodage CPU (%s)" % codec
        p = subprocess.Popen(enc_cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        state["proc"] = p
        while p.poll() is None:
            check()
            done = _read_progress_frame(prog_file)
            frac = min(1.0, done / enc_total) if enc_total else 0
            emit(ENC_LO + (100 - ENC_LO) * frac, enc_stage,
                 frame=done, frames_total=enc_total)
            time.sleep(0.3)
        state["proc"] = None
        if p.returncode not in (0, None):
            raise RuntimeError("Encodage : echec (code %s)" % p.returncode)

        # -- Etape 4 : images d'apercu avant / apres ------------------------
        preview_ok = _make_preview(meta["path"], out_path, meta["duration"])

        emit(100, "Termine", frame=enc_total, frames_total=enc_total)
        out_size = os.path.getsize(out_path)
        return {
            "output": out_path,
            "output_name": out_name,
            "output_size": out_size,
            "out_w": out_w,
            "out_h": out_h,
            "out_fps": round(out_fps, 2),
            "out_frames": enc_total,
            "interpolated": do_interp,
            "encoder_used": codec,
            "hardware": hardware,
            "preview": preview_ok,
            "preview_token": job_id,
            "elapsed": round(time.time() - started, 1),
        }
    finally:
        # Nettoyage des images temporaires (peut etre volumineux)
        shutil.rmtree(work, ignore_errors=True)


def _make_preview(src, out, duration):
    """Extrait une image avant (source) et apres (resultat) au milieu de la video."""
    try:
        os.makedirs(PREVIEW_DIR, exist_ok=True)
        mid = max(0.1, (duration or 1.0) / 2.0)
        before = os.path.join(PREVIEW_DIR, "before.png")
        after = os.path.join(PREVIEW_DIR, "after.png")
        for inp, outp in ((src, before), (out, after)):
            _run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                  "-ss", "%.3f" % mid, "-i", inp, "-frames:v", "1", outp])
        return os.path.exists(before) and os.path.exists(after)
    except Exception:
        return False


def _read_progress_frame(prog_file):
    """Lit la derniere valeur frame= du fichier -progress de ffmpeg."""
    try:
        with open(prog_file, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
    except OSError:
        return 0
    last = 0
    for m in re.finditer(r"frame=(\d+)", txt):
        last = int(m.group(1))
    return last
