# -*- coding: utf-8 -*-
"""
Topaz Local - serveur web local.
Sert l'interface et pilote le moteur d'amelioration.
Aucune dependance externe : http.server de la bibliotheque standard.
"""
import os
import sys
import json
import threading
import subprocess
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import engine

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
PORT = 8765

# Etat global du job courant ------------------------------------------------
JOB = {
    "status": "idle",      # idle | running | done | error | cancelled
    "progress": {"percent": 0, "stage": "", "elapsed": 0, "eta": 0},
    "result": None,
    "error": None,
}
JOB_LOCK = threading.Lock()
CANCEL = threading.Event()


def set_progress(info):
    with JOB_LOCK:
        JOB["progress"] = info


def worker(meta, settings):
    CANCEL.clear()
    with JOB_LOCK:
        JOB.update(status="running", result=None, error=None,
                   progress={"percent": 0, "stage": "Demarrage", "elapsed": 0, "eta": 0})
    try:
        result = engine.enhance(meta, settings, set_progress, CANCEL.is_set)
        with JOB_LOCK:
            JOB.update(status="done", result=result)
    except engine.Cancelled:
        with JOB_LOCK:
            JOB.update(status="cancelled", error="Annule par l'utilisateur")
    except Exception as exc:  # noqa
        with JOB_LOCK:
            JOB.update(status="error", error=str(exc))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silencieux

    # -- utilitaires ------------------------------------------------------
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    # -- GET --------------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._serve_file(os.path.join(WEB, "index.html"), "text/html; charset=utf-8")
        if path.startswith("/preview/"):
            fname = os.path.basename(path)
            if fname in ("before.png", "after.png"):
                return self._serve_image(os.path.join(engine.PREVIEW_DIR, fname))
            return self._json({"error": "not found"}, 404)
        if path == "/status":
            with JOB_LOCK:
                return self._json({
                    "status": JOB["status"],
                    "progress": JOB["progress"],
                    "result": JOB["result"],
                    "error": JOB["error"],
                })
        return self._json({"error": "not found"}, 404)

    def _serve_file(self, fpath, ctype):
        try:
            with open(fpath, "rb") as f:
                body = f.read()
        except OSError:
            return self._json({"error": "fichier introuvable"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_image(self, fpath):
        try:
            with open(fpath, "rb") as f:
                body = f.read()
        except OSError:
            return self._json({"error": "image introuvable"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- POST -------------------------------------------------------------
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/browse":
            return self._browse()
        if path == "/start":
            return self._start()
        if path == "/cancel":
            CANCEL.set()
            return self._json({"ok": True})
        if path == "/open-folder":
            try:
                engine.open_path(engine.OUTPUT_DIR)
            except Exception as e:
                return self._json({"ok": False, "error": str(e)})
            return self._json({"ok": True})
        if path == "/open-file":
            data = self._read_body()
            f = data.get("path", "")
            try:
                if f and os.path.exists(f):
                    engine.open_path(f)
            except Exception as e:
                return self._json({"ok": False, "error": str(e)})
            return self._json({"ok": True})
        return self._json({"error": "not found"}, 404)

    def _browse(self):
        """Ouvre le selecteur natif puis analyse la video choisie."""
        try:
            proc = subprocess.run(
                [sys.executable, os.path.join(ROOT, "pick_file.py")],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", creationflags=engine.CREATE_NO_WINDOW,
            )
            path = (proc.stdout or "").strip()
        except Exception as e:
            return self._json({"ok": False, "error": str(e)})

        if not path:
            return self._json({"ok": False, "cancelled": True})
        if not os.path.exists(path):
            return self._json({"ok": False, "error": "Fichier introuvable"})

        try:
            meta = engine.probe(path)
        except Exception as e:
            return self._json({"ok": False, "error": str(e)})

        auto = engine.auto_settings(meta)
        out_w, out_h = engine.compute_output_dims(meta, auto)
        return self._json({"ok": True, "meta": meta, "auto": auto,
                           "out_w": out_w, "out_h": out_h})

    def _start(self):
        with JOB_LOCK:
            if JOB["status"] == "running":
                return self._json({"ok": False, "error": "Un traitement est deja en cours"})
        data = self._read_body()
        path = data.get("path")
        if not path or not os.path.exists(path):
            return self._json({"ok": False, "error": "Video introuvable"})
        try:
            meta = engine.probe(path)
        except Exception as e:
            return self._json({"ok": False, "error": str(e)})

        settings = data.get("settings") or engine.auto_settings(meta)
        # Recalcule target_height si non fourni (override resolution)
        t = threading.Thread(target=worker, args=(meta, settings), daemon=True)
        t.start()
        return self._json({"ok": True})


def main():
    os.chdir(ROOT)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = "http://127.0.0.1:%d/" % PORT
    print("=" * 56)
    print("  Topaz Local demarre")
    print("  Ouvre ton navigateur sur : " + url)
    print("  (Ctrl+C pour arreter)")
    print("=" * 56)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArret.")
        server.shutdown()


if __name__ == "__main__":
    main()
