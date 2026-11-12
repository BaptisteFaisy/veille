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

# ---------------------------------------------------------------------------
# Analyse du SIGNAL BRUT — jumeau Python de core/src/signal.c + signal_gen.c.
#
# Mêmes formules, même LCG, mêmes conventions (médiane SUPÉRIEURE, divisions
# entières tronquées vers zéro) : le différentiel C↔Python doit rester vert.
# ---------------------------------------------------------------------------

SIG_WINDOW_MAX = 512
SIG_MAX_BEATS = 32
SIG_HR_THRESHOLD = 120
SIG_STUCK_PLAGE = 2
SIG_BRUIT_PCT = 12
SIG_DERIVE_FACTEUR = 4


def _trunc_div(a, b):
    """Division entière C (troncature vers zéro) — // de Python arrondit vers -inf."""
    return -((-a) // b) if a < 0 else a // b


def _int16(v):
    """Cast (int16_t) C : repli modulo 2**16 sur [-32768, 32767]."""
    v %= 65536
    return v - 65536 if v >= 32768 else v


def _median(x):
    """Médiane SUPÉRIEURE : valeur de rang len(x)//2 (comme select_kth en C)."""
    return sorted(x)[len(x) // 2]


class GenKind:
    ECG = 0
    FLAT = 1
    DEAD = 2
    NOISY = 3
    DRIFT = 4


_GEN_NAMES = {GenKind.ECG: "ecg", GenKind.FLAT: "flat", GenKind.DEAD: "dead",
              GenKind.NOISY: "noisy", GenKind.DRIFT: "drift"}


class SignalGenerator:
    """Jumeau de veille_signal_gen (core/src/signal_gen.c)."""
    __slots__ = ("kind", "fs_hz", "rate_bpm", "amplitude", "drift_per_s",
                 "period", "rng", "index")

    def __init__(self, kind, fs_hz, rate_bpm, amplitude):
        if fs_hz <= 0:
            fs_hz = 250
        if rate_bpm <= 0:
            rate_bpm = 60
        self.kind = kind
        self.fs_hz = fs_hz
        self.rate_bpm = rate_bpm
        self.amplitude = amplitude
        self.drift_per_s = 200
        self.rng = 12345
        period = (fs_hz * 60) // rate_bpm
        self.period = period if period >= 1 else 1
        self.index = 0

    def _bruit(self):
        self.rng = (self.rng * 1103515245 + 12345) & 0xFFFFFFFF
        return ((self.rng >> 16) % 2001) - 1000

    def _ecg_valeur(self, pos):
        k = (self.period * 20) // 100
        w = (self.fs_hz * 3) // 100
        w = w if w >= 1 else 1
        d = pos - k
        if d < 0:
            d = -d
        v = 0
        if d <= w:
            v += self.amplitude * (w - d) // w
        kt = (self.period * 35) // 100
        wt = (self.fs_hz * 4) // 100
        wt = wt if wt >= 1 else 1
        dt = pos - kt
        if dt < 0:
            dt = -dt
        if dt <= wt:
            v += (self.amplitude // 4) * (wt - dt) // wt
        return v

    def next(self):
        i = self.index
        self.index += 1
        if self.kind == GenKind.FLAT:
            return _int16(self.amplitude)
        if self.kind == GenKind.DEAD:
            return 0
        v = self._ecg_valeur(i % self.period)
        b = self._bruit()
        if self.kind == GenKind.NOISY:
            v += _trunc_div(b * self.amplitude, 1000)
        else:
            v += _trunc_div(b, 100)
        if self.kind == GenKind.DRIFT:
            v += (self.drift_per_s * i) // self.fs_hz
        return _int16(v)


class SignalBuffer:
    """Jumeau de veille_signal_buffer (core/src/signal.c)."""
    __slots__ = ("buf", "n", "fs_hz", "refractory")

    def __init__(self, fs_hz=0):
        if fs_hz <= 0:
            fs_hz = 250
        self.fs_hz = fs_hz
        self.refractory = (fs_hz * 2) // 10
        if self.refractory < 1:
            self.refractory = 1
        self.buf = []
        self.n = 0

    def push(self, sample):
        if self.n < SIG_WINDOW_MAX:
            self.buf.append(sample)
            self.n += 1
        else:
            self.buf = self.buf[1:] + [sample]

    def window_full(self):
        return self.n >= SIG_WINDOW_MAX


def _sensor_state(buf):
    x = buf
    if len(x) < 2:
        return SensorState.OK
    lo = hi = x[0]
    zeros = True
    for v in x:
        if v < lo:
            lo = v
        if v > hi:
            hi = v
        if v != 0:
            zeros = False
    if zeros:
        return SensorState.DEAD
    plage = hi - lo
    if plage <= SIG_STUCK_PLAGE:
        return SensorState.STUCK
    mdiff = _median_abs_diff(x)
    if mdiff > 0 and mdiff * 100 > SIG_BRUIT_PCT * plage:
        return SensorState.NOISY
    echelle = mdiff if mdiff > 0 else 1
    if _quarter_shift(x) > SIG_DERIVE_FACTEUR * echelle:
        return SensorState.DRIFT
    return SensorState.OK


def _median_abs_diff(x):
    if len(x) < 2:
        return 0
    return _median([abs(x[i + 1] - x[i]) for i in range(len(x) - 1)])


def _quarter_shift(x):
    q = len(x) // 4
    if q < 1:
        return 0
    m1 = _median(x[:q])
    m2 = _median(x[len(x) - q:])
    return m2 - m1 if m2 > m1 else m1 - m2


def signal_sensor_state(buf):
    """État capteur déduit du signal brut (jumeau de veille_signal_sensor_state)."""
    return _sensor_state(buf.buf if isinstance(buf, SignalBuffer) else buf)


def signal_rate_bpm(buf):
    """Fréquence déduite des pics R (jumeau de veille_signal_rate_bpm)."""
    x = buf.buf if isinstance(buf, SignalBuffer) else buf
    n = len(x)
    fs = buf.fs_hz if isinstance(buf, SignalBuffer) else 250
    if n < 8 or fs <= 0:
        return 0
    lo = hi = x[0]
    for v in x[1:]:
        if v < lo:
            lo = v
        if v > hi:
            hi = v
    if hi - lo <= SIG_STUCK_PLAGE:
        return 0
    seuil = _median(x) + (hi - lo) // 2
    pics = []
    dernier = -1
    refr = buf.refractory if isinstance(buf, SignalBuffer) else (fs * 2) // 10 or 1
    for i in range(1, n - 1):
        if x[i] < seuil:
            continue
        if x[i] < x[i - 1] or x[i] < x[i + 1]:
            continue
        if dernier >= 0 and (i - dernier) < refr:
            continue
        if len(pics) == SIG_MAX_BEATS:
            pics.pop(0)
        pics.append(i)
        dernier = i
    if len(pics) < 2:
        return 0
    intervalle = (pics[-1] - pics[0]) // (len(pics) - 1)
    if intervalle <= 0:
        return 0
    return (60 * fs) // intervalle


def signal_decide(sensor, bpm, threshold=SIG_HR_THRESHOLD):
    """Décision de la chaîne (jumeau de veille_signal_decide)."""
    if sensor != SensorState.OK:
        return "tech_fault"
    if bpm > threshold:
        return "alarm_high"
    return "ok"
