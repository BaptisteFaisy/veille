"""Verdicts Veille — jumeau Python (même contrat que core/include/veille/verdict.h)."""
from enum import IntEnum

class VerdictCode(IntEnum):
    OK = 0
    LATENCY_BOUND_EXCEEDED = 1
    ALARM_MISSED = 2
    SENSOR_FAULT = 3
    PRIORITY_INVERSION = 4
    TECHNICAL_ALARM = 5
    CHAIN_FAULT = 6
    PROOF_COMPLETE = 7
    PROOF_COUNTEREXAMPLE = 8
    ACK_TIMEOUT = 9
    COUNT = 10

class Severity(IntEnum):
    INFO = 0
    WARNING = 1
    ERROR = 2

VERDICT_NAMES = [
    "VEILLE_OK", "VEILLE_LATENCY_BOUND_EXCEEDED", "VEILLE_ALARM_MISSED",
    "VEILLE_SENSOR_FAULT", "VEILLE_PRIORITY_INVERSION", "VEILLE_TECHNICAL_ALARM",
    "VEILLE_CHAIN_FAULT", "VEILLE_PROOF_COMPLETE", "VEILLE_PROOF_COUNTEREXAMPLE",
    "VEILLE_ACK_TIMEOUT",
]
VERDICT_SEV = [
    Severity.INFO, Severity.ERROR, Severity.ERROR, Severity.WARNING, Severity.ERROR,
    Severity.WARNING, Severity.ERROR, Severity.INFO, Severity.ERROR, Severity.WARNING,
]

def verdict_name(code):
    return VERDICT_NAMES[code] if 0 <= code < len(VERDICT_NAMES) else "VEILLE_UNKNOWN"

def severity_name(sev):
    return {Severity.INFO: "info", Severity.WARNING: "warning", Severity.ERROR: "error"}.get(sev, "info")

def default_severity(code):
    return VERDICT_SEV[code] if 0 <= code < len(VERDICT_SEV) else Severity.INFO

class Verdict:
    __slots__ = ("code", "sev", "message", "chain_id", "stage", "state",
                 "bound_ms", "latency_ms", "states_explored", "config_sha256")
    def __init__(self, code, sev=None, message="", **kw):
        self.code = code
        self.sev = sev if sev is not None else default_severity(code)
        self.message = message
        self.chain_id = kw.get("chain_id")
        self.stage = kw.get("stage")
        self.state = kw.get("state")
        self.bound_ms = kw.get("bound_ms", 0)
        self.latency_ms = kw.get("latency_ms", 0)
        self.states_explored = kw.get("states_explored", 0)
        self.config_sha256 = kw.get("config_sha256")
    def name(self):
        return verdict_name(self.code)
