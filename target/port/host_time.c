/* Port hôte (Linux/gcc) — horloge monotone pour la simulation.
 * Compilé dans le build hôte uniquement (make sim/demo) ; voir port_time.h. */
#define _POSIX_C_SOURCE 199309L   /* clock_gettime / CLOCK_MONOTONIC en -std=c11 strict */
#include "port_time.h"
#include <time.h>

long veille_now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000000L + ts.tv_nsec / 1000;
}
