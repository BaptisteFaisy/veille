#!/usr/bin/env python3
"""Analyse d'une trace noyau QNX (fichier .kev) : ordonnancement et message passing.

Utilise `traceprinter -f <fichier.kev> -v` du SDP (QNX_HOST doit être positionné :
`source ~/qnx800/qnxsdp-env.sh`), puis extrait :
  - le PID du processus suivi (reconnu par son nom) ;
  - l'histogramme des états de thread de ce PID (THRUNNING, THREADY, THINTR, ...) ;
  - le nombre d'événements de communication (classe COMM) : le passage de messages.

Usage : python3 tools/qnx/trace-e2.py <fichier.kev> [nom_de_processus]
"""
from __future__ import annotations

import collections
import pathlib
import re
import subprocess
import sys
import tempfile

TRACEP = "traceprinter"
RE_TS = re.compile(r"^t:0x([0-9a-f]+)")
RE_PID = re.compile(r"pid:(\d+)")
RE_NOM = re.compile(r"name:(\S+)")
RE_EVT = re.compile(r"^t:0x[0-9a-f]+\s+CPU:\d+\s+([A-Z_]+)\s*:([A-Za-z_]+)")


def decoder(fichier: pathlib.Path) -> pathlib.Path:
    """Décode la trace vers un fichier temporaire et le renvoie."""
    out = pathlib.Path(tempfile.mkstemp(suffix=".trace.txt")[1])
    with out.open("w", encoding="utf-8") as fh:
        proc = subprocess.run([TRACEP, "-f", str(fichier), "-v"],
                              stdout=fh, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        out.unlink()
        raise SystemExit(f"traceprinter a échoué ({proc.returncode}) : {proc.stderr[:400]}")
    return out


def trouver_pid(lignes: list[str], nom: str) -> int | None:
    """PID du processus dont le nom contient `nom`.

    Dans le bloc PROCESS, l'ordre est `ppid:` puis `pid:` puis `name:` : on
    remonte donc de la ligne du nom vers le `pid:` le plus proche qui n'est pas
    un `ppid:`."""
    for i, ligne in enumerate(lignes):
        m = RE_NOM.search(ligne)
        if m and nom in m.group(1):
            for j in range(i - 1, max(0, i - 6), -1):
                if "ppid" in lignes[j]:
                    continue
                mm = RE_PID.search(lignes[j])
                if mm:
                    return int(mm.group(1))
    return None


def analyser(lignes: list[str], nom: str) -> dict:
    pid = trouver_pid(lignes, nom)
    etats: dict[str, int] = collections.Counter()
    comm_total = comm_rm = 0
    premier = dernier = None
    for ligne in lignes:
        m = RE_TS.match(ligne)
        if m:
            t = int(m.group(1), 16)
            premier = t if premier is None else premier
            dernier = t
        e = RE_EVT.match(ligne)
        if not e:
            continue
        if e.group(1) == "COMM":
            comm_total += 1
            if pid and f"pid:{pid}" in ligne:
                comm_rm += 1
        elif pid and e.group(1) == "THREAD" and f"pid:{pid}" in ligne:
            etats[e.group(2)] += 1
    return {"pid": pid, "etats": etats, "comm_total": comm_total,
            "comm_rm": comm_rm, "debut": premier, "fin": dernier}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    nom = argv[2] if len(argv) > 2 else "./veille-rm"
    tmp = decoder(pathlib.Path(argv[1]))
    try:
        lignes = tmp.read_text(errors="replace").splitlines()
        r = analyser(lignes, nom)
    finally:
        tmp.unlink()
    print(f"# trace : {pathlib.Path(argv[1]).name} ({len(lignes)} lignes décodées)")
    print(f"# processus suivi : {nom} → pid {r['pid']}")
    if r["debut"] is not None and r["fin"] is not None:
        print(f"# fenêtre couverte : {r['fin'] - r['debut']} cycles CPU")
    print(f"# événements de communication (classe COMM) : {r['comm_total']} "
          f"(dont {r['comm_rm']} rattachés au pid suivi)")
    print("# états de thread du processus suivi :")
    for etat, n in r["etats"].most_common():
        print(f"#   {etat:<12} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))