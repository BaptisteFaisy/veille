#ifndef VEILLE_VERDICT_H
#define VEILLE_VERDICT_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* §4 du CONTRAT — ordre figé, sentinelle VEILLE_VERDICT__COUNT */
typedef enum {
    VEILLE_OK = 0,
    VEILLE_LATENCY_BOUND_EXCEEDED,
    VEILLE_ALARM_MISSED,
    VEILLE_SENSOR_FAULT,
    VEILLE_PRIORITY_INVERSION,
    VEILLE_TECHNICAL_ALARM,
    VEILLE_CHAIN_FAULT,
    VEILLE_PROOF_COMPLETE,
    VEILLE_PROOF_COUNTEREXAMPLE,
    VEILLE_ACK_TIMEOUT,
    VEILLE_VERDICT__COUNT
} veille_verdict_code;

typedef enum {
    VEILLE_SEV_INFO = 0,
    VEILLE_SEV_WARNING,
    VEILLE_SEV_ERROR
} veille_severity;

/* Verdict : code/sev/message toujours présents ; le reste optionnel (NULL/0 = absent). */
typedef struct {
    veille_verdict_code code;
    veille_severity     sev;
    const char         *message;
    const char         *chain_id;
    const char         *sensor_id;
    const char         *stage;
    const char         *state;
    long                bound_ms;
    long                latency_ms;
    long                threshold;
    int                 holder_prio;
    int                 waiter_prio;
    long                states_explored;
    const char         *config_sha256;
    long                ack_bound_ms;
    long                elapsed_ms;
} veille_verdict;

const char *veille_verdict_name(veille_verdict_code code);   /* hors plage -> "VEILLE_UNKNOWN" */
const char *veille_severity_name(veille_severity sev);        /* "info"|"warning"|"error" */
veille_severity veille_verdict_default_severity(veille_verdict_code code);
int veille_verdict_code_valid(veille_verdict_code code);      /* 1 si dans [0,COUNT) */

#ifdef __cplusplus
}
#endif
#endif /* VEILLE_VERDICT_H */
