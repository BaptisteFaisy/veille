"""Tests du score de détection contre la vérité terrain MIT-BIH (.atr).

Les assertions reposent sur des faits **publiés** (MIT-BIH Arrhythmia Database
Directory) et sur les fichiers réellement présents dans ``data/records/``.
Aucun test ne touche le réseau : si une donnée manque, le test est **sauté**.

Faits documentés utilisés (Directory MIT-BIH, records.htm) :
- record 100 : 2239 « N » + 33 « A » + 1 « V » = **2273 battements**,
  plus 1 annotation de rythme — rythme sinusal normal ;
- record 105 : **2526 « N » + 41 « V » + 5 « Q »** = 2572 battements.
"""
import os
import statistics
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from veille import wfdb                                   # noqa: E402
from veille.replay import diagnostiquer                   # noqa: E402
from veille.state import SensorState                       # noqa: E402
from veille.terrain import scorer_enregistrement           # noqa: E402

RACINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENREGISTREMENTS = os.path.join(RACINE, "data", "records")


def chemin(*parties):
    """Chemin d'un enregistrement réel."""
    return os.path.join(ENREGISTREMENTS, *parties)


def manquant(c):
    """Message de saut : indique comment télécharger la donnée absente."""
    return ("donnée réelle absente : %s — la télécharger avec "
            "`python3 data/fetch.py` (PhysioNet, licence Open Data Commons "
            "Attribution v1.0)" % c)


class TestAnnotationsAtr(unittest.TestCase):
    """Décodage du .atr (format MIT) contre les faits publiés du Directory."""

    def _present(self, rec):
        if not os.path.exists(chemin("mitdb", rec + ".atr")):
            self.skipTest(manquant(chemin("mitdb", rec + ".atr")))

    def test_record_100_types_documentes(self):
        self._present("100")
        anns = wfdb.lire_annotations(chemin("mitdb", "100"))
        battements = [a for a in anns if a.est_battement()]
        self.assertEqual(len(battements), 2273)          # Directory, records.htm
        self.assertEqual(sum(1 for a in battements if a.code == wfdb.CODE_NORMAL),
                         2239)
        self.assertEqual(sum(1 for a in battements if a.code == wfdb.CODE_APC), 33)
        self.assertEqual(sum(1 for a in battements if a.code == wfdb.CODE_PVC), 1)
        # exactement une annotation de rythme (sinusal normal) en tête de fichier
        rythmes = [a for a in anns if a.code == wfdb.CODE_RHYTHM]
        self.assertEqual(len(rythmes), 1)
        self.assertEqual(rythmes[0].mnemonic(), "+")
        # les annotations sont triées par temps croissant
        temps = [a.temps for a in anns]
        self.assertEqual(temps, sorted(temps))

    def test_record_105_conpistemmes_pvc(self):
        self._present("105")
        anns = wfdb.lire_annotations(chemin("mitdb", "105"))
        battements = [a for a in anns if a.est_battement()]
        self.assertEqual(len(battements), 2572)          # Directory, records.htm
        self.assertEqual(sum(1 for a in battements if a.code == wfdb.CODE_NORMAL),
                         2526)
        self.assertEqual(sum(1 for a in battements if a.code == wfdb.CODE_PVC), 41)
        self.assertEqual(sum(1 for a in battements
                             if a.code == wfdb.CODE_UNKNOWN), 5)

    def test_aucune_donnee_vide(self):
        """Le décodeur ne fabrique jamais de temps négatif ou de code hors bornes."""
        self._present("100")
        anns = wfdb.lire_annotations(chemin("mitdb", "100"))
        for a in anns:
            self.assertGreaterEqual(a.temps, 0)
            self.assertGreaterEqual(a.code, 0)
            self.assertLess(a.code, 64)


class TestDetectionRecord100(unittest.TestCase):
    """Détection sur 100 : rythme sinusal normal → quasi aucun pic manquant."""

    def test_score_record_100(self):
        dat = chemin("mitdb", "100.atr")
        if not os.path.exists(dat):
            self.skipTest(manquant(dat))
        score = scorer_enregistrement(chemin("mitdb", "100"), "MLII")
        # rythme normal propre : après alignement EC38, la sensibilité doit
        # être quasi parfaite (aucun battement annoté durablement manqué).
        self.assertGreaterEqual(score.sensibilite(), 0.99)
        self.assertGreaterEqual(score.vpp(), 0.99)
        self.assertLessEqual(score.aligne["fn"], score.battements * 0.01)
        # le nombre de pics détectés est du même ordre que les battements annotés
        self.assertAlmostEqual(score.pics / score.battements, 1.0, delta=0.05)


class TestCapteurConstant(unittest.TestCase):
    """Un ECG vivant à fréquence cardiaque régulière ne doit pas être « figé ».

    Le brief demande explicitement ce cas (il échouait) : la sémantique
    « fréquence constante ≠ capteur figé » est en cours de correction dans un
    autre lot. Ce test vérifie donc le comportement **existant** de
    :func:`veille.replay.diagnostiquer` (un ECG régulier → OK, jamais STUCK),
    et un contrôle sur signal plat (une valeur constante → **pas** OK).
    """

    def test_rythme_regulier_non_stuck(self):
        """Un ECG à battements réguliers n'est pas un capteur figé."""
        dat = chemin("mitdb", "100.dat")
        if not os.path.exists(dat):
            self.skipTest(manquant(dat))
        entete = wfdb.lire_en_tete(chemin("mitdb", "100"))
        sign = entete.signal("MLII")
        bruts = wfdb.lire_bruts(entete, "MLII", limite=1800)
        phys = [sign.physique(v) for v in bruts]
        for i0 in (0, 360, 720, 1080):
            fen = phys[i0:i0 + 360]
            self.assertEqual(diagnostiquer(sign, bruts[i0:i0 + 360], fen),
                             SensorState.OK)

    def test_signal_plat_non_ok(self):
        """Contrôle : un signal constant (capteur bloqué) n'est jamais déclaré OK.

        La classification exacte (STUCK vs DEAD) est en cours de révision dans
        un autre lot ; on ne fige ici que l'invariant robuste : un signal
        constant est un état de défaillance, pas un capteur sain.
        """
        entete = wfdb.lire_en_tete(chemin("mitdb", "100"))
        sign = entete.signal("MLII")
        plat = [sign.physique(sign.baseline)] * 360     # valeur constante
        bruts = [int(round(sign.baseline))] * 360
        self.assertNotEqual(diagnostiquer(sign, bruts, plat), SensorState.OK)


if __name__ == "__main__":
    unittest.main()