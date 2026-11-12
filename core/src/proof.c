#include "veille/proof.h"
#include "veille/alarm.h"
#include <string.h>

/* Espace complet des pannes d'étage : 2^VEILLE_STAGE__COUNT = 32 masques. */
#define STAGE_MASK_SPACE (1u << VEILLE_STAGE__COUNT)

typedef struct {
    const veille_chain_config *cfg;
    const veille_fault_mask   *mask;
    long bound;
    long states;
    long broken_states;      /* états à chaîne rompue (alarme technique, P2) */
    int  counterexample;
    veille_fault_state ce_state;
    long ce_latency;
} explore_ctx;

static void explore_dim(explore_ctx *ctx, veille_fault_state *st, int dim) {
    if (dim == 5) {
        ctx->states++;
        long lat = veille_state_worst_latency_ms(ctx->cfg, st);
        if (lat < 0) { ctx->broken_states++; return; }  /* P2 vérifiée globalement */
        if (lat > ctx->bound && !ctx->counterexample) {
            ctx->counterexample = 1;
            ctx->ce_state = *st;
            ctx->ce_latency = lat;
        }
        return;
    }
    int max = 1;
    switch (dim) {
        case 0: if (ctx->mask->explore_sensor) max = VEILLE_SENSOR__COUNT; break;
        case 1: if (ctx->mask->explore_bus)    max = VEILLE_BUS__COUNT; break;
        case 2: if (ctx->mask->explore_prio)   max = VEILLE_PRIO_MODE__COUNT; break;
        case 3: if (ctx->mask->explore_alarm)  max = VEILLE_ALARM__COUNT; break;
        case 4: if (ctx->mask->explore_stage)  max = (int)STAGE_MASK_SPACE; break;
        default: break;
    }
    for (int v = 0; v < max; v++) {
        switch (dim) {
            case 0: st->sensor = (veille_sensor_state)v; break;
            case 1: st->bus = (veille_bus_state)v; break;
            case 2: st->prio = (veille_prio_mode)v; break;
            case 3: st->alarm = (veille_alarm_state)v; break;
            case 4: st->stage_fault_mask = (unsigned)v; break;
            default: break;
        }
        explore_dim(ctx, st, dim + 1);
    }
}

int veille_proof_explore(const veille_chain_config *cfg, const veille_fault_mask *mask,
                         veille_verdict *out, size_t cap, size_t *n_out) {
    if (!cfg || !mask || !out || !n_out) return -1;
    if (!veille_chain_config_valid(cfg)) return -1;
    *n_out = 0;
    explore_ctx ctx;
    memset(&ctx, 0, sizeof(ctx));
    ctx.cfg = cfg;
    ctx.mask = mask;
    ctx.bound = cfg->bound_alarm_ms;
    veille_fault_state st;
    memset(&st, 0, sizeof(st));
    explore_dim(&ctx, &st, 0);

    /* P2 : si la chaîne peut se rompre, l'alarme technique doit tenir sa propre borne. */
    int tech_violation = (ctx.broken_states > 0 && cfg->tech_detect_ms > cfg->bound_tech_ms);
    int failed = ctx.counterexample || tech_violation;

    if (cap >= 1) {
        memset(&out[0], 0, sizeof(out[0]));
        out[0].states_explored = ctx.states;
        out[0].bound_ms = ctx.bound;
        if (failed) {
            out[0].code = VEILLE_PROOF_COUNTEREXAMPLE;
            out[0].sev = VEILLE_SEV_ERROR;
            if (tech_violation && !ctx.counterexample) {
                out[0].message = "alarme technique hors borne (P2)";
                out[0].bound_ms = cfg->bound_tech_ms;
                out[0].latency_ms = cfg->tech_detect_ms;
            } else {
                out[0].message = "contre-exemple trouvé";
                out[0].latency_ms = ctx.ce_latency;
            }
        } else {
            out[0].code = VEILLE_PROOF_COMPLETE;
            out[0].sev = VEILLE_SEV_INFO;
            out[0].message = "borne tenue sur tous les états";
        }
        *n_out = 1;
    }
    return failed ? 1 : 0;
}
