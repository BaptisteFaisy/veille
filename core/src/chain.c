#include "veille/chain.h"
#include <stddef.h>

static const char *STAGE_NAMES[VEILLE_STAGE__COUNT] = {
    "acquire", "filter", "decide", "alarm", "ack"
};

static const char *PRIO_NAMES[VEILLE_PRIO__COUNT] = {
    "high", "medium", "low", "technical"
};

const char *veille_stage_name(veille_stage s) {
    if (s < 0 || s >= VEILLE_STAGE__COUNT) return "?";
    return STAGE_NAMES[s];
}

const char *veille_priority_name(veille_priority p) {
    if (p < 0 || p >= VEILLE_PRIO__COUNT) return "?";
    return PRIO_NAMES[p];
}

long veille_chain_latency_ms(const veille_chain_config *cfg) {
    if (!cfg) return -1;
    long sum = 0;
    for (int i = 0; i < VEILLE_STAGE__COUNT; i++) sum += cfg->stage_latency_ms[i];
    return sum;
}

int veille_chain_config_valid(const veille_chain_config *cfg) {
    if (!cfg) return 0;
    if (cfg->priority < 0 || cfg->priority >= VEILLE_PRIO__COUNT) return 0;
    if (cfg->bound_alarm_ms <= 0) return 0;
    if (cfg->bound_tech_ms <= 0) return 0;
    if (cfg->tech_detect_ms < 0) return 0;
    for (int i = 0; i < VEILLE_STAGE__COUNT; i++)
        if (cfg->stage_latency_ms[i] < 0) return 0;
    return 1;
}
