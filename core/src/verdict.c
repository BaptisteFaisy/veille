#include "veille/verdict.h"

static const char *VERDICT_NAMES[VEILLE_VERDICT__COUNT] = {
    "VEILLE_OK",
    "VEILLE_LATENCY_BOUND_EXCEEDED",
    "VEILLE_ALARM_MISSED",
    "VEILLE_SENSOR_FAULT",
    "VEILLE_PRIORITY_INVERSION",
    "VEILLE_TECHNICAL_ALARM",
    "VEILLE_CHAIN_FAULT",
    "VEILLE_PROOF_COMPLETE",
    "VEILLE_PROOF_COUNTEREXAMPLE",
    "VEILLE_ACK_TIMEOUT"
};

static const veille_severity VERDICT_SEV[VEILLE_VERDICT__COUNT] = {
    VEILLE_SEV_INFO,     /* OK */
    VEILLE_SEV_ERROR,    /* LATENCY_BOUND_EXCEEDED */
    VEILLE_SEV_ERROR,    /* ALARM_MISSED */
    VEILLE_SEV_WARNING,  /* SENSOR_FAULT */
    VEILLE_SEV_ERROR,    /* PRIORITY_INVERSION */
    VEILLE_SEV_WARNING,  /* TECHNICAL_ALARM */
    VEILLE_SEV_ERROR,    /* CHAIN_FAULT */
    VEILLE_SEV_INFO,     /* PROOF_COMPLETE */
    VEILLE_SEV_ERROR,    /* PROOF_COUNTEREXAMPLE */
    VEILLE_SEV_WARNING   /* ACK_TIMEOUT */
};

const char *veille_verdict_name(veille_verdict_code code) {
    if (code < 0 || code >= VEILLE_VERDICT__COUNT) return "VEILLE_UNKNOWN";
    return VERDICT_NAMES[code];
}

const char *veille_severity_name(veille_severity sev) {
    switch (sev) {
        case VEILLE_SEV_INFO:    return "info";
        case VEILLE_SEV_WARNING: return "warning";
        case VEILLE_SEV_ERROR:   return "error";
        default:                 return "info";
    }
}

veille_severity veille_verdict_default_severity(veille_verdict_code code) {
    if (code < 0 || code >= VEILLE_VERDICT__COUNT) return VEILLE_SEV_INFO;
    return VERDICT_SEV[code];
}

int veille_verdict_code_valid(veille_verdict_code code) {
    return (code >= 0 && code < VEILLE_VERDICT__COUNT) ? 1 : 0;
}
