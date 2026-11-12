#!/usr/bin/env python3
"""Banc de latence Veille — mesure réelle de la chaîne sur l'hôte.

Mesure la **latence réelle** (temps mural, `time.perf_counter`) des trois
chemins de la chaîne existante, sur des données ECG réelles (MIT-BIH) :

1. **chaîne d'analyse** — :func:`veille.replay.rejouer` : acquisition,
   filtrage, décision d'état capteur, calcul de latence pire cas et
   verdicts. Latence mesurée par fenêtre d'analyse de 1 s (différence
   marginale entre deux préfixes du même enregistrement, donc exactement le
   coût d'une fenêtre supplémentaire) ;
2. **alarme** — :func:`veille.resmgr_client.ecrire_bpm` : écriture des lignes
   ``bpm N`` vers la destination (``/dev/veille`` sur cible QNX, un fichier
   sur l'hôte) ;
3. **décision** — :func:`veille.proof.proof_explore` : exploration exhaustive
   des 4800 états de défaillance (le cœur de la preuve de borne).

Le banc ne réécrit **aucune** logique de la chaîne : il appelle les modules
existants (`veille.wfdb`, `veille.replay`, `veille.resmgr_client`,
`veille.proof`) et se contente de chronométrer et d'agréger.

Charge simulée : des threads occupent le CPU pendant la mesure
(`--charge N`), pour observer la dégradation de latence sous contention.

Stdlib uniquement. Exemple :

    python3 tools/bench-latences.py --record data/records/mitdb/100 \\
        --signal MLII --fenetres 40 --repetitions 5 --charge 0 4
"""
import argparse
import os
import statistics
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "host"))

from veille import wfdb                                    # noqa: E402
from veille.proof import proof_explore, FaultMask           # noqa: E402
from veille.replay import rejouer                           # noqa: E402
from veille.resmgr_client import bpm_intervalles, detecter_pics_r, ecrire_bpm  # noqa: E402

FENETRE_S = 1.0        # durée d'une fenêtre d'analyse (identique au rejeu)
BORNE_PRIO = 100       # borne d'alarme haute IEC 60601-1-8 (ms)


def percentile(valeurs, p):
    """Percentile (interpolation linéaire) d'une liste de mesures.

    ``p`` est une fraction de 0 à 1. Méthode linéaire sur l'échantillon trié
    (identique à la définition de NumPy pour un échantillon fini).
    """
    if not valeurs:
        return 0.0
    tri = sorted(valeurs)
    if len(tri) == 1:
        return float(tri[0])
    pos = (len(tri) - 1) * p
    bas = int(pos)
    haut = min(bas + 1, len(tri) - 1)
    frac = pos - bas
    return float(tri[bas] * (1.0 - frac) + tri[haut] * frac)


def resume(mesures):
    """Agrège une liste de mesures (ms) → dict p50/p95/p99/max/moyenne."""
    if not mesures:
        return {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0,
                "moyenne": 0.0}
    return {"n": len(mesures),
            "p50": percentile(mesures, 0.50),
            "p95": percentile(mesures, 0.95),
            "p99": percentile(mesures, 0.99),
            "max": max(mesures),
            "moyenne": statistics.fmean(mesures)}


def charge_cpu(n):
    """Fil de charge CPU : n threads booléens actifs, stoppés via l'événement.

    Retourne ``(evt, threads)`` ; l'appelant pose ``evt.set()`` puis joint.
    """
    evt = threading.Event()
    threads = []

    def boucle():
        x = 0
        while not evt.is_set():
            x = (x + 1) & 0xFFFF  # charge légère, borne le passage en boucle
        return x

    for _ in range(n):
        t = threading.Thread(target=boucle, daemon=True)
        t.start()
        threads.append(t)
    return evt, threads


def arreter_charge(evt, threads):
    """Stoppe les threads de charge et attend leur fin."""
    evt.set()
    for t in threads:
        t.join(timeout=5)


def latence_fenetres(chemin, signal, fenetres, repetitions):
    """Latence (ms) d'une fenêtre d'analyse de 1 s via :func:`rejouer`.

    Pour chaque répétition et chaque ``k`` de 1 à ``fenetres``, on chronomètre
    ``rejouer(limite=k·F)`` — le coût réel (acquisition + décision + verdict)
    de faire traverser la chaîne par ``k`` fenêtres — puis on divise par ``k``
    : la latence amortie d'une fenêtre, telle que la voit un observateur qui
    alimente la chaîne en continu.
    """
    entete = wfdb.lire_en_tete(chemin)
    if entete.signal(signal) is None:
        raise KeyError("signal %r absent de %s (disponibles : %s)"
                       % (signal, entete.nom, ", ".join(entete.noms())))
    f = int(entete.fs * FENETRE_S)
    fenetres = min(fenetres, entete.nb_echantillons // f)
    mesures = []
    for _ in range(repetitions):
        for k in range(1, fenetres + 1):
            t0 = time.perf_counter()
            rejouer(chemin, signal, limite=k * f)
            mesures.append((time.perf_counter() - t0) * 1000.0 / k)
    return mesures


def latence_alarme(chemin, signal, repetitions):
    """Latence (ms) d'écriture d'une ligne ``bpm`` vers la destination.

    Mesure le temps mural de :func:`ecrire_bpm` sur l'ensemble des battements
    détectés, divisé par le nombre de lignes — le coût réel par battement de
    l'étage alarme (sur hôte : un simple fichier).
    """
    entete = wfdb.lire_en_tete(chemin)
    sig = entete.signal(signal)
    if sig is None:
        raise KeyError("signal %r absent de %s" % (signal, entete.nom))
    bruts = wfdb.lire_bruts(entete, signal)
    physiques = [sig.physique(v) for v in bruts]
    pics = detecter_pics_r(physiques, entete.fs)
    battements = bpm_intervalles(pics, entete.fs)
    if not battements:
        return []
    chemin_sortie = os.path.join(os.path.dirname(entete.chemin), ".bench.out")
    mesures = []
    for _ in range(repetitions):
        t0 = time.perf_counter()
        ecrites = ecrire_bpm(chemin_sortie, battements)
        duree = (time.perf_counter() - t0) * 1000.0
        mesures.append(duree / ecrites if ecrites else 0.0)
    try:
        os.remove(chemin_sortie)
    except OSError:
        pass
    return mesures


def latence_preuve(repetitions):
    """Latence (ms) de l'exploration exhaustive (4800 états) via proof_explore."""
    from veille.chain import ChainConfig

    cfg = ChainConfig(0, BORNE_PRIO, 60000, [5, 10, 10, 20, 5])
    mask = FaultMask(True, True, True, True, True)
    mesures = []
    for _ in range(repetitions):
        t0 = time.perf_counter()
        proof_explore(cfg, mask)
        mesures.append((time.perf_counter() - t0) * 1000.0)
    return mesures


def _format(res, unite="ms"):
    """Formate un dict de résumé {p50,p95,p99,max,moyenne} sur une ligne."""
    return ("p50=%.3f%s  p95=%.3f%s  p99=%.3f%s  max=%.3f%s  moyenne=%.3f%s"
            % (res["p50"], unite, res["p95"], unite, res["p99"], unite,
               res["max"], unite, res["moyenne"], unite))


def mesurer_charge(args, charge):
    """Mesure les trois chemins sous une charge CPU donnée (0 = repos)."""
    evt, threads = charge_cpu(charge)
    try:
        fenetres = latence_fenetres(args.record, args.signal,
                                    args.fenetres, args.repetitions)
        alarme = latence_alarme(args.record, args.signal, args.repetitions)
        preuve = latence_preuve(args.repetitions)
    finally:
        arreter_charge(evt, threads)
    return fenetres, alarme, preuve


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Latence réelle de la chaîne Veille sur l'hôte (réutilise la chaîne existante)")
    p.add_argument("--record", default="data/records/mitdb/100",
                   help="enregistrement ECG réel (défaut : data/records/mitdb/100)")
    p.add_argument("--signal", default="MLII", help="signal ECG (défaut : MLII)")
    p.add_argument("--fenetres", type=int, default=40,
                   help="nombre de fenêtres d'1 s mesurées (défaut : 40)")
    p.add_argument("--repetitions", type=int, default=5,
                   help="répétitions par mesure (défaut : 5)")
    p.add_argument("--charge", type=int, nargs="+", default=[0, 4],
                   help="niveaux de charge CPU simulée, ex. « 0 4 8 » (défaut : 0 4)")
    args = p.parse_args(argv)

    chemin = args.record
    entete = wfdb.lire_en_tete(chemin)
    if entete.signal(args.signal) is None:
        sys.stderr.write("signal %r absent de %s (disponibles : %s)\n"
                         % (args.signal, entete.nom, ", ".join(entete.noms())))
        return 2

    print("Banc de latence Veille — %s (%s, %d Hz)\n" % (entete.nom,
          args.signal, entete.fs))
    for charge in args.charge:
        fenetres, alarme, preuve = mesurer_charge(args, charge)
        print("Charge CPU simulée : %d thread(s)" % charge)
        print("  chaîne d'analyse (ms/fenêtre 1 s) … %s"
              % _format(resume(fenetres)))
        print("  alarme (ms/battement écrit) …………… %s"
              % _format(resume(alarme)))
        print("  preuve (ms/exploration 4800 états) … %s"
              % _format(resume(preuve)))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
