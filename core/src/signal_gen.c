/* Générateur de signaux synthétiques déterministes (core/src/signal_gen.c).
 * Jumeau Python : host/veille/state.py (mêmes formules, même LCG). */
#include "veille/signal_gen.h"
#include <string.h>

#define VEILLE_SIGGEN_FS_DEFAUT   250
#define VEILLE_SIGGEN_RATE_DEFAUT  60
#define VEILLE_SIGGEN_DRIFT_DEFAUT 200   /* codes ADC par seconde */
#define VEILLE_SIGGEN_RNG_INIT    12345u

/* Bruit uniforme -1000..1000 (LCG 32 bits, identique en C et en Python). */
static long bruit(veille_signal_gen *g) {
    g->rng = g->rng * 1103515245u + 12345u;
    return (long)((g->rng >> 16) % 2001u) - 1000;
}

/* Forme d'un battement : QRS triangulaire (20 % du cycle) + onde T (35 %).
 * Tout en arithmétique entière → mêmes bits des deux côtés. */
static long ecg_valeur(const veille_signal_gen *g, long pos) {
    long k = (g->period * 20) / 100;
    long w = (g->fs_hz * 3) / 100;
    if (w < 1) w = 1;
    long d = pos - k;
    if (d < 0) d = -d;
    long v = 0;
    if (d <= w) v += g->amplitude * (w - d) / w;
    long kt = (g->period * 35) / 100;
    long wt = (g->fs_hz * 4) / 100;
    if (wt < 1) wt = 1;
    long dt = pos - kt;
    if (dt < 0) dt = -dt;
    if (dt <= wt) v += (g->amplitude / 4) * (wt - dt) / wt;
    return v;
}

void veille_signal_gen_init(veille_signal_gen *g, veille_siggen_kind kind,
                            long fs_hz, long rate_bpm, long amplitude) {
    if (!g) return;
    memset(g, 0, sizeof(*g));
    if (fs_hz <= 0) fs_hz = VEILLE_SIGGEN_FS_DEFAUT;
    if (rate_bpm <= 0) rate_bpm = VEILLE_SIGGEN_RATE_DEFAUT;
    g->kind = kind;
    g->fs_hz = fs_hz;
    g->rate_bpm = rate_bpm;
    g->amplitude = amplitude;
    g->drift_per_s = VEILLE_SIGGEN_DRIFT_DEFAUT;
    g->rng = VEILLE_SIGGEN_RNG_INIT;
    g->period = (fs_hz * 60) / rate_bpm;
    if (g->period < 1) g->period = 1;
}

int16_t veille_signal_gen_next(veille_signal_gen *g) {
    if (!g) return 0;
    long i = g->index++;
    long v = 0;
    switch (g->kind) {
        case VEILLE_SIGGEN_FLAT: v = g->amplitude; break;
        case VEILLE_SIGGEN_DEAD: v = 0; break;
        default: {
            long pos = i % g->period;
            v = ecg_valeur(g, pos);
            long b = bruit(g);
            if (g->kind == VEILLE_SIGGEN_NOISY) v += b * g->amplitude / 1000;
            else v += b / 100;
            if (g->kind == VEILLE_SIGGEN_DRIFT) v += (g->drift_per_s * i) / g->fs_hz;
            break;
        }
    }
    return (int16_t)v;
}

const char *veille_siggen_kind_name(veille_siggen_kind k) {
    switch (k) {
        case VEILLE_SIGGEN_ECG:   return "ecg";
        case VEILLE_SIGGEN_FLAT:  return "flat";
        case VEILLE_SIGGEN_DEAD:  return "dead";
        case VEILLE_SIGGEN_NOISY: return "noisy";
        case VEILLE_SIGGEN_DRIFT: return "drift";
        default: return "?";
    }
}
