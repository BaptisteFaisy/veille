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
 *     du noyau pour les clients MsgSend (E2 — mesuré par le comportement) ;
 *   - watchdog « capteur muet » : timer noyau indépendant, alarme technique
 *     dans B_tech quand le signal disparaît (E4) ;
 *   - CHANNEL disconnect : notification de mort d'un pair → alarme technique.
 *
 * NOTE impérative sur les pulses : pulse_attach doit être appelé SANS
 * MSG_FLAG_ALLOC_PULSE et avec un code FIXE (VEILLE_PULSE_* dans [0,127]) —
 * MSG_FLAG_ALLOC_PULSE fait allouer par le dispatch un code arbitraire et
 * ignore le code demandé, ce qui désynchrronise le timer (qui envoie au code
 * écrit dans SIGEV_PULSE_INIT) et le handler (attaché ailleurs) : le tick ne
 * serait alors jamais servi. Vérifié expérimentalement sur cible.
 *
 * Options de ligne de commande (voir docs/QNX-BUILD.md §8) :
 *   --prio N          priorité SCHED_FIFO de base du rm (défaut 62)
 *   --watchdog-ms N   seuil de silence « capteur muet » (défaut 1000 ; 0 = off)
 *   --no-tick         coupe le capteur simulé interne (chaîne pilotée par les
 *                     seuls clients — utilisé pour la preuve E4)
 *   --no-inherit      témoin E2 : annule explicitement l'héritage de priorité
 *                     reçu du noyau (contrôle négatif de la mesure E2) */
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

/* Pulse de surveillance : silence du capteur → alarme technique (E4). */
static int pulse_watchdog(message_context_t *ctp, int code, unsigned flags, void *handle) {
    (void)ctp; (void)code; (void)flags;
    veille_rm_watchdog((veille_dev_t *)handle);
    return _RESMGR_NOREPLY;
}

/* Voie critique : le serveur tourne à SCHED_FIFO prio ; les clients en
 * MsgSend bénéficient de la priority inheritance du noyau (E2). */
static void setup_priority(int prio) {
    struct sched_param sp;
    memset(&sp, 0, sizeof(sp));
    sp.sched_priority = prio;
    if (pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp) != 0)
        fprintf(stderr, "[veille-rm] WARNING: priorité %d non appliquée\n", prio);
}

/* Cadence noyau : timer_create(CLOCK_MONOTONIC) + SIGEV_PULSE sur le coid du
 * dispatch. Un seul constructeur pour le tick d'acquisition ET le timer de
 * surveillance (zéro duplication). */
static int setup_timer(int coid, int period_ms, int pulse_code, int prio) {
    struct sigevent ev;
    SIGEV_PULSE_INIT(&ev, coid, prio, pulse_code, 0);
    timer_t tid;
    if (timer_create(CLOCK_MONOTONIC, &ev, &tid) != 0) return -1;
    struct itimerspec it;
    memset(&it, 0, sizeof(it));
    it.it_value.tv_nsec = (long)period_ms * 1000000L;
    it.it_interval.tv_nsec = (long)period_ms * 1000000L;
    return timer_settime(tid, 0, &it, NULL);
}

/* Options de ligne de commande (défauts = configuration de production). */
static void parse_options(int argc, char **argv, veille_rm_opts *o) {
    o->prio = VEILLE_PRIO_CRITICAL;
    o->tick = 1;
    o->watchdog_ms = VEILLE_WD_MS_DEFAULT;
    o->no_inherit = 0;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--no-tick") == 0) o->tick = 0;
        else if (strcmp(argv[i], "--no-inherit") == 0) o->no_inherit = 1;
        else if (strcmp(argv[i], "--prio") == 0 && i + 1 < argc) o->prio = atoi(argv[++i]);
        else if (strcmp(argv[i], "--watchdog-ms") == 0 && i + 1 < argc)
            o->watchdog_ms = atoi(argv[++i]);
        else fprintf(stderr, "[veille-rm] option inconnue : %s\n", argv[i]);
    }
}

/* DÉCONNEXION : le noyau livre la notification de mort de pair. Pour un
 * client iofunc (pathname), la livraison dépend du canal : on l'intercepte
 * dans la boucle (type ou code du pulse) — pas possible via pulse_attach,
 * car _PULSE_CODE_DISCONNECT (-33) est hors de [0,127]. Si la notification
 * n'arrive pas, c'est exactement le constat E4 à documenter. */
static int is_disconnect(dispatch_context_t *ctp) {
    if (!ctp || !ctp->resmgr_context.msg) return 0;
    if (ctp->resmgr_context.msg->type == (uint16_t)_PULSE_CODE_DISCONNECT) return 1;
    if (ctp->resmgr_context.msg->pulse.code == (int8_t)_PULSE_CODE_DISCONNECT) return 1;
    return 0;
}

int main(int argc, char **argv) {
    veille_rm_opts opts;
    parse_options(argc, argv, &opts);

    veille_rm_init(&veille_dev);
    veille_dev.prio_base = opts.prio;
    veille_dev.prio_effective = opts.prio;
    veille_dev.wd_ms = opts.watchdog_ms;
    veille_dev.no_inherit = opts.no_inherit;
    setup_priority(opts.prio);

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

    /* Pulses : code FIXE, SANS MSG_FLAG_ALLOC_PULSE (voir NOTA en tête). */
    if (pulse_attach(dpp, 0, VEILLE_PULSE_TICK, pulse_tick, &veille_dev) < 0)
        return EXIT_FAILURE;
    if (pulse_attach(dpp, 0, VEILLE_PULSE_WATCHDOG, pulse_watchdog, &veille_dev) < 0)
        return EXIT_FAILURE;

    int coid = message_connect(dpp, 0);   /* canal principal : dispatch_block le sert */
    if (coid < 0) return EXIT_FAILURE;
    /* Les pulses sont livrés à la priorité de base du rm : le boost de
     * priorité ne doit venir QUE du client (sinon la mesure E2 est faussée). */
    if (opts.tick && setup_timer(coid, VEILLE_PERIOD_MS, VEILLE_PULSE_TICK,
                                 opts.prio) != 0) return EXIT_FAILURE;
    if (opts.watchdog_ms > 0 &&
        setup_timer(coid, VEILLE_WD_PERIOD_MS, VEILLE_PULSE_WATCHDOG,
                    opts.prio) != 0) return EXIT_FAILURE;

    fprintf(stderr, "[veille-rm] prêt : prio=%d tick=%d watchdog_ms=%d no_inherit=%d\n",
            opts.prio, opts.tick, opts.watchdog_ms, opts.no_inherit);

    dispatch_context_t *ctp = dispatch_context_alloc(dpp);
    if (!ctp) return EXIT_FAILURE;
    for (;;) {
        ctp = dispatch_block(ctp);
        if (!ctp) break;
        if (is_disconnect(ctp)) { veille_rm_peer_lost(&veille_dev); continue; }
        dispatch_handler(ctp);
    }
    dispatch_context_free(ctp);
    return EXIT_SUCCESS;
}