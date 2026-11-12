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


# ---------------------------------------------------------------------------
# Chaîne au niveau SIGNAL — jumeau Python de target/pipe/veille_pipe.c
# (chemin veille_pipe_push_sample). Même filtré (moyenneur glissant de fenêtre
# 8) et même décision de seuil : le différentiel C↔Python le vérifie.
# ---------------------------------------------------------------------------

from .state import SensorState, SignalBuffer, signal_sensor_state, signal_rate_bpm

FILTER_WINDOW = 8
HR_THRESHOLD = 120


class PipeResult(IntEnum):
    OK = 0
    ALARM = 1
    TECH_STUCK = 2
    TECH_DEAD = 3
    TECH_NOISY = 4
    TECH_DRIFT = 5


def _tech_result(sensor):
    return {SensorState.DEAD: PipeResult.TECH_DEAD,
            SensorState.STUCK: PipeResult.TECH_STUCK,
            SensorState.NOISY: PipeResult.TECH_NOISY,
            SensorState.DRIFT: PipeResult.TECH_DRIFT}.get(sensor, PipeResult.OK)


class SampleChain:
    """Jumeau de veille_pipe_state + veille_pipe_push_sample (target/pipe)."""
    __slots__ = ("signal", "filter", "index", "last_bpm", "sensor")

    def __init__(self, fs_hz=250):
        self.signal = SignalBuffer(fs_hz)
        self.filter = []
        self.index = 0
        self.last_bpm = 0
        self.sensor = SensorState.OK

    def push_sample(self, brut):
        self.signal.push(brut)
        self.index += 1
        self.sensor = signal_sensor_state(self.signal)
        if self.sensor != SensorState.OK:
            return _tech_result(self.sensor)
        bpm = signal_rate_bpm(self.signal)
        if bpm > 0:
            self.last_bpm = bpm
            self.filter.append(bpm)
            if len(self.filter) > FILTER_WINDOW:
                self.filter.pop(0)
        return PipeResult.ALARM if self.filtered() > HR_THRESHOLD else PipeResult.OK

    def filtered(self):
        if not self.filter:
            return 0
        return sum(self.filter) // len(self.filter)

    def rate_bpm(self):
        return self.last_bpm

    def sensor_state(self):
        return self.sensor
