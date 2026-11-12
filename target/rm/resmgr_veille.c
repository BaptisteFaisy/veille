/* Veille — resource manager /dev/veille pour QNX 8.0 (niveau C).
 *
 * Squelette documenté : ne compile QUE sur cible QNX (qcc, SDP 8.0) — gardé hors du
 * build hôte par #ifdef __QNX__. La logique de chaîne et la preuve restent dans core/
 * (portable, testé sur hôte) ; ce fichier n'est que la colle QNX.
 *
 * Ce que QNX apporte ici (voir docs/SAFETY.md §6) :
 *   - resmgr_attach sur /dev/veille (iofunc) : un seul processus possède la chaîne ;
 *     les clients (UI, journal, réseau) y accèdent par API typée (read/write/devctl),
 *     jamais par fichier partagé ni verrou à dimensionner à la main.
 *   - cadence d'acquisition par timer_create + MsgSendPulse : périodicité noyau,
 *     pas de sleep() sujet à la dérive du scheduler.
 *   - voie critique alarme par MsgSend : priority inheritance du noyau — le sink
 *     tourne à la priorité de l'appelant (VEILLE_PRIO_CRITICAL) le temps du message,
 *     donc jamais préempté par du travail best-effort (état prio_inverted du modèle
 *     est corrigé par le noyau, pas seulement détecté).
 *   - mort d'un pair : CHANNEL disconnect notifié par le noyau → alarme technique
 *     dans B_tech (P2), au lieu d'attendre en silence.
 *   - kernel trace : tracelogger capture MsgSend/timers/priorités → preuve empirique
 *     L_measured <= B_proof.
 *
 * Build cible (QNX SDP 8.0 — QEMU x86_64 ou RPi5 aarch64) :
 *   qcc -V gcc_ntoaarch64le -O2 -Wall -Wextra -Icore/include \
 *       target/rm/resmgr_veille.c core/src/*.c -o resmgr_veille
 * Image système : voir image/ (mkifs).
 */
#ifdef __QNX__

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/neutrino.h>
#include <sys/iofunc.h>
#include <sys/dispatch.h>
#include <time.h>
#include <pthread.h>
#include <sched.h>

#include "veille/chain.h"
#include "veille/state.h"
#include "veille/proof.h"
#include "veille/report.h"

#define VEILLE_PRIO_CRITICAL  62          /* priorité de la voie critique */
#define VEILLE_PERIOD_MS      10          /* cadence d'acquisition */
#define VEILLE_PULSE_TICK     (_PULSE_CODE_MINAVAIL + 1)
#define VEILLE_MOUNT_POINT    "/dev/veille"

/* État du serveur : attributs iofunc + contexte de chaîne. */
typedef struct {
    iofunc_attr_t attr;
    veille_chain_config cfg;
    long last_bpm;
} veille_dev_t;

static veille_dev_t veille_dev;
static dispatch_t *dip;
static resmgr_context_t *ctp;

/* devctl : commande typée (ex. VEILLE_DEVCTL_PROOF lance la preuve, renvoie le verdict). */
#define VEILLE_DEVCTL_PROOF   __DIOF(_DCMD_MISC, 1, veille_verdict)
#define VEILLE_DEVCTL_STATE   __DION(_DCMD_MISC, 2, veille_fault_state)

static int veille_iofunc_devctl(resmgr_context_t *ctp, RESMGR_OCB_T *ocb,
                                IOFUNC_OCB_T *non_io_ocb) {
    (void)ocb; (void)non_io_ocb;
    if (ctp->msg->i.type != _IO_DEVCTL) return ENOSYS;
    switch (ctp->msg->i.cmd) {
    case VEILLE_DEVCTL_PROOF: {
        veille_fault_mask mask = {1, 1, 1, 1, 1};
        veille_verdict out;
        size_t n = 0;
        veille_proof_explore(&veille_dev.cfg, &mask, &out, 1, &n);
        return RESMGR_NOREPLY;  /* réponse réelle : MsgReply avec le verdict */
    }
    default:
        return ENOSYS;
    }
}

/* Pulse de cadence : un échantillon traverse la chaîne.
 * Sur pulse TICK → acquire → filter → decide ; si seuil franchi → MsgSend au sink
 * d'alarme (priority inheritance : le sink répond à VEILLE_PRIO_CRITICAL). */
static void handle_tick_pulse(void) {
    /* acquire : lecture capteur (driver simulé ou réel via resmgr capteur) */
    /* filter + decide : logique portable de core/ (veille_alarm_should_fire) */
    /* alarm : MsgSend(connection_sink, &msg, sizeof(msg), &reply, sizeof(reply));
     *         la latence de ce MsgSend est bornée par le noyau (priority inheritance)
     *         et vérifiable dans la trace kernel. */
}

int main(int argc, char **argv) {
    (void)argc; (void)argv;

    /* 1. Config de chaîne (bornes IEC 60601-1-8 gelées, voir CONTRACT.md §3) */
    memset(&veille_dev, 0, sizeof(veille_dev));
    veille_dev.cfg.priority = VEILLE_PRIO_HIGH;
    veille_dev.cfg.bound_alarm_ms = 200;
    veille_dev.cfg.bound_ack_ms = 60000;
    veille_dev.cfg.bound_tech_ms = 50;
    veille_dev.cfg.tech_detect_ms = 15;
    veille_dev.cfg.stage_latency_ms[VEILLE_STAGE_ACQUIRE] = 5;
    veille_dev.cfg.stage_latency_ms[VEILLE_STAGE_FILTER] = 10;
    veille_dev.cfg.stage_latency_ms[VEILLE_STAGE_DECIDE] = 10;
    veille_dev.cfg.stage_latency_ms[VEILLE_STAGE_ALARM] = 20;
    veille_dev.cfg.stage_latency_ms[VEILLE_STAGE_ACK] = 5;
    veille_dev.last_bpm = 72;
    iofunc_attr_init(&veille_dev.attr, S_IFNAM | S_IRUSR | S_IWUSR, NULL, NULL);

    /* 2. resmgr_attach : /dev/veille (un seul propriétaire, API typée) */
    dispatch_t *dispatch = dispatch_create();
    if (!dispatch) return EXIT_FAILURE;
    resmgr_attr_t rattr;
    memset(&rattr, 0, sizeof(rattr));
    resmgr_connection_t *conn =
        resmgr_attach(dispatch, &rattr, VEILLE_MOUNT_POINT, _FTYPE_ANY, 0,
                      NULL, NULL, NULL, &veille_dev.attr);
    if (!conn) return EXIT_FAILURE;
    ctp = resmgr_context_alloc(dispatch);

    /* 3. Cadence noyau : timer_create + SIGEV_PULSE (pas de sleep()) */
    struct sigevent ev;
    SIGEV_PULSE_INIT(&ev, ctp->rcvid, VEILLE_PRIO_CRITICAL, VEILLE_PULSE_TICK, 0);
    timer_t tid;
    struct _clockperiod period = {0};
    period.nsec = VEILLE_PERIOD_MS * 1000000L;
    struct itimerspec it;
    memset(&it, 0, sizeof(it));
    it.it_value.tv_nsec = VEILLE_PERIOD_MS * 1000000L;
    it.it_interval.tv_nsec = VEILLE_PERIOD_MS * 1000000L;
    if (timer_create(CLOCK_MONOTONIC, &ev, &tid) == 0)
        timer_settime(tid, 0, &it, NULL);
    (void)period;

    /* 4. Boucle de réception : pulses (cadence, disconnect) + messages clients */
    for (;;) {
        ctp = resmgr_context_block(ctp);
        if (ctp->msg == NULL) continue;
        if (ctp->rcvid == 0) {                 /* pulse noyau */
            struct _pulse pulse;
            memcpy(&pulse, ctp->msg, sizeof(pulse));
            if (pulse.code == VEILLE_PULSE_TICK) handle_tick_pulse();
            /* pulse DISCONNECT (CHANNEL disconnect) : un pair est mort →
             * alarme technique dans B_tech (P2) — le noyau notifie, on ne devine pas. */
            continue;
        }
        resmgr_handler(ctp, dispatch);          /* read/write/devctl clients */
    }
    return EXIT_SUCCESS;
}

#else
/* Build hôte : ce fichier ne compile que sur QNX. La chaîne est démontrée sur hôte
 * par target/sim/sim.c (latences mesurées) et prouvée par core/ (exploration). */
#endif /* __QNX__ */
