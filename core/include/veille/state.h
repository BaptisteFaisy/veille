#ifndef VEILLE_STATE_H
#define VEILLE_STATE_H

#include "veille/chain.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* §7.1 du cahier — dimensions de l'espace d'états de défaillance */
typedef enum {
    VEILLE_SENSOR_OK = 0,
    VEILLE_SENSOR_STUCK,    /* valeur figée */
    VEILLE_SENSOR_DEAD,     /* pas d'échantillon */
    VEILLE_SENSOR_NOISY,    /* valeurs aberrantes */
    VEILLE_SENSOR_DRIFT,    /* dérive lente */
    VEILLE_SENSOR__COUNT
} veille_sensor_state;

typedef enum {
    VEILLE_BUS_OK = 0,
    VEILLE_BUS_SATURATED,   /* charge */
    VEILLE_BUS_SPIKE,       /* pic de latence */
    VEILLE_BUS__COUNT
} veille_bus_state;

typedef enum {
    VEILLE_PRIO_NORMAL = 0,
    VEILLE_PRIO_INVERTED,   /* tâche basse priorité tient un verrou */
    VEILLE_PRIO_MODE__COUNT
} veille_prio_mode;

typedef enum {
    VEILLE_ALARM_NONE = 0,
    VEILLE_ALARM_SINGLE,
    VEILLE_ALARM_CONCURRENT,
    VEILLE_ALARM_LOCKED,
    VEILLE_ALARM_ACKED,
    VEILLE_ALARM__COUNT
} veille_alarm_state;

typedef struct {
    veille_sensor_state sensor;
    veille_bus_state    bus;
    veille_prio_mode    prio;
    veille_alarm_state  alarm;
    unsigned            stage_fault_mask;   /* bit i = étage i en panne */
} veille_fault_state;

const char *veille_sensor_state_name(veille_sensor_state s);
const char *veille_bus_state_name(veille_bus_state b);
const char *veille_prio_mode_name(veille_prio_mode p);
const char *veille_alarm_state_name(veille_alarm_state a);

/* Latence pire-cas de la chaîne dans cet état (ms). <0 si chaîne rompue. */
long veille_state_worst_latency_ms(const veille_chain_config *cfg, const veille_fault_state *st);
/* 1 si un étage critique est en panne (chaîne rompue → alarme technique). */
int  veille_state_chain_broken(const veille_fault_state *st);
/* Sérialise l'état en "sensor_stuck|bus_saturated|..." (noms joints par '|'). */
void veille_state_to_string(const veille_fault_state *st, char *buf, size_t cap);

#ifdef __cplusplus
}
#endif
#endif /* VEILLE_STATE_H */
