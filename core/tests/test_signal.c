/* Preuve au niveau SIGNAL (core/tests/test_signal.c).
 *
 * Ce que ce test démontre, pas n'affirme :
 *  1. un signal PLAT est détecté comme tel (capteur figé) QUELLE QUE SOIT la
 *     fréquence instantanée (60 bpm comme 180 bpm) ;
 *  2. un rythme RÉGULIER mais vivant (ECG synthetically constant) n'est PAS
 *     « figé » — c'est exactement la fausse alarme technique que l'ancien
 *     détecteur (bpm arrondis égaux) déclenchait sur fibrillation atriale ;
 *  3. une tachycardie soutenue donne une alarme PHYSIOLOGIQUE (pas technique) ;
 *  4. un signal mort donne une alarme technique « capteur mort ».
 *
 * Mode ligne de commande (utilisé par le différentiel C↔Python) :
 *   test_signal.bin --sig ecg|flat|dead|noisy|drift --fs N --rate N --amp N --samples N
 *   → "sensor=<état> bpm=<n> decision=<décision>"
 */
#include "veille/signal.h"
#include "veille/signal_gen.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    veille_sensor_state sensor;
    long bpm;
    veille_decision decision;
} resultat;

/* Joue un signal synthétique et rend l'état capteur + la fréquence. */
static resultat analyser(veille_siggen_kind kind, long fs, long rate, long amp, long n) {
    resultat r;
    veille_signal_gen g;
    veille_signal_gen_init(&g, kind, fs, rate, amp);
    veille_signal_buffer b;
    veille_signal_buffer_init(&b, fs);
    for (long i = 0; i < n; i++) veille_signal_push(&b, veille_signal_gen_next(&g));
    r.sensor = veille_signal_sensor_state(&b);
    r.bpm = veille_signal_rate_bpm(&b);
    r.decision = veille_signal_decide(r.sensor, r.bpm, VEILLE_SIG_HR_THRESHOLD);
    return r;
}

static void afficher(const char *nom, resultat r) {
    printf("%-10s sensor=%-12s bpm=%3ld decision=%s\n", nom,
           veille_sensor_state_name(r.sensor), r.bpm, veille_decision_name(r.decision));
}

static void echec(const char *msg, long v) {
    fprintf(stderr, "[ÉCHEC] %s (%ld)\n", msg, v);
    exit(1);
}

/* PROPRIÉTÉ 1 : un signal plat est figé, quelle que soit la fréquence. */
static void test_signal_plat(void) {
    long rates[2];
    rates[0] = 60; rates[1] = 180;
    for (int i = 0; i < 2; i++) {
        resultat r = analyser(VEILLE_SIGGEN_FLAT, 250, rates[i], 1200, 1024);
        afficher("flat", r);
        if (r.sensor != VEILLE_SENSOR_STUCK) echec("signal plat non détecté figé", rates[i]);
        if (r.decision != VEILLE_DECISION_TECH_FAULT) echec("signal plat sans alarme technique", rates[i]);
        if (r.bpm != 0) echec("signal plat : fréquence nonsense", r.bpm);
    }
}

/* PROPRIÉTÉ 2 : un rythme régulier mais VIVANT n'est pas un capteur figé. */
static void test_rythme_regulier(void) {
    resultat r = analyser(VEILLE_SIGGEN_ECG, 250, 60, 1200, 1024);
    afficher("ecg60", r);
    if (r.sensor != VEILLE_SENSOR_OK) echec("rythme régulier pris pour un capteur figé", r.bpm);
    if (r.bpm != 60) echec("fréquence mal mesurée sur ECG 60 bpm", r.bpm);
    if (r.decision != VEILLE_DECISION_OK) echec("ECG 60 bpm : alarme inattendue", r.bpm);
}

/* PROPRIÉTÉ 3 : tachycardie soutenue → alarme physiologique (pas technique). */
static void test_tachycardie(void) {
    resultat r = analyser(VEILLE_SIGGEN_ECG, 250, 180, 1200, 1024);
    afficher("ecg180", r);
    if (r.sensor != VEILLE_SENSOR_OK) echec("tachycardie prise pour une panne capteur", r.bpm);
    if (r.bpm != 180) echec("fréquence mal mesurée sur ECG 180 bpm", r.bpm);
    if (r.decision != VEILLE_DECISION_ALARM_HIGH) echec("tachycardie sans alarme physiologique", r.bpm);
}

/* PROPRIÉTÉ 4 : capteur mort, capteur bruité, dérive lente. */
static void test_pannes_capteur(void) {
    resultat mort = analyser(VEILLE_SIGGEN_DEAD, 250, 60, 1200, 1024);
    afficher("dead", mort);
    if (mort.sensor != VEILLE_SENSOR_DEAD) echec("capteur mort non détecté", mort.bpm);
    if (mort.decision != VEILLE_DECISION_TECH_FAULT) echec("capteur mort sans alarme technique", mort.bpm);
    resultat bruyant = analyser(VEILLE_SIGGEN_NOISY, 250, 60, 1200, 1024);
    afficher("noisy", bruyant);
    if (bruyant.sensor != VEILLE_SENSOR_NOISY) echec("capteur bruité non détecté", bruyant.bpm);
    resultat derive = analyser(VEILLE_SIGGEN_DRIFT, 250, 60, 1200, 1024);
    afficher("drift", derive);
    if (derive.sensor != VEILLE_SENSOR_DRIFT) echec("dérive non détectée", derive.bpm);
}

/* Mode CLI : une ligne de résultat pour le différentiel C↔Python. */
static veille_siggen_kind kind_depuis_nom(const char *nom) {
    if (strcmp(nom, "flat") == 0)  return VEILLE_SIGGEN_FLAT;
    if (strcmp(nom, "dead") == 0)  return VEILLE_SIGGEN_DEAD;
    if (strcmp(nom, "noisy") == 0) return VEILLE_SIGGEN_NOISY;
    if (strcmp(nom, "drift") == 0) return VEILLE_SIGGEN_DRIFT;
    return VEILLE_SIGGEN_ECG;
}

static long option_long(int argc, char **argv, const char *nom, long defaut) {
    for (int i = 1; i < argc - 1; i++)
        if (strcmp(argv[i], nom) == 0) return atol(argv[i + 1]);
    return defaut;
}

static const char *option_texte(int argc, char **argv, const char *nom, const char *defaut) {
    for (int i = 1; i < argc - 1; i++)
        if (strcmp(argv[i], nom) == 0) return argv[i + 1];
    return defaut;
}

int main(int argc, char **argv) {
    if (argc > 1) {
        const char *sig = option_texte(argc, argv, "--sig", "ecg");
        long fs = option_long(argc, argv, "--fs", 250);
        long rate = option_long(argc, argv, "--rate", 60);
        long amp = option_long(argc, argv, "--amp", 1200);
        long n = option_long(argc, argv, "--samples", 1024);
        resultat r = analyser(kind_depuis_nom(sig), fs, rate, amp, n);
        printf("sensor=%s bpm=%ld decision=%s\n",
               veille_sensor_state_name(r.sensor), r.bpm, veille_decision_name(r.decision));
        return 0;
    }
    test_signal_plat();
    test_rythme_regulier();
    test_tachycardie();
    test_pannes_capteur();
    printf("[OK] test_signal vert (plat ⇒ figé ; régulier ⇒ vivant ; tachy ⇒ alarme)\n");
    return 0;
}
