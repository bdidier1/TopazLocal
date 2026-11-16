# Topaz Local

**Amélioration vidéo par IA, 100 % en local sur ton PC.** Un équivalent libre et
optimisé GPU de Topaz Video AI : super-résolution (upscaling), débruitage,
netteté, et interpolation de fps pour un mouvement fluide.

Interface web sombre façon Topaz, avec **barre de progression**, **temps écoulé /
restant**, **vitesse** et un **comparateur avant / après**.

---

## Prérequis

- **Windows 10/11** ou **Linux** (Kali / Debian / Ubuntu)
- **Python 3** (Windows : [python.org](https://www.python.org/downloads/), coche
  *« Add Python to PATH »* · Linux : `sudo apt install python3 python3-tk`)
- **Carte graphique compatible Vulkan** (NVIDIA / AMD / Intel récente). Une carte
  NVIDIA est idéale (encodage matériel NVENC en bonus).

L'installeur télécharge automatiquement les trois moteurs nécessaires (une seule
fois, ~600 Mo) : **ffmpeg**, **Real-ESRGAN** (super-résolution IA) et **RIFE**
(interpolation de fps). Ils ne sont pas inclus dans le dépôt car ils dépassent la
limite de taille de GitHub.

## Installation

### Windows
1. Télécharge / clone ce dépôt.
2. Double-clique sur **`Installer.bat`** *(ou lance `install.ps1` dans PowerShell)*.

### Linux (Kali / Debian / Ubuntu)
```bash
sudo apt install python3 python3-tk curl unzip tar libvulkan1 mesa-vulkan-drivers
git clone https://github.com/bdidier1/TopazLocal.git
cd TopazLocal
chmod +x install.sh topaz-local.sh
./install.sh
```

## Utilisation

**Windows :** double-clique sur **`Topaz Local.bat`**.
**Linux :** lance **`./topaz-local.sh`** *(ou `python3 server.py`)*.

Ensuite :
1. Une fenêtre s'ouvre et le navigateur affiche l'application.
2. **Ouvrir une vidéo du PC**.
3. Laisse **Automatique** (règle tout pour la meilleure qualité, porte la vidéo à
   **au moins 60 fps**), ou désactive-le pour régler à la main.
4. **Améliorer la vidéo** → suis la progression (%, temps, ETA, vitesse).
5. À la fin : **comparateur avant / après** (survole l'image), puis
   **Lire la vidéo** / **Ouvrir le dossier**.

Les résultats sont dans **`output/`** (suffixe `_topaz.mp4`).

---

## Comment ça marche

| Étape | Outil | Rôle |
|-------|-------|------|
| Analyse | ffprobe | résolution, fps, durée, audio |
| Extraction | ffmpeg | découpe la vidéo en images PNG sans perte |
| **Super-résolution IA** | **Real-ESRGAN** (ncnn-Vulkan) | reconstruit les détails sur le **GPU** |
| **Interpolation de fps** | **RIFE** (ncnn-Vulkan) | crée des images intermédiaires → mouvement fluide |
| Finition | ffmpeg | redimension cible + netteté + remux audio |
| Encodage | NVENC ou libx264 | ré-encode la vidéo finale |

### Réglages automatiques
- Source ≤ 720p → modèle **qualité max** `realesrgan-x4plus` (×4)
- Source HD (≤ 1500p) → modèle **rapide** `animevideov3` (×2)
- Source > 1500p → pas d'upscale IA, juste nettoyage/netteté
- **fps porté à ≥ 60** (interpolation RIFE), durée et audio conservés
- Sortie plafonnée à **2160p (4K)**

### Réglages manuels
Modèle IA · résolution cible · **fps cible** (Source/30/48/60/90/120/144/240) ·
netteté · réduction du bruit · encodeur (H.264 / H.265) · qualité.

---

## Performances

Le gros du temps, c'est l'**IA sur le GPU**. Pour aller plus vite : modèle
**« Rapide »**, résolution cible plus basse, ou fps cible moindre.

**Encodage GPU (NVENC) :** le build ffmpeg récent exige un pilote NVIDIA **610+**.
Si le tien est plus ancien, l'app **bascule automatiquement sur l'encodeur CPU**
(rapide aussi). Mets à jour ton pilote NVIDIA pour activer l'encodage GPU.

## Dépannage
- *« python n'est pas reconnu »* → installe Python 3 en cochant *Add to PATH*.
- L'IA ne démarre pas → mets à jour les pilotes GPU (Vulkan requis).
- Vidéo très longue → beaucoup d'images temporaires (dossier `jobs/`, vidé
  automatiquement à la fin) ; prévois de l'espace disque.

---

## Structure du projet

```
TopazLocal/
├─ Installer.bat / install.ps1   # installe les dépendances (Windows)
├─ install.sh                    # installe les dépendances (Linux)
├─ Topaz Local.bat               # lance l'application (Windows)
├─ topaz-local.sh                # lance l'application (Linux)
├─ server.py                     # serveur web local (bibliothèque standard)
├─ engine.py                     # pipeline d'amélioration (ffmpeg + IA)
├─ pick_file.py                  # sélecteur de fichier natif
├─ web/index.html                # interface
└─ tools/                        # binaires (téléchargés par l'installeur, non versionnés)
```

## Crédits
[Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) ·
[RIFE (ncnn-vulkan)](https://github.com/nihui/rife-ncnn-vulkan) ·
[ffmpeg](https://ffmpeg.org). Ce projet ne fait que les orchestrer localement.
