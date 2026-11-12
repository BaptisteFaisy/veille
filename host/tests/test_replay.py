"""Tests Veille sur enregistrements PHYSIOLOGIQUES RÉELS (PhysioNet).

Toutes les assertions portent sur les fichiers réellement présents dans
``data/records/`` (MIT-BIH, BIDMC, Sleep-EDF). Aucun test ne touche le
réseau : si une donnée manque, le test est **sauté** avec la commande de
téléchargement dans le message.

Les décodages 212 et 16 sont recalculés **à la main** dans ce fichier
(formulation arithmétique, indépendante de ``veille.wfdb``) puis comparés au
module — aucune valeur recopiée d'un outil tiers.
"""
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from veille import wfdb                                   # noqa: E402
from veille.chain import Priority                          # noqa: E402
from veille.report import report_json, report_text         # noqa: E402
from veille.replay import rejouer                          # noqa: E402
from veille.resmgr_client import alimenter                 # noqa: E402
from veille.verdict import VERDICT_NAMES                   # noqa: E402

RACINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENREGISTREMENTS = os.path.join(RACINE, "data", "records")
LIGNE_VERDICT = re.compile(r"^(ERROR|WARN |INFO )  VEILLE_[A-Z_]+")


def chemin(*parties):
    """Chemin d'un enregistrement réel."""
    return os.path.join(ENREGISTREMENTS, *parties)


def manquant(chemin_):
    """Message de saut : indique la commande de téléchargement à lancer."""
    return ("donnée réelle absente : %s — la télécharger avec "
            "`python3 data/fetch.py` (PhysioNet, licence Open Data Commons "
            "Attribution v1.0)" % chemin_)


def Decoder212Manuel(tampon, nb):
    """Décodage 212 écrit à la main : deux valeurs 12 bits par 3 octets.

    Formulation arithmétique (indépendante de ``veille.wfdb.decoder_212``) :
    - échantillon 0 = octet 0 + 256 × (octet 1 modulo 16) ;
    - échantillon 1 = octet 2 + 256 × (octet 1 divisé par 16) ;
    - complément à deux sur 12 bits.
    """
    valeurs = []
    for i in range(0, (len(tampon) // 3) * 3, 3):
        o0, o1, o2 = tampon[i], tampon[i + 1], tampon[i + 2]
        v0 = o0 + 256 * (o1 % 16)
        v1 = o2 + 256 * (o1 // 16)
        if v0 >= 2048:
            v0 -= 4096
        if v1 >= 2048:
            v1 -= 4096
        valeurs.append(v0)
        valeurs.append(v1)
        if len(valeurs) >= nb:
            break
    return valeurs[:nb]


def decoder16Manuel(tampon, nb):
    """Décodage 16 écrit à la main : int16 little-endian."""
    valeurs = []
    for i in range(0, (len(tampon) // 2) * 2, 2):
        valeurs.append(int.from_bytes(tampon[i:i + 2], "little", signed=True))
        if len(valeurs) >= nb:
            break
    return valeurs[:nb]


class TestEnTete(unittest.TestCase):
    """En-têtes WFDB réels."""

    def test_entete_mitdb_100(self):
        chemin_hea = chemin("mitdb", "100.hea")
        if not os.path.exists(chemin_hea):
            self.skipTest(manquant(chemin_hea))
        entete = wfdb.lire_en_tete(chemin("mitdb", "100"))
        self.assertEqual(entete.nom, "100")
        self.assertEqual(entete.nb_signaux, 2)
        self.assertEqual(entete.fs, 360)
        self.assertEqual(entete.nb_echantillons, 650000)
        self.assertEqual(entete.noms(), ["MLII", "V5"])
        mlii = entete.signal("MLII")
        self.assertEqual(mlii.format, 212)
        self.assertEqual(mlii.gain, 200)
        self.assertEqual(mlii.baseline, 1024)
        self.assertEqual(mlii.adc_res, 11)
        self.assertEqual(mlii.checksum, -22131)
        self.assertAlmostEqual(entete.duree_s(), 650000 / 360.0, places=6)

    def test_entete_bidmc01(self):
        chemin_hea = chemin("bidmc", "bidmc01.hea")
        if not os.path.exists(chemin_hea):
            self.skipTest(manquant(chemin_hea))
        entete = wfdb.lire_en_tete(chemin("bidmc", "bidmc01"))
        self.assertEqual(entete.nb_signaux, 5)
        self.assertEqual(entete.fs, 125)
        self.assertEqual(entete.nb_echantillons, 60001)
        self.assertEqual(entete.noms(), ["RESP", "PLETH", "V", "AVR", "II"])
        pleth = entete.signal("PLETH")
        self.assertEqual(pleth.format, 16)
        self.assertEqual(pleth.baseline, -63710)
        self.assertEqual(pleth.unites, "NU")

    def test_entete_slpdb(self):
        chemin_hea = chemin("slpdb", "slp02a.hea")
        if not os.path.exists(chemin_hea):
            self.skipTest(manquant(chemin_hea))
        entete = wfdb.lire_en_tete(chemin("slpdb", "slp02a"))
        self.assertEqual(entete.nb_signaux, 4)
        self.assertEqual(entete.fs, 250)
        self.assertEqual(entete.nb_echantillons, 2700000)
        bp = entete.signal("BP")
        self.assertEqual(bp.format, 212)
        self.assertEqual(bp.unites, "mmHg")
        self.assertEqual(bp.baseline, -513)


class TestDecodage(unittest.TestCase):
    """Décodage 212 et 16 — recalculé à la main dans ce fichier."""

    def test_212_mitdb_100(self):
        dat = chemin("mitdb", "100.dat")
        if not os.path.exists(dat):
            self.skipTest(manquant(dat))
        with open(dat, "rb") as f:
            tampon = f.read(48)
        attendu = Decoder212Manuel(tampon, 32)
        self.assertEqual(len(attendu), 32)
        mlii = wfdb.lire_signal(chemin("mitdb", "100"), "MLII", limite=16)
        v5 = wfdb.lire_signal(chemin("mitdb", "100"), "V5", limite=16)
        self.assertEqual(mlii.bruts, attendu[0::2][:16])
        self.assertEqual(v5.bruts, attendu[1::2][:16])
        # valeurs d'initialisation portées par l'en-tête lui-même
        self.assertEqual(mlii.bruts[0], 995)
        self.assertEqual(v5.bruts[0], 1011)
        # conversion physique : (brut - baseline) / gain
        self.assertAlmostEqual(mlii.physiques[0], (995 - 1024) / 200.0, places=9)
        self.assertEqual(mlii.fs, 360)

    def test_212_checksum_mitdb_100(self):
        dat = chemin("mitdb", "100.dat")
        if not os.path.exists(dat):
            self.skipTest(manquant(dat))
        entete = wfdb.lire_en_tete(chemin("mitdb", "100"))
        for nom in ("MLII", "V5"):
            bruts = wfdb.lire_bruts(entete, nom)
            self.assertEqual(len(bruts), 650000)
            self.assertEqual(wfdb.somme_16_signee(bruts),
                             entete.signal(nom).checksum)

    def test_16_bidmc01(self):
        dat = chemin("bidmc", "bidmc01.dat")
        if not os.path.exists(dat):
            self.skipTest(manquant(dat))
        with open(dat, "rb") as f:
            tampon = f.read(40)
        attendu = decoder16Manuel(tampon, 20)
        entete = wfdb.lire_en_tete(chemin("bidmc", "bidmc01"))
        for indice, nom in enumerate(("RESP", "PLETH", "V", "AVR", "II")):
            lus = wfdb.lire_bruts(entete, nom, limite=4)
            self.assertEqual(lus, attendu[indice::5][:4])
        pleth = wfdb.lire_signal(chemin("bidmc", "bidmc01"), "PLETH", limite=4)
        self.assertAlmostEqual(pleth.physiques[0],
                               (pleth.bruts[0] - pleth.signal.baseline) / pleth.signal.gain,
                               places=12)

    def test_signal_absent(self):
        dat = chemin("mitdb", "100.dat")
        if not os.path.exists(dat):
            self.skipTest(manquant(dat))
        with self.assertRaises(KeyError):
            wfdb.lire_signal(chemin("mitdb", "100"), "PAS_UN_SIGNAL", limite=1)


class TestNumeriques(unittest.TestCase):
    """CSV numérique BIDMC (SpO2 et HR réellement mesurés)."""

    def test_csv_bidmc01(self):
        csv = chemin("bidmc", "bidmc_csv", "bidmc_01_Numerics.csv")
        if not os.path.exists(csv):
            self.skipTest(manquant(csv))
        numeriques = wfdb.lire_numeriques_bidmc(csv)
        self.assertEqual(len(numeriques), 481)
        self.assertEqual(numeriques.temps[0], 0)
        self.assertEqual(numeriques.temps[-1], 480)
        self.assertEqual(numeriques.serie("HR")[0], 94)
        self.assertEqual(numeriques.serie("SpO2")[0], 97)
        self.assertEqual(numeriques.serie("PULSE")[0], 93)
        self.assertEqual(numeriques.serie("RESP")[0], 25)
        spo2 = numeriques.serie("spo2")
        hr = numeriques.serie("hr")
        presents = [v for v in spo2 if v is not None]
        self.assertTrue(all(80 <= v <= 100 for v in presents))
        # le CSV réel publie des « NaN » quand le moniteur ne rapportait pas SpO2
        self.assertTrue(any(v is None for v in spo2))
        self.assertTrue(all(30 <= v <= 200 for v in hr))


class TestRejeu(unittest.TestCase):
    """Rejeu borné d'un signal réel dans la chaîne existante."""

    def test_rejeu_borne_verdicts_conformes(self):
        dat = chemin("mitdb", "100.dat")
        if not os.path.exists(dat):
            self.skipTest(manquant(dat))
        verdicts, meta = rejouer(chemin("mitdb", "100"), "MLII",
                                  limite=3600, priorite=Priority.HIGH)
        self.assertTrue(verdicts)
        for v in verdicts:
            self.assertIn(v.name(), VERDICT_NAMES)      # 10 codes du CONTRAT.md §4
            self.assertTrue(v.message)
        self.assertEqual(verdicts[0].chain_id, "100_MLII")
        self.assertEqual(verdicts[0].latency_ms, 50)     # somme des 5 étages
        self.assertLessEqual(verdicts[0].latency_ms, 100)  # borne IEC haute
        # rendu texte : format §6.1 (préfixe de sévérité sur 5 caractères)
        lignes = report_text(verdicts).splitlines()
        for ligne in lignes[:-1]:
            self.assertRegex(ligne, LIGNE_VERDICT)
        self.assertEqual(lignes[-1], "OK")
        # rendu JSON : une ligne par verdict, clés figées, séparateurs compacts
        json_lignes = report_json(verdicts).splitlines()
        self.assertEqual(len(json_lignes), len(verdicts))
        self.assertTrue(json_lignes[0].startswith('{"code":"VEILLE_OK","sev":"info"'))
        self.assertIn('"chain_id":"100_MLII"', json_lignes[0])
        # meta d'audit : empreinte SHA-256 du .dat réellement rejoué
        self.assertEqual(len(meta["config_sha256"]), 64)

    def test_rejeu_signaux_bidmc_et_slpdb(self):
        cas = (("bidmc", "bidmc01", "PLETH"), ("slpdb", "slp02a", "ECG"))
        for dossier, enregistrement, nom_signal in cas:
            if not os.path.isdir(chemin(dossier)):
                self.skipTest(manquant(chemin(dossier)))
            entete = wfdb.lire_en_tete(chemin(dossier, enregistrement))
            if entete.signal(nom_signal) is None:
                self.skipTest(manquant(nom_signal))
            verdicts, _meta = rejouer(chemin(dossier, enregistrement),
                                      nom_signal, limite=6000)
            self.assertTrue(verdicts)
            for v in verdicts:
                self.assertIn(v.name(), VERDICT_NAMES)


class TestResmgrClient(unittest.TestCase):
    """Client du resource manager alimenté par un ECG réel."""

    def test_bpm_dans_fichier_temporaire(self):
        dat = chemin("mitdb", "100.dat")
        if not os.path.exists(dat):
            self.skipTest(manquant(dat))
        with tempfile.TemporaryDirectory() as dossier:
            sortie = os.path.join(dossier, "veille.out")
            synthese = alimenter(chemin("mitdb", "100"), "MLII", sortie, limite=36000)
            with open(sortie, "r", encoding="utf-8") as f:
                lignes = f.read().splitlines()
        self.assertEqual(len(lignes), synthese["battements"])
        self.assertGreater(len(lignes), 50)
        for ligne in lignes:
            self.assertRegex(ligne, r"^bpm \d+$")
        # record 100 de MIT-BIH : rythme sinusal normal, ~75 bpm
        self.assertGreater(synthese["bpm_moyen"], 55)
        self.assertLess(synthese["bpm_moyen"], 100)
        self.assertGreaterEqual(synthese["bpm_min"], 30)
        self.assertLessEqual(synthese["bpm_max"], 200)

    def test_bpm_confronte_au_hr_reel_bidmc(self):
        dat = chemin("bidmc", "bidmc01.dat")
        csv = chemin("bidmc", "bidmc_csv", "bidmc_01_Numerics.csv")
        if not (os.path.exists(dat) and os.path.exists(csv)):
            self.skipTest(manquant(dat))
        with tempfile.TemporaryDirectory() as dossier:
            sortie = os.path.join(dossier, "veille.out")
            synthese = alimenter(chemin("bidmc", "bidmc01"), "II", sortie)
        hr_reel = [v for v in wfdb.lire_numeriques_bidmc(csv).serie("HR")
                   if v is not None]
        moyenne_reelle = sum(hr_reel) / len(hr_reel)
        self.assertGreater(synthese["battements"], 500)
        self.assertLess(abs(synthese["bpm_moyen"] - moyenne_reelle), 5.0)
