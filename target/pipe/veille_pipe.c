/* Pipeline portable acquire→filter→decide — voir veille_pipe.h.
 * Extrait de target/sim/sim.c pour être partagé à l'identique entre la
 * simulation hôte et le resource manager QNX (zéro duplication). */
#include "veille_pipe.h"
#include <string.h>

void veille_pipe_default_config(veille_chain_config *cfg) {
    if (!cfg) return;
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

void veille_pipe_state_init(veille_pipe_state *st) {
    if (!st) return;
    memset(st, 0, sizeof(*st));
    st->last_raw = -1;   /* aucune lecture brute encore vue */
    st->last_bpm = 0;
    st->sensor = VEILLE_SENSOR_OK;
    veille_signal_buffer_init(&st->signal, 0);   /* 250 Hz par défaut */
}

void veille_pipe_set_fs(veille_pipe_state *st, long fs_hz) {
    if (!st) return;
    veille_signal_buffer_init(&st->signal, fs_hz);
}

/* Pousse une valeur dans la fenêtre glissante. */
static long filter_push(veille_pipe_filter *f, long v) {
    f->window[f->idx] = v;
    f->idx = (f->idx + 1) % VEILLE_FILTER_WINDOW;
    if (f->filled < VEILLE_FILTER_WINDOW) f->filled++;
    long sum = 0;
    for (int i = 0; i < f->filled; i++) sum += f->window[i];
    return sum / f->filled;
}

long veille_pipe_filtered(const veille_pipe_state *st) {
    if (!st || st->filter.filled == 0) return 0;
    long sum = 0;
    for (int i = 0; i < st->filter.filled; i++) sum += st->filter.window[i];
    return sum / st->filter.filled;
}

veille_pipe_result veille_pipe_push(veille_pipe_state *st, long raw_bpm) {
    if (!st) return VEILLE_PIPE_OK;
    if (raw_bpm < 0) return VEILLE_PIPE_TECH_DEAD;   /* capteur mort : rien à filtrer */
    long prev = st->last_raw;
    st->last_raw = raw_bpm;
    long filtered = filter_push(&st->filter, raw_bpm);
    st->index++;
    /* Valeur figée : la lecture ne bouge plus → alarme technique (P2).
     * Détection honnête sur la valeur (le capteur sain varie toujours). */
    if (prev >= 0 && raw_bpm == prev) return VEILLE_PIPE_TECH_STUCK;
    return (filtered > VEILLE_HR_THRESHOLD) ? VEILLE_PIPE_ALARM : VEILLE_PIPE_OK;
}

long veille_pipe_sensor_bpm(int i, int samples, int fault, long *last) {
    if (fault == 2) return -1;
    if (fault == 1) return last ? *last : -1;
    long base = VEILLE_HR_NORMAL + (i > samples / 2 ? 60 : 0);
    long v = base + (long)(i % 7) - 3;
    if (last) *last = v;
    return v;
}

int veille_pipe_fault_at(int i) {
    if (i >= 100 && i <= 104) return 1;   /* capteur figé */
    if (i >= 300 && i <= 302) return 2;   /* capteur mort */
    return 0;
}

/* Traduit un état capteur fautif en résultat de pipeline (alarme technique). */
static veille_pipe_result tech_result(veille_sensor_state s) {
    switch (s) {
        case VEILLE_SENSOR_DEAD:  return VEILLE_PIPE_TECH_DEAD;
        case VEILLE_SENSOR_STUCK: return VEILLE_PIPE_TECH_STUCK;
        case VEILLE_SENSOR_NOISY: return VEILLE_PIPE_TECH_NOISY;
        case VEILLE_SENSOR_DRIFT: return VEILLE_PIPE_TECH_DRIFT;
        default: return VEILLE_PIPE_OK;
    }
}

/* Chemin SIGNAL BRUT : l'état capteur vient des échantillons (pas du bpm),
 * la fréquence des pics R, puis la décision de seuil sur le bpm filtré. */
veille_pipe_result veille_pipe_push_sample(veille_pipe_state *st, int16_t brut) {
    if (!st) return VEILLE_PIPE_OK;
    veille_signal_push(&st->signal, brut);
    st->index++;
    st->sensor = veille_signal_sensor_state(&st->signal);
    if (st->sensor != VEILLE_SENSOR_OK) return tech_result(st->sensor);
    long bpm = veille_signal_rate_bpm(&st->signal);
    if (bpm > 0) {
        st->last_bpm = bpm;
        filter_push(&st->filter, bpm);   /* filtre moyenneur glissant sur le bpm */
    }
    long filtered = veille_pipe_filtered(st);
    return (filtered > VEILLE_HR_THRESHOLD) ? VEILLE_PIPE_ALARM : VEILLE_PIPE_OK;
}

long veille_pipe_rate_bpm(const veille_pipe_state *st) {
    return st ? st->last_bpm : 0;
}

veille_sensor_state veille_pipe_sensor_state(const veille_pipe_state *st) {
    return st ? st->sensor : VEILLE_SENSOR_OK;
}
