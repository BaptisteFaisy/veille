/* Veille — simulation hôte portable de la chaîne capteur→alarme.
 *
 * Démo SANS QNX (socle S) : produit des échantillons physiologiques simulés, les fait
 * traverser la chaîne acquire→filter→decide→alarm avec horodatage monotone, mesure la
 * latence réelle L_measured, injecte des pannes de capteur, et confronte le résultat à
 * la borne prouvée B_proof par l'exploration exhaustive (core/proof.c).
 *
 * Sur cible QNX 8.0 (niveau C), la même chaîne est portée dans target/rm/resmgr_veille.c
 * avec pulses/timers noyau et priority inheritance MsgSend ; la latence mesurée par
 * kernel trace (tracelogger) doit rester <= B_proof. Voir docs/SAFETY.md §5-6.
 *
 * Build : make sim    Run : make demo
 */
#include "veille/chain.h"
#include "veille/state.h"
#include "veille/proof.h"
#include "veille/report.h"
#include "veille_pipe.h"
#include "port_time.h"
#include <stdio.h>
#include <string.h>

#define SAMPLES        600      /* échantillons simulés */

typedef struct {
    long max_alarm_us;
    long max_tech_us;
    int  n_alarm;
    int  n_tech;
    int  violations;
} sim_stats;

/* Un échantillon traverse la chaîne ; retour horodaté. stats mis à jour. */
static void run_chain(veille_pipe_state *ps, long *last, int i,
                      const veille_chain_config *cfg, sim_stats *st) {
    long t0 = veille_now_us();
    long bpm = veille_pipe_sensor_bpm(i, SAMPLES, veille_pipe_fault_at(i), last);
    veille_pipe_result r = veille_pipe_push(ps, bpm);
    long dt_us = veille_now_us() - t0;

    if (r == VEILLE_PIPE_TECH_DEAD || r == VEILLE_PIPE_TECH_STUCK) {
        st->n_tech++;
        if (dt_us > st->max_tech_us) st->max_tech_us = dt_us;
        if (dt_us / 1000 > cfg->bound_tech_ms) st->violations++;
        printf("[%3d] %-13s → alarme technique en %ld.%03ld ms (borne %ld ms)\n",
               i, r == VEILLE_PIPE_TECH_DEAD ? "CAPTEUR MORT " : "CAPTEUR FIGÉ ",
               dt_us / 1000, dt_us % 1000, cfg->bound_tech_ms);
        return;
    }
    if (r == VEILLE_PIPE_ALARM) {  /* seuil franchi → alarme haute priorité */
        st->n_alarm++;
        if (dt_us > st->max_alarm_us) st->max_alarm_us = dt_us;
        if (dt_us / 1000 > cfg->bound_alarm_ms) st->violations++;
        if (st->n_alarm <= 3 || st->n_alarm % 100 == 0)
            printf("[%3d] bpm=%ld (filtré) → ALARME haute en %ld.%03ld ms (borne %ld ms)\n",
                   i, veille_pipe_filtered(ps), dt_us / 1000, dt_us % 1000, cfg->bound_alarm_ms);
    }
}

int main(void) {
    printf("=== Veille — simulation hôte de la chaîne capteur→alarme ===\n\n");

    /* 1. Preuve exhaustive (modèle) — la borne de référence */
    veille_chain_config cfg;
    veille_pipe_default_config(&cfg);
    veille_fault_mask mask = {1, 1, 1, 1, 1};
    veille_verdict v[2];
    size_t nv = 0;
    int rc = veille_proof_explore(&cfg, &mask, v, 2, &nv);
    char buf[1024];
    long len = veille_report_text(v, nv, buf, sizeof(buf));
    printf("--- preuve modèle (exploration exhaustive) ---\n%.*s\n", (int)len, buf);
    if (rc != 0) { printf("[ÉCHEC] la borne n'est pas prouvée, simulation annulée.\n"); return 1; }

    /* 2. Simulation : latences réelles confrontées à la borne prouvée */
    printf("--- simulation (%d échantillons, pannes injectées) ---\n", SAMPLES);
    veille_pipe_state ps;
    veille_pipe_state_init(&ps);
    sim_stats st;
    memset(&st, 0, sizeof(st));
    long last = VEILLE_HR_NORMAL;
    for (int i = 0; i < SAMPLES; i++) run_chain(&ps, &last, i, &cfg, &st);

    /* 3. Bilan : double preuve (modèle + mesure) */
    printf("\n--- bilan ---\n");
    printf("alarmes physiologiques : %d (latence max %ld.%03ld ms, borne prouvée %ld ms)\n",
           st.n_alarm, st.max_alarm_us / 1000, st.max_alarm_us % 1000, cfg.bound_alarm_ms);
    printf("alarmes techniques     : %d (latence max %ld.%03ld ms, borne %ld ms)\n",
           st.n_tech, st.max_tech_us / 1000, st.max_tech_us % 1000, cfg.bound_tech_ms);
    printf("marge de sûreté        : %ld ms (borne prouvée - latence mesurée max)\n",
           cfg.bound_alarm_ms - st.max_alarm_us / 1000);
    if (st.violations == 0) {
        printf("[OK] L_measured <= B_proof sur tous les échantillons — double preuve cohérente.\n");
        return 0;
    }
    printf("[ÉCHEC] %d violation(s) de borne mesurée(s).\n", st.violations);
    return 1;
}
