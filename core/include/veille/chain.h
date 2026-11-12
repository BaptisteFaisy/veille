#ifndef VEILLE_CHAIN_H
#define VEILLE_CHAIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* §1 du CONTRAT — chaîne figée : sample→acquire→filter→decide→alarm→ack */
typedef enum {
    VEILLE_STAGE_ACQUIRE = 0,
    VEILLE_STAGE_FILTER,
    VEILLE_STAGE_DECIDE,
    VEILLE_STAGE_ALARM,
    VEILLE_STAGE_ACK,
    VEILLE_STAGE__COUNT
} veille_stage;

/* §3 du CONTRAT — priorités IEC 60601-1-8 (bornes configurables) */
typedef enum {
    VEILLE_PRIO_HIGH = 0,
    VEILLE_PRIO_MEDIUM,
    VEILLE_PRIO_LOW,
    VEILLE_PRIO_TECHNICAL,
    VEILLE_PRIO__COUNT
} veille_priority;

typedef struct {
    veille_priority priority;
    long bound_alarm_ms;                          /* B_alarm */
    long bound_ack_ms;                            /* B_ack */
    long bound_tech_ms;                           /* B_tech — alarme technique (défaut 50) */
    long tech_detect_ms;                          /* latence pire-cas de détection de panne d'étage */
    long stage_latency_ms[VEILLE_STAGE__COUNT];   /* latence pire-cas par étage */
} veille_chain_config;

const char *veille_stage_name(veille_stage s);
const char *veille_priority_name(veille_priority p);
long veille_chain_latency_ms(const veille_chain_config *cfg);  /* somme des étages */
int  veille_chain_config_valid(const veille_chain_config *cfg);

#ifdef __cplusplus
}
#endif
#endif /* VEILLE_CHAIN_H */
