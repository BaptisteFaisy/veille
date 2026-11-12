/* Veille — charge CPU calibrée (QNX 8.0) : outil de preuve (tools/qnx/).
 *
 * Occupe le CPU à une priorité SCHED_FIFO donnée, avec un cycle
 * « occupation H ms / repos S ms ». C'est ce qui rend la mesure E2
 * discriminante : un serveur à SCHED_FIFO 10 qui n'hérite d'aucune priorité
 * est préempté par cette charge (priorité 30), alors qu'un serveur hissé à la
 * priorité de son client (40) ne l'est pas.
 *
 * usage: hog --prio P [--hold-ms H] [--sleep-ms S] [--duration-ms D]
 */
#define _QNX_SOURCE 1
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sched.h>

static long now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long)ts.tv_sec * 1000000L + ts.tv_nsec / 1000L;
}

int main(int argc, char **argv) {
    int prio = 30, hold_ms = 20, sleep_ms = 1, duration_ms = 5000;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--prio") && i + 1 < argc) prio = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--hold-ms") && i + 1 < argc) hold_ms = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--sleep-ms") && i + 1 < argc) sleep_ms = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--duration-ms") && i + 1 < argc) duration_ms = atoi(argv[++i]);
        else {
            fprintf(stderr, "usage: %s --prio P [--hold-ms H] [--sleep-ms S] [--duration-ms D]\n",
                    argv[0]);
            return 2;
        }
    }
    struct sched_param sp;
    memset(&sp, 0, sizeof(sp));
    sp.sched_priority = prio;
    if (sched_setscheduler(0, SCHED_FIFO, &sp) != 0)
        fprintf(stderr, "[hog] WARNING: priorité %d non appliquée\n", prio);

    printf("# hog prio=%d hold_ms=%d sleep_ms=%d duration_ms=%d debut_us=%ld\n",
           prio, hold_ms, sleep_ms, duration_ms, now_us());
    fflush(stdout);
    long t0 = now_us();
    long fin = t0 + (long)duration_ms * 1000L;
    while (now_us() < fin) {
        long busy_until = now_us() + (long)hold_ms * 1000L;
        volatile double x = 1.0;
        while (now_us() < busy_until) x = x * 1.000001 + 0.5;   /* occupation */
        (void)x;
        if (sleep_ms > 0) {
            struct timespec ts = { sleep_ms / 1000L, (long)(sleep_ms % 1000) * 1000000L };
            nanosleep(&ts, NULL);
        }
    }
    printf("# hog fin_us=%ld\n", now_us());
    return 0;
}
