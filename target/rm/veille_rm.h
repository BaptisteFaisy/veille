#ifndef VEILLE_RM_H
#define VEILLE_RM_H

/* Veille — resource manager /dev/veille (QNX 8.0, niveau C).
 *
 * Découpage (fonctions < 50 lignes, zéro duplication) :
 *   - resmgr_veille.c : main — dispatch, resmgr_attach, timer+pulses, boucle
 *   - rm_chain.c      : chaîne acquire→filter→decide→verdict (texte du CONTRAT)
 *   - rm_io.c         : handlers io_read / io_write (iofunc)
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

#define VEILLE_MOUNT_POINT     "/dev/veille"
#define VEILLE_PRIO_CRITICAL   62       /* priorité voie critique (SCHED_FIFO) */
#define VEILLE_PERIOD_MS       10       /* cadence d'acquisition (timer noyau) */
#define VEILLE_PULSE_TICK      (_PULSE_CODE_MINAVAIL + 1)
#define VEILLE_REPORT_CAP      1024     /* verdict texte au format du CONTRAT */
#define VEILLE_WRITE_CAP       64       /* taille max d'un échantillon écrit */
#define VEILLE_TICK_CYCLE      600      /* cycle du capteur simulé (ticks) */

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
} veille_dev_t;

/* rm_chain.c — chaîne et verdicts */
void veille_rm_init(veille_dev_t *dev);
void veille_rm_push(veille_dev_t *dev, long raw_bpm);      /* write / tick */
void veille_rm_tick(veille_dev_t *dev);                    /* pulse cadence */
void veille_rm_peer_lost(veille_dev_t *dev);               /* CHANNEL disconnect */

/* rm_io.c — handlers iofunc */
int veille_io_read(resmgr_context_t *ctp, io_read_t *msg, RESMGR_OCB_T *ocb);
int veille_io_write(resmgr_context_t *ctp, io_write_t *msg, RESMGR_OCB_T *ocb);

#endif /* VEILLE_RM_H */
