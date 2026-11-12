"""Client du resource manager Veille — alimente ``/dev/veille`` depuis un ECG RÉEL.

Ce module fait le lien entre un enregistrement physiologique mesuré
(PhysioNet) et le resource manager QNX ``/dev/veille`` :

1. **Détection des pics R** sur l'ECG réel par un algorithme *seuil glissant*
   inspiré de Pan-Tompkins, écrit ici sans aucune bibliothèque :
   dérivée → carrure → intégration par moyenne glissante (~150 ms) →
   seuil adaptatif ``NPK + 0.25·(SPK − NPK)`` → période réfractaire 200 ms ;
   l'index du pic est affiné par le maximum de déflection du signal brut.
2. **Bpm instantané** à partir des intervalles R-R : ``bpm = 60 / RR``,
   RR médian sur les ``--lissage`` derniers intervalles plausibles
   (30–200 bpm), donc robuste à une contraction isolée.
3. **Écriture** d'une ligne ``bpm <valeur>\\n`` par battement dans la
   destination : ``/dev/veille`` sur cible QNX (resource manager), un simple
   fichier sur l'hôte (test). Rien d'autre n'est écrit.

La cadence est celle de l'enregistrement (360/250/125 Hz) : les échantillons
sont consommés dans l'ordre, sans rééchantillonnage. ``--temps-reel`` ajoute
une temporisation pour respecter l'horloge murale (utile sur cible, inutile
en test).

Détection de pics R **simple et non clinique** — voir ``docs/REAL-DATA.md``,
section « limites ».
"""
import argparse
import os
import statistics
import sys
import time

from . import wfdb

CHEMIN_DEFAUT = "/dev/veille"
FENETRE_INTEGRATION_S = 0.15    # fenêtre d'intégration de l'énergie QRS
REFRAC_S = 0.20                 # période réfractaire (200 ms)
RATIO_SEUIL = 0.25              # seuil = NPK + RATIO_SEUIL·(SPK − NPK)
BPM_MIN = 30.0
BPM_MAX = 200.0
LISSAGE_DEFAUT = 3              # nombre d'intervalles R-R médianisés


def _moyenne_glissante(valeurs, taille):
    """Moyenne glissante sur ``taille`` échantillons (O(n), une passe)."""
    if taille <= 1 or not valeurs:
        return list(valeurs)
    total = float(sum(valeurs[:taille]))
    sortie = [total / taille]
    for i in range(taille, len(valeurs)):
        total += valeurs[i] - valeurs[i - taille]
        sortie.append(total / taille)
    return sortie


def _energie_qrs(physiques):
    """Dérivée puis carrure : énergie des complexes QRS (onsets dominants)."""
    derivee = [0.0]
    for i in range(1, len(physiques)):
        derivee.append(physiques[i] - physiques[i - 1])
    return [v * v for v in derivee]


def _affiner_pic(physiques, index, fs):
    """Affine l'index du pic : maximum de déflection du signal brut proche."""
    fenetre = max(1, int(round(FENETRE_INTEGRATION_S * fs)))
    debut = max(0, index - fenetre)
    fin = min(len(physiques), index + fenetre // 2 + 1)
    segment = physiques[debut:fin]
    if not segment:
        return index
    base = statistics.median(segment)
    meilleur = max(range(len(segment)), key=lambda k: abs(segment[k] - base))
    return debut + meilleur


def detecter_pics_r(physiques, fs):
    """Détecte les pics R d'un ECG réel. Retourne la liste des index.

    Algorithme (seuil glissant, sans bibliothèque) :
    - énergie = moyenne glissante de la carrure de la dérivée (fenêtre 150 ms) ;
    - pics d'énergie : maxima locaux au-dessus d'un seuil adaptatif
      ``NPK + 0.25·(SPK − NPK)``, où SPK/NPK suivent le signal et le bruit ;
    - période réfractaire de 200 ms (un seul pic par battement) ;
    - index affiné sur le maximum de déflection du signal brut.
    """
    energie = _moyenne_glissante(_energie_qrs(physiques),
                                 max(1, int(round(FENETRE_INTEGRATION_S * fs))))
    if len(energie) < 3:
        return []
    init = energie[:max(1, int(2 * fs))]
    spk = max(init) or 1e-12
    npk = (sum(init) / len(init)) or 1e-12
    seuil = npk + RATIO_SEUIL * (spk - npk)
    refr = max(1, int(round(REFRAC_S * fs)))
    pics, dernier = [], -refr
    for j in range(1, len(energie) - 1):
        v = energie[j]
        if v < seuil:
            npk = 0.125 * v + 0.875 * npk
            seuil = npk + RATIO_SEUIL * (spk - npk)
            continue
        if v < energie[j - 1] or v < energie[j + 1]:
            continue
        if j - dernier < refr:
            continue
        spk = 0.25 * v + 0.75 * spk
        npk = 0.125 * v + 0.875 * npk
        seuil = npk + RATIO_SEUIL * (spk - npk)
        pics.append(_affiner_pic(physiques, j, fs))
        dernier = j
    return pics


def bpm_intervalles(pics, fs, lissage=LISSAGE_DEFAUT):
    """Bpm instantané à chaque pic R, déduit des intervalles R-R.

    Retourne la liste ``[(index_echantillon, bpm), …]``. Les intervalles
    implausibles (< 30 bpm ou > 200 bpm) sont ignorés ; le bpm publié est
    ``60 / RR`` où RR est la médiane des ``lissage`` derniers intervalles
    retenus (robuste à une contraction isolée).
    """
    resultats = []
    intervalles = []
    for i in range(1, len(pics)):
        rr = (pics[i] - pics[i - 1]) / fs
        if not (60.0 / BPM_MAX <= rr <= 60.0 / BPM_MIN):
            continue
        intervalles.append(rr)
        mediane = statistics.median(intervalles[-max(1, lissage):])
        resultats.append((pics[i], 60.0 / mediane))
    return resultats


def _ouvrir_sortie(chemin):
    """Ouvre la destination en écriture (fichier tronqué, périphérique QNX intact)."""
    if os.path.isfile(chemin):
        os.truncate(chemin, 0)
    descripteur = os.open(chemin, os.O_WRONLY | os.O_CREAT, 0o644)
    return os.fdopen(descripteur, "w", encoding="utf-8")


def ecrire_bpm(chemin, battements, fs=None, temps_reel=False):
    """Écrit une ligne ``bpm <valeur>\\n`` par battement dans ``chemin``.

    ``temps_reel`` + ``fs`` : la temporisation entre deux lignes suit la
    cadence réelle du cœur (intervalle R-R mesuré). Retourne le nombre de
    lignes écrites.
    """
    ecrites = 0
    precedent = None
    with _ouvrir_sortie(chemin) as sortie:
        for index, bpm in battements:
            if temps_reel and fs and precedent is not None and index > precedent:
                time.sleep((index - precedent) / fs)
            sortie.write("bpm %d\n" % round(bpm))
            precedent = index
            ecrites += 1
    return ecrites


def alimenter(chemin_record, nom_signal, chemin_sortie=CHEMIN_DEFAUT,
              limite=None, lissage=LISSAGE_DEFAUT, temps_reel=False):
    """Alimente la destination (resource manager QNX ou fichier) depuis un ECG réel.

    Retourne un dict de synthèse : ``pics`` (nb de pics R), ``battements``
    (nb de lignes écrites), ``bpm_min``, ``bpm_max``, ``bpm_moyen``.
    """
    entete = wfdb.lire_en_tete(chemin_record)
    signal = entete.signal(nom_signal)
    if signal is None:
        raise KeyError("signal %r absent de %s (disponibles : %s)"
                       % (nom_signal, entete.nom, ", ".join(entete.noms())))
    bruts = wfdb.lire_bruts(entete, nom_signal, limite)
    physiques = [signal.physique(v) for v in bruts]
    pics = detecter_pics_r(physiques, entete.fs)
    battements = bpm_intervalles(pics, entete.fs, lissage)
    ecrites = ecrire_bpm(chemin_sortie, battements, entete.fs, temps_reel)
    valeurs = [b for _i, b in battements]
    return {"pics": len(pics), "battements": ecrites,
            "bpm_min": min(valeurs) if valeurs else 0.0,
            "bpm_max": max(valeurs) if valeurs else 0.0,
            "bpm_moyen": (sum(valeurs) / len(valeurs)) if valeurs else 0.0}


def _parser():
    """Constructeur d'arguments du client resource manager."""
    p = argparse.ArgumentParser(
        prog="veille.resmgr_client",
        description="Alimente /dev/veille (ou un fichier) à partir d'un ECG réel")
    p.add_argument("--record", required=True,
                   help="enregistrement sans extension (ex. data/records/mitdb/100)")
    p.add_argument("--signal", required=True, help="nom du signal ECG (ex. MLII)")
    p.add_argument("--sortie", default=CHEMIN_DEFAUT,
                   help="destination des lignes bpm (défaut : %s)" % CHEMIN_DEFAUT)
    p.add_argument("--limite", type=int, default=None,
                   help="nombre maximal d'échantillons consommés")
    p.add_argument("--lissage", type=int, default=LISSAGE_DEFAUT,
                   help="nombre d'intervalles R-R médianisés (défaut : %d)" % LISSAGE_DEFAUT)
    p.add_argument("--temps-reel", action="store_true",
                   help="respecter l'horloge murale entre deux écritures")
    return p


def main(argv=None):
    args = _parser().parse_args(argv)
    synthese = alimenter(args.record, args.signal, args.sortie, args.limite,
                         args.lissage, args.temps_reel)
    sys.stdout.write(
        "%s : %d pic(s) R, %d ligne(s) « bpm » écrites vers %s — "
        "bpm min %.1f, moyen %.1f, max %.1f\n"
        % (args.record, synthese["pics"], synthese["battements"], args.sortie,
           synthese["bpm_min"], synthese["bpm_moyen"], synthese["bpm_max"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
