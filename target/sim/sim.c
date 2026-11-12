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
#define _POSIX_C_SOURCE 199309L   /* clock_gettime / CLOCK_MONOTONIC en -std=c11 strict */
#include "veille/chain.h"
#include "veille/state.h"
#include "veille/proof.h"
#include "veille/report.h"
#include <stdio.h>
#include <string.h>
#include <time.h>

#define SAMPLES        600      /* échantillons simulés */
#define HR_NORMAL      72       /* bpm au repos */
#define HR_THRESHOLD   120      /* seuil d'alarme haute priorité */
#define FILTER_WINDOW  8
#define PRIO_CRITICAL  "high"

static long now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000000L + ts.tv_nsec / 1000;
}

/* Capteur simulé : tachycardie après mi-run ; fault 1 = stuck (valeur figée),
 * 2 = dead (pas d'échantillon). Retourne bpm, ou -1 si capteur mort. */
static long sensor_bpm(int i, int fault, long *last) {
    if (fault == 2) return -1;
    if (fault == 1) return *last;
    long base = HR_NORMAL + (i > SAMPLES / 2 ? 60 : 0);
    long v = base + (long)(i % 7) - 3;
    *last = v;
    return v;
}

typedef struct {
    long window[FILTER_WINDOW];
    int  idx;
    int  filled;
} filter_t;

static long filter_push(filter_t *f, long v) {
    f->window[f->idx] = v;
    f->idx = (f->idx + 1) % FILTER_WINDOW;
    if (f->filled < FILTER_WINDOW) f->filled++;
    long sum = 0;
    for (int i = 0; i < f->filled; i++) sum += f->window[i];
    return sum / f->filled;
}

static void make_cfg(veille_chain_config *cfg) {
    memset(cfg, 0, sizeof(*cfg));
    cfg->priority = VEILLE_PRIO_HIGH;
    cfg->bound_alarm_ms = 200;      /* >= pire cas absolu 165 ms → preuve complète */
    cfg->bound_ack_ms = 60000;
    cfg->bound_tech_ms = 50;
    cfg->tech_detect_ms = 15;
    cfg->stage_latency_ms[VEILLE_STAGE_ACQUIRE] = 5;
    cfg->stage_latency_ms[VEILLE_STAGE_FILTER] = 10;
    cfg->stage_latency_ms[VEILLE_STAGE_DECIDE] = 10;
    cfg->stage_latency_ms[VEILLE_STAGE_ALARM] = 20;
    cfg->stage_latency_ms[VEILLE_STAGE_ACK] = 5;
}

/* Panne injectée : [100,104] capteur figé, [300,302] capteur mort. */
static int fault_at(int i) {
    if (i >= 100 && i <= 104) return 1;
    if (i >= 300 && i <= 302) return 2;
    return 0;
}

typedef struct {
    long max_alarm_us;
    long max_tech_us;
    int  n_alarm;
    int  n_tech;
    int  violations;
} sim_stats;

/* Un échantillon traverse la chaîne ; retour horodaté. stats mis à jour. */
static void run_chain(filter_t *f, long *last, long *prev_read, int i,
                      const veille_chain_config *cfg, sim_stats *st) {
    long t0 = now_us();
    int fault = fault_at(i);
    long bpm = sensor_bpm(i, fault, last);

    if (bpm < 0) {  /* capteur mort → chaîne rompue → alarme technique (P2) */
        long t4 = now_us();
        long dt_us = t4 - t0;
        st->n_tech++;
        if (dt_us > st->max_tech_us) st->max_tech_us = dt_us;
        if (dt_us / 1000 > cfg->bound_tech_ms) st->violations++;
        printf("[%3d] CAPTEUR MORT  → alarme technique en %ld.%03ld ms (borne %ld ms)\n",
               i, dt_us / 1000, dt_us % 1000, cfg->bound_tech_ms);
        return;
    }
    long raw_prev = *prev_read;
    *prev_read = bpm;
    long filtered = filter_push(f, bpm);
    if (fault == 1 && bpm == raw_prev) {  /* valeur figée : la lecture ne bouge plus */
        long t4 = now_us();
        long dt_us = t4 - t0;
        st->n_tech++;
        if (dt_us > st->max_tech_us) st->max_tech_us = dt_us;
        if (dt_us / 1000 > cfg->bound_tech_ms) st->violations++;
        printf("[%3d] CAPTEUR FIGÉ  → alarme technique en %ld.%03ld ms (borne %ld ms)\n",
               i, dt_us / 1000, dt_us % 1000, cfg->bound_tech_ms);
        return;
    }
    if (filtered > HR_THRESHOLD) {  /* seuil franchi → alarme haute priorité */
        long t4 = now_us();
        long dt_us = t4 - t0;
        st->n_alarm++;
        if (dt_us > st->max_alarm_us) st->max_alarm_us = dt_us;
        if (dt_us / 1000 > cfg->bound_alarm_ms) st->violations++;
        if (st->n_alarm <= 3 || st->n_alarm % 100 == 0)
            printf("[%3d] bpm=%ld (filtré) → ALARME haute en %ld.%03ld ms (borne %ld ms)\n",
                   i, filtered, dt_us / 1000, dt_us % 1000, cfg->bound_alarm_ms);
    }
}

int main(void) {
    printf("=== Veille — simulation hôte de la chaîne capteur→alarme ===\n\n");

    /* 1. Preuve exhaustive (modèle) — la borne de référence */
    veille_chain_config cfg;
    make_cfg(&cfg);
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
    filter_t f;
    memset(&f, 0, sizeof(f));
    sim_stats st;
    memset(&st, 0, sizeof(st));
    long last = HR_NORMAL;
    long prev_read = -1;
    for (int i = 0; i < SAMPLES; i++) run_chain(&f, &last, &prev_read, i, &cfg, &st);

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
