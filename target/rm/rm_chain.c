/* Veille — resource manager QNX 8.0 : chaîne acquire→filter→decide→verdict.
 *
 * Un échantillon (poussé par un write client OU par le tick du timer noyau)
 * traverse target/pipe/veille_pipe.c (partagé avec la sim hôte — zéro
 * duplication) ; l'horodatage vient de target/port/qnx_time.c (core/ reste
 * pur : ni horloge ni fichier ni socket). Le verdict est mis en forme au
 * FORMAT TEXTE DU CONTRAT par core/report.c (veille_report_text).
 *
 * Ce fichier porte aussi les mesures de la chaîne de preuve :
 *   - E3 : régularité réelle du tick noyau (intervalles, écart, ppm) ;
 *   - E4 : watchdog « capteur muet » (perte de signal) ;
 *   - E2 : observation de la priorité effective (héritage du noyau) ;
 *   - H2 : latences réelles de la chaîne (échantillon → verdict). */
#include <string.h>
#include <stdio.h>
#include <pthread.h>
#include <sched.h>

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

/* Met en forme les verdicts dans dev->report (format texte du CONTRAT).
 * Le rapport porte le verdict de la chaîne PUIS, s'il y en a une, l'alarme
 * technique courante (B_tech) : une alarme technique ne masque pas l'état du
 * capteur, et l'état du capteur n'efface pas l'alarme. */
static void format_verdicts(veille_dev_t *dev, const veille_verdict *v, size_t n) {
    veille_verdict all[3];
    size_t k = 0;
    for (size_t i = 0; i < n && k < 2; i++) all[k++] = v[i];
    if (dev->tech_kind != VEILLE_TECH_NONE && k < 3) all[k++] = dev->tech_v;
    long len = veille_report_text(all, k, dev->report, sizeof(dev->report));
    dev->report_len = (len > 0 && len < (long)sizeof(dev->report)) ? len : 0;
}

/* Alarme technique courante : la plus grave reste visible. La perte de
 * signal (capteur muet) prime sur la mort d'un pair. */
void veille_rm_set_tech(veille_dev_t *dev, int kind, const char *msg,
                        veille_sensor_state sensor, long bound_ms, long latency_ms) {
    if (dev->tech_kind == VEILLE_TECH_SILENCE && kind == VEILLE_TECH_DISCONNECT)
        return;                       /* ne masque pas une alarme de silence */
    snprintf(dev->tech_msg, sizeof(dev->tech_msg), "%s", msg);
    fill_verdict(&dev->tech_v, VEILLE_TECHNICAL_ALARM, dev->tech_msg,
                 sensor, VEILLE_ALARM_NONE, bound_ms, latency_ms);
    dev->tech_kind = kind;
}

/* Levée d'une alarme technique (le signal est revenu). */
void veille_rm_clear_tech(veille_dev_t *dev, int kind) {
    if (dev->tech_kind != kind) return;
    dev->tech_kind = VEILLE_TECH_NONE;
    dev->tech_v.message = NULL;
}

void veille_rm_init(veille_dev_t *dev) {
    memset(dev, 0, sizeof(*dev));
    iofunc_attr_init(&dev->attr,
                     S_IFNAM | S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP | S_IROTH | S_IWOTH,
                     NULL, NULL);
    veille_pipe_default_config(&dev->cfg);
    veille_pipe_state_init(&dev->pipe);
    dev->last_bpm = VEILLE_HR_NORMAL;
    dev->tick_period_us = (long)VEILLE_PERIOD_MS * 1000L;
    dev->wd_ms = VEILLE_WD_MS_DEFAULT;
    dev->start_us = veille_now_us();
    dev->tick_last_us = dev->start_us;   /* 1er intervalle mesuré depuis le boot */
    dev->wd_last_us = dev->start_us;
    veille_verdict v;
    fill_verdict(&v, VEILLE_OK, "chaine prete - aucun echantillon",
                 VEILLE_SENSOR_OK, VEILLE_ALARM_NONE, dev->cfg.bound_alarm_ms, 0);
    format_verdicts(dev, &v, 1);
}

/* Bucket d'histogramme : n_exact buckets exacts (0..n_exact-1 µs), puis des
 * bins log2 (n_exact, 2*n_exact, 4*n_exact, ...). Partagé par les deux
 * histogrammes (écart de tick, latence) — une seule implémentation. */
static int hist_bucket(long v, int n_exact) {
    if (v < 0) v = 0;
    if (v < n_exact) return (int)v;
    int k = 0;
    long lim = n_exact;
    while (v >= lim && k < VEILLE_LAT_LOGBINS - 1) { lim <<= 1; k++; }
    return n_exact + k;
}

/* --- E3 : statistique d'intervalle entre deux ticks noyau ---------------- */
static void tick_stats_update(veille_dev_t *dev, long now_us) {
    long d = now_us - dev->tick_last_us;
    dev->tick_last_us = now_us;
    dev->uptime_us = now_us - dev->start_us;
    dev->n_ticks++;
    if (d <= 0) return;                       /* premier tick : pas d'intervalle */
    if (dev->tick_min_us == 0 || d < dev->tick_min_us) dev->tick_min_us = d;
    if (d > dev->tick_max_us) dev->tick_max_us = d;
    dev->tick_sum_us += d;
    long dev_us = d - dev->tick_period_us;
    if (dev_us < 0) dev_us = -dev_us;
    if (dev_us > dev->tick_maxdev_us) dev->tick_maxdev_us = dev_us;
    if (d > 2 * dev->tick_period_us) dev->tick_coalesced++;
    int b = hist_bucket(dev_us, VEILLE_TICK_EXACT);
    if (b < VEILLE_TICK_BUCKETS) dev->tick_hist[b]++;
}

/* --- H2 : latence de la chaîne (entrée échantillon → verdict prêt) ------- */
static void lat_note(veille_dev_t *dev, long dt_us, int from_tick) {
    unsigned long *hist = from_tick ? dev->lat_tick_hist : dev->lat_write_hist;
    if (from_tick) {
        dev->lat_tick_n++;
        dev->lat_tick_sum_us += dt_us;
        if (dt_us > dev->lat_tick_max_us) dev->lat_tick_max_us = dt_us;
    } else {
        dev->lat_write_n++;
        dev->lat_write_sum_us += dt_us;
        if (dt_us > dev->lat_write_max_us) dev->lat_write_max_us = dt_us;
    }
    int b = hist_bucket(dt_us, VEILLE_LAT_EXACT);
    if (b < VEILLE_LAT_BUCKETS) hist[b]++;
}

/* Pousse un échantillon brut dans la chaîne, horodate, construit le verdict. */
static void push_sample(veille_dev_t *dev, long raw_bpm, int from_tick) {
    long t0 = veille_now_us();                       /* horodatage d'arrivée */
    veille_pipe_result r = veille_pipe_push(&dev->pipe, raw_bpm);
    long dt_ms = (veille_now_us() - t0) / 1000;      /* L_measured */
    dev->n_samples++;
    lat_note(dev, veille_now_us() - t0, from_tick);
    dev->wd_last_us = veille_now_us();               /* le capteur parle : on réarme */
    dev->wd_fired = 0;
    veille_rm_clear_tech(dev, VEILLE_TECH_SILENCE);   /* le signal est revenu */

    const veille_chain_config *c = &dev->cfg;
    veille_verdict v[2];
    size_t n = 0;
    if (r == VEILLE_PIPE_ALARM) {                    /* seuil franchi → alarme haute */
        fill_verdict(&v[n++], dt_ms <= c->bound_alarm_ms ? VEILLE_OK
                                                         : VEILLE_LATENCY_BOUND_EXCEEDED,
                     "alarme haute priorite - seuil franchi",
                     VEILLE_SENSOR_OK, VEILLE_ALARM_SINGLE, c->bound_alarm_ms, dt_ms);
    } else if (r == VEILLE_PIPE_TECH_STUCK || r == VEILLE_PIPE_TECH_DEAD) {
        fill_verdict(&v[n++], VEILLE_TECHNICAL_ALARM,
                     r == VEILLE_PIPE_TECH_DEAD ? "capteur mort" : "capteur fige",
                     r == VEILLE_PIPE_TECH_DEAD ? VEILLE_SENSOR_DEAD : VEILLE_SENSOR_STUCK,
                     VEILLE_ALARM_NONE, c->bound_tech_ms, dt_ms);
        if (dt_ms > c->bound_tech_ms)                /* borne technique dépassée */
            fill_verdict(&v[n++], VEILLE_LATENCY_BOUND_EXCEEDED, "B_tech depassee",
                         VEILLE_SENSOR_OK, VEILLE_ALARM_NONE, c->bound_tech_ms, dt_ms);
    } else {
        fill_verdict(&v[n++], VEILLE_OK, "echantillon traite - seuil non franchi",
                     VEILLE_SENSOR_OK, VEILLE_ALARM_NONE, c->bound_alarm_ms, dt_ms);
    }
    format_verdicts(dev, v, n);
}

void veille_rm_push(veille_dev_t *dev, long raw_bpm) { push_sample(dev, raw_bpm, 0); }

/* Tick du timer noyau : capteur simulé (cycle de VEILLE_TICK_CYCLE échantillons,
 * pannes injectées incluses — même modèle que la sim hôte). */
void veille_rm_tick(veille_dev_t *dev) {
    long now = veille_now_us();
    tick_stats_update(dev, now);
    int i = dev->tick_index % VEILLE_TICK_CYCLE;
    dev->tick_index++;
    long bpm = veille_pipe_sensor_bpm(i, VEILLE_TICK_CYCLE,
                                      veille_pipe_fault_at(i), &dev->last_bpm);
    push_sample(dev, bpm, 1);
}

/* CHANNEL disconnect : le noyau notifie la mort d'un pair → alarme technique
 * dans B_tech (P2), au lieu d'attendre en silence. */
void veille_rm_peer_lost(veille_dev_t *dev) {
    dev->n_disconnects++;
    if (dev->n_clients <= 0) {
        /* Notification sans client connecté : on l'ignore (rien à signaler). */
        fprintf(stderr, "[veille-rm] notification de disconnect sans client (ignoree)\n");
        return;
    }
    dev->n_clients--;
    fprintf(stderr, "[veille-rm] mort d'un pair detectee (clients=%d)\n", dev->n_clients);
    veille_rm_set_tech(dev, VEILLE_TECH_DISCONNECT, "mort d'un pair - CHANNEL disconnect",
                       VEILLE_SENSOR_OK, dev->cfg.bound_tech_ms, 0);
    format_verdicts(dev, NULL, 0);   /* réaffiche le rapport avec l'alarme */
}

/* --- E4 : watchdog « capteur muet » --------------------------------------
 * Mécanisme médicalement juste : PERTE DE SIGNAL. Si aucun échantillon
 * n'arrive depuis plus de wd_ms, le rm émet une alarme technique dans B_tech.
 * Le silence est détecté par un timer noyau indépendant du tick d'acquisition
 * (100 ms) : il fonctionne donc même en mode --no-tick (chaîne pilotée par
 * les seuls clients). */
void veille_rm_watchdog(veille_dev_t *dev) {
    long now = veille_now_us();
    if (dev->wd_ms <= 0) return;                 /* surveillance désactivée */
    if (dev->wd_last_us <= 0) { dev->wd_last_us = now; return; }
    long silence_ms = (now - dev->wd_last_us) / 1000L;
    dev->wd_silence_ms = silence_ms;
    if (silence_ms < dev->wd_ms || dev->wd_fired) return;
    dev->wd_fired = 1;
    dev->wd_count++;
    char msg[96];
    snprintf(msg, sizeof(msg),
             "capteur muet - aucun echantillon depuis %ld ms (seuil %d ms)",
             silence_ms, dev->wd_ms);
    veille_rm_set_tech(dev, VEILLE_TECH_SILENCE, msg, VEILLE_SENSOR_DEAD,
                       dev->cfg.bound_tech_ms, (long)dev->cfg.tech_detect_ms);
    format_verdicts(dev, NULL, 0);   /* réaffiche le rapport avec l'alarme */
    fprintf(stderr, "[veille-rm] ALARME TECHNIQUE : %s\n", msg);
}

/* --- E2 : observation de la priorité effective ----------------------------
 * QNX applique l'héritage de priorité au serveur qui reçoit un MsgSend : le
 * fil qui traite le message tourne à la priorité de l'appelant jusqu'à la
 * réponse. On l'observe DIRECTEMENT (pthread_getschedparam) au moment de la
 * réception : c'est une preuve comportementale, pas une trace noyau. */
int veille_rm_prio_effective(veille_dev_t *dev) {
    int policy = 0;
    struct sched_param sp;
    memset(&sp, 0, sizeof(sp));
    if (pthread_getschedparam(pthread_self(), &policy, &sp) != 0) return -1;
    (void)dev;
    return sp.sched_priority;
}

void veille_rm_prio_observed(veille_dev_t *dev) {
    int p = veille_rm_prio_effective(dev);
    if (p < 0) return;
    dev->prio_effective = p;
    if (p >= 0 && p < VEILLE_PRIO_HIST_MAX) dev->prio_hist[p]++;
}

/* Témoin « sans héritage » : on rend explicitement au fil sa priorité de base
 * au début du traitement, ce qui annule le boosttemporaire que le noyau a accordé.
 * Sert de contrôle négatif pour E2 (même noyau, même charge, seul le boost
 * diffère). */
void veille_rm_prio_drop(veille_dev_t *dev) {
    struct sched_param sp;
    memset(&sp, 0, sizeof(sp));
    sp.sched_priority = dev->prio_base;
    if (pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp) == 0) {
        dev->prio_dropped = 1;
        dev->prio_after_drop = veille_rm_prio_effective(dev);
    }
}

/* Comptage des clients : ouvertures (handler open) et morts notifiées. */
void veille_rm_note_client(veille_dev_t *dev, int opened) {
    if (opened) { dev->n_clients++; dev->n_opens++; }
    else if (dev->n_clients > 0) dev->n_clients--;
}
