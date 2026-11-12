"""Rapports Veille — jumeau Python (mêmes formats que report.c, octet pour octet)."""
import json
from .verdict import verdict_name, severity_name, Severity

def report_text(verdicts):
    lines = []
    errors = 0
    for v in verdicts:
        if v.sev == Severity.ERROR: errors += 1
        sev = {Severity.ERROR: "ERROR", Severity.WARNING: "WARN ", Severity.INFO: "INFO "}[v.sev]
        details = []
        if v.chain_id: details.append("chain=%s" % v.chain_id)
        if v.stage: details.append("stage=%s" % v.stage)
        if v.state: details.append("state=%s" % v.state)
        if v.bound_ms: details.append("bound=%dms" % v.bound_ms)
        if v.latency_ms: details.append("latency=%dms" % v.latency_ms)
        if v.states_explored: details.append("states=%d" % v.states_explored)
        if v.config_sha256: details.append("config_sha256=%s" % v.config_sha256)
        line = "%s  %s" % (sev, verdict_name(v.code))
        if details: line += "  " + "  ".join(details)
        lines.append(line)
    lines.append("OK" if errors == 0 else "FAILED %d error(s)" % errors)
    return "\n".join(lines) + "\n"

def report_json(verdicts):
    out = []
    for v in verdicts:
        obj = {"code": verdict_name(v.code), "sev": severity_name(v.sev)}
        if v.chain_id: obj["chain_id"] = v.chain_id
        if v.bound_ms: obj["bound_ms"] = v.bound_ms
        if v.latency_ms: obj["latency_ms"] = v.latency_ms
        if v.states_explored: obj["states_explored"] = v.states_explored
        if v.config_sha256: obj["config_sha256"] = v.config_sha256
        obj["message"] = v.message or ""
        out.append(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
    return "\n".join(out) + "\n" if out else ""

def report_markdown(verdicts, meta=None):
    meta = meta or {}
    cf = meta.get("config_file") or "inconnu"
    cs = meta.get("config_sha256") or "inconnu"
    ts = meta.get("timestamp_utc") or "inconnu"
    vv = meta.get("veille_version") or "inconnu"
    errors = sum(1 for v in verdicts if v.sev == Severity.ERROR)
    states = max((v.states_explored for v in verdicts), default=0)
    return (
        "# Rapport de preuve de latence — Veille\n\n"
        "- Configuration : %s\n- Empreinte SHA-256 : %s\n"
        "- Horodatage (UTC) : %s\n- Version de Veille : %s\n\n"
        "## Synthèse\n%s\n\n## Propriétés vérifiées\n"
        "### P1 — Latence d'alarme\n- Méthode : exploration exhaustive de %d états\n"
        "- Résultat : %s\n" % (cf, cs, ts, vv, "FAILED" if errors else "OK",
                               states, "contre-exemple" if errors else "borne tenue")
    )

def exit_code(verdicts):
    return 1 if any(v.sev == Severity.ERROR for v in verdicts) else 0
