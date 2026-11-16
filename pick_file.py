# -*- coding: utf-8 -*-
"""Ouvre une boite de dialogue native pour choisir une video.
Le chemin choisi est ecrit sur la sortie standard (UTF-8)."""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import tkinter as tk
from tkinter import filedialog

root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)

path = filedialog.askopenfilename(
    title="Choisir une video a ameliorer",
    filetypes=[
        ("Videos", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.wmv *.flv *.mpg *.mpeg *.ts *.m2ts"),
        ("Tous les fichiers", "*.*"),
    ],
)
root.destroy()
if path:
    sys.stdout.write(path)
