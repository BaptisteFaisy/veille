#!/usr/bin/env python3
"""Test différentiel C↔Python : même contrat, mêmes sorties (octet pour octet).
Tout désaccord est un bug, réduit dichotomiquement.

Deux étages :
  1. preuve (4800 états) — le différentiel historique ;
  2. SIGNAL brute — l'état capteur + la fréquence déduits du signal brute
     (l'API corrective) comparés entre le binaire C (core/tests/test_signal.bin)
     et le jumeau Python, puis confrontés aux scénarios scenarios/signal_*.json.
"""
import subprocess, sys, os, re, json, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "host"))
from veille import ChainConfig, Priority, FaultMask, proof_explore
from veille.state import (SignalGenerator, SignalBuffer, GenKind, SENSOR_NAMES,
                          signal_sensor_state, signal_rate_bpm, signal_decide)

BIN_SIGNAL = os.path.join(os.path.dirname(__file__), "..", "core", "tests", "test_signal.bin")
GEN_MAP = {"flat": GenKind.FLAT, "dead": GenKind.DEAD, "noisy": GenKind.NOISY,
           "drift": GenKind.DRIFT, "ecg": GenKind.ECG}
# Décision → code de verdict (convention de target/sim/sim.c et du resource manager).
DECISION_CODE = {"tech_fault": "VEILLE_TECHNICAL_ALARM",
                 "alarm_high": "VEILLE_OK", "ok": "VEILLE_OK"}


def run_c():
    bin_path = os.path.join(os.path.dirname(__file__), "..", "core", "tests", "test_proof.bin")
    if not os.path.exists(bin_path):
        return None
    out = subprocess.run([bin_path], capture_output=True, text=True).stdout
    m = re.search(r"states=(\d+).*?latency=(\d+)", out)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def run_py():
    cfg = ChainConfig(Priority.HIGH, 100, 60000, [5, 10, 10, 20, 5])
    mask = FaultMask(sensor=True, bus=True, prio=True, alarm=True, stage=True)
    _rc, verdicts = proof_explore(cfg, mask)
    v = verdicts[0]
    return v.states_explored, v.latency_ms


def run_c_signal(kind, fs, rate, amp, samples):
    if not os.path.exists(BIN_SIGNAL):
        return None
    out = subprocess.run([BIN_SIGNAL, "--sig", kind, "--fs", str(fs), "--rate", str(rate),
                          "--amp", str(amp), "--samples", str(samples)],
                         capture_output=True, text=True).stdout
    m = re.search(r"sensor=(\S+)\s+bpm=(-?\d+)\s+decision=(\S+)", out)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else None


def run_py_signal(kind, fs, rate, amp, samples):
    g = SignalGenerator(GEN_MAP[kind], fs, rate, amp)
    b = SignalBuffer(fs)
    for _ in range(samples):
        b.push(g.next())
    s = signal_sensor_state(b)
    bpm = signal_rate_bpm(b)
    return SENSOR_NAMES[s], bpm, signal_decide(s, bpm)


CASES = [("flat", 250, 60, 1200, 1024), ("flat", 250, 180, 1200, 1024),
         ("ecg", 250, 60, 1200, 1024), ("ecg", 250, 180, 1200, 1024),
         ("ecg", 250, 90, 1200, 1024),
         ("dead", 250, 60, 1200, 1024), ("noisy", 250, 60, 1200, 1024),
         ("drift", 250, 60, 1200, 1024)]


def diff_signal():
    fails = 0
    for kind, fs, rate, amp, samples in CASES:
        c = run_c_signal(kind, fs, rate, amp, samples)
        p = run_py_signal(kind, fs, rate, amp, samples)
        if c is None:
            print("[SKIP] différentiel signal (binaire C absent — lancé après make test)")
            return 0
        tag = "C≈Py" if c == p else "ÉCART"
        print("  %-5s rate=%-3d %-7s C=(%s,%d,%s) Py=(%s,%d,%s)"
              % (kind, rate, tag, c[0], c[1], c[2], p[0], p[1], p[2]))
        if c != p:
            fails += 1
    return fails


def diff_scenarios():
    fails = 0
    for path in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "scenarios",
                                              "signal_*.json"))):
        data = json.load(open(path, encoding="utf-8"))
        sig = data["signal"]
        exp = data["expected"]
        kind = sig["generator"]
        args = (kind, sig["fs_hz"], sig["rate_bpm"], sig["amplitude"], sig["samples"])
        c = run_c_signal(*args)
        p = run_py_signal(*args)
        ok = (c is not None and c == p
              and c[0] == exp["sensor"] and c[1] == exp["bpm"]
              and c[2] == exp["decision"]
              and DECISION_CODE.get(c[2]) == exp["code"])
        print("  %-28s %s" % (os.path.basename(path), "OK" if ok else "ÉCHEC"))
        if ok:
            print("        C=(%s, %d, %s) → %s" % (c[0], c[1], c[2], exp["code"]))
        else:
            print("        attendu sensor=%s bpm=%s decision=%s code=%s ; C=%r Py=%r"
                  % (exp["sensor"], exp["bpm"], exp["decision"], exp["code"], c, p))
            fails += 1
    return fails


def main():
    c = run_c()
    p = run_py()
    print("=== différentiel preuve (4800 états) ===")
    print("C  :", c)
    print("Py :", p)
    if c is None:
        print("[SKIP] différentiel preuve (binaire C absent — lancé après make test)")
    elif c != p:
        print("[FAIL] désaccord C↔Python : %r != %r" % (c, p))
        return 1
    else:
        print("[OK] différentiel C↔Python vert (states=%d, latency=%d)" % p)

    print("=== différentiel signal brute ===")
    fails = diff_signal()
    print("=== scénarios signal (scenarios/signal_*.json) ===")
    fails += diff_scenarios()
    if fails:
        print("[FAIL] %d désaccord(s) C↔Python ou scénario(s) non conforme(s)" % fails)
        return 1
    print("[OK] différentiel C↔Python vert (preuve + signal brute + scénarios)")
    return 0


if __name__ == "__main__":
    sys.exit(main())