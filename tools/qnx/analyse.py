#!/usr/bin/env python3
"""Veille — analyse des journaux de preuve QNX 8.0 (tools/qnx/).

Lit les journaux de preuve/qnx80/ et produit les tableaux de chiffres qui
servent au compte rendu docs/QNX-EVIDENCE.md :
  - latences client→rm (échantillons bruts « rtt_us= ») : p50/p95/p99/max ;
  - cadence du tick (statistiques du rm et sonde indépendante) ;
  - compteur de priorités observées par le rm (preuve d'héritage E2).

Usage :  python3 tools/qnx/analyse.py [répertoire-des-journaux] [--markdown]
"""
import glob
import os
import re
import sys

RTT = re.compile(r"^rtt_us=(\d+)$", re.M)


def percentiles(valeurs):
    """Percentiles exacts sur l'échantillon brut (tri par copie)."""
    if not valeurs:
        return {}
    v = sorted(valeurs)
    n = len(v)

    def pct(p):
        if n == 1:
            return v[0]
        k = (n - 1) * p / 100.0
        f = int(k)
        c = min(f + 1, n - 1)
        return int(round(v[f] + (v[c] - v[f]) * (k - f)))

    return {
        "n": n,
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "max": v[-1],
        "min": v[0],
        "moy": int(round(sum(v) / float(n))),
    }


def lire_stats(chemin):
    """Extrait le dictionnaire cle=valeur d'un journal de statistiques."""
    stats = {}
    for ligne in open(chemin, encoding="utf-8", errors="replace"):
        ligne = ligne.strip()
        if "=" not in ligne or ligne.startswith("#"):
            continue
        cle, _, val = ligne.partition("=")
        stats[cle.strip()] = val.strip()
    return stats


def journal_tri(dossier, prefixe):
    fichiers = sorted(glob.glob(os.path.join(dossier, prefixe + "-*.log")))
    return fichiers[0] if fichiers else None


def main():
    dossier = sys.argv[1] if len(sys.argv) > 1 else "preuve/qnx80"
    markdown = "--markdown" in sys.argv

    print(f"# Analyse des journaux — {dossier}\n")

    print("## Latences client→rm (aller-retour d'une écriture, µs)\n")
    print("| mesure | n | p50 | p95 | p99 | max | min | moyenne |")
    print("|---|---|---|---|---|---|---|---|")
    noms = []
    for p in glob.glob(dossier + "/*.log"):
        nom = os.path.basename(p)[:-4]
        nom = re.sub(r"-\d{8}T\d{6}Z$", "", nom)      # retire l'horodatage
        if re.match(r"^(h2|e2)-", nom) and "-stats" not in nom:
            noms.append(nom)
    for prefixe in sorted(set(noms)):
        f = journal_tri(dossier, prefixe)
        if not f:
            continue
        vals = [int(x) for x in RTT.findall(open(f, encoding="utf-8", errors="replace").read())]
        if not vals:
            continue
        p = percentiles(vals)
        print(f"| {prefixe} | {p['n']} | {p['p50']} | {p['p95']} | {p['p99']} | "
              f"{p['max']} | {p['min']} | {p['moy']} |")

    print("\n## Cadence du tick (E3)\n")
    for prefixe in ("e3-tick-repos", "e3-tick-charge"):
        f = journal_tri(dossier, prefixe)
        if not f:
            continue
        s = lire_stats(f)
        up = int(s.get("uptime_us", 0))
        ticks = int(s.get("ticks", 0))
        taux = (ticks * 1e6 / up) if up else 0
        n_int = max(ticks - 1, 1)
        print(f"- **{prefixe}** : {ticks} ticks en {up/1e6:.1f} s → {taux:.1f} Hz "
              f"(nominal 100 Hz) ; intervalle min {s.get('tick_min_us')} µs, "
              f"max {s.get('tick_max_us')} µs, moyenne {int(s.get('tick_sum_us',0))//n_int} µs ; "
              f"écart max à la période {s.get('tick_maxdev_us')} µs = "
              f"{s.get('tick_maxdev_ppm')} ppm ; ticks regroupés (> 2 périodes) : "
              f"{s.get('tick_coalesced')} ; latence de chaîne (tick→verdict) max "
              f"{s.get('lat_tick_max_us')} µs")
    f = journal_tri(dossier, "e3-sonde-independante")
    if f:
        for ligne in open(f, encoding="utf-8", errors="replace"):
            if ligne.startswith("tick_probe"):
                print(f"- **sonde indépendante** (canal dédié, sans rm) : {ligne.strip()}")

    print("\n## Héritage de priorité (E2) — priorités vues par le rm\n")
    print("| essai | base | effectif(s) observée(s) | drop | après drop |")
    print("|---|---|---|---|---|")
    for f in sorted(glob.glob(os.path.join(dossier, "e2-*-stats-*.log"))):
        s = lire_stats(f)
        brut = [int(x) for x in (s.get("prio_hist") or "0").split(",")] if s.get("prio_hist") else []
        hist = {i: v for i, v in enumerate(brut) if v}
        nom = os.path.basename(f).split("-stats-")[0]
        vus = ", ".join(f"{k}×{v}" for k, v in sorted(hist.items()))
        print(f"| {nom} | {s.get('prio_base')} | {vus} | {s.get('prio_dropped')} | "
              f"{s.get('prio_after_drop')} |")


if __name__ == "__main__":
    main()
