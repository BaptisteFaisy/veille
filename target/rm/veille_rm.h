#ifndef VEILLE_RM_H
#define VEILLE_RM_H

/* Veille — resource manager /dev/veille (QNX 8.0, niveau C).
 *
 * Découpage (fonctions < 50 lignes, zéro duplication) :
 *   - resmgr_veille.c : main — dispatch, resmgr_attach, timers+pulses, options
 *   - rm_chain.c      : chaîne acquire→filter→decide→verdict + watchdog + stats
 *   - rm_io.c         : handlers io_read / io_write / devctl (iofunc)
 *   - veille_rm.h     : ce fichier — état partagé du serveur
 *
 * La logique de chaîne vit dans target/pipe/ (portable, partagée avec la sim
 * hôte) et core/ (pur, prouvé) ; ici ce n'est que la colle QNX.
 * Sources compilées UNIQUEMENT par `make qnx` (qcc) — jamais par le build hôte.
 */

#include <sys/iofunc.h>
#include <sys/dispatch.h>

#include "veille/chain.h"
#include "veille/state.h"
#include "veille/verdict.h"
#include "veille_pipe.h"
#include "veille_rm_protocol.h"

#define VEILLE_PRIO_CRITICAL   62       /* priorité voie critique (SCHED_FIFO) */
#define VEILLE_PERIOD_MS       10       /* cadence d'acquisition (timer noyau) */
#define VEILLE_PULSE_TICK      (_PULSE_CODE_MINAVAIL + 1)
#define VEILLE_PULSE_WATCHDOG  (_PULSE_CODE_MINAVAIL + 2)
#define VEILLE_REPORT_CAP      1024     /* verdict texte au format du CONTRAT */
#define VEILLE_WRITE_CAP       4096     /* taille max d'une écriture (octets) */
#define VEILLE_BATCH_MAX       256      /* échantillons max par écriture */
#define VEILLE_TICK_CYCLE      600      /* cycle du capteur simulé (ticks) */

/* --- Chaine de mesure (E2/E3/E4/H2) ------------------------------------- */
#define VEILLE_WD_MS_DEFAULT   1000     /* silence capteur : seuil par défaut */
#define VEILLE_WD_PERIOD_MS    100      /* période du timer de surveillance */
#define VEILLE_PRIO_HIST_MAX   64       /* histogramme des priorités reçues */
#define VEILLE_LAT_EXACT       128      /* buckets exacts (µs) de latence */
#define VEILLE_LAT_LOGBINS     32       /* bins log2 au-delà des buckets exacts */
#define VEILLE_LAT_BUCKETS     (VEILLE_LAT_EXACT + VEILLE_LAT_LOGBINS)
#define VEILLE_TICK_EXACT      64       /* buckets exacts (µs) d'écart de tick */
#define VEILLE_TICK_BUCKETS     (VEILLE_TICK_EXACT + VEILLE_LAT_LOGBINS)
#define VEILLE_STATS_CAP       8192     /* tampon du canal de mesures (read) */

/* Nature de l'alarme technique courante (une seule à la fois). */
#define VEILLE_TECH_NONE        0
#define VEILLE_TECH_DISCONNECT  1   /* mort d'un pair (CHANNEL disconnect) */
#define VEILLE_TECH_SILENCE     2   /* capteur muet (perte de signal) */

/* Options de ligne de commande (démarrage du rm). */
typedef struct {
    int  prio;            /* priorité SCHED_FIFO de base du rm */
    int  tick;            /* 1 = capteur simulé interne activé */
    int  watchdog_ms;     /* silence capteur au-delà duquel on alarme */
    int  no_inherit;      /* 1 = témoin : on annule l'héritage de priorité */
} veille_rm_opts;

/* État du serveur : attribut iofunc EN PREMIER (RESMGR_HANDLE_T = attr). */
typedef struct {
    iofunc_attr_t         attr;
    veille_chain_config   cfg;              /* bornes gelées — CONTRACT.md §3 */
    veille_pipe_state     pipe;             /* acquire→filter→decide */
    long                  last_bpm;         /* état du capteur simulé (tick) */
    int                   tick_index;       /* position dans le cycle simulé */
    char                  report[VEILLE_REPORT_CAP];  /* verdict courant */
    long                  report_len;       /* octets valides dans report */
    unsigned long         n_samples;        /* échantillons poussés */
    unsigned long         n_disconnects;    /* morts de pairs notifiées */
    int                   n_clients;        /* clients connectés (connect handler) */
    unsigned long         n_opens;          /* ouvertures vues */
    /* --- E3 : cadence réelle du tick noyau ------------------------------- */
    long                  tick_period_us;   /* période demandée (µs) */
    long                  start_us;         /* horodatage de démarrage (µs) */
    long                  uptime_us;        /* temps de service (µs) */
    unsigned long         n_ticks;          /* ticks reçus */
    long                  tick_last_us;     /* horodatage du dernier tick */
    long                  tick_min_us;      /* intervalle min entre ticks */
    long                  tick_max_us;      /* intervalle max entre ticks */
    long                  tick_sum_us;      /* somme des intervalles */
    long                  tick_maxdev_us;   /* max |intervalle - période| */
    unsigned long         tick_coalesced;   /* ticks regroupés (intervalle > 2 périodes) */
    unsigned long         tick_hist[VEILLE_TICK_BUCKETS]; /* histogramme des écarts */
    /* --- H2 : latences réelles (chaîne et aller-retour client) ----------- */
    unsigned long         lat_tick_n;       /* échantillons (tick) mesurés */
    long                  lat_tick_max_us;
    long                  lat_tick_sum_us;
    unsigned long         lat_tick_hist[VEILLE_LAT_BUCKETS];
    unsigned long         lat_write_n;      /* écritures clients mesurées */
    long                  lat_write_max_us;
    long                  lat_write_sum_us;
    unsigned long         lat_write_hist[VEILLE_LAT_BUCKETS];
    /* --- E2 : héritage de priorité --------------------------------------- */
    int                   prio_base;        /* priorité de base du rm */
    int                   prio_effective;   /* priorité effective courante */
    int                   prio_dropped;     /* 1 si l'héritage a été annulé */
    int                   prio_after_drop;  /* priorité effective APRÈS annulation */
    int                   no_inherit;       /* 1 = témoin E2 (boost annulé) */
    unsigned long         prio_hist[VEILLE_PRIO_HIST_MAX]; /* priorités reçues */
    /* --- Alarme technique courante (B_tech) --------------------------------
     * Elle est TENUE À PART du verdict de la chaîne : une alarme technique
     * (perte de signal, mort d'un pair) ne doit pas masquer l'état du
     * capteur — et inversement. Le rapport peut porter plusieurs verdicts
     * (format texte du CONTRAT). */
    int                   tech_kind;        /* VEILLE_TECH_* */
    veille_verdict        tech_v;           /* alarme technique courante */
    char                  tech_msg[96];     /* texte de l'alarme (stable) */
    /* --- E4 : watchdog « capteur muet » ---------------------------------- */
    int                   wd_ms;            /* seuil de silence (ms) */
    int                   wd_fired;         /* alarme en cours (épisode) */
    unsigned long         wd_count;         /* nb d'alarmes « capteur muet » */
    long                  wd_last_us;       /* dernier échantillon vu (µs) */
    long                  wd_silence_ms;    /* silence mesuré au dernier contrôle */
} veille_dev_t;

/* rm_chain.c — chaîne et verdicts */
void veille_rm_init(veille_dev_t *dev);
void veille_rm_push(veille_dev_t *dev, long raw_bpm);      /* write / tick */
void veille_rm_tick(veille_dev_t *dev);                    /* pulse cadence */
void veille_rm_peer_lost(veille_dev_t *dev);               /* CHANNEL disconnect */
void veille_rm_watchdog(veille_dev_t *dev);                /* contrôle du silence */
void veille_rm_set_tech(veille_dev_t *dev, int kind, const char *msg,
                        veille_sensor_state sensor, long bound_ms, long latency_ms);
void veille_rm_clear_tech(veille_dev_t *dev, int kind);    /* levée d'une alarme */
void veille_rm_note_client(veille_dev_t *dev, int opened); /* comptage clients */
void veille_rm_prio_observed(veille_dev_t *dev);           /* priorité reçue */
int  veille_rm_prio_effective(veille_dev_t *dev);          /* priorité courante */
void veille_rm_prio_drop(veille_dev_t *dev);               /* annule l'héritage */
void veille_rm_stats_text(const veille_dev_t *dev, char *buf, size_t cap);

/* rm_io.c — handlers iofunc */
int veille_open(resmgr_context_t *ctp, io_open_t *msg, RESMGR_HANDLE_T *handle, void *extra);
int veille_io_read(resmgr_context_t *ctp, io_read_t *msg, RESMGR_OCB_T *ocb);
int veille_io_write(resmgr_context_t *ctp, io_write_t *msg, RESMGR_OCB_T *ocb);

#endif /* VEILLE_RM_H */
