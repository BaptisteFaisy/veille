#!/usr/bin/env python3
"""Téléchargement poli et vérifié d'enregistrements PhysioNet réels pour Veille.

Sélection déterministe et petite (≤ 100 Mo au total) :
- mitdb 100 (rythme sinusal normal) et 105 (nombreux extrasystoles
  ventriculaires), avec leurs annotations .atr (vérité terrain) ;
- bidmc 01 et 02 (RESP/PLETH/V/AVR/II à 125 Hz) + CSV numériques
  (SpO2, fréquence respiratoire) et respirations annotées ;
- slpdb slp01a et slp02a (ECG/BP/EEG/RESP à 250 Hz).

Règles de politesse (PhysioNet limite le débit) :
- ≥ 2 s entre deux requêtes ;
- ≤ 3 tentatives par fichier, repli exponentiel (2 s, 4 s) ;
- jamais de re-téléchargement d'un fichier déjà présent ET vérifié
  (empreinte SHA-256 du SHA256SUMS.txt publié) : il est laissé intact ;
- tout est journalisé (stdout + data/records/fetch.log).

Licence des données : Open Data Commons Attribution License v1.0
(https://physionet.org/about/license/). Voir docs/REAL-DATA.md.

Usage : python3 data/fetch.py [--dest RÉP] [--db mitdb|bidmc|slpdb]
Stdlib uniquement, aucune dépendance.
"""
import argparse
import hashlib
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = "https://physionet.org/files"
POLITENESS_S = 2.0        # délai minimal entre deux requêtes
MAX_ATTEMPTS = 3          # tentatives par fichier
BACKOFF_S = 2.0           # base du repli exponentiel (2 s, 4 s)
TIMEOUT_S = 300           # délai maximal par requête
USER_AGENT = "veille-real-data/0.2 (polite research fetch; see docs/REAL-DATA.md)"

# Sélection figée : {jeu/version: [chemins relatifs au jeu]}.
# Le premier fichier de chaque jeu est son SHA256SUMS.txt publié.
SELECTION = {
    "mitdb/1.0.0": [
        "SHA256SUMS.txt",
        "100.hea", "100.dat", "100.atr",
        "105.hea", "105.dat", "105.atr",
    ],
    "bidmc/1.0.0": [
        "SHA256SUMS.txt",
        "bidmc01.hea", "bidmc01.dat",
        "bidmc02.hea", "bidmc02.dat",
        "bidmc_csv/bidmc_01_Numerics.csv", "bidmc_csv/bidmc_02_Numerics.csv",
        "bidmc_csv/bidmc_01_Breaths.csv", "bidmc_csv/bidmc_02_Breaths.csv",
    ],
    "slpdb/1.0.0": [
        "SHA256SUMS.txt",
        "slp01a.hea", "slp01a.dat",
        "slp02a.hea", "slp02a.dat",
    ],
}

_last_request_ts = 0.0    # horodatage du dernier départ de requête (politesses)

# Les 48 enregistrements de la base MIT-BIH (liste publiée dans RECORDS).
MITDB_COMPLET = ("100 101 102 103 104 105 106 107 108 109 111 112 113 114 115 "
                 "116 117 118 119 121 122 123 124 200 201 202 203 205 207 208 "
                 "209 210 212 213 214 215 217 219 220 221 222 223 228 230 231 "
                 "232 233 234").split()


def sha256_file(path):
    """Empreinte SHA-256 hexadécimale d'un fichier local, par blocs de 1 Mo."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


class Journal:
    """Journal horodaté : stdout + fichier fetch.log dans le dépôt de données."""

    def __init__(self, log_path):
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        self._f = open(log_path, "a", encoding="utf-8")

    def log(self, niveau, msg):
        ligne = "%s [%s] %s" % (time.strftime("%Y-%m-%dT%H:%M:%S%z"), niveau, msg)
        print(ligne, flush=True)
        self._f.write(ligne + "\n")
        self._f.flush()

    def close(self):
        self._f.close()


def _throttle(journal):
    """Garantit ≥ POLITENESS_S entre deux départs de requête."""
    global _last_request_ts
    attente = POLITENESS_S - (time.monotonic() - _last_request_ts)
    if attente > 0:
        time.sleep(attente)
    _last_request_ts = time.monotonic()


def _download_once(url, dest_part):
    """Une tentative de téléchargement atomique (fichier .part puis rename)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as rep:
        with open(dest_part, "wb") as f:
            while True:
                bloc = rep.read(1 << 20)
                if not bloc:
                    break
                f.write(bloc)


def polite_get(url, dest, journal):
    """Télécharge url vers dest ; ≤ MAX_ATTEMPTS tentatives, repli exponentiel.

    Retourne True si le fichier est en place, False en cas d'échec définitif
    (404, 502 persistant, réseau). N'écrase jamais un .part précédent : chaque
    tentative repart de zéro dans dest.part puis renomme atomiquement.
    """
    dest_part = dest + ".part"
    for tentative in range(1, MAX_ATTEMPTS + 1):
        try:
            _throttle(journal)
            _download_once(url, dest_part)
            os.replace(dest_part, dest)
            return True
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as e:
            code = getattr(e, "code", None)
            journal.log("WARN", "tentative %d/%d échouée pour %s : %s%s"
                        % (tentative, MAX_ATTEMPTS, url,
                           "HTTP %d " % code if code else "", e))
            if os.path.exists(dest_part):
                try:
                    os.remove(dest_part)
                except OSError:
                    pass
            if code == 404:            # absent du serveur : inutile d'insister
                return False
            if tentative < MAX_ATTEMPTS:
                time.sleep(BACKOFF_S * (2 ** (tentative - 1)))
    return False


def load_sha_map(path):
    """Lit un SHA256SUMS.txt publié → {chemin_relatif: empreinte_hex}."""
    table = {}
    with open(path, "r", encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.rstrip("\n")
            if not ligne.strip():
                continue
            parties = ligne.split()
            if len(parties) >= 2 and len(parties[0]) == 64:
                nom = parties[1].lstrip("*")
                table[nom] = parties[0]
    return table


def fetch_db(db, dest_root, journal):
    """Télécharge et vérifie la sélection d'un jeu. Retourne (ok, échecs).

    Cache : un fichier déjà présent dont l'empreinte correspond au
    SHA256SUMS.txt publié n'est JAMAIS re-téléchargé ni réécrit.
    """
    nom_db = db.split("/")[0]
    rep_db = os.path.join(dest_root, nom_db)
    url_base = "%s/%s" % (BASE_URL, db)
    os.makedirs(rep_db, exist_ok=True)
    journal.log("INFO", "jeu %s → %s" % (db, rep_db))
    echecs = []

    sha_local = os.path.join(rep_db, "SHA256SUMS.txt")
    if not os.path.exists(sha_local):
        if not polite_get(url_base + "/SHA256SUMS.txt", sha_local, journal):
            journal.log("ERROR", "SHA256SUMS.txt introuvable pour %s" % db)
            return False, [db + "/SHA256SUMS.txt"]
    sha_map = load_sha_map(sha_local)

    for rel in SELECTION[db]:
        if rel == "SHA256SUMS.txt":
            continue
        dest = os.path.join(rep_db, rel)
        attendu = sha_map.get(rel)
        if os.path.exists(dest):
            if attendu is None:
                journal.log("WARN", "%s présent mais absent du SHA256SUMS.txt" % rel)
                continue
            if sha256_file(dest) == attendu:
                journal.log("CACHE", "%s déjà présent et vérifié (%s)" % (rel, attendu[:16]))
                continue
            journal.log("WARN", "%s présent mais empreinte invalide : re-téléchargement" % rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if not polite_get("%s/%s" % (url_base, rel), dest, journal):
            journal.log("ERROR", "%s : téléchargement impossible (404/502 ?)" % rel)
            echecs.append(db + "/" + rel)
            continue
        if attendu is None:
            journal.log("WARN", "%s téléchargé mais sans empreinte publiée" % rel)
            continue
        obtenu = sha256_file(dest)
        if obtenu != attendu:
            journal.log("ERROR", "%s : SHA-256 invalide %s ≠ %s" % (rel, obtenu, attendu))
            os.remove(dest)
            echecs.append(db + "/" + rel)
        else:
            journal.log("OK", "%s téléchargé et vérifié (%s)" % (rel, obtenu[:16]))
    return not echecs, echecs


def fetch_mitdb_complet(dest_root, journal):
    """Télécharge les 48 enregistrements MIT-BIH (signal + vérité terrain .atr).

    Mêmes conventions que :func:`fetch_db` : cache (jamais de re-téléchargement
    d'un fichier déjà présent et vérifié), empreinte SHA-256 contrôlée contre
    le ``SHA256SUMS.txt`` publié, ≥ 2 s entre deux requêtes, journal horodaté.

    Retourne ``(nb_telecharges, echecs)`` : ``nb_telecharges`` ne compte que
    les fichiers réellement téléchargés (les fichiers déjà en cache ne sont
    pas re-téléchargés et ne sont pas comptés).
    """
    rep_db = os.path.join(dest_root, "mitdb")
    url_base = "%s/mitdb/1.0.0" % BASE_URL
    os.makedirs(rep_db, exist_ok=True)
    journal.log("INFO", "MIT-BIH complet (48 enregistrements) → %s" % rep_db)
    sha_local = os.path.join(rep_db, "SHA256SUMS.txt")
    if not os.path.exists(sha_local):
        if not polite_get(url_base + "/SHA256SUMS.txt", sha_local, journal):
            journal.log("ERROR", "SHA256SUMS.txt introuvable pour mitdb")
            return 0, ["mitdb/SHA256SUMS.txt"]
    sha_map = load_sha_map(sha_local)
    telecharges, echecs = 0, []
    for nom in MITDB_COMPLET:
        for rel in ("%s.hea" % nom, "%s.dat" % nom, "%s.atr" % nom):
            dest = os.path.join(rep_db, rel)
            attendu = sha_map.get(rel)
            if os.path.exists(dest) and attendu and sha256_file(dest) == attendu:
                journal.log("CACHE", "%s déjà présent et vérifié" % rel)
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if not polite_get("%s/%s" % (url_base, rel), dest, journal):
                journal.log("ERROR", "%s : téléchargement impossible" % rel)
                echecs.append("mitdb/" + rel)
                continue
            if attendu is None:
                journal.log("WARN", "%s téléchargé mais sans empreinte publiée" % rel)
                telecharges += 1
                continue
            obtenu = sha256_file(dest)
            if obtenu != attendu:
                journal.log("ERROR", "%s : SHA-256 invalide %s ≠ %s"
                            % (rel, obtenu, attendu))
                os.remove(dest)
                echecs.append("mitdb/" + rel)
                continue
            telecharges += 1
            journal.log("OK", "%s téléchargé et vérifié (%s)" % (rel, obtenu[:16]))
    return telecharges, echecs


def main(argv=None):
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = argparse.ArgumentParser(description="Télécharge la sélection Veille depuis PhysioNet.")
    p.add_argument("--dest", default=os.path.join(racine, "data", "records"),
                   help="répertoire de destination (défaut : data/records)")
    p.add_argument("--db", choices=sorted(k.split("/")[0] for k in SELECTION),
                   help="ne télécharger qu'un jeu")
    p.add_argument("--mitdb-complet", action="store_true",
                   help="télécharger les 48 enregistrements MIT-BIH (signal + .atr)")
    args = p.parse_args(argv)

    journal = Journal(os.path.join(args.dest, "fetch.log"))
    journal.log("INFO", "destination : %s" % args.dest)
    os.makedirs(args.dest, exist_ok=True)
    tous_echecs = []
    if args.mitdb_complet:
        nb, echecs = fetch_mitdb_complet(args.dest, journal)
        journal.log("OK", "MIT-BIH : %d fichier(s) téléchargé(s)" % nb)
        tous_echecs += echecs
    for db in SELECTION:
        if args.db and db.split("/")[0] != args.db:
            continue
        _, echecs = fetch_db(db, args.dest, journal)
        tous_echecs += echecs
    if tous_echecs:
        journal.log("ERROR", "échecs (%d) : %s" % (len(tous_echecs), ", ".join(tous_echecs)))
    else:
        journal.log("OK", "sélection complète téléchargée et vérifiée")
    journal.close()
    return 1 if tous_echecs else 0


if __name__ == "__main__":
    sys.exit(main())
