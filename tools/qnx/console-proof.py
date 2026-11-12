#!/usr/bin/env python3
"""Capture de l'écran de la console série QNX toutes les 2 s, rendue en PNG.

La preuve « ça tourne vraiment » : la VM QNX 8.0 (booterment headless) expose sa
console sur un socket TCP. Ce script s'y connecte, déroule une démonstration,
lit ce que la console affiche, le débarrasse des séquences ANSI, et rend le
tampon terminal en image PNG (fond sombre, fonte à chasse fixe) — une capture
d'écran par étape, plus une capture automatique toutes les 2 s.

Usage : python3 tools/qnx/console-proof.py [repertoire_sortie]
"""
from __future__ import annotations

import re
import socket
import sys
import time
from pathlib import Path

HOTE, PORT = "127.0.0.1", 4444
RE_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b[()][0-9A-B]|\x1b[<>]|\r")
# Étapes (commande, attente en secondes, étiquette du plan de la vidéo)
DEMO = [
    ("uname -a; date -u", 3, "1-uname-qnx80"),
    ("cd /data/veille && slay -9 veille-rm 2>/dev/null; sleep 1; "
     "nohup ./veille-rm --no-tick > /tmp/rm.log 2>&1 & sleep 2; ls -l /dev/veille",
     6, "2-resmgr-demarre"),
    ("sh /data/veille/rm-test.sh", 10, "3-quatre-issues"),
    ("cd /data/veille-py && python3 -m veille.resmgr_client "
     "--record /data/veille-data/mitdb/222 --signal MLII --sortie /dev/veille",
     12, "4-ecg-reel-mitdb222"),
    ("head -2 /dev/veille; pidin -F '%p %n' | grep '[v]eille'",
     3, "5-verdict-et-processus"),
]


def connexion() -> socket.socket:
    s = socket.create_connection((HOTE, PORT), timeout=15)
    s.settimeout(1.0)
    return s


def lire(s: socket.socket, duree: float) -> str:
    buf = bytearray()
    fin = time.time() + duree
    while time.time() < fin:
        try:
            d = s.recv(65536)
            if not d:
                break
            buf.extend(d)
        except socket.timeout:
            if buf:
                break
    return buf.decode("utf-8", "replace")


def login(s: socket.socket) -> str:
    """Connexion à la console ; login root/root si un prompt login apparaît."""
    s.sendall(b"\n")
    t = lire(s, 3)
    if "login:" in t:
        s.sendall(b"root\n")
        lire(s, 2)
        s.sendall(b"root\n")
        t += lire(s, 4)
    return t


def rendre(tampon: list[str], largeur: int, hauteur: int) -> object:
    from PIL import Image, ImageDraw, ImageFont
    ligne_h = 22
    img = Image.new("RGB", (largeur, hauteur), (13, 15, 20))
    d = ImageDraw.Draw(img)
    fonte = ImageFont.load_default()
    y = 8
    for ligne in tampon[-((hauteur - 16) // ligne_h):]:
        d.text((8, y), (ligne or " ").rstrip()[:120], font=fonte, fill=(208, 214, 220))
        y += ligne_h
    return img


def capturer(s: socket.socket, tampon: list[str]) -> None:
    brut = lire(s, 1.0)
    if brut:
        propre = RE_ANSI.sub("", brut)
        for l in propre.split("\n"):
            l = l.rstrip()
            if l.strip():
                tampon.append(l)
        tampon[:] = tampon[-60:]


def main(argv: list[str]) -> int:
    sortie = Path(argv[1]) if len(argv) > 1 else Path("/tmp/qnx-screens")
    sortie.mkdir(parents=True, exist_ok=True)
    s = connexion()
    tampon: list[str] = []
    tampon.extend(RE_ANSI.sub("", login(s)).split("\n"))
    index = 0
    etape_actuelle = None
    fin_demo = time.time() + 90
    demarrage = time.time()
    while time.time() < fin_demo:
        # une commande de démo quand on n'en attend pas une déjà
        if etape_actuelle is None and index < len(DEMO):
            cmd, attente, label = DEMO[index]
            index += 1
            etape_actuelle = (time.time() + attente, label)
            s.sendall((cmd + "\n").encode())
        capturer(s, tampon)
        if etape_actuelle and time.time() >= etape_actuelle[0]:
            label = etape_actuelle[1]
            img = rendre(tampon, 900, 760)
            img.save(sortie / f"{label}.png")
            print(f"[{time.time() - demarrage:4.0f}s] {label}.png ({len(tampon)} lignes)")
            etape_actuelle = None
        # capture automatique toutes les 2 s (préuve de vivacité)
        n = int((time.time() - demarrage) // 2)
        aut = sortie / f"auto-{n:03d}s.png"
        if not aut.exists() and len(tampon) > 3:
            rendre(tampon, 900, 760).save(aut)
        time.sleep(0.3)
    s.close()
    print(f"terminé : {len(list(sortie.glob('*.png')))} captures dans {sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))