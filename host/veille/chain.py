"""Chaîne Veille — jumeau Python (même contrat que core/include/veille/chain.h)."""
from enum import IntEnum

class Stage(IntEnum):
    ACQUIRE = 0; FILTER = 1; DECIDE = 2; ALARM = 3; ACK = 4; COUNT = 5

class Priority(IntEnum):
    HIGH = 0; MEDIUM = 1; LOW = 2; TECHNICAL = 3; COUNT = 4

STAGE_NAMES = ["acquire", "filter", "decide", "alarm", "ack"]
PRIO_NAMES = ["high", "medium", "low", "technical"]

def stage_name(s):
    return STAGE_NAMES[s] if 0 <= s < len(STAGE_NAMES) else "?"

def priority_name(p):
    return PRIO_NAMES[p] if 0 <= p < len(PRIO_NAMES) else "?"

class ChainConfig:
    __slots__ = ("priority", "bound_alarm_ms", "bound_ack_ms",
                 "bound_tech_ms", "tech_detect_ms", "stage_latency_ms")
    def __init__(self, priority, bound_alarm_ms, bound_ack_ms, stage_latency_ms,
                 bound_tech_ms=50, tech_detect_ms=15):
        self.priority = priority
        self.bound_alarm_ms = bound_alarm_ms
        self.bound_ack_ms = bound_ack_ms
        self.bound_tech_ms = bound_tech_ms
        self.tech_detect_ms = tech_detect_ms
        self.stage_latency_ms = list(stage_latency_ms)
    def valid(self):
        if not (0 <= self.priority < Priority.COUNT): return False
        if self.bound_alarm_ms <= 0: return False
        if self.bound_tech_ms <= 0: return False
        if self.tech_detect_ms < 0: return False
        return all(x >= 0 for x in self.stage_latency_ms)
    def latency_ms(self):
        return sum(self.stage_latency_ms)
