/* Veille — sonde de cadence du timer noyau (QNX 8.0), contrôle indépendant.
 *
 * Le resource manager /dev/veille compte les pulses qu'il SERT. Cette sonde
 * fait la même chose mais sur SON PROPRE canal (dispatch dédié) : elle
 * distingue donc
 *   - un timer noyau qui fire réellement à la cadence demandée, et
 *   - des pulses perdus/coalescés par le noyau (« unions » QNX : une seule
 *     instance en attente par canal) ou par le rm lui-même.
 *
 * usage: tick_probe [--period-ms P] [--duration-ms D] [--prio Q]
 */
#define _QNX_SOURCE 1
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sched.h>
#include <sys/neutrino.h>
#include <sys/dispatch.h>

#define PULSE_CODE (_PULSE_CODE_MINAVAIL + 1)

static long now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long)ts.tv_sec * 1000000L + ts.tv_nsec / 1000;
}

static long n_pulses;
static long min_us, max_us, sum_us, maxdev_us, coalesced;
static long last_us;

static int on_pulse(message_context_t *ctp, int code, unsigned flags, void *arg) {
    (void)ctp; (void)code; (void)flags; (void)arg;
    long now = now_us();
    long d = now - last_us;
    last_us = now;
    n_pulses++;
    if (n_pulses <= 1) return _RESMGR_NOREPLY;
    if (min_us == 0 || d < min_us) min_us = d;
    if (d > max_us) max_us = d;
    sum_us += d;
    long dev = d - 10000L;                 /* écart à la période demandée */
    if (dev < 0) dev = -dev;
    if (dev > maxdev_us) maxdev_us = dev;
    if (d > 20000L) coalesced++;
    return _RESMGR_NOREPLY;
}

int main(int argc, char **argv) {
    long period_us = 10000L, duration_us = 20000000L;
    int prio = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--period-ms") && i + 1 < argc) period_us = atol(argv[++i]) * 1000L;
        else if (!strcmp(argv[i], "--duration-ms") && i + 1 < argc) duration_us = atol(argv[++i]) * 1000L;
        else if (!strcmp(argv[i], "--prio") && i + 1 < argc) prio = atoi(argv[++i]);
    }
    if (prio > 0) {
        struct sched_param sp;
        memset(&sp, 0, sizeof(sp));
        sp.sched_priority = prio;
        if (sched_setscheduler(0, SCHED_FIFO, &sp) != 0)
            fprintf(stderr, "[tick_probe] WARNING: priorité %d non appliquée\n", prio);
    }
    dispatch_t *dpp = dispatch_create();
    if (pulse_attach(dpp, 0, PULSE_CODE, on_pulse, NULL) < 0) return 1;
    int coid = message_connect(dpp, 0);
    if (coid < 0) return 1;
    struct sigevent ev;
    SIGEV_PULSE_INIT(&ev, coid, 0, PULSE_CODE, 0);
    timer_t tid;
    if (timer_create(CLOCK_MONOTONIC, &ev, &tid) != 0) return 1;
    struct itimerspec it;
    memset(&it, 0, sizeof(it));
    it.it_value.tv_nsec = period_us * 1000L;    /* tv_nsec = NANOSECONDES */
    it.it_interval.tv_nsec = period_us * 1000L;
    if (timer_settime(tid, 0, &it, NULL) != 0) return 1;

    long t0 = now_us();
    last_us = t0;
    dispatch_context_t *ctp = dispatch_context_alloc(dpp);
    while (now_us() - t0 < duration_us) {
        ctp = dispatch_block(ctp);
        if (!ctp) break;
        dispatch_handler(ctp);
    }
    long elapsed = now_us() - t0;
    long n = n_pulses > 0 ? n_pulses - 1 : 0;
    printf("tick_probe pulses=%ld duree_us=%ld taux_hz=%.2f "
           "min_us=%ld max_us=%ld moyenne_us=%ld maxdev_us=%ld coalesced=%ld\n",
           n_pulses, elapsed, (double)n_pulses * 1e6 / (double)elapsed,
           min_us, max_us, n ? sum_us / n : 0, maxdev_us, coalesced);
    return 0;
}
