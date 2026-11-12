#include "veille/proof.h"
#include "veille/report.h"
#include <stdio.h>
#include <string.h>
#include <assert.h>

static void make_cfg(veille_chain_config *cfg, long bound) {
    memset(cfg, 0, sizeof(*cfg));
    cfg->priority = VEILLE_PRIO_HIGH;
    cfg->bound_alarm_ms = bound;
    cfg->bound_ack_ms = 60000;
    cfg->bound_tech_ms = 50;
    cfg->tech_detect_ms = 15;
    cfg->stage_latency_ms[VEILLE_STAGE_ACQUIRE] = 5;
    cfg->stage_latency_ms[VEILLE_STAGE_FILTER] = 10;
    cfg->stage_latency_ms[VEILLE_STAGE_DECIDE] = 10;
    cfg->stage_latency_ms[VEILLE_STAGE_ALARM] = 20;
    cfg->stage_latency_ms[VEILLE_STAGE_ACK] = 5;
}

int main(void) {
    veille_chain_config cfg;
    make_cfg(&cfg, 100);
    assert(veille_chain_config_valid(&cfg));
    assert(veille_chain_latency_ms(&cfg) == 50);

    /* Exploration COMPLÈTE : 5 capteur × 3 bus × 2 prio × 5 alarme × 32 masques = 4800.
     * Pire cas absolu 165 ms > 100 ms → contre-exemple attendu (premier à 105 ms). */
    veille_fault_mask mask = {1, 1, 1, 1, 1};
    veille_verdict out[4];
    size_t n = 0;
    int rc = veille_proof_explore(&cfg, &mask, out, 4, &n);
    printf("rc=%d n=%zu states=%ld code=%s latency=%ld\n",
           rc, n, out[0].states_explored, veille_verdict_name(out[0].code), out[0].latency_ms);
    assert(rc == 1);
    assert(out[0].code == VEILLE_PROOF_COUNTEREXAMPLE);
    assert(out[0].states_explored == 4800);
    assert(out[0].latency_ms == 105);

    char buf[2048];
    long len = veille_report_text(out, n, buf, sizeof(buf));
    assert(len > 0);
    printf("--- report_text ---\n%.*s", (int)len, buf);
    len = veille_report_json(out, n, buf, sizeof(buf));
    assert(len > 0);
    printf("--- report_json ---\n%.*s", (int)len, buf);

    /* Cas passant : borne 200 ms ≥ pire cas absolu 165 ms → preuve complète. */
    make_cfg(&cfg, 200);
    rc = veille_proof_explore(&cfg, &mask, out, 4, &n);
    printf("rc(200ms)=%d code=%s states=%ld\n", rc, veille_verdict_name(out[0].code), out[0].states_explored);
    assert(rc == 0);
    assert(out[0].code == VEILLE_PROOF_COMPLETE);
    assert(out[0].states_explored == 4800);

    /* P2 : détection technique (60 ms) hors borne technique (50 ms) → contre-exemple P2. */
    make_cfg(&cfg, 1000);
    cfg.tech_detect_ms = 60;
    rc = veille_proof_explore(&cfg, &mask, out, 4, &n);
    printf("rc(P2)=%d code=%s msg=%s\n", rc, veille_verdict_name(out[0].code), out[0].message);
    assert(rc == 1);
    assert(out[0].code == VEILLE_PROOF_COUNTEREXAMPLE);
    assert(strstr(out[0].message, "P2") != NULL);

    /* Rapport Markdown sur le cas passant */
    make_cfg(&cfg, 1000);
    rc = veille_proof_explore(&cfg, &mask, out, 4, &n);
    assert(rc == 0);
    veille_report_meta meta = {"cfg.json", "a3f9", "2026-11-12T00:00:00Z", "0.1.0"};
    len = veille_report_markdown(out, n, &meta, buf, sizeof(buf));
    assert(len > 0);
    printf("--- report_markdown ---\n%.*s", (int)len, buf);
    assert(veille_report_exit_code(out, n) == 0);

    printf("[OK] test_proof vert (4800 états, P1 + P2)\n");
    return 0;
}
