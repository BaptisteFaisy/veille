#!/usr/bin/env python3
"""Génère l'extrait de données réelles embarqué par la page « Rejeu réel ».

Principe : le site est 100 % statique et hors ligne. Les données patient ne
sont PAS committées (``data/records/`` est ignoré par git) ; on embarque donc
un petit extrait DÉRIVÉ dans ``site/data-reel.js``, produit par ce script à
partir du jeu local (MIT-BIH 222, fibrillation atriale + épisode SVTA).

Rien n'est réimplémenté ici : la lecture WFDB réutilise ``veille.wfdb``, la
détection des pics R / bpm réutilise ``veille.resmgr_client``, et la décision
(seuil 120 bpm, filtre 8) + la mesure de latence réutilisent la VRAIE chaîne C
(``target/pipe/veille_pipe.c`` + ``target/port/host_time.c``) via un petit
harnais compilé à la volée dans un répertoire temporaire.

Usage :
    python3 tools/genere-scene.py                # -> site/data-reel.js
    python3 tools/genere-scene.py --t0 705 --duree 32 --sortie /tmp/x.js

Dépendances : python3 (stdlib), gcc (compilation du harnais), et les données
locales ``data/records/mitdb/`` (``python3 data/fetch.py --db mitdb``).
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "host"))

from veille import wfdb  # noqa: E402
from veille import resmgr_client  # noqa: E402

# Sélection de l'épisode (valeurs par défaut, modifiables en ligne de commande).
RECORD = "222"
SIGNAL = "MLII"
T0 = 705.0          # début de la fenêtre (secondes patient)
DUREE = 32.0        # durée de la fenêtre (secondes patient)
PRE_ROLL = 6.0      # secondes de signal avant t0 (bande ECG toujours pleine)
MARGE_ANNOT = 2.0   # marge autour de la fenêtre pour les annotations affichées

# Constantes de la chaîne (gelées dans target/pipe/veille_pipe.h).
SEUIL_BPM = 120
FENETRE_FILTRE = 8
BORNE_ALARME_MS = 200
BORNE_TECH_MS = 50

# Résultats de la chaîne (target/pipe/veille_pipe.h, veille_pipe_result).
RESULTATS = {0: "OK", 1: "ALARME", 2: "STUCK", 3: "DEAD"}

SOURCE = {
    "base": "MIT-BIH Arrhythmia Database (PhysioNet)",
    "licence": "Open Data Commons Attribution License v1.0 (ODC-By 1.0)",
    "licence_url": "https://physionet.org/about/license/",
    "citations": [
        ("Goldberger 2000",
         "Goldberger AL, Amaral LAN, Glass L, et al. PhysioBank, PhysioToolkit, "
         "and PhysioNet: components of a new research resource for complex "
         "physiologic signals. Circulation. 2000;101(23):e215-e220."),
        ("MIT-BIH 1999",
         "Moody GB, Mark RG. MIT-BIH Arrhythmia Database [Data set]. PhysioNet. "
         "https://physionet.org/content/mitdb/1.0.0 (1999)."),
    ],
    "note": "extrait dérivé (valeurs physiques en mV, retraitées pour "
            "l'affichage) ; les .dat/.atr complets ne sont pas committés.",
}


def lire_annotations(chemin):
    """Annotations de rythme MIT-BIH : [(temps_ech, libellé)] (format binaire).

    Format WFDB « MIT » : fichier lu par paires d'octets [lo | (diff>>8)<<0 |
    label<<2] ; label = b1>>2, diff = b0 + 256*(b1&3). label==59 → SKIP
    (3 paires). Champs extra : 60=NUM, 61=SUB, 62=CHAN, 63=AUX (texte).
    """
    data = Path(chemin).read_bytes()
    pairs = [(data[i], data[i + 1]) for i in range(0, len(data) - 1, 2)]
    tot, bpi, anns = 0, 0, []
    while bpi < len(pairs):
        while bpi < len(pairs) and (pairs[bpi][1] >> 2) == 59:
            if bpi + 2 >= len(pairs):
                break
            a, b = pairs[bpi + 1], pairs[bpi + 2]
            skip = (a[0] << 16) + (a[1] << 24) + (b[0] << 0) + (b[1] << 8)
            if skip > 2147483647:
                skip -= 4294967296
            tot += skip
            bpi += 3
        if bpi >= len(pairs):
            break
        code = pairs[bpi][1] >> 2
        tot += pairs[bpi][0] + 256 * (pairs[bpi][1] & 3)
        bpi += 1
        aux = None
        while bpi < len(pairs):
            n1 = pairs[bpi][1] >> 2
            if n1 == 63:            # AUX : longueur + texte
                longueur = pairs[bpi][0]
                n_paires = (longueur + 1) // 2
                buf = bytearray()
                for k in range(n_paires):
                    if bpi + 1 + k >= len(pairs):
                        break
                    buf += bytes(pairs[bpi + 1 + k])
                aux = buf[:longueur].decode("latin-1", "replace").rstrip("\x00")
                bpi += 1 + n_paires
            elif n1 in (60, 61, 62):        # NUM / SUB / CHAN
                bpi += 1
            else:
                break
        if aux is not None:
            anns.append((tot, code, aux))
    return [(t, c, a) for t, c, a in anns]


def _harness_source():
    """Source C du harnais : rejoue des bpm bruts dans la vraie chaîne."""
    return r"""
/* Harnais temporaire généré par tools/genere-scene.py — non versionné.
 * Réutilise target/pipe/veille_pipe.c (la décision réelle) et
 * target/port/host_time.c (l'horloge monotone) pour mesurer la latence de
 * chaque échantillon bpm réel, comme le resource manager QNX. */
#include "veille_pipe.h"
#include "port_time.h"
#include <stdio.h>

int main(void) {
    veille_chain_config cfg;
    veille_pipe_default_config(&cfg);
    veille_pipe_state st;
    veille_pipe_state_init(&st);
    long bpm;
    int n = 0;
    while (scanf("%ld", &bpm) == 1) {
        long t0 = veille_now_us();
        veille_pipe_result r = veille_pipe_push(&st, bpm);
        long dt = veille_now_us() - t0;
        printf("%d %ld %d %ld\n", n, veille_pipe_filtered(&st), (int)r, dt);
        n++;
    }
    return 0;
}
"""


def _sources_core():
    """Sources core/src/*.c (le harnais lie la chaîne réelle complète)."""
    return sorted(str(p) for p in (RACINE / "core" / "src").glob("*.c"))


def compiler_harnais(tmpdir):
    """Compile le harnais ; retourne le chemin de l'exécutable (ou lève)."""
    src = Path(tmpdir) / "harness.c"
    src.write_text(_harness_source(), encoding="utf-8")
    bin_path = Path(tmpdir) / "veille-rejeu"
    cmd = ["gcc", "-std=c11", "-O2",
           "-Icore/include", "-Itarget/pipe", "-Itarget/port",
           str(src),
           "target/pipe/veille_pipe.c",
           "target/port/host_time.c"] + _sources_core() + ["-o", str(bin_path)]
    proc = subprocess.run(cmd, cwd=RACINE, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit("échec compilation harnais :\n" + proc.stderr)
    return bin_path


def mesurer(bin_path, bpm_bruts):
    """Rejoue les bpm bruts ; retourne [(filtre, resultat, latence_us), ...]."""
    entree = "\n".join(str(v) for v in bpm_bruts) + "\n"
    proc = subprocess.run([str(bin_path)], input=entree, capture_output=True,
                          text=True)
    if proc.returncode != 0:
        raise SystemExit("échec harnais :\n" + proc.stderr)
    lignes = []
    for ligne in proc.stdout.splitlines():
        if not ligne.strip():
            continue
        _n, filtre, resultat, latence = ligne.split()
        lignes.append((int(filtre), int(resultat), int(latence)))
    return lignes


def physiques_de(entete, bruts):
    """Valeurs physiques (mV) d'un signal brut déjà lu."""
    signal = entete.signal(SIGNAL)
    return [signal.physique(v) for v in bruts]


def fenetre_ecg(physiques, fs, t_debut, t_fin):
    """Fenêtre ECG quantifiée au µV (index relatif à ``t_debut``)."""
    j0, j1 = int(t_debut * fs), int(t_fin * fs)
    return [round(physiques[j] * 1000) for j in range(j0, j1)]


def battements_de(physiques, fs):
    """Série bpm réelle : [(index_echantillon, bpm), ...] (pics R)."""
    pics = resmgr_client.detecter_pics_r(physiques, fs)
    return resmgr_client.bpm_intervalles(pics, fs)


def annotations_fenetre(base, fs, t_debut, t_fin):
    """Annotations de rythme MIT-BIH dans ``[t_debut, t_fin]``."""
    sortie = []
    for t_ech, _code, libelle in lire_annotations(str(base) + ".atr"):
        t = t_ech / fs
        if libelle and t_debut <= t <= t_fin:
            sortie.append({"t": round(t, 3), "libelle": libelle})
    return sortie


def construire(args):
    """Produit le dict de données à embarquer."""
    base = (RACINE / args.data / args.record).resolve()
    entete = wfdb.lire_en_tete(str(base))
    fs = entete.fs
    t1 = args.t0 + args.duree
    t_ecg0 = args.t0 - args.pre_roll

    # ECG : on ne lit qu'un préfixe suffisant (gain de temps sur 650 000 éch.).
    bruts = wfdb.lire_bruts(entete, SIGNAL, int((t1 + MARGE_ANNOT) * fs))
    physiques = physiques_de(entete, bruts)
    ecg = fenetre_ecg(physiques, fs, t_ecg0, t1)

    # Série bpm réelle + rejeu dans la vraie chaîne C (latence mesurée).
    battements = battements_de(physiques, fs)
    bpm_bruts = [round(b) for _i, b in battements]
    with tempfile.TemporaryDirectory() as tmpdir:
        mesures = mesurer(compiler_harnais(tmpdir), bpm_bruts)

    # Battements de la fenêtre (+ pré-roll : les panneaux ont un état d'emblée).
    beats = [{"t": round(ech / fs, 3), "bpm": round(bpm), "filtre": filtre,
              "decision": RESULTATS[resultat], "latence_us": latence}
             for (ech, bpm), (filtre, resultat, latence)
             in zip(battements, mesures) if t_ecg0 <= ech / fs <= t1]

    latences = [b["latence_us"] for b in beats]
    return {
        "source": dict(SOURCE, record=args.record, signal=SIGNAL, fs=fs,
                       t0=args.t0, duree=args.duree, ecg_t0=round(t_ecg0, 3),
                       pre_roll=args.pre_roll),
        "chaine": {"seuil_bpm": SEUIL_BPM, "fenetre_filtre": FENETRE_FILTRE,
                   "borne_alarme_ms": BORNE_ALARME_MS,
                   "borne_tech_ms": BORNE_TECH_MS},
        "ecg": ecg, "ecg_fs": fs,
        "beats": beats,
        "annotations": annotations_fenetre(base, fs, t_ecg0, t1),
        "latence_us_max": max(latences) if latences else 0,
    }


def emettre(data, sortie):
    """Écrit le .js embarqué : ``window.VEILLE_REEL = {...}``."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    script = ("/* Généré par tools/genere-scene.py — ne pas éditer à la main.\n"
              "   Extrait dérivé de données réelles (MIT-BIH 222, ODC-By 1.0). */\n"
              "window.VEILLE_REEL = " + payload + ";\n")
    sortie.write_text(script, encoding="utf-8")


def _parser():
    p = argparse.ArgumentParser(prog="genere-scene",
                                description="Génère site/data-reel.js")
    p.add_argument("--record", default=RECORD)
    p.add_argument("--signal", default=SIGNAL)
    p.add_argument("--t0", type=float, default=T0)
    p.add_argument("--duree", type=float, default=DUREE)
    p.add_argument("--pre-roll", type=float, default=PRE_ROLL)
    p.add_argument("--data", default="data/records/mitdb")
    p.add_argument("--sortie", default="site/data-reel.js")
    return p


def main(argv=None):
    args = _parser().parse_args(argv)
    data = construire(args)
    emettre(data, RACINE / args.sortie)
    n_bats = len(data["beats"])
    n_ann = len(data["annotations"])
    print("[genere-scene] %s/%s fenêtre %.0f→%.0f s : %d battements, "
          "%d annotations, %d éch. ECG, latence max %d µs → %s"
          % (args.record, args.signal, args.t0, args.t0 + args.duree,
             n_bats, n_ann, len(data["ecg"]), data["latence_us_max"],
             args.sortie))
    return 0


if __name__ == "__main__":
    sys.exit(main())