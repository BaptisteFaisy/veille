import unittest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from veille import (ChainConfig, Priority, FaultMask, proof_explore,
                    report_text, report_json, VerdictCode, Severity)
from veille.state import (SignalGenerator, GenKind, SignalBuffer, SensorState,
                          signal_sensor_state, signal_rate_bpm, signal_decide)
from veille.chain import SampleChain, PipeResult

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


class TestSignal(unittest.TestCase):
    """Jumeau Python des preuves au niveau SIGNAL (core/tests/test_signal.c)."""

    def _analyser(self, kind, rate, fs=250, amp=1200, n=1024):
        g = SignalGenerator(kind, fs, rate, amp)
        b = SignalBuffer(fs)
        for _ in range(n):
            b.push(g.next())
        s = signal_sensor_state(b)
        bpm = signal_rate_bpm(b)
        return s, bpm, signal_decide(s, bpm)

    def test_signal_plat_fige_quelle_que_soit_la_frequence(self):
        # La propriété : un signal PLAT est figé à 60 bpm comme à 180 bpm.
        for rate in (60, 180):
            s, bpm, d = self._analyser(GenKind.FLAT, rate)
            self.assertEqual(s, SensorState.STUCK)
            self.assertEqual(bpm, 0)
            self.assertEqual(d, "tech_fault")

    def test_rythme_regulier_non_fige(self):
        # Cas qui échouait : rythme constant mais signal vivant ≠ capteur figé.
        s, bpm, d = self._analyser(GenKind.ECG, 60)
        self.assertEqual(s, SensorState.OK)
        self.assertEqual(bpm, 60)
        self.assertEqual(d, "ok")

    def test_tachycardie_alarme_physiologique(self):
        s, bpm, d = self._analyser(GenKind.ECG, 180)
        self.assertEqual(s, SensorState.OK)
        self.assertEqual(bpm, 180)
        self.assertEqual(d, "alarm_high")

    def test_pannes_capteur(self):
        s, bpm, d = self._analyser(GenKind.DEAD, 60)
        self.assertEqual(s, SensorState.DEAD)
        self.assertEqual(d, "tech_fault")
        s, bpm, d = self._analyser(GenKind.NOISY, 60)
        self.assertEqual(s, SensorState.NOISY)
        self.assertEqual(d, "tech_fault")
        s, bpm, d = self._analyser(GenKind.DRIFT, 60)
        self.assertEqual(s, SensorState.DRIFT)
        self.assertEqual(d, "tech_fault")

    def test_pipeline_signal(self):
        # Chaîne complète (SampleChain) : plat → figé, tachycardie → alarme haute.
        g = SignalGenerator(GenKind.FLAT, 250, 60, 1200)
        c = SampleChain(250)
        r = PipeResult.OK
        for _ in range(1024):
            r = c.push_sample(g.next())
        self.assertEqual(r, PipeResult.TECH_STUCK)
        g = SignalGenerator(GenKind.ECG, 250, 180, 1200)
        c = SampleChain(250)
        for _ in range(1024):
            r = c.push_sample(g.next())
        self.assertEqual(r, PipeResult.ALARM)
        self.assertEqual(c.rate_bpm(), 180)
