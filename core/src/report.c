#include "veille/report.h"
#include <stdio.h>
#include <string.h>

static long append_pair(char *buf, size_t cap, size_t off, const char *key, const char *val) {
    if (!val || off >= cap) return off;
    int w = snprintf(buf + off, cap - off, "%s%s=%s", off ? "  " : "", key, val);
    return (w > 0 && (size_t)w < cap - off) ? off + (size_t)w : off;
}

static long append_long(char *buf, size_t cap, size_t off, const char *key, long val) {
    if (!val || off >= cap) return off;
    char b[32];
    snprintf(b, sizeof(b), "%ld", val);
    return append_pair(buf, cap, off, key, b);
}

long veille_report_text(const veille_verdict *v, size_t n, char *buf, size_t cap) {
    if (!v || !buf || cap == 0) return -1;
    size_t off = 0;
    int errors = 0;
    for (size_t i = 0; i < n && off < cap; i++) {
        const veille_verdict *x = &v[i];
        if (x->sev == VEILLE_SEV_ERROR) errors++;
        const char *sev = (x->sev == VEILLE_SEV_ERROR) ? "ERROR" :
                          (x->sev == VEILLE_SEV_WARNING) ? "WARN " : "INFO ";
        int w = snprintf(buf + off, cap - off, "%s  %s", sev, veille_verdict_name(x->code));
        if (w < 0 || (size_t)w >= cap - off) break;
        off += (size_t)w;
        off = append_pair(buf, cap, off, "chain", x->chain_id);
        off = append_pair(buf, cap, off, "stage", x->stage);
        off = append_pair(buf, cap, off, "state", x->state);
        off = append_long(buf, cap, off, "bound", x->bound_ms);
        off = append_long(buf, cap, off, "latency", x->latency_ms);
        off = append_long(buf, cap, off, "states", x->states_explored);
        off = append_pair(buf, cap, off, "config_sha256", x->config_sha256);
        if (off < cap - 1) { buf[off++] = '\n'; buf[off] = '\0'; }
    }
    if (errors == 0) {
        if (off + 3 < cap) { memcpy(buf + off, "OK\n", 3); off += 3; buf[off] = '\0'; }
    } else {
        int w = snprintf(buf + off, cap - off, "FAILED %d error(s)\n", errors);
        if (w > 0 && (size_t)w < cap - off) off += (size_t)w;
    }
    return (long)off;
}

long veille_report_json(const veille_verdict *v, size_t n, char *buf, size_t cap) {
    if (!v || !buf || cap == 0) return -1;
    size_t off = 0;
    for (size_t i = 0; i < n && off < cap; i++) {
        const veille_verdict *x = &v[i];
        int w = snprintf(buf + off, cap - off, "{\"code\":\"%s\",\"sev\":\"%s\"",
                         veille_verdict_name(x->code), veille_severity_name(x->sev));
        if (w < 0 || (size_t)w >= cap - off) break;
        off += (size_t)w;
        if (x->chain_id) {
            w = snprintf(buf + off, cap - off, ",\"chain_id\":\"%s\"", x->chain_id);
            if (w > 0 && (size_t)w < cap - off) off += (size_t)w;
        }
        if (x->bound_ms) {
            w = snprintf(buf + off, cap - off, ",\"bound_ms\":%ld", x->bound_ms);
            if (w > 0 && (size_t)w < cap - off) off += (size_t)w;
        }
        if (x->latency_ms) {
            w = snprintf(buf + off, cap - off, ",\"latency_ms\":%ld", x->latency_ms);
            if (w > 0 && (size_t)w < cap - off) off += (size_t)w;
        }
        if (x->states_explored) {
            w = snprintf(buf + off, cap - off, ",\"states_explored\":%ld", x->states_explored);
            if (w > 0 && (size_t)w < cap - off) off += (size_t)w;
        }
        const char *msg = x->message ? x->message : "";
        w = snprintf(buf + off, cap - off, ",\"message\":\"%s\"}\n", msg);
        if (w > 0 && (size_t)w < cap - off) off += (size_t)w; else break;
    }
    return (long)off;
}

long veille_report_markdown(const veille_verdict *v, size_t n,
                            const veille_report_meta *meta, char *buf, size_t cap) {
    if (!v || !buf || cap == 0) return -1;
    const char *cf = (meta && meta->config_file)   ? meta->config_file   : "inconnu";
    const char *cs = (meta && meta->config_sha256) ? meta->config_sha256 : "inconnu";
    const char *ts = (meta && meta->timestamp_utc) ? meta->timestamp_utc : "inconnu";
    const char *vv = (meta && meta->veille_version)? meta->veille_version: "inconnu";
    int errors = 0;
    long states = 0;
    for (size_t i = 0; i < n; i++) {
        if (v[i].sev == VEILLE_SEV_ERROR) errors++;
        if (v[i].states_explored) states = v[i].states_explored;
    }
    int w = snprintf(buf, cap,
        "# Rapport de preuve de latence — Veille\n\n"
        "- Configuration : %s\n- Empreinte SHA-256 : %s\n"
        "- Horodatage (UTC) : %s\n- Version de Veille : %s\n\n"
        "## Synthèse\n%s\n\n## Propriétés vérifiées\n"
        "### P1 — Latence d'alarme\n- Méthode : exploration exhaustive de %ld états\n"
        "- Résultat : %s\n",
        cf, cs, ts, vv, errors ? "FAILED" : "OK", states,
        errors ? "contre-exemple" : "borne tenue");
    return (w > 0) ? w : -1;
}

int veille_report_exit_code(const veille_verdict *v, size_t n) {
    if (!v) return 1;
    for (size_t i = 0; i < n; i++) if (v[i].sev == VEILLE_SEV_ERROR) return 1;
    return 0;
}
