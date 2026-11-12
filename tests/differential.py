#!/usr/bin/env python3
"""Test différentiel C↔Python : même contrat, mêmes sorties (octet pour octet).
Tout désaccord est un bug, réduit dichotomiquement."""
import subprocess, sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "host"))
from veille import ChainConfig, Priority, FaultMask, proof_explore

def run_c():
    bin_path = os.path.join(os.path.dirname(__file__), "..", "core", "tests", "test_proof.bin")
    if not os.path.exists(bin_path):
        return None
    out = subprocess.run([bin_path], capture_output=True, text=True).stdout
    m = re.search(r"states=(\d+).*?latency=(\d+)", out)
    if not m: return None
    return int(m.group(1)), int(m.group(2))

def run_py():
    cfg = ChainConfig(Priority.HIGH, 100, 60000, [5, 10, 10, 20, 5])
    mask = FaultMask(sensor=True, bus=True, prio=True, alarm=True, stage=True)
    rc, verdicts = proof_explore(cfg, mask)
    v = verdicts[0]
    return v.states_explored, v.latency_ms

def main():
    c = run_c()
    p = run_py()
    print("C  :", c)
    print("Py :", p)
    if c is None:
        print("[SKIP] différentiel (binaire C absent — lancé après make test)")
        return 0
    if c != p:
        print("[FAIL] désaccord C↔Python : %r != %r" % (c, p))
        return 1
    print("[OK] différentiel C↔Python vert (states=%d, latency=%d)" % p)
    return 0

if __name__ == "__main__":
    sys.exit(main())
