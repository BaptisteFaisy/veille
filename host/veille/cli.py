"""CLI Veille — exploration exhaustive de la latence d'alarme."""
import argparse
import json
import sys
from .chain import ChainConfig, Priority
from .proof import FaultMask, proof_explore
from .report import report_text, report_json, report_markdown, exit_code

DEFAULT_STAGES = [5, 10, 10, 20, 5]   # acquire, filter, decide, alarm, ack

def build_config(bound_ms, priority=Priority.HIGH):
    return ChainConfig(priority, bound_ms, 60000, DEFAULT_STAGES)

def emit(verdicts, args):
    if args.json:
        sys.stdout.write(report_json(verdicts))
    elif args.markdown:
        meta = {"config_file": getattr(args, "file", "cli"),
                "config_sha256": None, "timestamp_utc": None, "veille_version": "0.1.0"}
        sys.stdout.write(report_markdown(verdicts, meta))
    else:
        sys.stdout.write(report_text(verdicts))

def cmd_proof(args):
    cfg = build_config(args.bound, Priority.HIGH)
    full = not args.subset
    mask = FaultMask(sensor=True, bus=full, prio=full, alarm=full, stage=full)
    rc, verdicts = proof_explore(cfg, mask)
    emit(verdicts, args)
    return rc

def cmd_scenario(args):
    with open(args.file, "r", encoding="utf-8") as f:
        data = json.load(f)
    cfg = ChainConfig(data.get("priority", 0), data["bound_alarm_ms"],
                      data.get("bound_ack_ms", 60000), data["stage_latency_ms"],
                      data.get("bound_tech_ms", 50), data.get("tech_detect_ms", 15))
    m = data.get("mask", {})
    mask = FaultMask(sensor=m.get("sensor", True), bus=m.get("bus", True),
                     prio=m.get("prio", True), alarm=m.get("alarm", True),
                     stage=m.get("stage", True))
    rc, verdicts = proof_explore(cfg, mask)
    emit(verdicts, args)
    return rc

def main(argv=None):
    p = argparse.ArgumentParser(prog="veille", description="Veille — preuve de latence d'alarme (QNX 8.0)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, func, help_txt in (("proof", cmd_proof, "exploration exhaustive des états de défaillance"),
                                 ("scenario", cmd_scenario, "preuve sur un scénario JSON de référence")):
        sp = sub.add_parser(name, help=help_txt)
        if name == "proof":
            sp.add_argument("--bound", type=int, default=100, help="borne B_alarm en ms (défaut 100)")
            sp.add_argument("--subset", action="store_true", help="sous-ensemble S4 (capteur seul)")
        else:
            sp.add_argument("file", help="scénario JSON (scenarios/*.json)")
        sp.add_argument("--json", action="store_true", help="sortie JSON")
        sp.add_argument("--markdown", action="store_true", help="sortie Markdown (audit)")
        sp.set_defaults(func=func)
    args = p.parse_args(argv)
    return args.func(args)

if __name__ == "__main__":
    sys.exit(main())
