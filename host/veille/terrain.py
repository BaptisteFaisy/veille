"""Score de détection des pics R contre la vérité terrain MIT-BIH (.atr).

Ce module compare les **pics R détectés** (détecteur à seuil glissant de
:mod:`veille.resmgr_client`, heuristique et non clinique) aux **battements
annotés** de la base MIT-BIH (fichier ``.atr`` au format WFDB, lu par
:func:`veille.wfdb.lire_annotations`), puis produit les métriques attendues
par un jury médical.

Trois mesures, toutes documentées :

1. **Détection battement par battement** (convention ANSI/AAMI EC57, fenêtre
   d'appariement ±150 ms) : sensibilité ``VP/(VP+FN)``, valeur prédictive
   positive ``VP/(VP+FP)``, comptes bruts VP/FP/FN ;
2. **Matrice de confusion 2×2 sur grille** (pas de 100 ms) : une case est
   « positive » de référence si elle contient un battement annoté, « négative »
   sinon ; le détecteur y est positif s'il y a un pic. C'est le seul cadre
   qui fournit un dénominateur de **vrais négatifs** ;
3. **Score d'alarme** : sur les enregistrements tachyarythmiques (205 = tachy-
   cardie ventriculaire, 222 = fibrillation atriale), le seuil de 120 bpm
   déclenche-t-il l'alarme pendant les épisodes annotés comme rapides, et
   seulement là ?

**Alignement temporel** : le détecteur vise l'énergie du complexe QRS, pas le
sommet R : ses pics ont un **déchage constant** de l'ordre de 140 ms par
rapport aux annotations. La pratique EC38 (bxb, option ``-f``) reserve les
5 premières minutes à une période d'**apprentissage** qui sert à aligner le
flux de l'algorithme sur la référence avant toute comparaison. Le module
applique donc cet alignement (décalage médian calculé sur les 5 premières
minutes) et publie **les deux mesures** : brute (sans alignement) et alignée.
La différence entre les deux chiffre exactement le défaut de calage temporel.

CLI :
    python3 -m veille.terrain --record data/records/mitdb/205 --signal MLII
    python3 -m veille.terrain --record ... --signal MLII --json
    python3 -m veille.terrain --batch data/records/mitdb   # les 48 records

Limites : le détecteur de pics R est simple et **non clinique** ; aucune
validation clinique n'est revendiquée. Voir ``docs/TERRAIN.md``.
"""
import argparse
import json
import os
import statistics
import sys

from . import wfdb
from .resmgr_client import bpm_intervalles, detecter_pics_r

TOLERANCE_S = 0.150     # fenêtre d'appariement détection ↔ battement (EC57)
GRILLE_S = 0.100        # pas de la grille de confusion (100 ms)
SEUIL_ALARME_BPM = 120  # seuil d'alarme de tachycardie (CONTRAT.md)
APPRENTISSAGE_S = 300.0  # période d'apprentissage EC38 (5 premières minutes)

# Arythmies rapides (vérité terrain) qui exigent une alarme à ≥ 120 bpm.
RHYTHMES_TACHY = frozenset(("VT", "VFL", "SVTA", "AFIB", "AFL"))


class Score:
    """Résultat du score d'un enregistrement (détection + alarme)."""

    __slots__ = ("record", "signal", "fs", "n_echantillons", "pics",
                 "battements", "decalage_ms", "brut", "aligne", "grille",
                 "bpm_min", "bpm_max", "bpm_moyen", "episodes", "alarme")

    def __init__(self, **kw):
        for nom in self.__slots__:
            setattr(self, nom, kw.get(nom))

    def sensibilite(self):
        """Sensibilité alignée : VP / (VP + FN), convention EC57."""
        m = self.aligne or {}
        total = m.get("vp", 0) + m.get("fn", 0)
        return (m.get("vp", 0) / total) if total else 0.0

    def vpp(self):
        """Valeur prédictive positive alignée : VP / (VP + FP)."""
        m = self.aligne or {}
        total = m.get("vp", 0) + m.get("fp", 0)
        return (m.get("vp", 0) / total) if total else 0.0

    def specificite(self):
        """Spécificité : VN / (VN + FP) sur la grille de confusion."""
        g = self.grille or {}
        total = g.get("vn", 0) + g.get("fp", 0)
        return (g.get("vn", 0) / total) if total else 0.0

    def matrice_battements(self):
        """Matrice de confusion battement par battement (VP/FP/FN)."""
        return dict(self.aligne or {})

    def matrice_grille(self):
        """Matrice de confusion 2×2 sur la grille de 100 ms."""
        return dict(self.grille or {})

    def to_dict(self):
        """Représentation sérialisable (JSON)."""
        return {"record": self.record, "signal": self.signal, "fs": self.fs,
                "echantillons": self.n_echantillons,
                "pics_detectes": self.pics,
                "battements_annotes": self.battements,
                "decalage_ms": self.decalage_ms,
                "brut": self.brut, "aligne": self.aligne,
                "sensibilite": self.sensibilite(), "vpp": self.vpp(),
                "specificite": self.specificite(),
                "matrice_battements": self.matrice_battements(),
                "matrice_grille": self.matrice_grille(),
                "bpm_min": self.bpm_min, "bpm_max": self.bpm_max,
                "bpm_moyen": self.bpm_moyen,
                "episodes": self.episodes, "alarme": self.alarme}


def apparier(pics, battements, fs, tolerance_s=TOLERANCE_S):
    """Apparie les pics détectés aux battements annotés (fenêtre glissante).

    Retourne ``{"vp":…, "fp":…, "fn":…}``. Deux curseurs glissent sur les
    deux listes triées : un battement annoté est « détecté » si un pic tombe
    dans la fenêtre de tolérance (par défaut ±150 ms, convention EC57) ; tout
    pic hors fenêtre est un faux positif, tout battement sans pic un faux
    négatif. Un battement ne reçoit jamais qu'un seul pic.
    """
    tolerance = int(round(tolerance_s * fs))
    vp = 0
    j = 0
    n_battements = len(battements)
    for pic in pics:
        while j < n_battements and battements[j] < pic - tolerance:
            j += 1
        if j < n_battements and abs(battements[j] - pic) <= tolerance:
            vp += 1
            j += 1
    return {"vp": vp, "fp": len(pics) - vp, "fn": n_battements - vp}


def decalage_median(pics, battements, fs, debut_s=0.0, fin_s=None):
    """Décalage médian (en échantillons) des pics par rapport aux battements.

    Pour chaque pic, on cherche le battement annoté le plus proche ; le
    décalage est la médiane de ces écarts (positif = pics en retard). Sert à
    l'alignement temporel de la période d'apprentissage EC38.
    """
    if not pics or not battements:
        return 0
    lo = int(debut_s * fs)
    hi = int(fin_s * fs) if fin_s is not None else None
    ecarts = []
    j = 0
    for pic in pics:
        if pic < lo or (hi is not None and pic > hi):
            continue
        while j < len(battements) and battements[j] < pic:
            j += 1
        candidats = []
        if j < len(battements):
            candidats.append(battements[j] - pic)
        if j > 0:
            candidats.append(battements[j - 1] - pic)
        if candidats:
            ecarts.append(min(candidats, key=abs))
    return int(statistics.median(ecarts)) if ecarts else 0


def grille_confusion(pics, battements, fs, n_echantillons, pas_s=GRILLE_S):
    """Matrice de confusion 2×2 sur une grille temporelle de pas ``pas_s``.

    Une case est « positive » de référence si elle contient au moins un
    battement annoté, « négative » sinon ; le détecteur y est positif s'il y
    a au moins un pic. C'est la seule façon d'obtenir un dénominateur de vrais
    négatifs (cellules sans battement) pour la spécificité.
    """
    pas = max(1, int(round(pas_s * fs)))
    n_cases = n_echantillons // pas + 1
    ref = set()
    det = set()
    for b in battements:
        ref.add(b // pas)
    for p in pics:
        det.add(p // pas)
    vp = len(ref & det)
    fp = len(det - ref)
    fn = len(ref - det)
    return {"vp": vp, "fp": fp, "fn": fn, "vn": n_cases - vp - fp - fn,
            "pas_ms": int(round(pas_s * 1000)), "n_cases": n_cases}


def normaliser_rythme(aux):
    """Nom de rythme normalisé : ``"(VT\\x00"`` → ``"VT"``.

    Les annotations RHYTHM portent dans ``aux`` le nom du rythme précédé de
    ``(`` et suivi d'un octet nul de padding (``(N``, ``(VT``, ``(AFIB``…).
    """
    nom = (aux or "").strip("\x00").strip()
    if nom.startswith("("):
        nom = nom[1:]
    return nom.strip()


def extraire_episodes(annotations, fs):
    """Épisodes de rythme délimités par les annotations RHYTHM (code 28).

    Chaque annotation RHYTHM porte dans ``aux`` le nom du rythme ; l'épisode
    court jusqu'à l'annotation de rythme suivante. Retourne une liste de dicts
    ``{debut_s, fin_s, nom, tachy}`` (le dernier épisode est borné par la
    dernière annotation, faute de marqueur de fin explicite).
    """
    moments = [(a.temps, normaliser_rythme(a.aux)) for a in annotations
               if a.code == wfdb.CODE_RHYTHM]
    if not moments:
        return []
    derniere = max((a.temps for a in annotations), default=0)
    episodes = []
    for i, (debut, nom) in enumerate(moments):
        fin = moments[i + 1][0] if i + 1 < len(moments) else derniere
        episodes.append({"debut_s": debut / fs, "fin_s": fin / fs,
                         "nom": nom, "tachy": nom in RHYTHMES_TACHY})
    return episodes


def score_alarme(episodes, bpm_serie, fs, seuil=SEUIL_ALARME_BPM):
    """Croise les épisodes de rythme annotés avec la série bpm de la chaîne.

    Pour chaque épisode : bpm maximal publié par la chaîne, franchissement du
    seuil d'alarme, nombre de battements détectés, et **délai de déclenchement**
    (secondes entre le début de l'épisode annoté et le premier battement publié
    au-dessus du seuil — c'est la question « l'alarme sonne-t-elle au bon
    moment ? »). ``bpm_serie`` est la liste ``[(index_echantillon, bpm)]`` de
    :func:`bpm_intervalles`.
    """
    resultats = []
    for ep in episodes:
        dans = [(idx, bpm) for idx, bpm in bpm_serie
                if ep["debut_s"] * fs <= idx < ep["fin_s"] * fs]
        vals = [bpm for _idx, bpm in dans]
        item = dict(ep)
        item["bpm_max"] = max(vals) if vals else 0
        item["bpm_moyen"] = (sum(vals) / len(vals)) if vals else 0.0
        item["franchit_seuil"] = any(v >= seuil for v in vals)
        item["n_battements"] = len(vals)
        item["delai_alarme_s"] = _delai_alarme(dans, ep["debut_s"], fs, seuil)
        resultats.append(item)
    return resultats


def _delai_alarme(battements, debut_s, fs, seuil):
    """Secondes entre le début de l'épisode et le premier bpm ≥ seuil.

    ``None`` si le seuil n'est jamais franchi pendant l'épisode.
    """
    for idx, bpm in battements:
        if bpm >= seuil:
            return round(idx / fs - debut_s, 3)
    return None


def choisir_signal(entete, nom):
    """Choisit le signal ECG à analyser.

    ``nom`` valant ``"auto"`` (défaut), on prend ``MLII`` s'il existe, sinon
    le premier signal de l'enregistrement : dans MIT-BIH, le canal supérieur
    est le lead II modifié (MLII) sauf pour les records 102, 104 et 114 où il
    s'agit de V5. Un nom explicite absent de l'enregistrement lève une
    :class:`KeyError` (erreur franche, pas de repli silencieux).
    """
    if nom and nom.lower() != "auto":
        signal = entete.signal(nom)
        if signal is None:
            raise KeyError("signal %r absent de %s (disponibles : %s)"
                           % (nom, entete.nom, ", ".join(entete.noms())))
        return signal
    signal = entete.signal("MLII") or entete.signaux[0]
    return signal


def scorer_enregistrement(chemin, nom_signal):
    """Score complet d'un enregistrement (détection + rythme + alarme).

    Retourne un :class:`Score`. Réutilise :mod:`veille.wfdb` pour lire le
    signal et les annotations, et :mod:`veille.resmgr_client` pour la détection
    des pics R — aucune logique de détection n'est réécrite ici.
    """
    entete = wfdb.lire_en_tete(chemin)
    signal = choisir_signal(entete, nom_signal)
    bruts = wfdb.lire_bruts(entete, signal.nom)
    physiques = [signal.physique(v) for v in bruts]
    fs = entete.fs
    pics = detecter_pics_r(physiques, fs)
    annotations = wfdb.lire_annotations(chemin)
    battements = [a.temps for a in annotations if a.est_battement()]
    brut = apparier(pics, battements, fs)
    decalage = decalage_median(pics, battements, fs, 0.0, APPRENTISSAGE_S)
    pics_alignes = [p + decalage for p in pics]
    aligne = apparier(pics_alignes, battements, fs)
    grille = grille_confusion(pics_alignes, battements, fs, len(bruts))
    serie_bpm = bpm_intervalles(pics, fs)
    valeurs = [b for _i, b in serie_bpm]
    episodes = score_alarme(extraire_episodes(annotations, fs), serie_bpm, fs)
    return Score(record=entete.nom, signal=signal.nom, fs=fs,
                 n_echantillons=len(bruts), pics=len(pics),
                 battements=len(battements),
                 decalage_ms=round(decalage * 1000.0 / fs, 1),
                 brut=brut, aligne=aligne, grille=grille,
                 bpm_min=min(valeurs) if valeurs else 0.0,
                 bpm_max=max(valeurs) if valeurs else 0.0,
                 bpm_moyen=(sum(valeurs) / len(valeurs)) if valeurs else 0.0,
                 episodes=episodes, alarme=synthese_alarme(episodes))


def synthese_alarme(episodes):
    """Synthèse du score d'alarme : épisodes tachy vus / manqués, fausses alarmes."""
    vus = sum(1 for e in episodes if e["tachy"] and e["franchit_seuil"])
    manques = sum(1 for e in episodes if e["tachy"] and not e["franchit_seuil"])
    fausses = sum(1 for e in episodes if not e["tachy"] and e["franchit_seuil"])
    norms = sum(1 for e in episodes if not e["tachy"])
    return {"episodes_tachy": vus + manques, "episodes_tachy_vus": vus,
            "episodes_tachy_manques": manques,
            "episodes_normaux": norms, "fausses_alarmes": fausses}


def ligne_texte(score):
    """Une ligne de synthèse lisible pour un enregistrement."""
    return ("%-6s %-5s se=%6.2f%%  vpp=%6.2f%%  sp=%6.2f%%  VP=%4d FP=%3d "
            "FN=%3d  bpm[%3.0f-%3.0f]  decalage=%+6.1f ms"
            % (score.record, score.signal, 100 * score.sensibilite(),
               100 * score.vpp(), 100 * score.specificite(),
               score.aligne["vp"], score.aligne["fp"], score.aligne["fn"],
               score.bpm_min, score.bpm_max, score.decalage_ms))


def texte_alarme(score):
    """Rendu texte du score d'alarme (épisodes tachy vs seuil 120 bpm)."""
    synth = score.alarme or {}
    lignes = ["  alarme : %d/%d épisodes tachy vus, %d manqués, %d fausses "
              "alarmes sur %d épisodes non-tachy"
              % (synth.get("episodes_tachy_vus", 0),
                 synth.get("episodes_tachy", 0),
                 synth.get("episodes_tachy_manques", 0),
                 synth.get("fausses_alarmes", 0),
                 synth.get("episodes_normaux", 0))]
    for ep in score.episodes:
        if ep["tachy"] or ep["franchit_seuil"]:
            delai = ep.get("delai_alarme_s")
            lignes.append("    [%8.3f → %8.3f s] %-6s tachy=%-3s bpm_max=%3d "
                          "seuil120=%-7s délai=%s"
                          % (ep["debut_s"], ep["fin_s"], ep["nom"],
                             "oui" if ep["tachy"] else "non", ep["bpm_max"],
                             "FRANCHI" if ep["franchit_seuil"] else "non",
                             ("%.3f s" % delai) if delai is not None else "—"))
    return "\n".join(lignes)


def rapport_texte(score, verbose_alarme=False):
    """Rapport texte complet (métriques + matrices + score d'alarme)."""
    lignes = [ligne_texte(score)]
    g = score.matrice_grille()
    lignes.append("  grille %d ms : VP=%d FP=%d FN=%d VN=%d (%d cases)"
                  % (g.get("pas_ms", 100), g.get("vp", 0), g.get("fp", 0),
                     g.get("fn", 0), g.get("vn", 0), g.get("n_cases", 0)))
    lignes.append("  sans alignement : VP=%d FP=%d FN=%d (décalage médian "
                  "%+.1f ms — défaut de calage temporel du détecteur)"
                  % (score.brut["vp"], score.brut["fp"], score.brut["fn"],
                     score.decalage_ms))
    if verbose_alarme:
        lignes.append(texte_alarme(score))
    return "\n".join(lignes) + "\n"


def _parser():
    """Constructeur d'arguments de la CLI terrain."""
    p = argparse.ArgumentParser(
        prog="veille.terrain",
        description="Score de détection des pics R contre la vérité terrain MIT-BIH")
    p.add_argument("--record",
                   help="enregistrement sans extension (ex. data/records/mitdb/205)")
    p.add_argument("--signal", default="auto",
                   help="nom du signal ECG (défaut : auto = MLII ou 1er signal)")
    p.add_argument("--batch", metavar="REPERTOIRE",
                   help="répertoire MIT-BIH : score sur tous les enregistrements")
    p.add_argument("--alarme", action="store_true",
                   help="détailler les épisodes de rythme et le score d'alarme")
    p.add_argument("--json", action="store_true", help="sortie JSON")
    return p


def _liste_enregistrements(repertoire):
    """Chemins d'enregistrements (sans extension) triés d'un répertoire."""
    return [os.path.join(repertoire, f[:-4])
            for f in sorted(os.listdir(repertoire)) if f.endswith(".hea")]


def _resume(scores):
    """Résumé global d'une liste de scores (moyennes et totaux)."""
    n = len(scores)
    if not n:
        return {}
    se = sum(s.sensibilite() for s in scores) / n
    vpp = sum(s.vpp() for s in scores) / n
    sp = sum(s.specificite() for s in scores) / n
    vp = sum(s.aligne["vp"] for s in scores)
    fp = sum(s.aligne["fp"] for s in scores)
    fn = sum(s.aligne["fn"] for s in scores)
    return {"enregistrements": n,
            "sensibilite_moyenne": se, "vpp_moyenne": vpp,
            "specificite_moyenne": sp,
            "vp_total": vp, "fp_total": fp, "fn_total": fn,
            "sensibilite_globale": vp / (vp + fn) if (vp + fn) else 0.0,
            "vpp_globale": vp / (vp + fp) if (vp + fp) else 0.0,
            "bpm_min_global": min(s.bpm_min for s in scores),
            "bpm_max_global": max(s.bpm_max for s in scores)}


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.batch:
        scores = [scorer_enregistrement(ch, args.signal)
                  for ch in _liste_enregistrements(args.batch)]
        if args.json:
            sys.stdout.write(json.dumps(
                {"enregistrements": [s.to_dict() for s in scores],
                 "resume": _resume(scores)}, ensure_ascii=False, indent=1) + "\n")
            return 0
        for s in scores:
            sys.stdout.write(rapport_texte(s, args.alarme))
        r = _resume(scores)
        sys.stdout.write("\nRésumé (%d enregistrements) : sensibilité moyenne "
                         "%.2f%%, VPP %.2f%%, spécificité %.2f%%\n"
                         % (r["enregistrements"], 100 * r["sensibilite_moyenne"],
                            100 * r["vpp_moyenne"], 100 * r["specificite_moyenne"]))
        return 0
    if not args.record:
        _parser().print_help()
        return 2
    score = scorer_enregistrement(args.record, args.signal)
    if args.json:
        sys.stdout.write(json.dumps(score.to_dict(), ensure_ascii=False, indent=1) + "\n")
    else:
        sys.stdout.write(rapport_texte(score, args.alarme))
    return 0


if __name__ == "__main__":
    sys.exit(main())
