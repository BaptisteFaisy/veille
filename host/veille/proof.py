"""Exploration exhaustive Veille — jumeau Python (même contrat que proof.h/proof.c)."""
from .state import SensorState, BusState, PrioMode, AlarmState, FaultState
from .verdict import Verdict, VerdictCode, Severity

# Espace complet des pannes d'étage : 2**5 = 32 masques (comme STAGE_MASK_SPACE en C).
STAGE_MASK_SPACE = 32

class FaultMask:
    __slots__ = ("sensor", "bus", "prio", "alarm", "stage")
    def __init__(self, sensor=True, bus=True, prio=True, alarm=True, stage=True):
        self.sensor = sensor; self.bus = bus; self.prio = prio
        self.alarm = alarm; self.stage = stage

def explore(cfg, mask):
    """Énumère tous les états ; retourne un dict {states, broken, ce_state, ce_latency}."""
    bound = cfg.bound_alarm_ms
    result = {"states": 0, "broken": 0, "ce_state": None, "ce_latency": 0}
    def rec(st, dim):
        if dim == 5:
            result["states"] += 1
            lat = st.worst_latency_ms(cfg)
            if lat < 0:
                result["broken"] += 1   # chaîne rompue → P2 vérifiée globalement
                return
            if lat > bound and result["ce_state"] is None:
                result["ce_state"] = st.copy()
                result["ce_latency"] = lat
            return
        if dim == 0:
            rng = range(SensorState.COUNT) if mask.sensor else [0]
            for v in rng:
                st.sensor = v; rec(st, dim + 1)
        elif dim == 1:
            rng = range(BusState.COUNT) if mask.bus else [0]
            for v in rng:
                st.bus = v; rec(st, dim + 1)
        elif dim == 2:
            rng = range(PrioMode.COUNT) if mask.prio else [0]
            for v in rng:
                st.prio = v; rec(st, dim + 1)
        elif dim == 3:
            rng = range(AlarmState.COUNT) if mask.alarm else [0]
            for v in rng:
                st.alarm = v; rec(st, dim + 1)
        elif dim == 4:
            rng = range(STAGE_MASK_SPACE) if mask.stage else [0]
            for v in rng:
                st.stage_fault_mask = v; rec(st, dim + 1)
    rec(FaultState(), 0)
    return result

def proof_explore(cfg, mask):
    """Retourne (rc, verdicts) comme veille_proof_explore en C (0 preuve, 1 contre-exemple)."""
    if not cfg.valid(): return -1, []
    r = explore(cfg, mask)
    tech_violation = r["broken"] > 0 and cfg.tech_detect_ms > cfg.bound_tech_ms
    if r["ce_state"] is not None or tech_violation:
        if tech_violation and r["ce_state"] is None:
            v = Verdict(VerdictCode.PROOF_COUNTEREXAMPLE, Severity.ERROR,
                        "alarme technique hors borne (P2)", states_explored=r["states"],
                        bound_ms=cfg.bound_tech_ms, latency_ms=cfg.tech_detect_ms)
        else:
            v = Verdict(VerdictCode.PROOF_COUNTEREXAMPLE, Severity.ERROR,
                        "contre-exemple trouvé", states_explored=r["states"],
                        bound_ms=cfg.bound_alarm_ms, latency_ms=r["ce_latency"])
        return 1, [v]
    v = Verdict(VerdictCode.PROOF_COMPLETE, Severity.INFO,
                "borne tenue sur tous les états", states_explored=r["states"],
                bound_ms=cfg.bound_alarm_ms)
    return 0, [v]
