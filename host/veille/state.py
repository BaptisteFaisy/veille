"""États de défaillance Veille — jumeau Python (même contrat que state.h)."""
from enum import IntEnum

class SensorState(IntEnum):
    OK = 0; STUCK = 1; DEAD = 2; NOISY = 3; DRIFT = 4; COUNT = 5
class BusState(IntEnum):
    OK = 0; SATURATED = 1; SPIKE = 2; COUNT = 3
class PrioMode(IntEnum):
    NORMAL = 0; INVERTED = 1; COUNT = 2
class AlarmState(IntEnum):
    NONE = 0; SINGLE = 1; CONCURRENT = 2; LOCKED = 3; ACKED = 4; COUNT = 5

SENSOR_NAMES = ["sensor_ok", "sensor_stuck", "sensor_dead", "sensor_noisy", "sensor_drift"]
BUS_NAMES = ["bus_ok", "bus_saturated", "bus_spike"]
PRIO_MODE_NAMES = ["prio_normal", "prio_inverted"]
ALARM_NAMES = ["alarm_none", "alarm_single", "alarm_concurrent", "alarm_locked", "alarm_acked"]

CRITICAL_STAGES = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3)  # acquire, filter, decide, alarm

class FaultState:
    __slots__ = ("sensor", "bus", "prio", "alarm", "stage_fault_mask")
    def __init__(self, sensor=0, bus=0, prio=0, alarm=0, stage_fault_mask=0):
        self.sensor = sensor; self.bus = bus; self.prio = prio
        self.alarm = alarm; self.stage_fault_mask = stage_fault_mask
    def copy(self):
        return FaultState(self.sensor, self.bus, self.prio, self.alarm, self.stage_fault_mask)
    def chain_broken(self):
        return bool(self.stage_fault_mask & CRITICAL_STAGES)
    def worst_latency_ms(self, cfg):
        if self.chain_broken(): return -1
        s = sum(cfg.stage_latency_ms)
        if self.sensor == SensorState.STUCK: s += 5
        if self.sensor == SensorState.NOISY: s += 10
        if self.sensor == SensorState.DRIFT: s += 8
        if self.bus == BusState.SATURATED: s += 30
        if self.bus == BusState.SPIKE: s += 50
        if self.prio == PrioMode.INVERTED: s += 40
        if self.alarm == AlarmState.CONCURRENT: s += 15
        return s
    def to_string(self):
        parts = [SENSOR_NAMES[self.sensor], BUS_NAMES[self.bus],
                 PRIO_MODE_NAMES[self.prio], ALARM_NAMES[self.alarm]]
        s = "|".join(parts)
        if self.stage_fault_mask: s += "|stage_fault=0x%x" % self.stage_fault_mask
        return s
