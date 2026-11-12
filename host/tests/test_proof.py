import unittest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from veille import (ChainConfig, Priority, FaultMask, proof_explore,
                    report_text, report_json, VerdictCode, Severity)

STAGES = [5, 10, 10, 20, 5]
FULL = FaultMask(True, True, True, True, True)

class TestProof(unittest.TestCase):
    def test_counterexample(self):
        cfg = ChainConfig(Priority.HIGH, 100, 60000, STAGES)
        rc, vs = proof_explore(cfg, FULL)
        self.assertEqual(rc, 1)
        self.assertEqual(vs[0].code, VerdictCode.PROOF_COUNTEREXAMPLE)
        self.assertEqual(vs[0].states_explored, 4800)   # 5*3*2*5*32
        self.assertEqual(vs[0].latency_ms, 105)          # 50 + stuck(5) + spike(50)

    def test_complete(self):
        cfg = ChainConfig(Priority.HIGH, 200, 60000, STAGES)
        rc, vs = proof_explore(cfg, FULL)
        self.assertEqual(rc, 0)
        self.assertEqual(vs[0].code, VerdictCode.PROOF_COMPLETE)
        self.assertEqual(vs[0].states_explored, 4800)

    def test_subset(self):
        cfg = ChainConfig(Priority.HIGH, 1000, 60000, STAGES)
        rc, vs = proof_explore(cfg, FaultMask(sensor=True, bus=False, prio=False,
                                              alarm=False, stage=False))
        self.assertEqual(rc, 0)
        self.assertEqual(vs[0].states_explored, 5)      # capteur seul

    def test_tech_violation_p2(self):
        # borne d'alarme large (pas de contre-exemple P1) mais détection technique hors borne
        cfg = ChainConfig(Priority.HIGH, 1000, 60000, STAGES,
                          bound_tech_ms=50, tech_detect_ms=60)
        rc, vs = proof_explore(cfg, FULL)
        self.assertEqual(rc, 1)
        self.assertEqual(vs[0].code, VerdictCode.PROOF_COUNTEREXAMPLE)
        self.assertIn("P2", vs[0].message)
        self.assertEqual(vs[0].latency_ms, 60)
        self.assertEqual(vs[0].bound_ms, 50)

    def test_report_text(self):
        cfg = ChainConfig(Priority.HIGH, 1000, 60000, STAGES)
        _, vs = proof_explore(cfg, FULL)
        txt = report_text(vs)
        self.assertIn("VEILLE_PROOF_COMPLETE", txt)
        self.assertIn("OK", txt)

    def test_report_json(self):
        cfg = ChainConfig(Priority.HIGH, 1000, 60000, STAGES)
        _, vs = proof_explore(cfg, FULL)
        js = report_json(vs)
        self.assertIn('"code":"VEILLE_PROOF_COMPLETE"', js)
        self.assertIn('"sev":"info"', js)

if __name__ == "__main__":
    unittest.main()
