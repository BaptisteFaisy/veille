#ifndef VEILLE_SIGNAL_GEN_H
#define VEILLE_SIGNAL_GEN_H

/* Générateur de signaux ECG SYNTHÉTIQUES déterministes.
 *
 * Une seule implémentation partagée : la simulation hôte (target/sim), le
 * test C de preuve (core/tests/test_signal.c) et — via le jumeau Python
 * (host/veille/state.py) — le différentiel C↔Python. Aucun aléa : le bruit
 * vient d'un LCG 32 bits, identique bit à bit des deux côtés.
 *
 * Ce n'est PAS un signal clinique : c'est une banc de test de la chaîne
 * capteur→alarme (capter une valeur figée, un capteur mort, un bruit
 * excessif, une dérive lente, une tachycardie soutenue). */

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    VEILLE_SIGGEN_ECG = 0,   /* ECG : QRS triangulaire + onde T + bruit faible */
    VEILLE_SIGGEN_FLAT,      /* valeur constante non nulle → capteur figé */
    VEILLE_SIGGEN_DEAD,      /* zéro → capteur mort */
    VEILLE_SIGGEN_NOISY,     /* ECG + bruit uniforme large */
    VEILLE_SIGGEN_DRIFT      /* ECG + dérive lente de la ligne de base */
} veille_siggen_kind;

typedef struct {
    veille_siggen_kind kind;
    long     fs_hz;        /* fréquence d'échantillonnage */
    long     rate_bpm;     /* fréquence cardiaque visée */
    long     amplitude;    /* hauteur du pic R (codes ADC) */
    long     drift_per_s;  /* dérive lente (codes ADC par seconde) */
    long     period;       /* échantillons par battement */
    uint32_t rng;          /* état du LCG (bruit déterministe) */
    long     index;        /* numéro d'échantillon émis */
} veille_signal_gen;

/* Initialise le générateur (amplitude = hauteur du pic R). */
void veille_signal_gen_init(veille_signal_gen *g, veille_siggen_kind kind,
                            long fs_hz, long rate_bpm, long amplitude);

/* Échantillon suivant (codes ADC signés). */
int16_t veille_signal_gen_next(veille_signal_gen *g);

/* Nom lisible du générateur ("ecg", "flat", "dead", "noisy", "drift"). */
const char *veille_siggen_kind_name(veille_siggen_kind k);

#ifdef __cplusplus
}
#endif
#endif /* VEILLE_SIGNAL_GEN_H */
