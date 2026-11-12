/* Veille — client de mesure pour /dev/veille (QNX 8.0).
 *
 * Outil de preuve (tools/qnx/) : ce n'est PAS le client de production, c'est
 * la sonde qui mesure. Il est compilé par tools/qnx/build.sh avec qcc et
 * exécuté DANS l'invité QNX.
 *
 * Modes :
 *   stats                      affiche le canal de mesures du rm (devctl)
 *   samples --n N [options]    écrit N échantillons et mesure l'aller-retour
 *
 * Options :
 *   --prio P        priorité SCHED_FIFO du client (défaut : inchangée)
 *   --interval-us U pause entre deux écritures (0 = dos à dos)
 *   --bpm B         valeur écrite (défaut 72) ; alterne B et B+2 pour ne pas
 *                   déclencher la détection « capteur figé » (valeur figée)
 *   --stats         affiche le canal de mesures du rm à la fin du run
 *   --label L       étiquette imprimée dans la trace
 *
 * Mesure de latence : horodatage monotone (CLOCK_MONOTONIC) de part et
 * d'autre de l'écriture. L'écriture est un MsgSend : elle ne rend la main
 * qu'après la réponse du rm — le temps mesuré est donc l'aller-retour réel
 * (file d'attente du dispatch + traitement de la chaîne + réponse).
 */
#define _QNX_SOURCE 1
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <sched.h>
#include <unistd.h>

#include "veille_rm_protocol.h"

static long now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long)ts.tv_sec * 1000000L + ts.tv_nsec / 1000L;
}

static void set_prio(int p) {
    struct sched_param sp;
    memset(&sp, 0, sizeof(sp));
    sp.sched_priority = p;
    if (sched_setscheduler(0, SCHED_FIFO, &sp) != 0)
        fprintf(stderr, "[client] WARNING: priorité %d non appliquée\n", p);
}

/* Affiche le canal de mesures du rm (texte « cle=valeur », offset réservé). */
static int print_stats(int fd) {
    static char buf[8192];
    memset(buf, 0, sizeof(buf));
    if (lseek(fd, VEILLE_STATS_OFFSET, SEEK_SET) < 0) {
        perror("[client] lseek stats");
        return -1;
    }
    int n = read(fd, buf, sizeof(buf) - 1);
    if (n <= 0) {
        fprintf(stderr, "[client] read stats : échec (%d)\n", n);
        return -1;
    }
    buf[n] = '\0';
    fputs(buf, stdout);
    return 0;
}

static void usage(const char *me) {
    fprintf(stderr,
        "usage: %s stats | verdict\n"
        "       %s samples --n N [--prio P] [--interval-us U] [--bpm B] [--stats] [--label L]\n",
        me, me);
}

int main(int argc, char **argv) {
    if (argc < 2) { usage(argv[0]); return 2; }
    int n_samples = 0, prio = -1, interval_us = 0, bpm = 72, want_stats = 0;
    const char *label = "run";
    for (int i = 2; i < argc; i++) {
        if (!strcmp(argv[i], "--n") && i + 1 < argc) n_samples = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--prio") && i + 1 < argc) prio = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--interval-us") && i + 1 < argc) interval_us = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--bpm") && i + 1 < argc) bpm = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--label") && i + 1 < argc) label = argv[++i];
        else if (!strcmp(argv[i], "--stats")) want_stats = 1;
        else if (!strcmp(argv[1], "hold")) continue;   /* options du mode hold */
        else { usage(argv[0]); return 2; }
    }

    if (prio >= 0) set_prio(prio);
    int fd = open(VEILLE_MOUNT_POINT, O_RDWR);
    if (fd < 0) { perror("[client] open " VEILLE_MOUNT_POINT); return 1; }

    if (!strcmp(argv[1], "stats")) {
        print_stats(fd);
        close(fd);
        return 0;
    }
    if (!strcmp(argv[1], "verdict")) {          /* verdict courant (offset 0) */
        char v[2048];
        memset(v, 0, sizeof(v));
        int n = read(fd, v, sizeof(v) - 1);
        if (n < 0) { perror("[client] read verdict"); close(fd); return 1; }
        v[n] = '\0';
        printf("%s", v);
        close(fd);
        return 0;
    }
    if (!strcmp(argv[1], "hold")) {
        /* Démonstration E4 en un seul processus : on se tait d'abord (le
         * watchdog doit alarmer « capteur muet »), on lit le verdict, puis on
         * écrit des échantillons (le signal revient) et on relit le verdict.
         * Un seul processus = pas de notification de disconnect parasite
         * entre les deux lectures. */
        long silence_ms = 3000, duration_ms = 2000;
        for (int i = 2; i < argc; i++) {
            if (!strcmp(argv[i], "--silence-ms") && i + 1 < argc) silence_ms = atol(argv[++i]);
            else if (!strcmp(argv[i], "--duration-ms") && i + 1 < argc) duration_ms = atol(argv[++i]);
            else if (!strcmp(argv[i], "--interval-us") && i + 1 < argc) interval_us = atoi(argv[++i]);
            else if (!strcmp(argv[i], "--bpm") && i + 1 < argc) bpm = atoi(argv[++i]);
        }
        printf("# hold silence_ms=%ld duration_ms=%ld interval_us=%d bpm=%d\n",
               silence_ms, duration_ms, interval_us, bpm);
        fflush(stdout);
        struct timespec ts;
        ts.tv_sec = silence_ms / 1000; ts.tv_nsec = (silence_ms % 1000) * 1000000L;
        nanosleep(&ts, NULL);
        char v[2048];
        lseek(fd, 0, SEEK_SET);          /* le verdict se relit depuis 0 */
        int n = read(fd, v, sizeof(v) - 1);
        if (n > 0) { v[n] = '\0'; printf("VERDICT_SILENCE:\n%s", v); }
        fflush(stdout);
        long fin = now_us() + duration_ms * 1000L;
        int i = 0;
        while (now_us() < fin) {
            char ligne[32];
            int len = snprintf(ligne, sizeof(ligne), "bpm %d\n", (i % 2) ? bpm + 2 : bpm);
            if (write(fd, ligne, (size_t)len) != len) break;
            i++;
            ts.tv_sec = interval_us / 1000000L;
            ts.tv_nsec = (long)(interval_us % 1000000L) * 1000L;
            if (interval_us > 0) nanosleep(&ts, NULL);
        }
        memset(v, 0, sizeof(v));
        lseek(fd, 0, SEEK_SET);
        n = read(fd, v, sizeof(v) - 1);
        if (n > 0) { v[n] = '\0'; printf("VERDICT_SIGNAL:\n%s", v); }
        fflush(stdout);
        close(fd);
        return 0;
    }
    if (strcmp(argv[1], "samples") != 0) { usage(argv[0]); close(fd); return 2; }

    printf("# label=%s prio=%d n=%d interval_us=%d bpm=%d\n", label, prio, n_samples,
           interval_us, bpm);
    long min_us = -1, max_us = 0, sum_us = 0;
    for (int i = 0; i < n_samples; i++) {
        char ligne[32];
        int len = snprintf(ligne, sizeof(ligne), "bpm %d\n", (i % 2) ? bpm + 2 : bpm);
        long t0 = now_us();
        int w = write(fd, ligne, (size_t)len);
        long t1 = now_us();
        if (w != len) { perror("[client] write"); break; }
        long dt = t1 - t0;
        printf("rtt_us=%ld\n", dt);
        fflush(stdout);
        sum_us += dt;
        if (min_us < 0 || dt < min_us) min_us = dt;
        if (dt > max_us) max_us = dt;
        if (interval_us > 0) {
            struct timespec ts = { interval_us / 1000000L, (long)(interval_us % 1000000L) * 1000L };
            nanosleep(&ts, NULL);
        }
    }
    printf("# fin label=%s echantillons=%d min_us=%ld max_us=%ld moyenne_us=%ld\n",
           label, n_samples, min_us, max_us, n_samples ? sum_us / n_samples : 0);
    if (want_stats) print_stats(fd);
    close(fd);
    return 0;
}
