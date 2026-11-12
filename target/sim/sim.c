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
#include "veille/signal.h"
#include "veille/signal_gen.h"
#include "veille_pipe.h"
#include "port_time.h"
#include <stdio.h>
#include <string.h>

#define SAMPLES        600      /* échantillons simulés */

/* Banc signal brut : 250 Hz, 1024 échantillons (~4 s), pic R à 1200 codes. */
#define SIG_FS         250
#define SIG_AMP        1200
#define SIG_SAMPLES    1024

typedef struct {
    long max_alarm_us;
    long max_tech_us;
    int  n_alarm;
    int  n_tech;
    int  violations;
    int  erreurs;      /* scénarios dont le verdict ne correspond pas à l'attendu */
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

/* --- Banc SIGNAL BRUT : c'est là que se joue le défaut corrigé ---------- */

/* Un scénario de signal : générateur → chaîne → verdict attendu. */
typedef struct {
    const char        *nom;
    veille_siggen_kind kind;
    long               rate_bpm;
    veille_pipe_result attendu;    /* résultat de pipeline attendu */
    const char        *libelle;    /* libellé du verdict */
    const char        *cause;      /* message porté par le verdict */
} scenario_signal;

static const scenario_signal SCENARIOS_SIGNAL[] = {
    { "plat",     VEILLE_SIGGEN_FLAT,  60, VEILLE_PIPE_TECH_STUCK, "capteur figé",  "capteur figé — signal plat" },
    { "tachy",    VEILLE_SIGGEN_ECG,  180, VEILLE_PIPE_ALARM,     "alarme haute",  "alarme haute priorité — seuil franchi" },
    { "mort",     VEILLE_SIGGEN_DEAD,  60, VEILLE_PIPE_TECH_DEAD,  "capteur mort",  "capteur mort — signal nul" },
    { "regulier", VEILLE_SIGGEN_ECG,   60, VEILLE_PIPE_OK,        "aucune alarme", "échantillon traité — seuil non franchi" }
};
#define NB_SCENARIOS_SIGNAL ((int)(sizeof(SCENARIOS_SIGNAL) / sizeof(SCENARIOS_SIGNAL[0])))

/* Verdict texte (CONTRAT §6.1) à partir de l'état capteur déduit du signal. */
static void fill_verdict_signal(veille_verdict *v, veille_verdict_code code, const char *msg,
                                veille_sensor_state sensor, long bound_ms, long latency_ms) {
    static char statebuf[128];
    veille_fault_state fs;
    memset(&fs, 0, sizeof(fs));
    fs.sensor = sensor;
    veille_state_to_string(&fs, statebuf, sizeof(statebuf));
    memset(v, 0, sizeof(*v));
    v->code = code;
    v->sev = veille_verdict_default_severity(code);
    v->message = msg;
    v->chain_id = "sim_signal";
    v->stage = veille_stage_name(sensor == VEILLE_SENSOR_OK ? VEILLE_STAGE_ALARM
                                                             : VEILLE_STAGE_DECIDE);
    v->state = statebuf;
    v->bound_ms = bound_ms;
    v->latency_ms = latency_ms;
}

static int est_technique(veille_pipe_result r) {
    return (r == VEILLE_PIPE_TECH_STUCK || r == VEILLE_PIPE_TECH_DEAD ||
            r == VEILLE_PIPE_TECH_NOISY || r == VEILLE_PIPE_TECH_DRIFT) ? 1 : 0;
}

/* Rejoue un scénario signal brut ; renvoie 1 si le verdict est conforme. */
static int run_scenario_signal(const scenario_signal *sc, const veille_chain_config *cfg) {
    veille_pipe_state ps;
    veille_pipe_state_init(&ps);
    veille_pipe_set_fs(&ps, SIG_FS);
    veille_signal_gen g;
    veille_signal_gen_init(&g, sc->kind, SIG_FS, sc->rate_bpm, SIG_AMP);
    veille_pipe_result r = VEILLE_PIPE_OK;
    long dt_us = 0, dt_alarme = -1;
    for (int i = 0; i < SIG_SAMPLES; i++) {
        int16_t s = veille_signal_gen_next(&g);
        long t0 = veille_now_us();
        r = veille_pipe_push_sample(&ps, s);
        dt_us = veille_now_us() - t0;
        if (r != VEILLE_PIPE_OK && dt_alarme < 0) dt_alarme = dt_us;
    }
    long lat = (dt_alarme >= 0) ? dt_alarme : dt_us;
    long borne = est_technique(r) ? cfg->bound_tech_ms : cfg->bound_alarm_ms;
    veille_verdict v;
    if (est_technique(r))
        fill_verdict_signal(&v, VEILLE_TECHNICAL_ALARM, sc->cause,
                             veille_pipe_sensor_state(&ps), borne, lat);
    else
        fill_verdict_signal(&v, VEILLE_OK, sc->cause, VEILLE_SENSOR_OK, borne, lat);
    char buf[1024];
    long len = veille_report_text(&v, 1, buf, sizeof(buf));
    printf("[%-8s] capteur=%-12s bpm=%3ld → %-13s (latence %ld.%03ld ms, borne %ld ms)\n",
           sc->nom, veille_sensor_state_name(veille_pipe_sensor_state(&ps)),
           veille_pipe_rate_bpm(&ps), sc->libelle, lat / 1000, lat % 1000, borne);
    printf("%.*s", (int)len, buf);
    if (r != sc->attendu) {
        printf("[ÉCHEC] scénario %s : résultat %d, attendu %d\n", sc->nom, (int)r, (int)sc->attendu);
        return 0;
    }
    if (lat / 1000 > borne) {
        printf("[ÉCHEC] scénario %s : latence %ld ms > borne %ld ms\n", sc->nom, lat / 1000, borne);
        return 0;
    }
    return 1;
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

    /* 3. Banc signal brut : capteur figé (et non alarme) / tachycardie / mort */
    printf("\n--- signal brut (%d Hz, %d échantillons) : défaut « capteur figé » corrigé ---\n",
           SIG_FS, SIG_SAMPLES);
    int n_signal_ok = 0;
    for (int i = 0; i < NB_SCENARIOS_SIGNAL; i++)
        if (run_scenario_signal(&SCENARIOS_SIGNAL[i], &cfg)) n_signal_ok++;
    if (n_signal_ok != NB_SCENARIOS_SIGNAL) st.erreurs++;

    /* 4. Bilan : double preuve (modèle + mesure) */
    printf("\n--- bilan ---\n");
    printf("alarmes physiologiques : %d (latence max %ld.%03ld ms, borne prouvée %ld ms)\n",
           st.n_alarm, st.max_alarm_us / 1000, st.max_alarm_us % 1000, cfg.bound_alarm_ms);
    printf("alarmes techniques     : %d (latence max %ld.%03ld ms, borne %ld ms)\n",
           st.n_tech, st.max_tech_us / 1000, st.max_tech_us % 1000, cfg.bound_tech_ms);
    printf("marge de sûreté        : %ld ms (borne prouvée - latence mesurée max)\n",
           cfg.bound_alarm_ms - st.max_alarm_us / 1000);
    if (st.violations == 0 && st.erreurs == 0) {
        printf("[OK] L_measured <= B_proof sur tous les échantillons — double preuve cohérente.\n");
        return 0;
    }
    if (st.erreurs > 0) printf("[ÉCHEC] %d scénario(s) signal au verdict inattendu.\n", st.erreurs);
    else printf("[ÉCHEC] %d violation(s) de borne mesurée(s).\n", st.violations);
    return 1;
}
