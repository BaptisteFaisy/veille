#ifndef VEILLE_ALARM_H
#define VEILLE_ALARM_H

#include "veille/chain.h"
#include "veille/state.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Décision : l'échantillon franchit-il un seuil physiologique ? (modèle simplifié) */
typedef struct {
    long threshold;   /* seuil */
    long value;       /* valeur filtrée */
    int  exceeded;    /* 1 si value > threshold */
} veille_decision;

/* Profil sonore IEC 60601-1-8 (modélisé — §3 du CONTRAT) */
typedef struct {
    int  pulses;      /* nombre de pulses */
    long pulse_ms;    /* durée d'un pulse */
    long pause_ms;    /* durée de la pause */
} veille_sound_profile;

void veille_alarm_sound_profile(veille_priority p, veille_sound_profile *out);
/* 1 si une alarme doit être déclenchée dans cet état (seuil franchi et chaîne intacte). */
int  veille_alarm_should_fire(const veille_decision *d, const veille_fault_state *st);
/* Latence de déclenchement de l'alarme dans cet état (ms). */
long veille_alarm_latency_ms(const veille_chain_config *cfg, const veille_fault_state *st);

#ifdef __cplusplus
}
#endif
#endif /* VEILLE_ALARM_H */
