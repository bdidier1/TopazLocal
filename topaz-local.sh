#!/usr/bin/env bash
# Lance Topaz Local (Linux)
cd "$(dirname "${BASH_SOURCE[0]}")"
if [ ! -x "tools/ffmpeg" ]; then
    echo "Les dependances ne sont pas installees. Lance d'abord :  ./install.sh"
    exit 1
fi
exec python3 server.py
