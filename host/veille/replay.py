"""Rejeu d'un enregistrement PHYSIOLOGIQUE RÉEL dans la chaîne Veille.

Le signal réel (MIT-BIH, BIDMC, Sleep-EDF) est lu par :mod:`veille.wfdb`,
puis traversé par la chaîne **existante** — jamais réimplémentée ici :

``sample → acquire → filter → decide → alarm → acknowledge``

- la cadence est celle du terrain (360 / 250 / 125 Hz) : chaque fenêtre
  d'analyse porte l'horodatage réel ``t = i / fs`` ;
- l'étage *decide* diagnostique l'état du capteur sur les valeurs réelles
  (bloqué / mort / bruité / dérive) en réutilisant les états de
  :mod:`veille.state` ;
- l'étage *alarm* mesure la latence pire-cas de la chaîne dans cet état via
  :meth:`veille.state.FaultState.worst_latency_ms` et la compare à la borne
  IEC 60601-1-8 de la priorité (100 / 500 / 1000 ms) ;
- les verdicts sont rendus par :mod:`veille.report` (texte, JSON, Markdown).

CLI :
    python3 -m veille.replay --record data/records/mitdb/100 --signal MLII \\
        [--format texte|json|markdown] [--limite N]

Le diagnostic capteur est **heuristique et non clinique** (voir
``docs/REAL-DATA.md``, section « limites »).
"""
import argparse
import os
import statistics
import sys
import time

from . import wfdb
from .chain import Priority, Stage, stage_name
from .cli import build_config
from .report import exit_code, report_json, report_markdown, report_text
from .state import SENSOR_NAMES, FaultState, SensorState
from .verdict import Severity, Verdict, VerdictCode

# Bornes d'alarme IEC 60601-1-8 (CONTRAT.md §3) par priorité.
BORNES = {Priority.HIGH: 100, Priority.MEDIUM: 500, Priority.LOW: 1000}
PRIORITES = {"haute": Priority.HIGH, "moyenne": Priority.MEDIUM, "basse": Priority.LOW}
FENETRE_S = 1.0            # durée d'une fenêtre d'analyse (fenêtre = 1 s)
EPS_REL = 1e-6            # tolérance relative pour « signal constant »
RATIO_BRUIT = 0.08        # pas médian > 8 % de l'amplitude robuste → bruité
DRIFT_MAD = 4.0           # dérive > 4 MAD entre les deux moitiés de fenêtre

# Rails des codeurs : format 212 → 12 bits signés, format 16 → int16.
RAILS = {wfdb.FORMAT_212: (-2048, 2047), wfdb.FORMAT_16: (-32768, 32767)}


def _mad(valeurs, median=None):
    """Déviation absolue médiane (échelle robuste du bruit)."""
    if median is None:
        median = statistics.median(valeurs)
    return statistics.median([abs(v - median) for v in valeurs])


def _est_constant(valeurs):
    """Vrai si toutes les valeurs de la fenêtre sont identiques (capteur bloqué)."""
    mini, maxi = min(valeurs), max(valeurs)
    return (maxi - mini) <= EPS_REL * max(1.0, abs(maxi))


def _sur_rail(brut, rails):
    """Vrai si la valeur brute est collée au butée du codeur."""
    bas, haut = rails
    return brut <= bas + 1 or brut >= haut - 1


def diagnostiquer(signal, bruts, physiques):
    """Diagnostique l'état du capteur sur une fenêtre réelle.

    Règles (simples, documentées, **non cliniques**) :
    - fenêtre constante + valeur collée au rail du codeur → capteur **mort** ;
    - fenêtre constante ailleurs → capteur **bloqué** ;
    - pas médian (variation rapide) > 8 % de l'amplitude robuste (p95−p05)
      → capteur **bruité** ;
    - médiane de la 2ᵉ moitié décalée de plus de 4 MAD → capteur **dérive** ;
    - sinon → capteur **sain**.

    Retourne un :class:`veille.state.SensorState`.
    """
    if len(bruts) < 2:
        return SensorState.OK
    if _est_constant(physiques):
        rails = RAILS.get(signal.format, (0, 0))
        return SensorState.DEAD if _sur_rail(bruts[0], rails) else SensorState.STUCK
    median = statistics.median(physiques)
    echelle = _mad(physiques, median)
    amplitude = _amplitude_robuste(physiques)
    if amplitude > 0:
        pas = sorted(abs(b - a) for a, b in zip(physiques, physiques[1:]))
        if pas[len(pas) // 2] > RATIO_BRUIT * amplitude:
            return SensorState.NOISY
        moitie = len(physiques) // 2
        derive = abs(statistics.median(physiques[moitie:])
                     - statistics.median(physiques[:moitie]))
        if echelle > 0 and derive > DRIFT_MAD * echelle:
            return SensorState.DRIFT
    return SensorState.OK


def _amplitude_robuste(valeurs):
    """Amplitude robuste p95 − p05 (insensible aux pics isolés)."""
    tri = sorted(valeurs)
    if len(tri) < 2:
        return 0.0
    return tri[int(0.95 * (len(tri) - 1))] - tri[int(0.05 * (len(tri) - 1))]


def _fenetres(bruts, physiques, taille):
    """Découpe un signal réel en fenêtres de ``taille`` échantillons."""
    for i0 in range(0, len(bruts), taille):
        yield i0, bruts[i0:i0 + taille], physiques[i0:i0 + taille]


def _verdict_etat(chain_id, etat, nb, premiere_s):
    """Verdict SENSOR_FAULT pour un état capteur fautif (agrégé par état)."""
    return Verdict(VerdictCode.SENSOR_FAULT, Severity.WARNING,
                   "capteur %s sur %d fenêtre(s), première à %.3f s"
                   % (SENSOR_NAMES[etat], nb, premiere_s),
                   chain_id=chain_id, stage=stage_name(Stage.DECIDE),
                   state=FaultState(sensor=etat).to_string())


def _verdict_latence(cfg, chain_id, latence, etat, t_s):
    """Verdict LATENCY_BOUND_EXCEEDED si la latence pire cas dépasse la borne."""
    return Verdict(VerdictCode.LATENCY_BOUND_EXCEEDED, Severity.ERROR,
                   "latence pire cas %d ms > borne %d ms (fenêtre à %.3f s)"
                   % (latence, cfg.bound_alarm_ms, t_s),
                   chain_id=chain_id, bound_ms=cfg.bound_alarm_ms,
                   latency_ms=latence, stage=stage_name(Stage.ALARM),
                   state=etat.to_string())


def rejouer(chemin, nom_signal, limite=None, priorite=Priority.HIGH,
            fenetre_s=FENETRE_S, preuve=False):
    """Rejoue un signal réel dans la chaîne. Retourne ``(verdicts, meta)``.

    ``limite`` borne le nombre d'échantillons lus (utile pour les tests et la
    cible QNX) ; ``preuve`` ajoute l'exploration exhaustive de l'espace de
    défaillance à la fin du rejeu.
    """
    entete = wfdb.lire_en_tete(chemin)
    signal = entete.signal(nom_signal)
    if signal is None:
        raise KeyError("signal %r absent de %s (disponibles : %s)"
                       % (nom_signal, entete.nom, ", ".join(entete.noms())))
    bruts = wfdb.lire_bruts(entete, nom_signal, limite)
    cfg = build_config(BORNES[priorite], priorite)
    chain_id = "%s_%s" % (entete.nom, signal.nom.replace(" ", "_"))
    physiques = [signal.physique(v) for v in bruts]
    taille = max(1, int(round(fenetre_s * entete.fs)))
    comptes = {}
    latence_max, pire, t_pire = 0, FaultState(), 0.0
    for i0, fen_b, fen_p in _fenetres(bruts, physiques, taille):
        etat = diagnostiquer(signal, fen_b, fen_p)
        compte = comptes.setdefault(etat, [0, i0 / entete.fs])
        compte[0] += 1
        courant = FaultState(sensor=etat)
        latence = courant.worst_latency_ms(cfg)
        if latence > latence_max:
            latence_max, pire, t_pire = latence, courant, i0 / entete.fs
    verdicts = []
    if latence_max > cfg.bound_alarm_ms:
        verdicts.append(_verdict_latence(cfg, chain_id, latence_max, pire, t_pire))
    else:
        verdicts.append(Verdict(VerdictCode.OK, Severity.INFO,
                                 "rejeu %s : %d fenêtre(s), latence pire cas %d ms "
                                 "(borne %d ms)"
                                 % (chain_id, sum(c[0] for c in comptes.values()),
                                    latence_max, cfg.bound_alarm_ms),
                                 chain_id=chain_id, latency_ms=latence_max))
    for etat, (nb, premiere_s) in sorted(comptes.items(), key=lambda kv: kv[0]):
        if etat != SensorState.OK:
            verdicts.append(_verdict_etat(chain_id, etat, nb, premiere_s))
    if preuve:
        from .proof import FaultMask, proof_explore
        _rc, verdicts_proof = proof_explore(cfg, FaultMask(True, True, True, True, True))
        verdicts.extend(verdicts_proof)
    meta = {"config_file": chemin,
            "config_sha256": wfdb.sha256_fichier(_fichier_donnees(entete, signal)),
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "veille_version": _version()}
    return verdicts, meta


def _fichier_donnees(entete, signal):
    return os.path.join(os.path.dirname(entete.chemin), signal.fichier)


def _version():
    from . import __version__
    return __version__


def _parser():
    """Constructeur d'arguments du rejeu."""
    p = argparse.ArgumentParser(
        prog="veille.replay",
        description="Rejoue un enregistrement physiologique réel dans la chaîne Veille")
    p.add_argument("--record", required=True,
                   help="enregistrement sans extension (ex. data/records/mitdb/100)")
    p.add_argument("--signal", required=True, help="nom du signal (ex. MLII)")
    p.add_argument("--format", choices=("texte", "json", "markdown"), default="texte",
                   help="format de sortie (défaut : texte)")
    p.add_argument("--limite", type=int, default=None,
                   help="nombre maximal d'échantillons rejoués")
    p.add_argument("--priorite", choices=sorted(PRIORITES), default="haute",
                   help="priorité IEC 60601-1-8 (borne 100/500/1000 ms)")
    p.add_argument("--fenetre", type=float, default=FENETRE_S,
                   help="durée de la fenêtre d'analyse en secondes (défaut : 1)")
    p.add_argument("--preuve", action="store_true",
                   help="ajoute l'exploration exhaustive de l'espace de défaillance")
    return p


def main(argv=None):
    args = _parser().parse_args(argv)
    verdicts, meta = rejouer(args.record, args.signal, args.limite,
                             PRIORITES[args.priorite], args.fenetre, args.preuve)
    if args.format == "json":
        sys.stdout.write(report_json(verdicts))
    elif args.format == "markdown":
        sys.stdout.write(report_markdown(verdicts, meta))
    else:
        sys.stdout.write(report_text(verdicts))
    return exit_code(verdicts)


if __name__ == "__main__":
    sys.exit(main())
