/* Analyse du signal BRUT → état capteur + fréquence (core/src/signal.c).
 *
 * Implémentation de référence, partagée par la simulation hôte, le
 * resource manager QNX et le test C. Le jumeau Python (host/veille/state.py)
 * refait EXACTEMENT le même calcul — le différentiel C↔Python le vérifie.
 *
 * Pur C11 : ni horloge, ni fichier, ni malloc (tampons sur la pile ou fournis
 * par l'appelant). */
#include "veille/signal.h"
#include <string.h>

#define VEILLE_SIG_FS_DEFAUT       250
#define VEILLE_SIG_STUCK_PLAGE     2    /* codes ADC : variation max d'un signal figé */
#define VEILLE_SIG_BRUIT_PCT       12   /* median|diff| > 12 % de la plage → bruité */
#define VEILLE_SIG_DERIVE_FACTEUR  4    /* dérive > 4 × median|diff| → dérive */

/* Sélection du k-ième plus petit (Hoare) — sans allocation, O(n) en moyenne. */
static int32_t select_kth(int32_t *a, int n, int k) {
    int left = 0, right = n - 1;
    while (left < right) {
        int32_t pivot = a[left + (right - left) / 2];
        int i = left, j = right;
        while (i <= j) {
            while (a[i] < pivot) i++;
            while (a[j] > pivot) j--;
            if (i <= j) {
                int32_t t = a[i]; a[i] = a[j]; a[j] = t;
                i++; j--;
            }
        }
        if (k <= j) right = j;
        else if (k >= i) left = i;
        else break;
    }
    return a[k];
}

/* Médiane SUPÉRIEURE d'un intervalle (copie dans tmp puis sélection).
 * Convention figée : médiane = valeur de rang n/2 (0-indexé, arrondi haut). */
static long median_of(const int16_t *x, int n, int32_t *tmp) {
    for (int i = 0; i < n; i++) tmp[i] = x[i];
    return select_kth(tmp, n, n / 2);
}

/* Médiane des écarts absolus consécutifs — échelle robuste du bruit. */
static long median_abs_diff(const int16_t *x, int n, int32_t *tmp) {
    if (n < 2) return 0;
    int m = n - 1;
    for (int i = 0; i < m; i++) {
        long d = (long)x[i + 1] - (long)x[i];
        tmp[i] = (int32_t)(d < 0 ? -d : d);
    }
    return select_kth(tmp, m, m / 2);
}

/* Décalage de la ligne de base entre le premier et le dernier quart de fenêtre. */
static long quarter_shift(const int16_t *x, int n, int32_t *tmp) {
    int q = n / 4;
    if (q < 1) return 0;
    long m1 = median_of(x, q, tmp);
    long m2 = median_of(x + n - q, q, tmp);
    return m2 > m1 ? m2 - m1 : m1 - m2;
}

void veille_signal_buffer_init(veille_signal_buffer *b, long fs_hz) {
    if (!b) return;
    memset(b, 0, sizeof(*b));
    if (fs_hz <= 0) fs_hz = VEILLE_SIG_FS_DEFAUT;
    b->fs_hz = fs_hz;
    b->refractory = (fs_hz * 2) / 10;      /* 0,2 s — ref Pulsatile */
    if (b->refractory < 1) b->refractory = 1;
}

void veille_signal_push(veille_signal_buffer *b, int16_t sample) {
    if (!b) return;
    if (b->n < VEILLE_SIG_WINDOW_MAX) {
        b->buf[b->n++] = sample;
        return;
    }
    memmove(b->buf, b->buf + 1, (VEILLE_SIG_WINDOW_MAX - 1) * sizeof(int16_t));
    b->buf[VEILLE_SIG_WINDOW_MAX - 1] = sample;
}

int veille_signal_window_full(const veille_signal_buffer *b) {
    return (b && b->n >= VEILLE_SIG_WINDOW_MAX) ? 1 : 0;
}

veille_sensor_state veille_signal_sensor_state(const veille_signal_buffer *b) {
    if (!b || b->n < 2) return VEILLE_SENSOR_OK;
    int n = b->n;
    const int16_t *x = b->buf;
    int32_t tmp[VEILLE_SIG_WINDOW_MAX];
    long lo = x[0], hi = x[0];
    int zeros = 1;
    for (int i = 0; i < n; i++) {
        if (x[i] < lo) lo = x[i];
        if (x[i] > hi) hi = x[i];
        if (x[i] != 0) zeros = 0;
    }
    if (zeros) return VEILLE_SENSOR_DEAD;                 /* signal mort */
    long plage = hi - lo;
    if (plage <= VEILLE_SIG_STUCK_PLAGE) return VEILLE_SENSOR_STUCK;  /* signal figé */
    long mdiff = median_abs_diff(x, n, tmp);
    if (mdiff > 0 && mdiff * 100 > VEILLE_SIG_BRUIT_PCT * plage)
        return VEILLE_SENSOR_NOISY;                        /* variance excessive */
    long echelle = (mdiff > 0) ? mdiff : 1;
    if (quarter_shift(x, n, tmp) > VEILLE_SIG_DERIVE_FACTEUR * echelle)
        return VEILLE_SENSOR_DRIFT;                        /* ligne de base qui bouge */
    return VEILLE_SENSOR_OK;
}

long veille_signal_rate_bpm(const veille_signal_buffer *b) {
    if (!b || b->n < 8 || b->fs_hz <= 0) return 0;
    int n = b->n;
    const int16_t *x = b->buf;
    int32_t tmp[VEILLE_SIG_WINDOW_MAX];
    long lo = x[0], hi = x[0];
    for (int i = 1; i < n; i++) {
        if (x[i] < lo) lo = x[i];
        if (x[i] > hi) hi = x[i];
    }
    long seuil = median_of(x, n, tmp) + (hi - lo) / 2;   /* seuil adaptatif */
    if (hi - lo <= VEILLE_SIG_STUCK_PLAGE) return 0;   /* signal figé : pas de fréquence */
    int pics[VEILLE_SIG_MAX_BEATS];
    int np = 0, dernier = -1;
    for (int i = 1; i < n - 1; i++) {
        if (x[i] < seuil) continue;                       /* sous le seuil */
        if (x[i] < x[i - 1] || x[i] < x[i + 1]) continue; /* pas un maximum local */
        if (dernier >= 0 && (i - dernier) < b->refractory) continue; /* réfractaire */
        if (np == VEILLE_SIG_MAX_BEATS) {                 /* on garde les plus récents */
            memmove(pics, pics + 1, (VEILLE_SIG_MAX_BEATS - 1) * sizeof(int));
            np--;
        }
        pics[np++] = i;
        dernier = i;
    }
    if (np < 2) return 0;
    long intervalle = (pics[np - 1] - pics[0]) / (np - 1);
    if (intervalle <= 0) return 0;
    return (60 * b->fs_hz) / intervalle;
}

veille_decision veille_signal_decide(veille_sensor_state sensor, long bpm, long threshold_bpm) {
    if (sensor != VEILLE_SENSOR_OK) return VEILLE_DECISION_TECH_FAULT;
    if (bpm > threshold_bpm) return VEILLE_DECISION_ALARM_HIGH;
    return VEILLE_DECISION_OK;
}

const char *veille_decision_name(veille_decision d) {
    switch (d) {
        case VEILLE_DECISION_ALARM_HIGH: return "alarm_high";
        case VEILLE_DECISION_TECH_FAULT: return "tech_fault";
        default: return "ok";
    }
}
