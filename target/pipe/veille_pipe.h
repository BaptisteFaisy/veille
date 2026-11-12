#ifndef VEILLE_PIPE_H
#define VEILLE_PIPE_H

#include "veille/chain.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Pipeline portable acquire→filter→decide — partagé entre la simulation hôte
 * (target/sim/sim.c) et le resource manager QNX (target/rm/). Pur C11 :
 * ni horloge ni fichier ni socket (l'horodatage vient de target/port/). */

#define VEILLE_HR_NORMAL      72    /* bpm au repos */
#define VEILLE_HR_THRESHOLD   120   /* seuil d'alarme haute priorité */
#define VEILLE_FILTER_WINDOW  8

/* Résultat du passage d'un échantillon dans la chaîne. */
typedef enum {
    VEILLE_PIPE_OK = 0,      /* seuil non franchi, chaîne saine */
    VEILLE_PIPE_ALARM,       /* seuil physiologique franchi → alarme haute */
    VEILLE_PIPE_TECH_STUCK,  /* valeur figée → alarme technique */
    VEILLE_PIPE_TECH_DEAD    /* capteur mort → alarme technique */
} veille_pipe_result;

/* Filtre moyenneur glissant. */
typedef struct {
    long window[VEILLE_FILTER_WINDOW];
    int  idx;
    int  filled;
} veille_pipe_filter;

/* État du pipeline : filtre + dernière lecture brute + compteur d'échantillons. */
typedef struct {
    veille_pipe_filter filter;
    long last_raw;    /* dernière lecture brute ; -1 = aucune */
    int  index;       /* nombre d'échantillons poussés */
} veille_pipe_state;

/* Config de chaîne par défaut (bornes gelées — CONTRACT.md §3). */
void veille_pipe_default_config(veille_chain_config *cfg);

void veille_pipe_state_init(veille_pipe_state *st);

/* Pousse un échantillon brut (bpm ; <0 = capteur mort) : filter→decide.
 * Incrémente st->index. Retourne le résultat de la chaîne. */
veille_pipe_result veille_pipe_push(veille_pipe_state *st, long raw_bpm);

/* Capteur simulé (partagé hôte/cible) : tachycardie après mi-run.
 * fault 1 = stuck (valeur figée), 2 = dead. Retourne bpm, ou -1 si mort. */
long veille_pipe_sensor_bpm(int i, int samples, int fault, long *last);

/* Panne injectée à l'échantillon i : [100,104] figé, [300,302] mort, sinon 0. */
int veille_pipe_fault_at(int i);

/* Valeur filtrée courante (pour rapport/verdict). */
long veille_pipe_filtered(const veille_pipe_state *st);

#ifdef __cplusplus
}
#endif
#endif /* VEILLE_PIPE_H */
