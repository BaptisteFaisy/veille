/* Veille — resource manager /dev/veille : programme principal (QNX 8.0).
 *
 * API vérifiée dans les en-têtes du SDP 8.0 (target/qnx/usr/include/sys/) :
 *   dispatch.h  : dispatch_create, resmgr_attach (retour int, 8 arg.),
 *                 pulse_attach, message_connect, dispatch_block/handler
 *   resmgr.h    : _RESMGR_CONNECT_NFUNCS, _RESMGR_IO_NFUNCS, _RESMGR_NOREPLY
 *   iofunc.h    : iofunc_func_init, iofunc_attr_init (dattr/info)
 *   siginfo.h   : SIGEV_PULSE_INIT (sigev_coid/priority/code)
 *   neutrino.h  : _PULSE_CODE_MINAVAIL=0, _PULSE_CODE_DISCONNECT=-33
 *
 * Ce que QNX apporte ici (docs/SAFETY.md §6, docs/QNX-BUILD.md) :
 *   - resmgr_attach /dev/veille : un seul processus possède la chaîne ;
 *   - cadence timer_create + SIGEV_PULSE : périodicité noyau, pas de sleep() ;
 *   - voie critique à SCHED_FIFO VEILLE_PRIO_CRITICAL : priority inheritance
 *     du noyau pour les clients MsgSend (E2 — à valider par kernel trace) ;
 *   - CHANNEL disconnect : mort d'un pair notifiée → alarme technique (E4). */
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "veille_rm.h"

static veille_dev_t veille_dev;   /* attr doit rester stable (pointée par iofunc) */

/* Pulse de cadence : un échantillon simulé traverse la chaîne (timer noyau). */
static int pulse_tick(message_context_t *ctp, int code, unsigned flags, void *handle) {
    (void)ctp; (void)code; (void)flags;
    veille_rm_tick((veille_dev_t *)handle);
    return _RESMGR_NOREPLY;       /* un pulse ne se répond pas */
}

/* CHANNEL disconnect : le noyau notifie la mort d'un pair → alarme technique
 * dans B_tech (P2). Livraison effective à valider sur cible (E4). */
static int pulse_disconnect(message_context_t *ctp, int code, unsigned flags, void *handle) {
    (void)ctp; (void)code; (void)flags;
    veille_rm_peer_lost((veille_dev_t *)handle);
    return _RESMGR_NOREPLY;
}

/* Voie critique : le serveur tourne à SCHED_FIFO VEILLE_PRIO_CRITICAL ; les
 * clients en MsgSend bénéficient de la priority inheritance du noyau (E2). */
static void setup_priority(void) {
    struct sched_param sp;
    memset(&sp, 0, sizeof(sp));
    sp.sched_priority = VEILLE_PRIO_CRITICAL;
    (void)pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp);
}

/* Cadence noyau : timer_create(CLOCK_MONOTONIC) + SIGEV_PULSE sur le coid du
 * dispatch, période VEILLE_PERIOD_MS (pas de sleep() sujet à dérive). */
static int setup_tick_timer(int coid) {
    struct sigevent ev;
    SIGEV_PULSE_INIT(&ev, coid, VEILLE_PRIO_CRITICAL, VEILLE_PULSE_TICK, 0);
    timer_t tid;
    if (timer_create(CLOCK_MONOTONIC, &ev, &tid) != 0) return -1;
    struct itimerspec it;
    memset(&it, 0, sizeof(it));
    it.it_value.tv_nsec = VEILLE_PERIOD_MS * 1000000L;
    it.it_interval.tv_nsec = VEILLE_PERIOD_MS * 1000000L;
    return timer_settime(tid, 0, &it, NULL);
}

/* Source des échantillons : par défaut un capteur simulé interne cadencé par le
 * timer noyau ; `--no-tick` coupe ce tick pour que la chaîne soit pilotée
 * UNIQUEMENT par les clients (rejeu de données réelles dans /dev/veille). */
static int tick_demande(int argc, char **argv) {
    for (int i = 1; i < argc; i++)
        if (strcmp(argv[i], "--no-tick") == 0) return 0;
    return 1;
}

int main(int argc, char **argv) {
    veille_rm_init(&veille_dev);
    setup_priority();

    dispatch_t *dpp = dispatch_create();
    if (!dpp) return EXIT_FAILURE;

    /* handlers iofunc : défauts + read/write de la chaîne (rm_io.c) */
    resmgr_connect_funcs_t connect_funcs;
    resmgr_io_funcs_t io_funcs;
    iofunc_func_init(_RESMGR_CONNECT_NFUNCS, &connect_funcs,
                     _RESMGR_IO_NFUNCS, &io_funcs);
    io_funcs.read = veille_io_read;
    io_funcs.write = veille_io_write;
    connect_funcs.open = veille_open;   /* comptage des clients connectés */

    resmgr_attr_t rattr;
    memset(&rattr, 0, sizeof(rattr));
    if (resmgr_attach(dpp, &rattr, VEILLE_MOUNT_POINT, _FTYPE_ANY, 0,
                      &connect_funcs, &io_funcs, &veille_dev.attr) < 0)
        return EXIT_FAILURE;

    if (pulse_attach(dpp, MSG_FLAG_ALLOC_PULSE, VEILLE_PULSE_TICK,
                     pulse_tick, &veille_dev) < 0)
        return EXIT_FAILURE;
    /* disconnect : toléré en échec (notification dépend du canal — E4) */
    (void)pulse_attach(dpp, MSG_FLAG_ALLOC_PULSE, _PULSE_CODE_DISCONNECT,
                       pulse_disconnect, &veille_dev);

    int coid = message_connect(dpp, MSG_FLAG_SIDE_CHANNEL);
    if (coid < 0) return EXIT_FAILURE;
    if (tick_demande(argc, argv) && setup_tick_timer(coid) != 0) return EXIT_FAILURE;

    dispatch_context_t *ctp = dispatch_context_alloc(dpp);
    if (!ctp) return EXIT_FAILURE;
    for (;;) {
        ctp = dispatch_block(ctp);
        if (!ctp) break;
        dispatch_handler(ctp);
    }
    dispatch_context_free(ctp);
    return EXIT_SUCCESS;
}
