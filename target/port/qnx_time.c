/* Port cible QNX 8.0 — horloge monotone.
 * Compilé dans le build QNX uniquement (make qnx) ; voir port_time.h.
 * QNX 8.0 gate CLOCK_MONOTONIC/clock_gettime derrière __EXT_POSIX1_200112
 * (sys/platform.h) : en -std=c11 strict, il faut _POSIX_C_SOURCE >= 200112L
 * (199309L ne suffit PAS, contrairement à glibc — CLOCK_MONOTONIC = POSIX 2001). */
#define _POSIX_C_SOURCE 200112L
#include "port_time.h"
#include <time.h>

long veille_now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000000L + ts.tv_nsec / 1000;
}
