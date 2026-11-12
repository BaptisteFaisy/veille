/* Veille — resource manager QNX 8.0 : chaîne acquire→filter→decide→verdict.
 *
 * Un échantillon (poussé par un write client OU par le tick du timer noyau)
 * traverse target/pipe/veille_pipe.c (partagé avec la sim hôte — zéro
 * duplication) ; l'horodatage vient de target/port/qnx_time.c (core/ reste
 * pur : ni horloge ni fichier ni socket). Le verdict est mis en forme au
 * FORMAT TEXTE DU CONTRAT par core/report.c (veille_report_text). */
#include <string.h>
#include <stdio.h>

#include "veille_rm.h"
#include "veille/report.h"
#include "port_time.h"

/* Remplit un verdict ; le texte du message fait partie du verdict (report). */
static void fill_verdict(veille_verdict *v, veille_verdict_code code, const char *message,
                         veille_sensor_state sensor, veille_alarm_state alarm,
                         long bound_ms, long latency_ms) {
    static char statebuf[128];   /* un seul serveur, un seul fil de traitement */
    veille_fault_state st;
    memset(&st, 0, sizeof(st));
    st.sensor = sensor;
    st.alarm = alarm;
    veille_state_to_string(&st, statebuf, sizeof(statebuf));

    memset(v, 0, sizeof(*v));
    v->code = code;
    v->sev = veille_verdict_default_severity(code);
    v->message = message;
    v->chain_id = VEILLE_MOUNT_POINT;
    v->stage = veille_stage_name(sensor == VEILLE_SENSOR_OK ? VEILLE_STAGE_ALARM
                                                            : VEILLE_STAGE_ACQUIRE);
    v->state = statebuf;
    v->bound_ms = bound_ms;
    v->latency_ms = latency_ms;
}

/* Met en forme les verdicts dans dev->report (format texte du CONTRAT). */
static void format_verdicts(veille_dev_t *dev, const veille_verdict *v, size_t n) {
    long len = veille_report_text(v, n, dev->report, sizeof(dev->report));
    dev->report_len = (len > 0 && len < (long)sizeof(dev->report)) ? len : 0;
}

void veille_rm_init(veille_dev_t *dev) {
    memset(dev, 0, sizeof(*dev));
    iofunc_attr_init(&dev->attr,
                     S_IFNAM | S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP | S_IROTH | S_IWOTH,
                     NULL, NULL);
    veille_pipe_default_config(&dev->cfg);
    veille_pipe_state_init(&dev->pipe);
    dev->last_bpm = VEILLE_HR_NORMAL;
    veille_verdict v;
    fill_verdict(&v, VEILLE_OK, "chaîne prête — aucun échantillon",
                 VEILLE_SENSOR_OK, VEILLE_ALARM_NONE, dev->cfg.bound_alarm_ms, 0);
    format_verdicts(dev, &v, 1);
}

/* Pousse un échantillon brut dans la chaîne, horodate, construit le verdict. */
void veille_rm_push(veille_dev_t *dev, long raw_bpm) {
    long t0 = veille_now_us();                       /* horodatage d'arrivée */
    veille_pipe_result r = veille_pipe_push(&dev->pipe, raw_bpm);
    long dt_ms = (veille_now_us() - t0) / 1000;      /* L_measured */
    dev->n_samples++;

    const veille_chain_config *c = &dev->cfg;
    veille_verdict v[2];
    size_t n = 0;
    if (r == VEILLE_PIPE_ALARM) {                    /* seuil franchi → alarme haute */
        fill_verdict(&v[n++], dt_ms <= c->bound_alarm_ms ? VEILLE_OK
                                                         : VEILLE_LATENCY_BOUND_EXCEEDED,
                     "alarme haute priorité — seuil franchi",
                     VEILLE_SENSOR_OK, VEILLE_ALARM_SINGLE, c->bound_alarm_ms, dt_ms);
    } else if (r == VEILLE_PIPE_TECH_STUCK || r == VEILLE_PIPE_TECH_DEAD) {
        fill_verdict(&v[n++], VEILLE_TECHNICAL_ALARM,
                     r == VEILLE_PIPE_TECH_DEAD ? "capteur mort" : "capteur figé",
                     r == VEILLE_PIPE_TECH_DEAD ? VEILLE_SENSOR_DEAD : VEILLE_SENSOR_STUCK,
                     VEILLE_ALARM_NONE, c->bound_tech_ms, dt_ms);
        if (dt_ms > c->bound_tech_ms)                /* borne technique dépassée */
            fill_verdict(&v[n++], VEILLE_LATENCY_BOUND_EXCEEDED, "B_tech dépassée",
                         VEILLE_SENSOR_OK, VEILLE_ALARM_NONE, c->bound_tech_ms, dt_ms);
    } else {
        fill_verdict(&v[n++], VEILLE_OK, "échantillon traité — seuil non franchi",
                     VEILLE_SENSOR_OK, VEILLE_ALARM_NONE, c->bound_alarm_ms, dt_ms);
    }
    format_verdicts(dev, v, n);
}

/* Tick du timer noyau : capteur simulé (cycle de VEILLE_TICK_CYCLE échantillons,
 * pannes injectées incluses — même modèle que la sim hôte). */
void veille_rm_tick(veille_dev_t *dev) {
    int i = dev->tick_index % VEILLE_TICK_CYCLE;
    dev->tick_index++;
    long bpm = veille_pipe_sensor_bpm(i, VEILLE_TICK_CYCLE,
                                      veille_pipe_fault_at(i), &dev->last_bpm);
    veille_rm_push(dev, bpm);
}

/* CHANNEL disconnect : le noyau notifie la mort d'un pair → alarme technique
 * dans B_tech (P2), au lieu d'attendre en silence. */
void veille_rm_peer_lost(veille_dev_t *dev) {
    dev->n_disconnects++;
    veille_verdict v;
    fill_verdict(&v, VEILLE_TECHNICAL_ALARM, "mort d'un pair — CHANNEL disconnect",
                 VEILLE_SENSOR_OK, VEILLE_ALARM_NONE, dev->cfg.bound_tech_ms, 0);
    format_verdicts(dev, &v, 1);
}
